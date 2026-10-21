"""Public survey releases, explicitly secondary browser tables and market quotes.

Market prices never become ballots or calibrated winner probabilities. Browser
captures retain their extraction method and first-observation time.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from observatory.domain import FetchedDocument, Observation, ParsedBatch, Poll
from observatory.registry import ELECTION_DATES

from .common import soup
from .research_polls import estimate, flat, period


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite public estimate")
    return result


def coefficient(source, fetcher):
    document = fetcher.fetch(source["url"])
    release = fetcher.fetch(source["release_url"])
    page, index = soup(document), soup(release)
    text = flat(page.get_text(" ", strip=True))
    if source["state_name"].casefold() not in text.casefold() or "U.S. Senate" not in text:
        raise ValueError("Original survey page has the wrong state or office")
    dates = period(text)
    sample = re.search(r"Sample\s+([\d,]+)\s+likely", text, re.I)
    moe = re.search(r"MoE\s*[±+]\s*([\d.]+)%", text)
    question = next((flat(e.get_text(" ", strip=True)) for e in page.select("p")
                     if "U.S. Senate were held today" in e.get_text()), None)
    if not sample or not moe or not question:
        raise ValueError("Original survey's sample, uncertainty or Senate question changed")
    rows = []
    parties = {"Republican": "REP", "Democrat": "DEM", "Independent": "IND", "Libertarian": "LIB"}
    for item in page.select(".cand"):
        name, percentage = item.select_one(".cand-name"), item.select_one(".cand-pct")
        party = item.select_one(".cand-party")
        if name is None or percentage is None:
            raise ValueError("Original candidate response row changed")
        rows.append(estimate(flat(name.text), parties.get(flat(party.text)) if party else None,
                             flat(percentage.text).replace(" ", "")))
    if (len(rows) < 2 or any(r["value"] is None for r in rows)
            or len({r["candidate"].casefold() for r in rows}) != len(rows)
            or abs(sum(r["value"] for r in rows) - 100) > 2):
        raise ValueError("Complete original response distribution does not reconcile")
    # The index dates its releases explicitly. Never guess a day from 'October'.
    link = next((a for a in index.find_all("a", href=True)
                 if a["href"].rstrip("/").endswith("/" + source["state"].lower())), None)
    match = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})", flat(link.text) if link else "")
    published = datetime.strptime(match[1], "%B %d, %Y").date().isoformat() if match else document.retrieved_at
    if dates[0] > dates[1] or dates[1] > published[:10]:
        raise ValueError("Survey release predates fieldwork or fieldwork dates are reversed")
    if published[:10] > max(document.retrieved_at[:10], release.retrieved_at[:10]):
        raise ValueError("Survey publication date is in the future relative to retrieved evidence")
    poll = Poll(study_id=f"coefficient-{source['state']}-{dates[0]}-{dates[1]}", state=source["state"],
        cycle=source.get("cycle", int(dates[1][:4])), producer="co/efficient", publisher="co/efficient",
        sponsor="Independent public series; no candidate/party/IE sponsor disclosed", field_start=dates[0],
        field_end=dates[1], published_at=published, population="LV", sample_size=int(sample[1].replace(",", "")),
        margin_of_error=float(moe[1]), methodology="Mobile text responses and landline interviews; see original release",
        question=question, estimates=rows, source_url=document.url, document_url=document.url,
        ballot_type="first_choice" if source["state"] in {"AK", "ME"} else "full_ballot",
        metadata={"source_url": document.url, "source_sha256": document.sha256,
            "publication_date_verified": bool(match), "publication_source_url": release.url,
            "publication_source_sha256": release.sha256, "question_wording_exact": True,
            "independent_producer_id": "coefficient", "parser_version": "original-coefficient-1"})
    return ParsedBatch(polls=[poll], data_as_of=dates[1], warnings=[
        "Original published survey responses; statewide uncertainty is not a candidate-margin uncertainty.",
        "Ranked-choice first choices do not establish the eventual winner." ] if source["state"] in {"AK", "ME"} else [])


def _capture_document(source, fetcher):
    path = fetcher.settings.data_dir / "source-captures" / "rcp" / f"{source['state']}.json"
    if fetcher.offline or not path.exists():
        try:
            offline = type(fetcher)(fetcher.settings, offline=True)
            try:
                document = offline.fetch(source["url"])
            finally:
                offline.close()
            fetcher.documents.append(document)
            return document
        except ValueError as exc:
            raise ValueError("RCP needs an explicit public browser-table capture; ordinary HTTP access is unavailable. Original producer sources can still update.") from exc
    data = path.read_bytes()
    if len(data) > 2_000_000:
        raise ValueError("Browser-table capture exceeds its bounded size")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("Browser-table capture must contain a structured source object")
    if (payload.get("schema") != "rcp-browser-tables-v1" or payload.get("url") != source["url"]
            or urlparse(payload["url"]).hostname not in {"www.realclearpolling.com", "realclearpolling.com"}):
        raise ValueError("Browser-table capture identity does not match the source")
    captured = datetime.fromisoformat(payload["captured_at"].replace("Z", "+00:00"))
    if captured.tzinfo is None:
        raise ValueError("Browser capture requires an explicit timestamp timezone")
    digest = hashlib.sha256(data).hexdigest()
    archived = fetcher.settings.archive_dir / digest[:2] / digest
    archived.parent.mkdir(parents=True, exist_ok=True)
    if not archived.exists():
        archived.write_bytes(data)
    document = FetchedDocument(url=payload["url"], sha256=digest, path=str(archived),
        content_type="application/vnd.observatory.browser-table+json", retrieved_at=payload["captured_at"], byte_count=len(data))
    cache = fetcher.settings.data_dir / "fetch-cache" / (hashlib.sha256(document.url.encode()).hexdigest() + ".json")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(document.model_dump_json())
    fetcher.documents.append(document)
    return document


def rcp_capture(source, fetcher):
    document = _capture_document(source, fetcher)
    payload = json.loads(Path(document.path).read_text())
    if (source["state_name"] not in payload.get("title", "") or str(source["cycle"]) not in payload["title"]
            or not re.search(r"\bSenate\b", payload.get("title", ""), re.I)):
        raise ValueError("Captured table is for another state, cycle or office")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], list):
        raise ValueError("Captured public polling table schema changed")
    table = tables[0]
    if (not table or not isinstance(table[0], dict) or not isinstance(table[0].get("cells"), list)
            or [str(c).lower() for c in table[0]["cells"][:4]] != ["pollster", "date", "sample", "moe"]):
        raise ValueError("Captured public polling table schema changed")
    headers = [re.sub(r"\s*\*+$", "", c).strip() for c in table[0]["cells"]]
    option_columns = [(i, h) for i, h in enumerate(headers[4:], 4) if h.lower() not in {"spread", "share"}]
    if len(option_columns) < 2 or len({name.casefold() for _, name in option_columns}) != len(option_columns):
        raise ValueError("Captured candidate option columns are absent or duplicated")
    year = source["cycle"]
    cutoff = date.fromisoformat(document.retrieved_at[:10])
    polls, excluded, identities = [], [], {}
    for row in table[1:]:
        if not isinstance(row, dict) or not isinstance(row.get("cells"), list):
            raise ValueError("Captured public polling row schema changed")
        cells = row["cells"]
        if not cells or cells[0] == "RCP Average":
            continue
        if len(cells) != len(headers) or not all(isinstance(cell, str) for cell in cells):
            raise ValueError("Captured public polling row columns are incomplete or malformed")
        dates = re.fullmatch(r"(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})", cells[1])
        sample = re.fullmatch(r"([\d,]+)\s+(LV|RV|A)", cells[2])
        if not dates or not sample:
            excluded.append({"producer": cells[0], "reason": "Missing fieldwork or population/sample metadata"})
            continue
        sm, sd, em, ed = map(int, dates.groups())
        end = date(year, em, ed)
        start = date(year - (sm > em), sm, sd)
        if end > cutoff:
            excluded.append({"producer": cells[0], "reason": "Fieldwork ends after the capture cutoff; no prior year is invented"})
            continue
        estimates = []
        for column, name in option_columns:
            value = cells[column].strip()
            if not re.fullmatch(r"\d+(?:\.\d+)?", value):
                raise ValueError("Captured candidate share is missing, suppressed or malformed")
            estimates.append(estimate(name, source.get("parties", {}).get(name), value))
        if sum(e["value"] for e in estimates) > 102:
            raise ValueError("Captured candidate shares exceed a rounded total")
        producer = cells[0].rstrip("*").strip()
        producer_id = re.sub(r"[^a-z0-9]", "", producer.casefold())
        origin = row.get("links", [{}])[0].get("url") if row.get("links") else None
        poll = Poll(study_id=f"rcp-{source['state']}-{producer_id}-{start}-{end}", state=source["state"],
            cycle=source["cycle"], producer=producer, publisher="RealClearPolling (secondary table)",
            field_start=start.isoformat(), field_end=end.isoformat(), published_at=document.retrieved_at,
            population=sample[2], sample_size=int(sample[1].replace(",", "")),
            margin_of_error=float(cells[3]) if re.fullmatch(r"\d+(?:\.\d+)?", cells[3]) else None,
            methodology="Secondary published table; original sampling, question wording and sponsorship not verified",
            question="RCP displayed Senate response summary: " + " / ".join(h for _, h in option_columns),
            ballot_type="aggregator_summary", estimates=estimates, source_url=document.url, document_url=document.url,
            metadata={"source_url": document.url, "source_sha256": document.sha256,
                "original_producer_url": origin, "source_tier": 4, "secondary_summary": True,
                "comparison_key": "rcp-summary:" + "|".join(h.casefold() for _, h in option_columns),
                "independent_producer_id": producer_id, "publication_date_verified": False,
                "first_archived_at": document.retrieved_at, "question_wording_exact": False,
                "date_year_basis": "Year assigned independently from current-cycle page; original study dates still require producer verification",
                "unreported_responses_not_imputed": True, "capture_method": payload["capture_method"],
                "sponsorship_status": "Not verified; RCP asterisks are not interpreted as partisan sponsorship",
                "parser_version": "rcp-browser-table-2"})
        identity = (producer_id, start.isoformat(), end.isoformat(), sample[2], tuple(name.casefold() for _, name in option_columns))
        signature = json.dumps({"sample": poll.sample_size, "moe": poll.margin_of_error, "estimates": poll.estimates}, sort_keys=True)
        if identity in identities:
            if identities[identity] != signature:
                raise ValueError("Conflicting duplicate study in captured polling table")
            continue
        identities[identity] = signature
        polls.append(poll)
    return ParsedBatch(polls=polls, data_as_of=max((p.field_end for p in polls), default=None),
        warnings=["Secondary RCP table captured in a public browser. Refresh requires another browser capture; this is not unattended HTTP ingestion.",
            "Summary configurations remain separate from original full-questionnaire polling averages; absent undecideds are not invented.",
            "Historical availability begins at capture, not fieldwork or an inferred release day."],
        metadata={"rcp_average": next((r for r in table if r.get("cells") and r["cells"][0] == "RCP Average"), None), "exclusions": excluded})


def polymarket(source, fetcher):
    document = fetcher.fetch(source["url"])
    payload = json.loads(Path(document.path).read_text())
    if (payload.get("slug") != source["event_slug"] or source["state_name"] not in payload.get("title", "")
            or not re.search(r"\bSenate\b", payload.get("title", ""), re.I)):
        raise ValueError("Market event identity changed")
    if not isinstance(payload.get("markets"), list):
        raise ValueError("Market event contract inventory schema changed")
    observations, identities, reviewed_contracts = [], {}, 0
    for market in payload["markets"]:
        if not isinstance(market, dict):
            raise ValueError("Market contract inventory row changed")
        question = market.get("question", "")
        label = market.get("groupItemTitle", "")
        explicit_party = re.search(r"\(([DRI])\)", label)
        party = ("DEM" if re.search(r"\bDemocrat(?:ic)?s?\b", question, re.I) else
                 "REP" if re.search(r"\bRepublicans?\b", question, re.I) else
                 {"D": "DEM", "R": "REP", "I": "IND"}.get(explicit_party[1]) if explicit_party else None)
        if (str(source["cycle"]) not in question or source["state_name"] not in question
                or not re.search(r"\bSenate\b", question, re.I)
                or re.fullmatch(r"(?:Candidate|Person)\s+[A-Z]", label, re.I) or label.casefold() == "other"):
            continue
        if not market.get("id") or not market.get("slug"):
            raise ValueError("Market contract identity missing")
        identity = str(market["id"])
        signature = json.dumps(market, sort_keys=True)
        if identity in identities:
            if identities[identity] != signature:
                raise ValueError("Conflicting duplicate market contract identity")
            continue
        identities[identity] = signature
        reviewed_contracts += 1
        # A closed or inactive named contract is still validated event-status
        # evidence. Preserve its snapshot without inventing a zero-dollar quote.
        if market.get("active") is not True or market.get("closed") is True:
            continue
        outcomes, prices = (json.loads(market[key]) if isinstance(market.get(key), str) else market.get(key, [])
                            for key in ("outcomes", "outcomePrices"))
        if not isinstance(outcomes, list) or not isinstance(prices, list) or len(outcomes) != 2 or len(prices) != 2 or set(outcomes) != {"Yes", "No"}:
            raise ValueError("Market Yes/No quote schema changed")
        numeric_prices = [_number(value) for value in prices]
        if any(not 0 <= price <= 1 for price in numeric_prices):
            raise ValueError("Market quote outside 0–1")
        price = numeric_prices[outcomes.index("Yes")]
        observations.append(Observation(state=source["state"], cycle=source["cycle"],
            election_date=ELECTION_DATES[source["cycle"]], date=document.retrieved_at[:10],
            metric="market_price_pct", value=100 * price, unit="percent of $1 contract payout", geography_id=source["state"],
            geography_name=source["state_name"], mode="market", category_dimension="market_contract",
            category=str(market["id"]), published_at=document.retrieved_at, metadata={
                "evidence_family": "prediction_market", "party": party, "question": question,
                "outcome_label": market.get("groupItemTitle"), "market_id": str(market["id"]),
                "market_slug": market["slug"], "event_slug": payload["slug"],
                "quote_at": document.retrieved_at, "provider_updated_at": market.get("updatedAt"),
                "active": bool(market.get("active")), "closed": bool(market.get("closed")),
                "liquidity_usd": _number(market.get("liquidity") or 0), "volume_usd": _number(market.get("volume") or 0),
                "best_bid": market.get("bestBid"), "best_ask": market.get("bestAsk"),
                "settlement_rules": market.get("description"), "market_end": market.get("endDate"),
                "source_url": document.url, "source_sha256": document.sha256,
                "display_url": "https://polymarket.com/event/" + payload["slug"],
                "native_definition": "Quoted Yes contract price times 100. Not a vote share, forecast margin or calibrated probability.",
                "parser_version": "public-polymarket-1"}))
    if not reviewed_contracts:
        raise ValueError("No explicit current-cycle state party-winner contracts in the original event")
    return ParsedBatch(observations=observations, data_as_of=document.retrieved_at[:10],
        metadata={"reference_data": True, "validated_event_slug": payload["slug"],
                  "reviewed_named_contracts": reviewed_contracts, "quoted_contracts": len(observations)}, warnings=[
        "Market quotes reflect contract prices, liquidity and settlement rules. They are optional context, not calibrated election probabilities or candidate margins.",
        "Quotes are timestamped at retrieval and are never backfilled into earlier research cutoffs."])


def collect(source, fetcher):
    return {"coefficient": coefficient, "rcp_capture": rcp_capture, "polymarket": polymarket}[source["parser"]](source, fetcher)
