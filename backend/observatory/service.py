"""One analytical read path for the UI, narrative briefs, and exports."""
from __future__ import annotations

import json
from collections import OrderedDict, defaultdict
from threading import RLock
from time import monotonic

from sqlalchemy import func, select

from .analytics.common import finite_number, instant
from .db import (
    Correction,
    Database,
    ObservationRecord,
    PollRecord,
    Revision,
    Snapshot,
    SourceState,
    record_dict,
)
from .domain import ResearchQuery, utc_now
from .geography import normalize_selections
from .registry import (
    ELECTION_DATES,
    METRICS,
    WATCHLIST,
    all_states,
    races,
    source_covers_state,
    sources,
    state_info,
)
from .settings import local_today


def _cached(database: Database, key: tuple, build):
    """Bounded, revision-aware JSON cache; callers receive independent objects."""
    guard = database.__dict__.setdefault("_service_cache_lock", RLock())
    with guard:
        cache = database.__dict__.setdefault("_service_cache", OrderedDict())
        entry = cache.get(key)
        if entry and monotonic() - entry[0] < 30:
            cache.move_to_end(key)
            return json.loads(entry[1])
    value = build()
    encoded = json.dumps(value, separators=(",", ":")).encode()
    if len(encoded) <= 12_000_000:
        with guard:
            cache[key] = (monotonic(), encoded)
            cache.move_to_end(key)
            while len(cache) > 12 or sum(len(item[1]) for item in cache.values()) > 48_000_000:
                cache.popitem(last=False)
    return value


def _inventory_token(database: Database) -> tuple:
    with database.session() as session:
        checked = session.scalar(select(func.max(SourceState.last_checked)))
    return (database.latest_revision(), checked, json.dumps(sources(), sort_keys=True))


def source_inventory(database: Database) -> list[dict]:
    return _cached(database, ("sources", *_inventory_token(database)), lambda: _source_inventory(database))


def _source_inventory(database: Database) -> list[dict]:
    with database.session() as session:
        states = {row.id: row for row in session.scalars(select(SourceState))}
        counts = dict(session.execute(select(ObservationRecord.source_id, func.count()).group_by(ObservationRecord.source_id)).all())
        poll_counts = dict(session.execute(select(PollRecord.source_id, func.count()).group_by(PollRecord.source_id)).all())
        result = []
        for source in sources():
            state = states.get(source["id"])
            result.append({"tier": 1, "enabled": True, "expected_hours": 24, **source,
                           **(record_dict(state) if state else {"status": "not_collected", "last_checked": None,
                           "last_changed": None, "data_as_of": None, "error": None, "warnings": []}),
                           "observation_count": counts.get(source["id"], 0), "poll_count": poll_counts.get(source["id"], 0)})
        return result


def bootstrap(database: Database) -> dict:
    with database.session() as session:
        covered = session.scalar(select(func.count(func.distinct(ObservationRecord.state)))) or 0
        polls_count = session.scalar(select(func.count(func.distinct(PollRecord.study_id)))) or 0
        observed_cycles = set(session.scalars(select(ObservationRecord.cycle).distinct()))
    return {"app": {"name": "Battleground Senate Observatory", "version": "0.1.0", "election_date": ELECTION_DATES[2026], "today": local_today()},
            "latest_revision": database.latest_revision(), "states": all_states(),
            "races": races(), "metrics": METRICS, "cycles": sorted({2026, 2024, 2022, 2020, 2018, 2016} | observed_cycles, reverse=True),
            "coverage": {"states_with_data": covered, "selected_states": len(WATCHLIST), "catalog_states": 50, "poll_count": polls_count, "source_count": len(sources())}}


def _source_priority(row: dict, source_map: dict) -> dict:
    source = source_map.get(row["source_id"], {})
    rank = source.get("tier", 1)
    if not isinstance(rank, int):
        rank = {"primary": 1, "official": 1, "archive": 2, "academic": 3, "secondary": 4}.get(str(rank), 4)
    rank = rank * 100 + int(source.get("priority", 10))
    return {**row, "metadata": {**row.get("metadata", {}), "source_priority": rank}}


