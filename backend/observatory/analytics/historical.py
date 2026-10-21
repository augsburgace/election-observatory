"""Calendar-aware aggregate comparisons with chronological and geographic safeguards."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from ..geography import canonicalize_observation, normalize_selections
from .common import RESEARCH_TIMEZONE, available_at, day, finite_number, instant, source_refs, version_rank


def geography_key(row: dict[str, Any]) -> str:
    return row.get("canonical_id") or row["geography_id"]

SUPPORTED_ALIGNMENTS = {"days_to_election", "days_since_opening", "voting_opportunities"}


def filter_observations(
    observations: list[dict[str, Any]], *, state: str, cycle: int, metric: str,
    mode: str = "all", as_of: str | None = None, time_basis: str = "reported",
    geography_ids: list[str] | None = None, category_dimension: str | None = None,
    category: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select one metric/grain, retaining only versions known before the cutoff.

    `all` selects an explicit total; it does not add source totals to subcategories
    or assume that separately reported modes are disjoint.
    """
    cutoff = instant(as_of, end_of_day=True) or datetime.now(UTC)
    selections = set(normalize_selections(state, geography_ids or []))
    versions: dict[tuple[Any, ...], dict[str, Any]] = {}
    warnings: set[str] = set()
    for original in observations:
        row = canonicalize_observation(original) if "canonical_id" not in original else original
        if row.get("state") != state or int(row.get("cycle", 0)) != int(cycle):
            continue
        if row.get("metric") != metric or row.get("mode", "all") != mode:
            continue
        if row.get("time_basis", "reported") != time_basis:
            continue
        if row.get("category_dimension") != category_dimension or row.get("category") != category:
            continue
        if selections and geography_key(row) not in selections and row.get("geography_id") not in selections:
            continue
        validation = row.get("validation") or {}
        if validation.get("status") == "quarantined":
            warnings.add(validation.get("reason", "An observation is quarantined by a documented quality validation."))
            continue
        if validation.get("reason"):
            warnings.add(validation["reason"])
        try:
            # Election dates must be valid even when a mode lacks comparison metadata.
            election_date = day(row["election_date"])
            observation_date = day(row["date"])
            if row.get("time_basis") == "reconstructed" and row.get("metric") == "ballot_records_requested" and state == "ME":
                if not validation.get("status") == "historical_warning":
                    warnings.add("Maine request-date history is withheld: standing requests do not establish current-cycle voting events.")
                    continue
            if observation_date.year < int(cycle) and row.get("time_basis") == "reconstructed" and validation.get("status") != "historical_warning":
                warnings.add("Reconstructed dates before the election year are excluded until their event semantics are validated.")
                continue
            if abs((observation_date - election_date).days) > 730 and validation.get("status") != "historical_warning":
                warnings.add("An observation with an anomalous election-relative date was excluded.")
                continue
            if observation_date > day(cutoff):
                continue
            known = available_at(row)
            # The caller has already pinned the evidence revision. Reconstructed
            # views filter historical source-record dates within that revision;
            # metadata distinguishes ballot-event dates from dated report snapshots.
            if time_basis != "reconstructed" and (known is None or known > cutoff):
                warnings.add("Records lacking contemporary publication evidence are excluded from this cutoff.")
                continue
            value = finite_number(row.get("value"), "Observation value")
            if value < 0:
                warnings.add("Invalid negative cumulative observations were excluded.")
                continue
        except (KeyError, TypeError, ValueError):
            warnings.add("Malformed observations were excluded.")
            continue
        key = (geography_key(row), row["date"], row.get("unit", "ballots"))
        previous = versions.get(key)
        if previous:
            same_source = previous.get("source_id") == row.get("source_id")
            if not same_source and previous["value"] != value:
                warnings.add("Conflicting sources exist; configured source priority determines the displayed value.")
            # A smaller authority rank is stronger. A newer version breaks ties.
            def rank(record: dict[str, Any]) -> tuple[int, tuple[str, str, str]]:
                priority = int((record.get("metadata") or {}).get("source_priority", 1))
                return (-priority, version_rank(record))
            if rank(row) <= rank(previous):
                continue
        versions[key] = row
    return sorted(versions.values(), key=lambda r: (r["date"], r["geography_id"])), sorted(warnings)


