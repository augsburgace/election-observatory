"""Same-stage EV evidence and turnout references, without interpolated facts.

The historical observation date and the date evidence became available are
different clocks. Retrospective comparisons are useful, but are never promoted
to contemporaneous backtests by this service.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from .analytics.common import available_at, day, instant, source_refs
from .analytics.historical import (
    _comparison,
    _grain,
    _latest_geographies,
    _series,
    filter_observations,
)
from .db import Revision, Snapshot
from .domain import ResearchQuery, utc_now
from .provenance import snapshot_references
from .registry import ELECTION_DATES, METRICS, sources, state_info
from .service import _cached, _calendar_references, _source_priority, capabilities

PARTICIPATION = {"ballots_cast", "ballots_accepted", "ballots_returned"}


def _references(database, rows, revision):
    refs = snapshot_references(database, source_refs(rows), revision)
    ids = {r.get("snapshot_id") for r in refs if r.get("snapshot_id")}
    inventory = {s["id"]: s for s in sources()}
    with database.session() as session:
        snapshots = {s.id: s for s in session.scalars(select(Snapshot).where(
            Snapshot.id.in_(ids), Snapshot.revision <= revision))} if ids else {}
    result = []
    seen = set()
    for ref in refs:
        key = (ref.get("source_id"), ref.get("snapshot_id"))
        if key in seen:
            continue
        seen.add(key)
        source = inventory.get(ref.get("source_id"), {})
        snap = snapshots.get(ref.get("snapshot_id"))
        result.append({"source_id": ref.get("source_id"), "snapshot_id": ref.get("snapshot_id"),
            "name": source.get("name", ref.get("source_id")),
            "role": ref.get("role", "observation"),
            "url": snap.url if snap else ref.get("source_url") or source.get("url"),
            "original_url": ref.get("original_url") or source.get("original_url") or source.get("discovery_url"),
            "sha256": snap.sha256 if snap else ref.get("sha256"),
            "retrieved_at": snap.retrieved_at if snap else None})
    return result


def _calendar(database, state, cycle, mode, revision, cutoff, retrospective):
    if mode != "early_in_person":
        return None
    query = ResearchQuery(state=state, cycle=cycle, baseline=cycle, mode=mode,
        revision=revision, as_of=cutoff, time_basis="reconstructed" if retrospective else "reported")
    return next(iter(_calendar_references(database, query, revision, cutoff)), None)


def _filtered(rows, *, state, cycle, metric, mode, cutoff, retrospective, calendar=None):
    candidates = []
    for row in rows:
        if row.get("cycle") != cycle or row.get("metric") != metric or row.get("mode") != mode:
            continue
        if not retrospective and row.get("correction") and instant(row["correction"]["created_at"]) > instant(cutoff, end_of_day=True):
            row = {**row, "value": row.get("original_value", row["correction"]["original"])}
        original_basis = row.get("time_basis", "reported")
        if original_basis == "final" or (not retrospective and original_basis != "reported"):
            continue
        metadata = {**row.get("metadata", {}), "original_time_basis": original_basis}
        if calendar:
            metadata["voting_open_date"] = calendar["voting_open_date"]
        # This is a query-time chronology adapter, never a stored observation.
        # Native publication / retrieval dates and source basis remain attached.
        candidates.append({**row, "metadata": metadata,
            "time_basis": "reconstructed" if retrospective else "reported"})
    return filter_observations(candidates, state=state, cycle=cycle, metric=metric, mode=mode,
        as_of=cutoff, time_basis="reconstructed" if retrospective else "reported")


def _trajectory(rows):
    return [{**p, "days_since_opening": (
        (day(p["date"]) - day(rows[0]["metadata"]["voting_open_date"])).days
        if rows and rows[0].get("metadata", {}).get("voting_open_date") else None)}
        for p in _series(rows, "days_to_election")]


def _geographies(rows):
    return [{"id": key, "name": row.get("geography_name", key), "date": row["date"],
        "value": row["value"], "source_id": row.get("source_id"), "observation_id": row.get("id")}
        for key, row in _latest_geographies(rows).items()]


def _mode_values(database, rows, state, cycle, metric, cutoff, retrospective, revision):
    values = []
    for mode in sorted({r.get("mode", "all") for r in rows if r["cycle"] == cycle}):
        filtered, _ = _filtered(rows, state=state, cycle=cycle, metric=metric, mode=mode,
            cutoff=cutoff, retrospective=retrospective)
        selected, grain = _grain(filtered, None)
        series = _series(selected, "days_to_election")
        if not series:
            continue
        last = series[-1]
        members = list(_latest_geographies(selected).values())
        values.append({"mode": mode, "metric": metric, "value": last["value"], "date": last["date"],
            "grain": grain, "definition": sorted({r.get("metadata", {}).get("native_definition", metric) for r in members}),
            "classification": sorted({r.get("metadata", {}).get("mode_classification") for r in members
                if r.get("metadata", {}).get("mode_classification")}),
            "source_refs": _references(database, members, revision),
            "aggregation_policy": "Separate native measures; do not add these rows without a verified disjoint-category definition and matching date/source."})
    return values


def _turnout(database, state, cycle, revision, cutoff, current, selected_rows, inventory):
    """Final participation is a reference quantity, never a current denominator."""
    finals = database.observations(state=state, revision=revision, metric="final_turnout",
        uncategorized=True, geography_type="state", all_versions=True)
    references = []
    for year in sorted({r["cycle"] for r in finals if r["cycle"] < cycle and r["cycle"] < day(cutoff).year}, reverse=True):
        candidates = [_source_priority(r, inventory) for r in finals if r["cycle"] == year and r.get("mode") == "all"
            and r.get("value", 0) > 0 and r.get("validation", {}).get("status") != "quarantined"]
        if not candidates:
            continue
        chosen = min(candidates, key=lambda r: (r["metadata"]["source_priority"],
            -int(r.get("revision", 0)), r.get("source_id", "")))
        references.append({"cycle": year, "value": chosen["value"], "date": chosen["date"],
            "election_type": "presidential" if year % 4 == 0 else ("midterm" if year % 2 == 0 else "off_year"),
            "definition": chosen.get("metadata", {}).get("native_definition", "Source-defined final participation")
                + (". " + chosen["metadata"]["participation_measurement_caveat"]
                   if chosen.get("metadata", {}).get("participation_measurement_caveat") else ""),
            "source_refs": _references(database, [chosen], revision),
            "reference_only": True,
            "alternate_source_values": [{"value": r["value"], "source_id": r["source_id"]}
                for r in candidates if r["id"] != chosen["id"]]})
    registration = None
    # Require a dated denominator and its explicit registration definition.
    for row in selected_rows:
        md = row.get("metadata", {})
        denominator = row.get("denominator")
        definition = md.get("denominator_definition")
        date = md.get("denominator_date")
        independently_dated = md.get("denominator_active_all_status") != "Not distinguished by this report"
        if len(selected_rows) == 1 and denominator and denominator > 0 and definition and date and day(date) <= day(cutoff) and independently_dated:
            registration = {"value": denominator, "date": date, "definition": definition,
                "participation_rate_pct": 100 * row["value"] / denominator,
                "source_refs": _references(database, [row], revision)}
    measured = current.get("value")
    full_measure = current.get("metric") in {"ballots_cast", "ballots_accepted"} and current.get("mode") == "all" and current.get("grain") == "state"
    receipt_measure = current.get("metric") == "ballots_returned"
    scenarios = []
    same_class = [r for r in references if r["cycle"] % 4 == cycle % 4]
    base = next(iter(same_class), None)
    if base:
        for name, multiplier in (("Lower turnout", .9), ("Prior-cycle turnout", 1.), ("Higher turnout", 1.1)):
            assumed = round(base["value"] * multiplier)
            consistent = not full_measure or measured is None or assumed >= measured
            scenarios.append({"name": name, "reference_cycle": base["cycle"], "multiplier": multiplier,
                "assumed_final_participation": assumed, "consistent": consistent,
                "reported_early_participation": measured if full_measure else None,
                "reported_measure_value": measured, "counted_participation_floor_applied": full_measure,
                "unaccepted_receipt_measure": receipt_measure,
                "remaining_participation": assumed - measured if consistent and full_measure and measured is not None else None,
                "early_share_of_assumed_final_pct": 100 * measured / assumed if consistent and full_measure and measured is not None else None,
                "interpretation": "Conditional assumption, not a fitted turnout forecast. Remaining participation includes later early votes and Election Day; candidate support is unspecified."})
    return {"registration_denominator": registration, "historical_final_participation": references,
        "scenarios": scenarios, "scenario_reference": base,
        "forecast_status": "Turnout scenarios are assumptions. Empirical turnout prediction requires a separate prior-only validation.",
        "warnings": ["Candidate votes, ballot requests, population and registered voters are different quantities.",
            "Report-dated registration references without an established registration snapshot and active/all definition remain source context; they do not establish a current registered-voter turnout rate.",
            "A prior cycle's final participation is not the denominator for this cycle's turnout rate.",
            "Remaining participation is shown only for a complete statewide all-method cast/accepted measure. Returned receipts can include unaccepted/rejected ballots and are not subtracted from counted final participation."]}


def stage_history(database, *, state="NC", cycle=2026, revision=None, as_of=None,
                  metric=None, mode=None, alignment="days_to_election", history_basis="retrospective",
                  baseline_cycles=(2016, 2018, 2020, 2022, 2024)):
    state = state.upper()
    state_info(state)
    if cycle not in ELECTION_DATES:
        raise ValueError("Unsupported election cycle")
    if alignment not in {"days_to_election", "days_since_opening"}:
        raise ValueError("Choose days_to_election or days_since_opening")
    if history_basis not in {"retrospective", "reported"}:
        raise ValueError("Choose retrospective or reported historical evidence")
    latest = database.latest_revision()
    revision = latest if revision is None else revision
    if not 0 <= revision <= latest:
        raise ValueError("The requested dataset revision does not exist")
    if as_of:
        instant(as_of, end_of_day=True)
    else:
        with database.session() as session:
            record = session.get(Revision, revision)
            as_of = record.created_at if record else utc_now()
    cycles = tuple(sorted({int(c) for c in baseline_cycles if 1976 <= int(c) < cycle}))
    key = ("ev_stage_history_v1", revision, state, cycle, as_of, metric, mode, alignment, history_basis, cycles)
    return _cached(database, key, lambda: _build(database, state, cycle, revision, as_of,
        metric, mode, alignment, history_basis, cycles))


def _build(database, state, cycle, revision, cutoff, metric, mode, alignment, basis, cycles):
    recommended = capabilities(database, state, cycle=cycle, revision=revision, as_of=cutoff).get("recommended_selection")
    metric = metric or (recommended or {}).get("metric", "ballots_cast")
    mode = mode or (recommended or {}).get("mode", "all")
    inventory = {s["id"]: s for s in sources()}
    rows = [_source_priority(r, inventory) for r in database.observations(state=state, revision=revision,
        metric=metric, uncategorized=True, all_versions=True)]
    current_calendar = _calendar(database, state, cycle, mode, revision, cutoff, False)
    current_rows, warnings = _filtered(rows, state=state, cycle=cycle, metric=metric, mode=mode,
        cutoff=cutoff, retrospective=False, calendar=current_calendar)
    current_grain, grain = _grain(current_rows, None)
    trajectory = _trajectory(current_grain)
    point = trajectory[-1] if trajectory else {}
    current_date = point.get("date")
    # Align to the latest actual report, rather than silently treating stale data as today's report.
    anchor = day(current_date or cutoff)
    dte = (day(ELECTION_DATES[cycle]) - anchor).days
    dso = (anchor - day(current_calendar["voting_open_date"])).days if current_calendar else None
    latest_current = list(_latest_geographies(current_grain).values())
    current = {"available": bool(point), "date": current_date, "cutoff": cutoff,
        "value": point.get("value"), "metric": metric, "mode": mode, "grain": grain,
        "days_to_election": dte, "days_since_opening": dso, "calendar": current_calendar,
        "age_days": max(0, (day(cutoff) - anchor).days) if current_date else None,
        "trajectory": trajectory, "geographies": _geographies(current_grain),
        "mode_values": _mode_values(database, rows, state, cycle, metric, cutoff, False, revision),
        "source_refs": _references(database, current_grain, revision)}
    comparisons = []
    for year in cycles:
        calendar = _calendar(database, state, year, mode, revision, cutoff, basis == "retrospective")
        aligned = alignment == "days_to_election" or (dso is not None and calendar is not None)
        target = day(ELECTION_DATES[year]) - timedelta(days=dte) if alignment == "days_to_election" else (
            day(calendar["voting_open_date"]) + timedelta(days=dso) if aligned else None)
        filtered, notes = _filtered(rows, state=state, cycle=year, metric=metric, mode=mode,
            cutoff=target.isoformat() if target else ELECTION_DATES[year], retrospective=basis == "retrospective", calendar=calendar)
        # An unsupported opening alignment is not replaced with a guessed opening.
        selected, historical_grain = _grain(filtered, None) if aligned else ([], "unavailable")
        historical_series = _trajectory(selected)
        last = historical_series[-1] if historical_series else {}
        observed_date = last.get("date")
        exact = bool(target and observed_date and target == day(observed_date) and not last.get("carried_forward_count"))
        comparison = _comparison(current_grain, selected, alignment) if current_grain and selected else None
        compatible = bool(comparison and comparison["status"] == "available" and not comparison["asynchronous"])
        final_cohort = any(r.get("metadata", {}).get("final_status_cohort") for r in selected)
        if final_cohort:
            compatible = False
        if not aligned:
            reason = "A verified opening calendar for this voting method is missing in one or both cycles."
        elif not selected:
            reason = "No eligible observation of this exact metric and method exists on or before the aligned cutoff."
        elif not exact:
            reason = "The latest eligible report predates the target stage; its age is visible and no exact-stage ratio is published."
        elif final_cohort:
            reason = "Final-status cohort reconstructed by recorded return date; later acceptance classifications cannot establish participation known at that stage."
        elif not compatible:
            reason = "The reports do not establish compatible matched geography, definitions, method classification and dates."
        else:
            reason = "Actual reports at the aligned stage; matched geographic coverage and definitions retained."
        refs = _references(database, selected, revision)
        classifications = sorted({r.get("metadata", {}).get("reconstruction_basis", "dated report") for r in selected})
        known_dates = [available_at(r) for r in selected if available_at(r)]
        chronology = {"basis": basis, "original_time_bases": sorted({r["metadata"]["original_time_basis"] for r in selected}),
            "description": "Only versions demonstrably available by the historical cutoff." if basis == "reported" else
                "Later-retained dated evidence. This does not establish what was publicly known on that date.",
            "reconstruction_types": classifications,
            "latest_known_at": max(known_dates).isoformat() if known_dates else None}
        comparisons.append({"cycle": year, "election_type": "presidential" if year % 4 == 0 else ("midterm" if year % 2 == 0 else "off_year"),
            "target_date": target.isoformat() if target else None, "observed_date": observed_date,
            "age_days": (target - day(observed_date)).days if target and observed_date else None,
            "value": last.get("value"), "available": bool(selected), "alignment_available": aligned,
            "same_stage": exact and compatible, "reason": reason,
            "pace_ratio": comparison["ratio"] if exact and compatible else None,
            "matched": comparison, "grain": historical_grain, "trajectory": historical_series,
            "geographies": _geographies(selected), "calendar": calendar, "chronology": chronology,
            "mode_values": _mode_values(database, rows, state, year, metric,
                target.isoformat() if target else ELECTION_DATES[year], basis == "retrospective", revision) if aligned else [],
            "source_refs": refs, "warnings": notes})
    definition = next((m for m in METRICS if m["id"] == metric), {"id": metric, "unit": "ballots", "description": metric})
    return {"schema": "observatory-ev-stage-history-v1", "revision": revision,
        "query": {"state": state, "cycle": cycle, "as_of": cutoff, "metric": metric, "mode": mode,
            "alignment": alignment, "history_basis": basis, "baseline_cycles": list(cycles)},
        "metric_definition": definition, "units": definition["unit"], "current": current, "cycles": comparisons,
        "turnout": _turnout(database, state, cycle, revision, cutoff, current, latest_current, inventory),
        "coverage": {"requested_cycles": len(cycles), "available_cycles": sum(c["available"] for c in comparisons),
            "same_stage_cycles": sum(c["same_stage"] for c in comparisons)},
        "warnings": sorted(set(warnings + ["Snapshot changes are newly reported ballots, not necessarily ballots cast that day.",
            "Presidential, midterm and off-year cycles have different electorates and voting opportunities.",
            "Registration, race, religion and past place-level results do not reveal an individual's candidate choice."]))}