def _composition(observations: list[dict], query: ResearchQuery) -> list[dict]:
    groups = defaultdict(list)
    for row in observations:
        try:
            finite_number(row["value"], "Observation value")
        except ValueError:
            continue
        if row.get("validation", {}).get("status") == "quarantined":
            continue
        if row["cycle"] == query.cycle and row["metric"] == query.metric and row["mode"] == query.mode and row["time_basis"] == query.time_basis and row.get("category_dimension"):
            groups[(row["category_dimension"], row["category"])].append(row)
    result = []
    for (dimension, category), group in groups.items():
        if query.geography_ids:
            selections = set(normalize_selections(query.state, query.geography_ids))
            group = [row for row in group if (row.get("canonical_id") or row["geography_id"]) in selections or row["geography_id"] in selections]
        elif any(row["geography_type"] == "state" for row in group):
            group = [row for row in group if row["geography_type"] == "state"]
        else:
            grain = next((g for g in ("county", "district", "municipality") if any(r["geography_type"] == g for r in group)), None)
            group = [row for row in group if row["geography_type"] == grain]
        latest = {}
        for row in sorted(group, key=lambda r: (r["date"], -r["metadata"].get("source_priority", 1), r["observed_at"])):
            latest[row.get("canonical_id") or row["geography_id"]] = row
        if latest:
            values = list(latest.values())
            result.append({"dimension": dimension, "category": category, "value": sum(r["value"] for r in values),
                           "metric": query.metric, "mode": query.mode, "date": max(r["date"] for r in values),
                           "source_ids": sorted({r["source_id"] for r in values}), "observation_ids": [r["id"] for r in values]})
    return result


def workspace(database: Database, query: ResearchQuery) -> dict:
    return _cached(database, ("workspace", query.model_dump_json(), *_inventory_token(database)),
                   lambda: _workspace(database, query))


def _display_observation(row: dict) -> dict:
    """Project a complete value row; verbose native fields remain in /evidence/id."""
    retained = {"parser_version", "period_end", "report_date", "reconstruction_basis", "is_revision",
                "revision_of", "revision_published_at", "boundary_vintage", "crosswalk_verified",
                "voting_open_date", "calendar_snapshot_id", "calendar_source_url"}
    return {**row, "metadata": {key: value for key, value in row.get("metadata", {}).items() if key in retained}}


def _compact_history(analysis: dict) -> dict:
    snapshots = {}
    for ref in analysis.get("sources", []):
        key = (ref.get("source_id"), ref.get("snapshot_id"))
        snapshots[key] = {name: ref[name] for name in ("source_id", "snapshot_id") if name in ref}
    return {**analysis, "sources": list(snapshots.values()),
            "geographies": [_display_observation(row) for row in analysis.get("geographies", [])]}


