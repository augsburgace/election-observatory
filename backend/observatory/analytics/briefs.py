"""Deterministic research briefs whose numerical claims carry evidence references."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .common import available_at, day, instant, source_refs
from .historical import historical_analysis
from .polling import poll_analysis


def state_brief(
    observations: list[dict[str, Any]], polls: list[dict[str, Any]], *, state: str,
    cycle: int = 2026, as_of: str | None = None, **filters: Any,
) -> dict[str, Any]:
    """Build ten useful research sections without external AI or invented findings."""
    cutoff = as_of or datetime.now(UTC).isoformat()
    history_keys = {"baseline", "metric", "mode", "time_basis", "geography_ids",
                    "category_dimension", "category", "alignment"}
    history = filters.get("_historical_analysis") or historical_analysis(observations, state=state, cycle=cycle, as_of=cutoff,
                                  **{key: value for key, value in filters.items() if key in history_keys})
    polling = filters.get("_polling_analysis") or poll_analysis(polls, state=state, cycle=cycle, as_of=cutoff)
    metric = history["metric"].replace("_", " ")
    latest = history["latest"]
    unit = latest.get("unit", "ballots") if latest else "ballots"
    sections: list[dict[str, Any]] = []

    def section(identifier: str, title: str, text: str, *, status: str = "available",
                facts: list[dict[str, Any]] | None = None) -> None:
        sections.append({"id": identifier, "title": title, "status": status,
                         "text": text, "facts": facts or [],
                         "sources": source_refs(ref for fact in (facts or []) for ref in fact.get("sources", []))})

    if latest:
        facts = [{"text": f"{latest['value']:,.0f} {metric} were reported through {latest['date']}.",
                  "value": latest["value"], "unit": unit, "date": latest["date"],
                  "sources": latest["sources"], "chart": "trajectory"}]
        if latest["newly_reported"] is not None:
            change = latest["newly_reported"]
            label = "A reported downward correction" if change < 0 else "Newly reported activity"
            facts.append({"text": f"{label} changes the selected total by {change:+,.0f} since the preceding observation.",
                          "value": change, "unit": unit, "sources": latest["sources"], "chart": "daily_changes"})
        elif latest["coverage_changed"]:
            facts.append({"text": "Reporting coverage changed, so a daily voting increase cannot be inferred from the total difference.",
                          "sources": latest["sources"], "chart": "coverage"})
        section("changes", "Latest reported changes", " ".join(f["text"] for f in facts), facts=facts)
    else:
        section("changes", "Latest reported changes",
                "No validated observations satisfy the selected metric, mode, evidence basis, and information cutoff. "
                "This is a coverage limitation; it does not establish zero voting activity.", status="unavailable")

    comparison = history["matched_comparison"]
    if comparison["status"] == "available" and not comparison.get("asynchronous"):
        delta = comparison["change"]
        text = (f"On matched reporting geographies, the selected total differs from {history['baseline']} by {delta:+,.0f} {unit}.")
        if comparison["percentage_change"] is not None:
            text += f" That is {comparison['percentage_change']:+.1f}% against the aligned historical count."
        refs = [ref for area in comparison["geographies"] for ref in area["sources"]]
        section("history", "Historical pace", text + " Calendar alignment alone does not establish identical voting rules.",
                facts=[{"text": text, "value": delta, "unit": unit, "sources": refs, "chart": "history"}])
    elif comparison.get("asynchronous"):
        refs = [ref for area in comparison["geographies"] for ref in area["sources"]]
        text = ("Historical pace is withheld because current and historical reports represent different aligned dates "
                "or asynchronous reporting areas. The available baseline is at a different reporting stage; a direct "
                "percentage change would be misleading. Inspect each place's report dates and publication evidence. "
                "A reconstructed view can inspect dated archived reports whose current files were revised later.")
        section("history", "Historical pace", text, status="non_comparable",
                facts=[{"text": "Matched source dates are not aligned; no pace estimate is published.",
                        "sources": refs, "chart": "history"}])
    else:
        section("history", "Historical pace", "A defensible matched historical comparison is unavailable for this selection. "
                "Do not substitute presidential-cycle totals or later reconstructed history without changing the labels.", status="unavailable")

    places = sorted(history["geographies"], key=lambda row: row["value"], reverse=True)[:5]
    if places:
        facts = [{"text": f"{row['geography_name']}: {row['value']:,.0f} {metric}, source date {row['date']}.",
                  "value": row["value"], "unit": row.get("unit", "ballots"), "geography_id": row["geography_id"],
                  "sources": source_refs([row]), "chart": "geography"} for row in places]
        section("geography", "Geographic contributors", "Largest available reporting areas: " + " ".join(f["text"] for f in facts), facts=facts)
    else:
        section("geography", "Geographic contributors", "No compatible reporting-area breakdown is available at this cutoff.", status="unavailable")

    deadline = instant(cutoff, end_of_day=True)
    composition = [row for row in observations if row.get("state") == state and row.get("cycle") == cycle
                   and row.get("metric") == history["metric"] and row.get("category_dimension")
                   and row.get("mode", "all") == history["mode"]
                   and row.get("time_basis", "reported") == history["time_basis"]
                   and (history["time_basis"] == "reconstructed"
                        or (available_at(row) is not None and available_at(row) <= deadline))
                   and day(row["date"]) <= day(deadline)]
    dimensions = sorted({row["category_dimension"] for row in composition})
    section("composition", "Supported composition analysis",
            ("Source categories are available for: " + ", ".join(dimensions) + ". Select a supported dimension to inspect its dated evidence. "
             "Separately published marginal categories cannot be combined into an inferred cross-tabulation.") if dimensions else
            "No supported demographic or registration breakdown is available for the selected metric. "
            "Registration and demographic composition would not establish candidate support.",
            status="available" if dimensions else "unavailable")

    if polling["eligible"]:
        facts = []
        for series in polling["series"]:
            for candidate, value in series["averages"].items():
                facts.append({"text": f"{candidate}: {value:.1f}% in the eligible descriptive average.", "value": value,
                              "unit": "percent", "sources": series["sources"], "chart": "polling"})
        text = " ".join(f["text"] for f in facts) if facts else (
            "Eligible original studies are available, but no comparable series meets the independent-producer threshold for an average.")
        section("polling", "Polling developments", text + " Undecideds remain in their reported categories; these are survey estimates.", facts=facts)
    else:
        section("polling", "Polling developments", "No eligible comparable likely-voter surveys are available within the selected recency window.", status="unavailable")
    section("scenarios", "Scenario implications", "Use the scenario studio to state turnout and candidate-support assumptions explicitly. "
            "Reported early ballots constrain turnout arithmetic but do not reveal candidate choices.", status="conditional")
    section("forecast", "Forecast implications", "Election probabilities require passing historical validation and a model that supports the state's counting rules. "
            "Early-vote registration composition is excluded from candidate forecasts.", status="conditional")
    section("sources", "Source coverage and revisions", "Inspect each fact's source snapshot and publication date. "
            "Negative reported changes are revisions; gaps and carried-forward observations remain visible. "
            + " ".join(history["warnings"]), facts=[])
    section("limits", "Conclusions the evidence does not support", "Voting pace is not a candidate vote count. "
            "An increase in reported ballots may reflect reporting batches, changed access, or changed voting behavior. "
            "County historical partisanship does not identify how early voters voted.")
    section("watch", "Developments to watch next", "Watch for additional dated official reports, changes in geographic coverage, "
            "revisions to earlier snapshots, newly released original polls, and documented changes to voting opportunities.")
    return {"state": state, "cycle": cycle, "as_of": history["as_of"],
            "title": f"{state} Senate research brief", "method": "deterministic sourced analysis",
            "summary": sections[0]["text"], "sections": sections,
            "sources": source_refs(history["sources"] + polling["sources"]),
            "warnings": sorted(set(history["warnings"] + polling["warnings"])),
            "query": {"state": state, "cycle": cycle, "as_of": cutoff,
                      **{key: value for key, value in filters.items() if key in history_keys}}}
