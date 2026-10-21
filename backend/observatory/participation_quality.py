"""Interpretation comes from the exact shared observation query, not a forecast."""
from datetime import date

from sqlalchemy import select

from .db import ObservationRecord
from .domain import ResearchQuery
from .registry import METRICS
from .service import workspace


def participation_quality(database, query: ResearchQuery):
    view = workspace(database, query)
    current = sorted((p for p in view["series"] if p["cycle"] == query.cycle), key=lambda p: p["date"])
    latest = current[-1] if current else None
    ids = sorted({int(r["id"]) for r in (latest or {}).get("sources", []) if r.get("id")})
    with database.session() as session:
        records = list(session.scalars(select(ObservationRecord).where(ObservationRecord.id.in_(ids)))) if ids else []
    inventory = {s["id"]: s for s in view["sources"]}
    sources = []
    for source_id in sorted({r.source_id for r in records}):
        group = [r for r in records if r.source_id == source_id]
        source = inventory.get(source_id, {})
        metadata = [r.payload.get("metadata", {}) for r in group]
        flags = sorted({str(m[k]) for m in metadata for k in ("definition_correction", "mode_classification", "status_classification",
            "upstream_method", "source_notes", "source_usage_note", "coverage_note") if m.get(k) not in (None, "", "NA")})
        if any(m.get("underlying_report_date_unverified") for m in metadata):
            flags.append("The producer's upload date is known; the underlying authority report date is not established.")
        sources.append({"id": source_id, "name": source.get("name", source_id), "tier": source.get("tier", 1),
            "url": source.get("url"), "authority": "Attributed research bridge" if any(m.get("academic_fallback") for m in metadata) else "Original election authority",
            "upstream_sources": sorted({str(m["upstream_source"]) for m in metadata if m.get("upstream_source")}),
            "native_definitions": sorted({str(m["native_definition"]) for m in metadata if m.get("native_definition")}),
            "flags": flags, "observation_ids": [r.id for r in group],
            "snapshot_ids": sorted({r.snapshot_id for r in group}), "last_checked": source.get("last_checked"),
            "collection_status": source.get("status"), "collection_error": source.get("error")})
    metric = next((m for m in METRICS if m["id"] == query.metric), {"id": query.metric, "label": query.metric, "unit": "ballots"})
    reported_date = view["summary"]["latest_date"]
    cutoff_date = date.fromisoformat(view["query"]["as_of"][:10])
    age = max(0, (cutoff_date - date.fromisoformat(reported_date)).days) if reported_date else None
    details = [r for r in view["geographies"] if r.get("type") != "state"]
    dates = sorted({r.get("date") for r in details if r.get("date")})
    detail_sum = sum(r["value"] for r in details) if details else None
    total = view["summary"]["total"]
    compare = view.get("comparison") or {}
    comparison_available = compare.get("ratio") is not None and not compare.get("asynchronous")
    reason = compare.get("reason") or ("Compatible aligned observations are available." if comparison_available else
        "A compatible same-stage historical observation is unavailable. Final early voting and final turnout are separate references.")
    if any(r.payload.get("metadata", {}).get("underlying_report_date_unverified") for r in records):
        comparison_available = False
        reason = "The underlying report date is not established; a precise same-stage historical pace comparison is withheld."
    previous = current[-2] if len(current) > 1 else None
    return {"revision": view["revision"], "query": view["query"], "state": query.state,
        "metric": metric, "headline": {"value": total, "date": reported_date, "days_old_at_cutoff": age,
            "newly_reported": view["summary"]["newly_reported"], "previous_report_date": previous["date"] if previous else None,
            "change_is_correction": bool(latest and latest.get("is_correction")),
            "change_semantics": "Change between source reports; it does not establish the day on which voting occurred."},
        "coverage": {"reporting_areas": len(details), "types": sorted({r["type"] for r in details}),
            "oldest_component_date": (latest or {}).get("oldest_component_date"),
            "carried_forward_count": (latest or {}).get("carried_forward_count", 0),
            "geographic_date_range": dates and [dates[0], dates[-1]] or [],
            "geographic_sum": detail_sum,
            "difference_from_selected_total": detail_sum - total if detail_sum is not None and total is not None and not query.geography_ids else None,
            "join": view["coverage"].get("geography_join", {})},
        "comparison": {"available": comparison_available, "reason": reason, "baseline": query.baseline,
            "ratio": compare.get("ratio") if comparison_available else None, "alignment": query.alignment,
            "coverage": compare}, "sources": sources,
        "daily_reports": [{k: p.get(k) for k in ("date", "value", "newly_reported", "is_correction", "coverage_changed", "carried_forward_count", "oldest_component_date")} for p in current],
        "read_this_first": [metric.get("description", "Read the original source definition before comparing."),
            "Newly reported ballots are reporting changes, not necessarily ballots voted that day.",
            "Party registration and demographic composition do not identify candidate votes.",
            "A pace difference is participation evidence; it is not a candidate lead or an election prediction."],
        "warnings": view["warnings"],
        "status": "available" if total is not None else "unavailable",
        "recommended_selection": view["coverage"].get("recommended_selection")}