def _workspace(database: Database, query: ResearchQuery) -> dict:
    from .analytics import historical_analysis, poll_analysis, state_brief
    if query.metric == "market_price_pct":
        raise ValueError("Market contract prices are optional forecast context, not voting participation. Use the forecast reasoning interface.")
    latest_revision = database.latest_revision()
    revision = latest_revision if query.revision is None else query.revision
    if revision > latest_revision or revision < 0:
        raise ValueError("The requested dataset revision does not exist")
    state = state_info(query.state)
    inventory = source_inventory(database)
    source_map = {source["id"]: source for source in inventory}
    with database.session() as session:
        pinned_revision = session.get(Revision, revision) if revision else None
        revision_times = [pinned_revision.created_at] if pinned_revision else []
        if query.revision is not None:
            for model, field in ((ObservationRecord, ObservationRecord.observed_at), (PollRecord, PollRecord.observed_at), (Snapshot, Snapshot.retrieved_at), (Correction, Correction.created_at)):
                timestamp = session.scalar(select(func.max(field)).where(model.revision <= revision))
                if timestamp:
                    revision_times.append(timestamp)
    effective_cutoff = query.as_of or (max(revision_times) if query.revision is not None and revision_times else utc_now())
    date_window = getattr(query, "date_window", None)
    if date_window and instant(date_window[1], end_of_day=True) < instant(effective_cutoff, end_of_day=True):
        effective_cutoff = instant(date_window[1], end_of_day=True).isoformat()
    scope = {"revision": revision, "state": query.state, "cutoff": effective_cutoff, "all_versions": True,
             "metric": query.metric, "mode": query.mode, "time_basis": query.time_basis}
    current_rows = database.observations(cycle=query.cycle, **scope)
    baseline_rows = database.observations(cycle=query.baseline, uncategorized=query.category_dimension is None,
                                         **scope) if query.baseline != query.cycle else []
    observations = [_source_priority(row, source_map) for row in current_rows + baseline_rows]
    calendar_references = _calendar_references(database, query, revision, effective_cutoff)
    calendar_by_cycle = {item["cycle"]: item for item in calendar_references}
    if query.mode == "early_in_person":
        observations = [{**row, "metadata": {**row.get("metadata", {}),
            "voting_open_date": calendar_by_cycle[row["cycle"]]["voting_open_date"],
            "calendar_snapshot_id": calendar_by_cycle[row["cycle"]]["snapshot_id"],
            "calendar_source_url": calendar_by_cycle[row["cycle"]]["source_url"]}}
            if row["cycle"] in calendar_by_cycle else row for row in observations]
    poll_records = database.polls(revision=revision, state=query.state, cutoff=effective_cutoff)
    catalog = _cached(database, ("catalog", revision, query.state, effective_cutoff),
                      lambda: database.observation_catalog(revision=revision, state=query.state, cutoff=effective_cutoff))
    catalog = [row for row in catalog if row["metric"] != "market_price_pct"]
    alignment = {"days_since_open": "days_since_opening", "calendar": "days_to_election"}.get(query.alignment, query.alignment)
    analysis = historical_analysis(observations, state=query.state, cycle=query.cycle, baseline=query.baseline,
        metric=query.metric, mode=query.mode, as_of=effective_cutoff, time_basis=query.time_basis,
        geography_ids=query.geography_ids or None, category_dimension=query.category_dimension,
        category=query.category, alignment=alignment)
    polling = poll_analysis(poll_records, as_of=effective_cutoff, state=query.state, cycle=query.cycle)
    series = []
    for cycle, points in ((query.cycle, analysis["current_series"]), (query.baseline, analysis["baseline_series"])):
        for point in points:
            refs = point.get("sources", [])
            series.append({**point, "cycle": cycle, "metric": query.metric, "mode": query.mode,
                           "time_basis": query.time_basis, "observation_ids": [r["id"] for r in refs if r.get("id")],
                           "source_ids": sorted({r["source_id"] for r in refs if r.get("source_id")})})
    matched = analysis["matched_comparison"]
    matched_map = {r.get("canonical_id") or r["geography_id"]: r for r in matched.get("geographies", [])}
    latest = analysis.get("latest")
    total = latest["value"] if latest else None
    geographies = []
    for row in analysis["geographies"]:
        match = matched_map.get(row.get("canonical_id") or row["geography_id"], {})
        geographies.append({"id": row["geography_id"], "canonical_id": row.get("canonical_id"), "geography_join": row.get("geography_join"), "name": row["geography_name"], "type": row["geography_type"],
            "value": row["value"], "baseline_value": match.get("baseline") if not matched.get("asynchronous") else None,
            "change": match.get("change") if not matched.get("asynchronous") else None,
            "share": row["value"] / total if total else None, "denominator": row.get("denominator"),
            "date": row["date"], "source_ids": [row["source_id"]], "observation_ids": [row["id"]],
            "metadata": row.get("metadata", {})})
    relevant = [r for r in catalog if r["cycle"] == query.cycle and r["time_basis"] == query.time_basis]
    available_metrics = sorted({r["metric"] for r in relevant})
    available_modes = sorted({r["mode"] for r in relevant if r["metric"] == query.metric})
    warnings = analysis["warnings"] + polling.get("warnings", [])
    unmatched = [row for row in geographies if row.get("geography_join", {}).get("status") == "unmatched"]
    if unmatched:
        warnings.append(f"{len(unmatched)} reporting areas have no verified join to the available county boundaries; their observations remain available in tables.")
    if query.category_dimension and not any(r.get("category_dimension") == query.category_dimension and r.get("category") == query.category for r in relevant):
        warnings.append("The selected category combination is not published in the selected evidence.")
    if query.alignment == "calendar":
        warnings.append("Calendar display is descriptive; cross-cycle comparisons remain aligned by days to Election Day.")
    if not latest:
        warnings.append("No observations match this metric, voting mode, time basis, and cutoff. Choose an available measure; missing is not zero.")
    if query.time_basis == "reported" and any(r["cycle"] == query.baseline and r["time_basis"] == "reconstructed" for r in catalog):
        warnings.append("Historical reconstruction exists; switch evidence mode to inspect its documented basis. It cannot establish what was reported then.")
    metric = next((m for m in METRICS if m["id"] == query.metric), {"label": query.metric.replace("_", " "), "unit": "ballots"})
    try:
        raw_brief = state_brief(observations, poll_records, state=query.state, cycle=query.cycle, baseline=query.baseline,
                                metric=query.metric, mode=query.mode, as_of=effective_cutoff, time_basis=query.time_basis,
                                geography_ids=query.geography_ids or None, category_dimension=query.category_dimension,
                                category=query.category, alignment=alignment,
                                _historical_analysis=analysis, _polling_analysis=polling)
        sections = raw_brief.get("sections", []) if isinstance(raw_brief, dict) else raw_brief
        brief = []
        for i, section in enumerate(sections):
            refs = section.get("sources", [])
            brief.append({**section, "id": section.get("id", f"brief-{i}"), "title": section.get("title", "Research finding"),
                          "text": section.get("text", section.get("body", "")),
                          "observation_ids": [r["id"] for r in refs if r.get("id")],
                          "source_ids": sorted({r["source_id"] for r in refs if r.get("source_id")})})
    except TypeError:
        # A source-independent factual brief remains available even if a specialist section is unsupported.
        brief = []
    if not brief:
        brief = [{"id": "coverage", "title": "Evidence coverage", "text": f"{state['name']}: " + (f"{total:,.0f} {metric['label'].lower()} are represented at the selected cutoff." if total is not None else "No compatible published observations are available for this selection."),
                  "observation_ids": [r["id"] for r in latest.get("sources", []) if r.get("id")] if latest else [],
                  "source_ids": [r["source_id"] for r in latest.get("sources", []) if r.get("source_id")] if latest else []}]
    national = _cached(database, ("national", revision, query.cycle, query.baseline, query.metric, query.mode,
                                  query.time_basis, effective_cutoff, *_inventory_token(database)),
                        lambda: _national(database, query, revision, effective_cutoff, inventory, source_map))
    average = polling.get("averages") or None
    # Keep payloads at the research grain. Other modes support the mode chart; marginal groups use composition.
    from .analytics import filter_observations
    displayed_observations = []
    for cycle, cutoff in ((query.cycle, effective_cutoff), (query.baseline, analysis.get("baseline_as_of"))):
        if cutoff is None:
            continue
        selected, _ = filter_observations(observations, state=query.state, cycle=cycle, metric=query.metric,
            mode=query.mode, as_of=cutoff, time_basis=query.time_basis, geography_ids=query.geography_ids or None,
            category_dimension=query.category_dimension, category=query.category)
        displayed_observations.extend(selected)
    if date_window:
        from datetime import timedelta

        from .analytics.common import day
        window_start = day(date_window[0])
        baseline_start = (window_start - timedelta(days=(day(ELECTION_DATES[query.cycle]) - day(ELECTION_DATES[query.baseline])).days))
        series = [point for point in series if day(point["date"]) >= (window_start if point["cycle"] == query.cycle else baseline_start)]
        displayed_observations = [row for row in displayed_observations if day(row["date"]) >= (window_start if row["cycle"] == query.cycle else baseline_start)]
        analysis["current_series"] = [point for point in analysis["current_series"] if day(point["date"]) >= window_start]
        analysis["baseline_series"] = [point for point in analysis["baseline_series"] if day(point["date"]) >= baseline_start]
    selected_count = len(displayed_observations)
    # Only the latest statewide row per other mode is needed for the mode chart.
    # It is explicit context and never contributes to the selected total or CSV grain.
    context_rows = [_source_priority(row, source_map) for row in database.observations(
        revision=revision, state=query.state, cycle=query.cycle, cutoff=effective_cutoff, all_versions=True,
        metric=query.metric, time_basis=query.time_basis, uncategorized=True, geography_type="state")]
    mode_context_ids = []
    for mode in sorted({row["mode"] for row in context_rows} - {query.mode}):
        selected, _ = filter_observations(context_rows, state=query.state, cycle=query.cycle, metric=query.metric,
                                         mode=mode, as_of=effective_cutoff, time_basis=query.time_basis)
        if selected:
            row = max(selected, key=lambda record: record["date"])
            displayed_observations.append(row)
            mode_context_ids.append(row["id"])
    return {"revision": revision, "latest_revision": latest_revision, "query": {**query.model_dump(), "revision": revision, "as_of": effective_cutoff},
        "state": state, "summary": {"total": total, "latest_date": latest["date"] if latest else None,
            "newly_reported": latest.get("newly_reported") if latest else None,
            "baseline_total": matched.get("baseline"), "pace_ratio": matched.get("ratio") if not matched.get("asynchronous") else None,
            "geography_count": len(geographies), "coverage_status": "available" if latest else "not_published",
            "poll_count": len({p["study_id"] for p in poll_records if p["cycle"] == query.cycle}), "poll_question_count": len([p for p in poll_records if p["cycle"] == query.cycle]), "metric_label": metric["label"], "unit": metric["unit"]},
        "observations": [_display_observation(row) for row in displayed_observations],
        "observation_scope": {"complete": True, "selected_count": selected_count, "context_count": len(mode_context_ids),
            "mode_context_ids": mode_context_ids,
            "description": "All selected current/baseline value rows, plus latest statewide mode context; no row limit is applied.",
            "native_metadata": "Full native fields and source lineage remain available at /api/v1/evidence/{id}."},
        "series": series, "geographies": geographies,
        "geographic_research": _geographic_research(observations, query, total, effective_cutoff),
        "composition": _composition(observations, query), "polls": poll_records,
        "polling": {**polling, "available": bool(average), "average": average,
            "eligible_count": polling.get("producer_count", 0), "reason": "At least three independent comparable producers are required for a descriptive average." if not average else "Simple mean of latest eligible independent producers.",
            "included": polling.get("eligible", []), "sensitivity": [item for item in polling.get("series", [])]},
        "sources": [s for s in inventory if s.get("state") == query.state], "brief": brief,
        "coverage": {"status": "available" if latest else "limited", "available_metrics": available_metrics,
            "available_modes": available_modes, "available_dimensions": sorted({r["category_dimension"] for r in relevant if r.get("category_dimension")}),
            "available_cycles": sorted({r["cycle"] for r in catalog}, reverse=True), "geographic_count": len(geographies),
            "geography_join": {"matched": sum(row.get("geography_join", {}).get("status") == "matched" for row in geographies),
                "unmatched": [{"id": row["id"], "name": row["name"]} for row in unmatched],
                "native": sum(row.get("geography_join", {}).get("status") == "native_geography" for row in geographies)},
            "recommended_selection": _recommended_selection(relevant),
            "as_reported_available": any(r["time_basis"] == "reported" for r in catalog),
            "reconstructed_available": any(r["time_basis"] == "reconstructed" for r in catalog)},
        "warnings": sorted(set(warnings)), "national": national,
        "calendar": [{"date": ELECTION_DATES[query.cycle], "label": "General election", "source_url": "https://www.fec.gov/documents/5910/2026pdates.pdf"}]
            + [{"date": item[field], "label": label, "source_url": item["source_url"]}
               for item in calendar_references if item["cycle"] == query.cycle
               for field, label in (("voting_open_date", "In-person early voting opens"),
                                    ("voting_close_date", "In-person early voting closes"))],
        "calendar_references": calendar_references,
        "comparison": matched, "historical": _compact_history(analysis)}


