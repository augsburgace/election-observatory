"""Deterministic, sourced explanations with independently optional outside context.

The EV estimate is immutable across these switches. External evidence is an
inspectable challenge to that estimate until a combined model passes validation.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .analytics.common import available_at, instant
from .db import ObservationRecord, Snapshot
from .ev_forecast import early_vote_forecasts
from .settings import local_today

VERSION = "sourced-ev-explanation-1"


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _margin(value):
    if value is None:
        return "no supported party-margin call"
    if abs(value) < .05:
        return "an even race"
    return f"{'Republicans' if value > 0 else 'Democrats'} ahead by {abs(value):.1f} points"


def _refs(database, rows, revision):
    ids = {r.get("snapshot_id") for r in rows if r.get("snapshot_id") is not None}
    with database.session() as session:
        return [{"snapshot_id": s.id, "source_id": s.source_id, "url": s.url, "sha256": s.sha256,
                 "retrieved_at": s.retrieved_at, "title": s.source_id}
                for s in session.scalars(select(Snapshot).where(Snapshot.id.in_(ids), Snapshot.revision <= revision))]


def _producer(value):
    name = re.sub(r"[^a-z0-9]", "", value.casefold())
    if "marist" in name:
        return "marist"
    if "bowlinggreen" in name or "bgsu" in name:
        return "bgsuyougov"
    if "coefficient" in name:
        return "coefficient"
    if "emerson" in name:
        return "emerson"
    if "suffolk" in name:
        return "suffolk"
    return name


def polling_signal(database, state, revision, cutoff, cycle):
    end = instant(cutoff, end_of_day=True)
    earliest = end - timedelta(days=21)
    candidates, exclusions = [], []
    for poll in database.polls(state=state, revision=revision, cutoff=cutoff):
        reason = None
        start, stop = instant(poll.get("field_start")), instant(poll.get("field_end"), end_of_day=True)
        population = str(poll.get("population", "")).upper()
        if poll.get("cycle") != cycle:
            continue
        if poll.get("question_type") != "vote_choice":
            reason = "Expectation or other question, not a vote-choice response"
        elif population not in {"LV", "LIKELY VOTERS"}:
            reason = "Different population; kept in the polling inventory"
        elif start is None or stop is None or start > stop or stop > end:
            reason = "Invalid or future fieldwork"
        elif available_at(poll) is None or available_at(poll) > end:
            reason = "Not available at this cutoff"
        elif start + (stop - start) / 2 < earliest:
            reason = "Fieldwork midpoint more than 21 days before cutoff"
        elif poll.get("ballot_type") in {"hypothetical", "simulated_final_round"}:
            reason = "Hypothetical or alternative round; kept separate"
        if reason:
            exclusions.append({"producer": poll.get("producer"), "study_id": poll.get("study_id"), "reason": reason})
        else:
            candidates.append(poll)
    # A primary release takes precedence over a secondary copy of the same
    # producer's fieldwork. Different producers are not given precision weights.
    candidates.sort(key=lambda p: (p.get("field_end", ""), not p.get("metadata", {}).get("secondary_summary", False),
                                   p.get("published_at", ""), p.get("revision", 0)), reverse=True)
    selected, producers, samples = [], set(), set()
    for poll in candidates:
        producer = _producer(str(poll.get("metadata", {}).get("independent_producer_id") or poll["producer"]))
        sample = poll.get("metadata", {}).get("shared_sample_id")
        if producer in producers or (sample and sample in samples):
            exclusions.append({"producer": poll["producer"], "study_id": poll["study_id"], "reason": "A newer or more complete source from this producer/shared sample is shown"})
            continue
        producers.add(producer)
        if sample:
            samples.add(sample)
        refs = _refs(database, [poll], revision)
        estimates = poll.get("estimates", [])
        named_party = {party: [e for e in estimates if e.get("party") in aliases and isinstance(e.get("value"), (int, float))]
                       for party, aliases in (("DEM", {"D", "DEM"}), ("REP", {"R", "REP"}))}
        margin = (named_party["REP"][0]["value"] - named_party["DEM"][0]["value"]
                  if len(named_party["REP"]) == len(named_party["DEM"]) == 1 else None)
        selected.append({k: poll.get(k) for k in ("study_id", "producer", "field_start", "field_end", "population", "sample_size",
            "question", "ballot_type", "estimates", "source_url", "document_url", "margin_of_error")} | {
            "secondary_summary": bool(poll.get("metadata", {}).get("secondary_summary")), "source_refs": refs,
            "published_at": poll.get("published_at"), "margin_pp": margin,
            "original_producer_url": poll.get("metadata", {}).get("original_producer_url")})
    refs = _refs(database, candidates, revision)
    if not selected:
        return {"status": "unavailable", "studies": [], "summary": "No eligible recent likely-voter Senate studies are retained at this cutoff and revision.",
                "reason": "Original and secondary inventories remain visible in Polls; unavailable is not an even race.", "exclusions": exclusions, "source_refs": []}
    directions = {"DEM": 0, "REP": 0, "even": 0}
    for p in selected:
        m = p["margin_pp"]
        if m is not None:
            directions["REP" if m > 0 else "DEM" if m < 0 else "even"] += 1
    return {"status": "available", "studies": selected, "producer_count": len(selected), "directions": directions,
        "summary": f"{len(selected)} recent distinct listed pollster{'s' if len(selected) != 1 else ''} retained: {directions['DEM']} Democratic leads, {directions['REP']} Republican leads and {directions['even']} even results among studies with one named option per major party.",
        "reason": "Studies are displayed separately because candidate configurations, methods and populations differ. Secondary pollster labels and undisclosed shared samples do not establish statistical independence. No pooled margin of error, automatic undecided allocation or forecast blend is calculated.",
        "exclusions": exclusions, "source_refs": refs}


def market_signal(database, state, revision, cutoff, cycle):
    from .registry import sources

    end = instant(cutoff, end_of_day=True)
    configured = {source["id"]: source for source in sources()
                  if source.get("parser") == "polymarket" and source.get("state") == state and source.get("cycle") == cycle}
    latest_events, event_refs = {}, []
    with database.session() as session:
        snapshots = session.scalars(select(Snapshot).where(Snapshot.source_id.in_(configured),
            Snapshot.revision <= revision).order_by(Snapshot.revision.desc(), Snapshot.id.desc()))
        for snapshot in snapshots:
            if snapshot.source_id in latest_events or instant(snapshot.retrieved_at) > end:
                continue
            # Even an unavailable/corrupt latest archived event withholds old
            # contract prices; it cannot justify silently reviving an older one.
            latest_events[snapshot.source_id] = set()
            source = configured[snapshot.source_id]
            path = Path(snapshot.path)
            if (not path.is_file() or path.stat().st_size > 2_000_000
                    or hashlib.sha256(path.read_bytes()).hexdigest() != snapshot.sha256):
                continue
            payload = json.loads(path.read_text())
            if (not isinstance(payload, dict) or payload.get("slug") != source["event_slug"]
                    or state != source["state"] or source["state_name"] not in payload.get("title", "")
                    or not re.search(r"\bSenate\b", payload.get("title", ""), re.I)
                    or not isinstance(payload.get("markets"), list)):
                continue
            latest_events[snapshot.source_id] = {str(market["id"]) for market in payload["markets"]
                if isinstance(market, dict) and market.get("id") and market.get("active") is True and market.get("closed") is not True
                and str(cycle) in market.get("question", "") and source["state_name"] in market.get("question", "")
                and re.search(r"\bSenate\b", market.get("question", ""), re.I)
                and not re.fullmatch(r"(?:Candidate|Person)\s+[A-Z]", market.get("groupItemTitle", ""), re.I)
                and market.get("groupItemTitle", "").casefold() != "other"}
            event_refs.append({"snapshot_id": snapshot.id})
    latest = {}
    with database.session() as session:
        records = session.scalars(select(ObservationRecord).where(ObservationRecord.state == state,
            ObservationRecord.cycle == cycle, ObservationRecord.metric == "market_price_pct",
            ObservationRecord.revision <= revision).order_by(ObservationRecord.revision, ObservationRecord.id))
        for row in records:
            payload = row.payload
            if available_at({**payload, "observed_at": row.observed_at}) > end:
                continue
            meta = payload.get("metadata", {})
            at = instant(meta.get("quote_at"))
            if at is None or at > end:
                continue
            key = (row.source_id, meta.get("market_id"))
            latest[key] = {**payload, "snapshot_id": row.snapshot_id, "source_id": row.source_id}
    markets = []
    for row in latest.values():
        meta = row["metadata"]
        if row["source_id"] in latest_events and str(meta.get("market_id")) not in latest_events[row["source_id"]]:
            continue
        if not meta.get("active") or meta.get("closed") or end - instant(meta["quote_at"]) > timedelta(days=3):
            continue
        markets.append({"provider": "Polymarket", "party": meta.get("party"), "outcome_label": meta.get("outcome_label"),
            "price_pct": row["value"], "quote_at": meta["quote_at"], "provider_updated_at": meta.get("provider_updated_at"), "question": meta["question"],
            "liquidity_usd": meta.get("liquidity_usd"), "volume_usd": meta.get("volume_usd"),
            "source_url": meta["source_url"], "display_url": meta.get("display_url"),
            "definition": meta["native_definition"], "unit": row["unit"],
            "settlement_rules": meta.get("settlement_rules"), "best_bid": meta.get("best_bid"), "best_ask": meta.get("best_ask"),
            "source_refs": _refs(database, [row], revision)})
    status_refs = _refs(database, event_refs, revision)
    return {"status": "available" if markets else "unavailable", "markets": markets,
        "summary": f"{len(markets)} recent public contract quotes are retained. Prices are percentages of a $1 payout, not vote shares or this model’s win probabilities." if markets else "No recent supported open-contract quote is retained for this state at the selected cutoff and revision.",
        "reason": "The latest validated event inventory at this cutoff removes closed, inactive or missing contracts. Separate contracts need not sum to 100%. Liquidity, spreads and settlement rules affect prices. No price-to-vote-margin conversion is made.",
        "event_status_source_refs": status_refs,
        "source_refs": [r for market in markets for r in market["source_refs"]] + status_refs}


def context_signal(database, state, revision, cutoff, cycle):
    end = instant(cutoff, end_of_day=True)
    with database.session() as session:
        snapshots = list(session.scalars(select(Snapshot).where(Snapshot.source_id == f"rcp-{state.lower()}-senate-{cycle}",
            Snapshot.revision <= revision).order_by(Snapshot.revision.desc(), Snapshot.id.desc())))
    for snapshot in snapshots:
        if instant(snapshot.retrieved_at) > end or "browser-table" not in snapshot.content_type:
            continue
        path = Path(snapshot.path)
        if path.stat().st_size > 2_000_000 or hashlib.sha256(path.read_bytes()).hexdigest() != snapshot.sha256:
            continue
        payload = json.loads(path.read_text())
        text = " ".join(payload.get("context", []))
        match = re.search(r"RCP Rating(.+?)Seat Held By", text)
        if not match:
            continue
        refs = _refs(database, [{"snapshot_id": snapshot.id}], revision)
        item = {"label": "RCP published race rating", "value": match[1].strip(), "date": payload["captured_at"],
                "source_refs": refs, "definition": "An external analyst classification, not an observed early-vote quantity or calibrated probability"}
        return {"status": "available", "items": [item], "summary": f"RCP classifies this contest as {item['value']} in the captured page.",
                "reason": "This is a separately attributed analyst assessment. It does not alter the EV estimate or independently validate polling/market signals.", "source_refs": refs}
    return {"status": "unavailable", "items": [], "summary": "No dated additional analyst assessment is retained for this exact investigation.",
            "reason": "The EV briefing still uses its documented voting calendars, historical results and measurement limitations.", "source_refs": []}


def explain_call(call, signals, *, revision, cutoff, switches):
    early = call["evidence"]["early_vote"]
    geography = call["evidence"]["geographic_tilt"]
    reference = call["evidence"]["historical_reference"]
    margin = call["call"].get("margin_pp")
    state = call["state_name"]
    status = call["call"]["status"]
    headline = f"{state}: {_margin(margin)} under the early-vote model"
    summary = (f"The provisional call is {_margin(margin)}. " if margin is not None else "The available evidence does not support a party-margin estimate. ")
    summary += ("It starts with earlier Senate results and adjusts for where current early participation is coming from."
                if status == "ev_informed" else "Eligible early-vote geography cannot currently support an adjustment, so any displayed point is historical context only.")
    paragraphs, drivers = [], []
    refs = call.get("sources", [])
    paragraphs.append({"title": "What has actually happened", "text": (
        f"The source reports {early['total']:,.0f} {early.get('metric_label', 'early ballots').lower()} through {early.get('date')}. "
        f"The model uses {early.get('mode', 'source-defined')} methods under the source’s definition. A newly reported ballot can have been cast earlier; participation counts do not reveal candidate choices."
        if early.get("total") is not None else "No eligible current participation total is available in this pinned investigation."),
        "evidence_refs": early.get("source_refs", [])})
    drivers.append({"label": "Reported participation", "role": "measured", "value": early.get("total"),
                    "text": f"Source reporting date: {early.get('date') or 'unavailable'}", "direction": "neutral"})
    if reference.get("margin_pp") is not None:
        text = f"Earlier Senate contests provide a starting reference of {_margin(reference['margin_pp'])}. "
        if geography.get("available"):
            adjustment = geography.get("adjustment_pp") or 0
            text += (f"The geographic mix adds {abs(adjustment):.2f} points toward {'Republicans' if adjustment >= 0 else 'Democrats'} under the explicit 0.35 conversion assumption. "
                f"{geography.get('matched_areas', 0)} reporting areas are matched. "
                + ("The comparison uses compatible same-stage early-vote geography." if geography.get("same_stage") else "It uses final historical geographic context because comparable same-stage county evidence is unavailable."))
        else:
            text += "No compatible geographic adjustment is applied."
        paragraphs.append({"title": "Why the call leans this way", "text": text,
                           "evidence_refs": reference.get("source_refs", [])})
        drivers.extend([{"label": "Earlier Senate reference", "role": "historical", "value": reference["margin_pp"],
                         "text": "Different seats, nominees and election environments can weaken this reference.", "direction": "REP" if reference["margin_pp"] > 0 else "DEM"},
                        {"label": "Early-vote geographic adjustment", "role": "assumption", "value": geography.get("adjustment_pp"),
                         "text": "A county’s historical vote does not identify how its current early voters voted.", "direction": "REP" if (geography.get("adjustment_pp") or 0) > 0 else "DEM" if (geography.get("adjustment_pp") or 0) < 0 else "neutral"}])
    places = sorted(geography.get("rows", []), key=lambda r: abs(r.get("contribution_pp") or 0), reverse=True)[:3]
    if places:
        details = [f"{p['name']}: {p['early_votes']:,.0f} reported ballots, {p['early_share_pct']:.1f}% of matched current participation versus {p['reference_share_pct']:.1f}% of the reference"
                   for p in places]
        paragraphs.append({"title": "Which places explain the change", "text": "; ".join(details) +
            ". These places have the largest geographic-context contributions. A changed geographic mix can affect the estimate without revealing any individual’s candidate choice.",
            "evidence_refs": [r for p in places for r in p.get("source_refs", [])]})
    turnout = call["evidence"].get("turnout_projection") or {}
    paragraphs.append({"title": "Turnout can change the story", "text":
        "Earlier voting can mean more eventual participants, a shift from Election Day to early voting, or a switch between mail and in-person methods. The turnout workbench separates those possibilities. "
        + ("A prior-cycle participation analogue is available below; its span excludes model error and is not a confidence interval." if turnout.get("available") or turnout.get("status") in {"available", "supported"} else "The retained same-stage history is not sufficient for a supported final-turnout extrapolation here. Explicit low/reference/high assumptions remain available."),
        "evidence_refs": turnout.get("source_refs", [])})
    composition = call["evidence"].get("composition", [])
    if composition:
        dimensions = sorted({str(r.get("dimension")) for r in composition if r.get("dimension")})
        paragraphs.append({"title": "Who is participating", "text": "Published composition is available for " + ", ".join(dimensions) +
            ". These are the source’s reported groups. Party registration and demographic totals are not candidate votes; their added predictive value is tested separately below. Separate marginal tables cannot establish joint age-by-party or demographic intersections.", "evidence_refs": refs})
    for key, label in (("polls", "What the polls add"), ("markets", "What market prices add"), ("context", "What other assessments add")):
        signal = signals[key]
        if switches[key]:
            paragraphs.append({"title": label, "text": signal["summary"] + " " + signal.get("reason", ""), "evidence_refs": signal.get("source_refs", [])})
    if margin is not None and abs(margin) >= .05:
        ev_party = "REP" if margin > 0 else "DEM"
        challenges = []
        polling = signals["polls"]
        directions = polling.get("directions", {})
        if switches["polls"] and directions.get("DEM", 0) != directions.get("REP", 0):
            poll_party = "DEM" if directions.get("DEM", 0) > directions.get("REP", 0) else "REP"
            agrees = poll_party == ev_party
            challenges.append("More of the retained recent surveys point " + ("in the EV call’s direction" if agrees else "against the EV call’s direction") +
                ". Their different questions and response options still remain separate.")
        markets = signals["markets"].get("markets", [])
        if switches["markets"] and markets:
            favored = max(markets, key=lambda m: m["price_pct"])
            if favored.get("party") in {"DEM", "REP"}:
                challenges.append("The highest-priced retained market contract " +
                    ("agrees with" if favored["party"] == ev_party else "challenges") + " the EV call’s direction.")
            elif favored.get("party") == "IND":
                challenges.append("The highest-priced market contract is for an independent option. A Democratic-minus-Republican reference does not describe that option’s support.")
        if challenges:
            paragraphs.append({"title": "Do the outside signals agree?", "text": " ".join(challenges) +
                " This agreement check is included in the reasoning. It does not turn the sources into independent confirmations, reweight the EV point or create a validated combined forecast.",
                "evidence_refs": polling.get("source_refs", []) + signals["markets"].get("source_refs", [])})
    paragraphs.append({"title": "How much trust this deserves", "text":
        "This is a concrete conditional direction, with a wide unvalidated range. The historical EV study is small and has not established reliable improvement over its historical reference. Turnout, party composition, method shifts and precinct patterns are evaluated separately; more inputs do not automatically make a more accurate forecast.", "evidence_refs": []})
    return headline, summary, paragraphs, drivers


def forecast_reasoning(database, *, state="OH", revision=None, as_of=None, cycle=2026,
                       include_polls=False, include_markets=False, include_context=False, race_id=None):
    revision = database.latest_revision() if revision is None else revision
    cutoff = as_of or local_today()
    run = early_vote_forecasts(database, state=state, revision=revision, as_of=cutoff, cycle=cycle)
    call = next((c for c in run["calls"] if c["race_id"] == race_id and c["state"] == state), None) if race_id else run.get("selected")
    if call is None:
        return {"revision": revision, "as_of": cutoff, "state": state, "mode": "ev_only", "status": "unavailable",
                "headline": "No supported Senate contest for this selection", "summary": "Choose a contest represented in the Senate registry.", "paragraphs": [], "drivers": [], "signals": {}, "warnings": [], "source_refs": []}
    switches = {"polls": bool(include_polls), "markets": bool(include_markets), "context": bool(include_context)}
    readers = {"polls": polling_signal, "markets": market_signal, "context": context_signal}
    signals = {key: readers[key](database, state, revision, cutoff, cycle) if enabled else {
        "status": "off", "summary": "Excluded from this explanation.", "reason": "Enable explicitly to inspect additional evidence.", "source_refs": []}
        for key, enabled in switches.items()}
    headline, summary, paragraphs, drivers = explain_call(call, signals, revision=revision, cutoff=cutoff, switches=switches)
    refs = list({(r.get("snapshot_id") or r.get("id"), r.get("url") or r.get("source_url")): r
        for r in call.get("sources", []) + [r for signal in signals.values() for r in signal.get("source_refs", [])]}.values())
    # Do not expose the legacy contextual poll-count field in an EV-only result.
    public_call = {**call, "evidence": {**call["evidence"], "polls": {"excluded_from_ev_model": True}}}
    manifest = {"version": VERSION, "revision": revision, "cutoff": cutoff, "cycle": cycle, "state": state,
        "race_id": call["race_id"], "switches": switches, "ev_model_version": run["model_version"],
        "ev_call_sha256": _hash(call["call"]), "external_signals_sha256": _hash(signals),
        "method": "Local deterministic templates and reproducible arithmetic; no external AI service",
        "point_policy": "External signals inform the written context; they do not alter the EV model point, its range or validation record."}
    return {"revision": revision, "as_of": cutoff, "state": state, "mode": "expanded" if any(switches.values()) else "ev_only",
        "switches": switches, "headline": headline, "summary": summary, "paragraphs": paragraphs, "drivers": drivers,
        "signals": signals, "ev_call": public_call, "warnings": [
            "Polling, market contracts and analyst assessments can share information and are not independent confirmations.",
            "Optional outside context does not change the EV estimate. A combined forecast requires separate historical validation."] if any(switches.values()) else ["EV-only mode excludes polling results, market prices and external analyst ratings from this explanation."],
        "source_refs": refs, "method": {"generator": "Deterministic sourced explanation", "external_api_required": False,
            "ev_point_unchanged": True, "calibrated_probability": False}, "manifest": {**manifest, "sha256": _hash(manifest)}}