def _coordinate(row: dict[str, Any], alignment: str) -> int | None:
    try:
        if alignment == "days_to_election":
            return (day(row["date"]) - day(row["election_date"])).days
        metadata = row.get("metadata") or {}
        if alignment == "days_since_opening" and metadata.get("voting_open_date"):
            return (day(row["date"]) - day(metadata["voting_open_date"])).days
        if alignment == "voting_opportunities" and metadata.get("opportunity_index") is not None:
            value = finite_number(metadata["opportunity_index"], "Voting opportunity index")
            return int(value) if value >= 0 and value.is_integer() else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return None


def _grain(rows: list[dict[str, Any]], selected: list[str] | None) -> tuple[list[dict[str, Any]], str]:
    if not rows:
        return [], "unavailable"
    if selected:
        types = {r.get("geography_type", "state") for r in rows}
        if len(types) != 1:
            return [], "incompatible"
        return rows, next(iter(types))
    state_rows = [r for r in rows if r.get("geography_type", "state") == "state"]
    if state_rows:
        return state_rows, "state"
    # Do not mix counties, precincts, municipalities, or districts.
    for grain in ("county", "district", "municipality", "precinct"):
        group = [r for r in rows if r.get("geography_type") == grain]
        if group:
            return group, grain
    return [], "unavailable"


def _series(rows: list[dict[str, Any]], alignment: str) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    current: dict[str, dict[str, Any]] = {}
    series = []
    previous = None
    previous_geographies: set[str] = set()
    for date_key, updates in sorted(by_date.items()):
        for row in updates:
            current[geography_key(row)] = row
        members = list(current.values())
        value = sum(float(row["value"]) for row in members)
        coordinates = {_coordinate(row, alignment) for row in updates}
        x = next(iter(coordinates)) if len(coordinates) == 1 and None not in coordinates else None
        current_geographies = set(current)
        covered = len(current_geographies)
        current_denominators = [row.get("denominator") for row in members]
        try:
            denominators = [finite_number(v, "Denominator") for v in current_denominators]
            denominator = sum(denominators) if denominators and all(v > 0 for v in denominators) else None
        except ValueError:
            denominator = None
        same_coverage = previous_geographies == current_geographies
        delta = value - previous if previous is not None and same_coverage else None
        series.append({
            "date": date_key, "x": x, "days_to_election": _coordinate(updates[0], "days_to_election"),
            "value": value, "unit": updates[0].get("unit", "ballots"),
            "newly_reported": delta, "is_correction": delta is not None and delta < 0,
            "coverage_changed": previous is not None and not same_coverage,
            "geography_count": covered, "geography_ids": sorted(current),
            "carried_forward_count": sum(row["date"] != date_key for row in members),
            "oldest_component_date": min(row["date"] for row in members),
            "denominator": denominator,
            "rate": 100 * value / denominator if denominator else None,
            "sources": source_refs(members),
        })
        previous, previous_geographies = value, current_geographies
    return series