def _calendar_references(database: Database, query: ResearchQuery, revision: int, cutoff: str) -> list[dict]:
    from .connectors.calendars import calendar_reference
    references = [calendar_reference(query.state, cycle, "early_in_person") for cycle in {query.cycle, query.baseline}]
    result = []
    with database.session() as session:
        for reference in references:
            if reference is None:
                continue
            source_state = session.get(SourceState, reference["id"])
            if not source_state or not source_state.document_hash or not source_state.last_changed:
                continue
            snapshots = session.scalars(select(Snapshot).where(Snapshot.revision <= revision,
                Snapshot.source_id == reference["id"], Snapshot.url == reference["source_url"]).order_by(Snapshot.revision.desc()))
            snapshot = next((item for item in snapshots if query.time_basis == "reconstructed"
                             or instant(item.retrieved_at) <= instant(cutoff, end_of_day=True)), None)
            if snapshot:
                result.append({**reference, "snapshot_id": snapshot.id, "source_id": snapshot.source_id,
                    "source_sha256": snapshot.sha256, "snapshot_revision": snapshot.revision,
                    "retrieved_at": snapshot.retrieved_at, "source_status": source_state.status})
    return sorted(result, key=lambda item: item["cycle"], reverse=True)


def _national(database: Database, query: ResearchQuery, revision: int, cutoff: str,
              inventory: list[dict], source_map: dict) -> list[dict]:
    # A publication process has an immutable evidence snapshot. Keep its small
    # national summaries across state builds rather than repeatedly evicting
    # them from the short-lived interactive workspace cache.
    cache = getattr(database, "_publication_national_cache", None)
    if cache is None:
        return _national_uncached(database, query, revision, cutoff, inventory, source_map)
    from copy import deepcopy
    key = (revision, cutoff, query.cycle, query.baseline, query.metric, query.mode, query.time_basis,
           json.dumps(inventory, sort_keys=True), json.dumps(source_map, sort_keys=True))
    if key not in cache:
        cache[key] = _national_uncached(database, query, revision, cutoff, inventory, source_map)
        if len(cache) > 128:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    return deepcopy(cache[key])


def _national_uncached(database: Database, query: ResearchQuery, revision: int, cutoff: str,
                       inventory: list[dict], source_map: dict) -> list[dict]:
    from .analytics import historical_analysis
    all_polls = database.polls(revision=revision, cutoff=cutoff)
    national_by_state = defaultdict(list)
    scope = {"revision": revision, "cycle": query.cycle, "cutoff": cutoff, "all_versions": True,
             "metric": query.metric, "mode": query.mode, "time_basis": query.time_basis, "uncategorized": True}
    for row in database.observations(geography_type="state", **scope):
        national_by_state[row["state"]].append(_source_priority(row, source_map))
    missing_states = [info["code"] for info in all_states() if info["code"] not in national_by_state]
    if missing_states:
        for row in database.observations(states=missing_states, **scope):
            national_by_state[row["state"]].append(_source_priority(row, source_map))
    national = []
    for info in all_states():
        analysis = historical_analysis(national_by_state[info["code"]], state=info["code"], cycle=query.cycle,
            baseline=query.baseline, metric=query.metric, mode=query.mode, as_of=cutoff, time_basis=query.time_basis)
        point = analysis.get("latest")
        national.append({"code": info["code"], "name": info["name"], "fips": info["fips"], "watchlist": info["watchlist"],
            "contested": info["contested"], "senate_election_status": "scheduled" if info["contested"] else "no_regular_senate_contest",
            "canonical_id": f"state:{info['code']}",
            "value": point["value"] if point else None, "latest_date": point["date"] if point else None,
            "newly_reported": point.get("newly_reported") if point else None,
            "trajectory": [{"date": p["date"], "value": p["value"]} for p in analysis["current_series"]],
            "source_count": sum(source_covers_state(source, info["code"]) for source in inventory),
            "poll_count": len({poll["study_id"] for poll in all_polls if poll["state"] == info["code"] and poll["cycle"] == query.cycle}),
            "coverage_status": "available" if point else "not_published", "metric": query.metric})
    return national