def _latest_geographies(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for row in sorted(rows, key=lambda r: (r["date"], version_rank(r))):
        latest[geography_key(row)] = row
    return latest


def _comparison(current: list[dict[str, Any]], baseline: list[dict[str, Any]], alignment: str) -> dict[str, Any]:
    left, right = _latest_geographies(current), _latest_geographies(baseline)
    shared = sorted(set(left) & set(right))
    matched, rejected = [], []
    for geography in shared:
        a, b = left[geography], right[geography]
        ma, mb = a.get("metadata") or {}, b.get("metadata") or {}
        compatible = (
            not ma.get("underlying_report_date_unverified")
            and not mb.get("underlying_report_date_unverified")
            and ma.get("mode_classification") == mb.get("mode_classification")
            and a.get("geography_type", "state") == b.get("geography_type", "state")
            and a.get("unit", "ballots") == b.get("unit", "ballots")
            and ma.get("metric_definition", a["metric"]) == mb.get("metric_definition", b["metric"])
            and (not ma.get("boundary_vintage") or not mb.get("boundary_vintage")
                 or ma["boundary_vintage"] == mb["boundary_vintage"]
                 or (ma.get("crosswalk_verified") and mb.get("crosswalk_verified")))
        )
        if not compatible:
            rejected.append(geography)
            continue
        va, vb = float(a["value"]), float(b["value"])
        current_dte = _coordinate(a, "days_to_election")
        baseline_dte = _coordinate(b, "days_to_election")
        current_coordinate, baseline_coordinate = _coordinate(a, alignment), _coordinate(b, alignment)
        matched.append({"geography_id": a["geography_id"], "canonical_id": a.get("canonical_id"), "geography_name": a.get("geography_name", geography),
                        "current": va, "baseline": vb, "change": va - vb,
                        "percentage_change": 100 * (va - vb) / vb if vb else None,
                        "current_date": a["date"], "baseline_date": b["date"],
                        "current_days_to_election": current_dte, "baseline_days_to_election": baseline_dte,
                        "aligned_date_match": (current_coordinate is not None and current_coordinate == baseline_coordinate),
                        "sources": source_refs([a, b])})
    current_total, baseline_total = sum(r["current"] for r in matched), sum(r["baseline"] for r in matched)
    asynchronous = (len({row["current_date"] for row in matched}) > 1
                    or len({row["baseline_date"] for row in matched}) > 1
                    or any(not row["aligned_date_match"] for row in matched))
    return {
        "status": "available" if matched else "no_compatible_geographies",
        "current": current_total if matched else None, "baseline": baseline_total if matched else None,
        "change": current_total - baseline_total if matched else None,
        "percentage_change": 100 * (current_total - baseline_total) / baseline_total if baseline_total else None,
        "ratio": current_total / baseline_total if baseline_total and not asynchronous else None,
        "matched_count": len(matched), "geographies": matched,
        "current_unmatched": sorted(left[key]["geography_id"] for key in set(left) - set(shared)),
        "baseline_unmatched": sorted(right[key]["geography_id"] for key in set(right) - set(shared)),
        "incompatible_geographies": rejected,
        "asynchronous": asynchronous,
        "warning": "Calendar alignment does not establish identical voting rules or reporting definitions.",
    }


def historical_analysis(
    observations: list[dict[str, Any]], *, state: str, cycle: int, baseline: int = 2022,
    metric: str = "ballots_accepted", mode: str = "all", as_of: str | None = None,
    time_basis: str = "reported", geography_ids: list[str] | None = None,
    category_dimension: str | None = None, category: str | None = None,
    alignment: str = "days_to_election",
) -> dict[str, Any]:
    if alignment not in SUPPORTED_ALIGNMENTS:
        raise ValueError(f"Alignment must be one of {', '.join(sorted(SUPPORTED_ALIGNMENTS))}")
    cutoff = instant(as_of, end_of_day=True) or datetime.now(UTC)
    kwargs = {"state": state, "metric": metric, "mode": mode, "time_basis": time_basis,
              "geography_ids": geography_ids, "category_dimension": category_dimension, "category": category}
    current_all, warnings = filter_observations(observations, cycle=cycle, as_of=cutoff.isoformat(), **kwargs)
    anchor_rows, _ = _grain(current_all, geography_ids)
    anchor_date = max((day(row["date"]) for row in anchor_rows), default=None)
    baseline_candidates = [r for r in observations if r.get("state") == state and int(r.get("cycle", 0)) == baseline
                           and r.get("metric") == metric and r.get("mode", "all") == mode]
    current_election = next((r.get("election_date") for r in current_all if r.get("election_date")), None)
    baseline_election = next((r.get("election_date") for r in baseline_candidates if r.get("election_date")), None)
    baseline_cutoff = None
    comparison_anchor = {
        "date": anchor_date.isoformat() if anchor_date else None,
        "requested_date": day(cutoff).isoformat(),
        "days_to_election": (anchor_date - day(current_election)).days if anchor_date and current_election else None,
        "age_days": (day(cutoff) - anchor_date).days if anchor_date else None,
        "basis": "latest_current_observation", "time_basis": time_basis,
    }
    if anchor_date and anchor_date < day(cutoff):
        warnings.append(f"Latest current observation is dated {anchor_date.isoformat()}; historical comparison is "
                        f"anchored to that observation, {(day(cutoff) - anchor_date).days} day(s) before the requested cutoff.")
    if current_election and baseline_election and anchor_date and alignment == "days_to_election":
        days_left = (day(current_election) - anchor_date).days
        baseline_cutoff = datetime.combine(day(baseline_election) - timedelta(days=days_left),
                                           cutoff.astimezone(RESEARCH_TIMEZONE).timetz())
    elif anchor_rows and alignment == "days_since_opening":
        opened = (anchor_rows[-1].get("metadata") or {}).get("voting_open_date")
        baseline_opened = next(((r.get("metadata") or {}).get("voting_open_date") for r in baseline_candidates
                                if (r.get("metadata") or {}).get("voting_open_date")), None)
        if opened and baseline_opened:
            elapsed = (anchor_date - day(opened)).days
            baseline_cutoff = datetime.combine(day(baseline_opened) + timedelta(days=elapsed),
                                               cutoff.astimezone(RESEARCH_TIMEZONE).timetz())
    elif anchor_rows and alignment == "voting_opportunities":
        target = _coordinate(anchor_rows[-1], alignment)
        allowed = [r for r in baseline_candidates if _coordinate(r, alignment) is not None
                   and target is not None and _coordinate(r, alignment) <= target]
        if allowed:
            baseline_cutoff = instant(max(r["date"] for r in allowed), end_of_day=True)

    # No baseline alignment is claimed when required election calendars are unavailable.
    baseline_all: list[dict[str, Any]] = []
    if baseline_cutoff is not None:
        # Reconstructed histories are grouped by historical event date within the
        # caller's pinned revision. Reported history requires contemporary evidence.
        knowledge_cutoff = baseline_cutoff if time_basis == "reported" else cutoff
        baseline_all, more = filter_observations(observations, cycle=baseline,
                                                as_of=knowledge_cutoff.isoformat(), **kwargs)
        baseline_all = [r for r in baseline_all if day(r["date"]) <= day(baseline_cutoff)]
        warnings.extend(more)
    else:
        warnings.append("Historical alignment unavailable until both cycles have documented calendar metadata.")

    current, current_grain = _grain(current_all, geography_ids)
    historic, historic_grain = _grain(baseline_all, geography_ids)
    if len({row.get("unit", "ballots") for row in current}) > 1:
        current = []
        warnings.append("Incompatible units prevent an aggregate of current observations.")
    if len({row.get("unit", "ballots") for row in historic}) > 1:
        historic = []
        warnings.append("Incompatible units prevent an aggregate of historical observations.")
    if current_grain != historic_grain and historic:
        warnings.append("Different reporting grains prevent a direct aggregate comparison.")
    series = _series(current, alignment)
    baseline_series = _series(historic, alignment)
    if any(point["x"] is None for point in series + baseline_series):
        warnings.append("Some observations lack metadata for the selected alignment.")

    # Prefer matched detailed geography when present in both cycles, even if statewide
    # totals are available. Detail never gets added to statewide totals.
    comparison_current, comparison_baseline = current, historic
    comparison_grain = current_grain
    if not geography_ids:
        for grain in ("county", "district", "municipality", "precinct"):
            a = [r for r in current_all if r.get("geography_type") == grain]
            b = [r for r in baseline_all if r.get("geography_type") == grain]
            if a and b:
                comparison_current, comparison_baseline, comparison_grain = a, b, grain
                break
    comparison = _comparison(comparison_current, comparison_baseline, alignment)
    comparison["geography_type"] = comparison_grain
    if comparison["asynchronous"]:
        warnings.append("Matched geographies have asynchronous or unequally aligned report dates; inspect each place's source date before interpreting pace.")
    if time_basis == "reconstructed":
        warnings.append("Reconstructed history does not establish what officials reported at the time; inspect whether source dates represent ballot events or dated report snapshots.")
    if any(point["carried_forward_count"] for point in series):
        warnings.append("Some geographic values are carried forward from their last actual observation.")
    return {
        "state": state, "cycle": cycle, "baseline": baseline, "metric": metric, "mode": mode,
        "as_of": cutoff.isoformat(), "baseline_as_of": baseline_cutoff.isoformat() if baseline_cutoff else None,
        "comparison_anchor": comparison_anchor,
        "time_basis": time_basis, "alignment": alignment, "geography_type": current_grain,
        "status": "available" if series else "no_observations",
        "current_series": series, "baseline_series": baseline_series,
        "latest": series[-1] if series else None, "matched_comparison": comparison,
        "geographies": list(_latest_geographies([r for r in current_all if r.get("geography_type") != "state"]).values()),
        "sources": source_refs(current + historic + comparison_current + comparison_baseline),
        "warnings": sorted(set(warnings)),
        "definition": "A single metric, voting mode, and demographic grain; state totals never sum with their components.",
    }