def _recommended_selection(catalog: list[dict]) -> dict | None:
    """A suggestion for a new investigation; never rewrites an explicit query."""
    preference = ("ballots_cast", "ballots_accepted", "ballots_returned", "ballot_records_returned",
                  "ballots_issued", "ballot_records_issued", "ballots_requested", "ballot_records_requested")
    tiers = {s["id"]: s.get("tier", 1) for s in sources()}
    available = [row for row in catalog if row["metric"] in preference and not row.get("category_dimension")]
    strongest = min((tiers.get(row.get("source_id"), 4) for row in available), default=None)
    catalog = [row for row in available if tiers.get(row.get("source_id"), 4) == strongest]
    for metric in preference:
        options = [row for row in catalog if row["metric"] == metric and not row.get("category_dimension")]
        if options:
            chosen = min(options, key=lambda row: (row["mode"] != "all", row["mode"]))
            return {"metric": chosen["metric"], "mode": chosen["mode"], "time_basis": chosen["time_basis"],
                    "reason": "Available reported participation measure; definitions remain explicit."}
    return None


def capabilities(database: Database, state: str, *, cycle: int = 2026, revision: int | None = None,
                 as_of: str | None = None, time_basis: str = "reported") -> dict:
    revision = database.latest_revision() if revision is None else revision
    cutoff = as_of or utc_now()
    catalog = database.observation_catalog(revision=revision, state=state, cutoff=cutoff)
    relevant = [row for row in catalog if row["cycle"] == cycle and row["time_basis"] == time_basis
                and row["metric"] != "market_price_pct"]
    info = state_info(state)
    return {"state": state, "revision": revision, "as_of": cutoff, "cycle": cycle, "time_basis": time_basis,
            "senate_election_status": "scheduled" if info["contested"] else "no_regular_senate_contest",
            "watchlist": info["watchlist"], "participation_available": bool(relevant),
            "metrics": sorted({row["metric"] for row in relevant}),
            "dimensions": sorted({row["category_dimension"] for row in relevant if row.get("category_dimension")}),
            "combinations": relevant, "recommended_selection": _recommended_selection(relevant),
            "note": "Capability describes archived evidence, independently of whether a Senate contest is scheduled."}


def _geographic_research(observations: list[dict], query: ResearchQuery, total: float | None, cutoff: str) -> dict:
    from .analytics import filter_observations, historical_analysis
    from .analytics.common import day
    from .geography import county_index
    alignment = {"days_since_open": "days_since_opening", "calendar": "days_to_election"}.get(query.alignment, query.alignment)
    selected, warnings = filter_observations(observations, state=query.state, cycle=query.cycle,
        metric=query.metric, mode=query.mode, as_of=cutoff, time_basis=query.time_basis,
        category_dimension=query.category_dimension, category=query.category)
    details = [row for row in selected if row["geography_type"] != "state"]
    grain = next((value for value in ("county", "district", "municipality", "precinct")
                  if any(row["geography_type"] == value for row in details)), None)
    if query.geography_ids:
        targets = set(normalize_selections(query.state, query.geography_ids))
        details = [row for row in details if (row.get("canonical_id") or row["geography_id"]) in targets or row["geography_id"] in targets]
        grains = {row["geography_type"] for row in details}
        if len(grains) > 1:
            return {"status": "incompatible_grains", "places": [], "rankings": [], "waterfall": [], "concentration": [],
                    "warnings": ["Selected geographies use different reporting grains; compare them separately."]}
        grain = next(iter(grains), grain)
    else:
        details = [row for row in details if row["geography_type"] == grain]
    groups = defaultdict(list)
    for row in details:
        groups[row.get("canonical_id") or row["geography_id"]].append(row)
    # Baseline records join only through a verified canonical ID or unchanged native ID.
    for row in observations:
        key = row.get("canonical_id") or row["geography_id"]
        if row["cycle"] == query.baseline and key in groups:
            groups[key].append(row)
    places, rankings, changes = [], [], []
    window = getattr(query, "date_window", None)
    for key, rows in groups.items():
        analysis = historical_analysis(rows, state=query.state, cycle=query.cycle, baseline=query.baseline,
            metric=query.metric, mode=query.mode, as_of=cutoff, time_basis=query.time_basis,
            geography_ids=[key], category_dimension=query.category_dimension, category=query.category,
            alignment=alignment)
        points = analysis["current_series"]
        if not points:
            continue
        latest = points[-1]
        row = max((row for row in rows if row["cycle"] == query.cycle), key=lambda row: row["date"])
        visible = [point for point in points if not window or day(point["date"]) >= day(window[0])]
        baseline_visible = analysis["baseline_series"]
        if window:
            from datetime import timedelta
            baseline_start = day(window[0]) - timedelta(days=(day(ELECTION_DATES[query.cycle]) - day(ELECTION_DATES[query.baseline])).days)
            baseline_visible = [point for point in baseline_visible if day(point["date"]) >= baseline_start]
        def compact(point):
            return {name: point.get(name) for name in ("date", "x", "days_to_election", "value", "newly_reported", "is_correction", "rate")} | {
                "observation_ids": [ref["id"] for ref in point.get("sources", []) if ref.get("id")],
                "source_ids": sorted({ref["source_id"] for ref in point.get("sources", []) if ref.get("source_id")})}
        comparison = analysis["matched_comparison"]
        prior = next((point for point in reversed(points[:-1]) if not window or day(point["date"]) <= day(window[0])), None)
        change = latest["value"] - prior["value"] if prior else None
        entry = {"id": row["geography_id"], "canonical_id": row.get("canonical_id"), "name": row["geography_name"],
            "type": row["geography_type"], "value": latest["value"], "date": latest["date"],
            "share": latest["value"] / total if total and not query.geography_ids else None,
            "newly_reported": latest.get("newly_reported"), "window_change": change,
            "window_start_date": prior["date"] if prior else None,
            "baseline_value": comparison.get("baseline") if not comparison.get("asynchronous") else None,
            "historical_change": comparison.get("change") if not comparison.get("asynchronous") else None,
            "comparison_compatible": comparison["status"] == "available" and not comparison.get("asynchronous"),
            "geography_join": row.get("geography_join"),
            "observation_ids": [ref["id"] for ref in latest.get("sources", []) if ref.get("id")],
            "source_ids": sorted({ref["source_id"] for ref in latest.get("sources", []) if ref.get("source_id")})}
        rankings.append(entry)
        places.append({**entry, "series": [compact(point) for point in visible],
                       "baseline_series": [compact(point) for point in baseline_visible],
                       "endpoints": {"current": compact(latest), "baseline": compact(analysis["baseline_series"][-1]) if analysis["baseline_series"] else None},
                       "warnings": analysis["warnings"]})
        if change is not None:
            changes.append({**entry, "change": change})
    rankings.sort(key=lambda row: (-row["value"], row["name"]))
    detail_total = sum(row["value"] for row in rankings)
    concentration, running = [], 0
    for index, row in enumerate(rankings):
        running += row["value"]
        row["rank"] = index + 1
        concentration.append({"rank": index + 1, "id": row["id"], "canonical_id": row["canonical_id"], "name": row["name"],
                              "place_share": (index + 1) / len(rankings), "cumulative_value": running,
                              "cumulative_share": running / detail_total if detail_total else None})
    changes.sort(key=lambda row: (-row["change"], row["name"]))
    running = 0
    for row in changes:
        row["start"] = running
        running += row["change"]
        row["end"] = running
    dates = sorted({row["date"] for row in rankings})
    expected = len(county_index(query.state)["by_geoid"]) if grain == "county" else None
    return {"status": "available" if places else "not_published", "grain": grain,
        "places": places, "rankings": rankings, "waterfall": changes, "concentration": concentration,
        "coverage": {"observed_places": len(rankings), "boundary_places": expected,
                     "matched_boundary_places": sum(row.get("geography_join", {}).get("status") == "matched" for row in rankings),
                     "dates": dates, "synchronous": len(dates) <= 1, "detail_total": detail_total,
                     "statewide_total": total if not query.geography_ids else None},
        "explanations": {
            "trajectories": "Each line is an individually reported place. Steps advance only on actual observations.",
            "rankings": "Ranked reported volume at each place's latest available observation; dates may differ.",
            "waterfall": "Change between actual observations within each place; negative values may be source corrections. This is not a count of voting-day activity.",
            "concentration": "Cumulative share of reported detail, ordered by volume. It is not population-adjusted participation.",
            "share": "Place share is provided only against an unfiltered compatible statewide total."},
        "warnings": warnings + (["Latest reporting dates differ across places; ranked volumes are not a synchronized reporting snapshot."] if len(dates) > 1 else [])}


def per_place_series(database: Database, query: ResearchQuery) -> dict:
    """Individually labeled trajectories and companion charts from one evidence read."""
    view = workspace(database, query)
    return {"revision": view["revision"], "query": view["query"], "metric": view["historical"]["metric"],
            "unit": view["summary"]["unit"], **view["geographic_research"]}


def compact_workspace(database: Database, query: ResearchQuery) -> dict:
    return _cached(database, ("compact_workspace", query.model_dump_json(), *_inventory_token(database)),
                   lambda: _compact_workspace(database, query))


def _compact_workspace(database: Database, query: ResearchQuery) -> dict:
    """Version-two overview without repeated raw observations or full native polls.

    All observations remain queryable through the v1 evidence and paginated
    evidence interfaces. No arbitrary row truncation or metric recomputation occurs.
    """
    view = workspace(database, query)
    return {key: value for key, value in view.items() if key not in {"observations", "polls", "historical"}} | {
        "historical": {key: value for key, value in view["historical"].items() if key not in {"geographies", "sources"}},
        "evidence": {"count": view["observation_scope"]["selected_count"], "complete": True,
                     "detail_endpoint": "/api/v1/evidence/{id}", "omitted_from_summary": "raw observation rows and full poll records"}}
