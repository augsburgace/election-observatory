"""Transparent descriptive polling, never an inference from early-vote registration."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean
from typing import Any

from .common import (
    available_at,
    evidence,
    finite_number,
    instant,
    is_generic_poll_response,
    source_refs,
    version_rank,
)


def _population(value: str) -> str:
    normalized = value.strip().lower().replace("_", " ")
    return {"lv": "LV", "likely voters": "LV", "likely voter": "LV",
            "rv": "RV", "registered voters": "RV", "adults": "A", "a": "A"}.get(normalized, value.upper())


def _estimates(poll: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in poll.get("estimates", []):
        # Connectors use candidate/label/name; party alone does not identify a person.
        label = item.get("candidate") or item.get("label") or item.get("name")
        raw = item.get("value", item.get("share", item.get("percentage", item.get("percent"))))
        if label is None or raw is None:
            continue
        value = finite_number(raw, "Poll estimate")
        if not 0 <= value <= 100:
            raise ValueError("Poll estimates must be percentages from 0 to 100")
        if str(label) in result:
            raise ValueError("Repeated response labels in a survey")
        result[str(label)] = value
    if sum(result.values()) > 102:  # Whole-number releases commonly have rounding discrepancies.
        raise ValueError("Survey response shares exceed a plausible rounded total")
    return result


def _question_key(poll: dict[str, Any]) -> str:
    metadata = poll.get("metadata") or {}
    # Explicit connector keys encode exact ballot/candidate configuration.
    if metadata.get("comparison_key"):
        return str(metadata["comparison_key"])
    respondents = []
    for item in poll.get("estimates", []):
        label = str(item.get("candidate") or item.get("label") or item.get("name") or "")
        if is_generic_poll_response(label):
            continue
        if label:
            respondents.append(label.casefold().strip())
    return "|".join(sorted(respondents))


def _summary(polls: list[dict[str, Any]], *, minimum: int = 3) -> dict[str, Any]:
    sets = [_estimates(poll) for poll in polls]
    common = set.intersection(*(set(values) for values in sets)) if sets else set()
    all_labels = set().union(*(set(values) for values in sets)) if sets else set()
    averages = {label: round(mean(values[label] for values in sets), 3) for label in sorted(common)}
    ranges = {label: {"min": min(values[label] for values in sets),
                      "max": max(values[label] for values in sets)} for label in sorted(common)}
    publishable = len(polls) >= minimum
    return {
        "status": "available" if publishable else "insufficient_polls",
        "producer_count": len(polls), "minimum_producers": minimum,
        "averages": averages if publishable else {}, "range": ranges if publishable else {},
        "unmatched_response_labels": sorted(all_labels - common),
        "method": "Unweighted mean of latest eligible survey per independent producer",
        "warning": "A descriptive average is not a forecast or a pooled margin of error.",
    }


def poll_analysis(
    polls: list[dict[str, Any]], *, as_of: str, state: str | None = None,
    cycle: int | None = None, population: str = "LV", question_type: str = "vote_choice",
    ballot_type: str = "full_ballot", window_days: int = 21, include_partisan: bool = True,
    comparison_key: str | None = None,
) -> dict[str, Any]:
    """Eligibility, duplicate suppression, averages, and sensitivity in one reproducible response.

    Publication/first-observation cutoffs prevent historical leakage. A connector may
    use independent_producer_id and shared_sample_id to establish collaborations.
    Competing question configurations are returned as separate series.
    """
    if not 1 <= window_days <= 180:
        raise ValueError("Polling window must be between 1 and 180 days")
    cutoff = instant(as_of, end_of_day=True)
    assert cutoff is not None
    lower = cutoff - timedelta(days=window_days)
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for poll in polls:
        reason = None
        if state and poll.get("state") != state:
            continue
        if cycle is not None and poll.get("cycle") != cycle:
            continue
        try:
            start = instant(poll.get("field_start"))
            end = instant(poll.get("field_end"), end_of_day=True)
            published = available_at(poll)
            if start is None or end is None or start > end:
                reason = "Invalid or missing fieldwork dates"
            elif published is None:
                reason = "No established publication or first-observation time"
            elif published > cutoff or end > cutoff:
                reason = "Not available before the cutoff"
            elif published < start:
                reason = "Publication precedes fieldwork"
            elif start + (end - start) / 2 < lower:
                reason = "Fieldwork midpoint outside the recency window"
            elif _population(str(poll.get("population", ""))) != _population(population):
                reason = "Different sample population"
            elif poll.get("question_type", "vote_choice") != question_type:
                reason = "Different question type"
            elif poll.get("ballot_type", "full_ballot") != ballot_type:
                reason = "Different ballot configuration"
            elif not include_partisan and poll.get("partisan_sponsor"):
                reason = "Partisan sponsorship excluded by selection"
            elif not poll.get("producer"):
                reason = "Missing actual producer"
            elif not _estimates(poll):
                reason = "No usable response estimates"
        except (ValueError, TypeError):
            reason = "Invalid survey dates or response estimates"
        if reason:
            excluded.append({**evidence(poll), "study_id": poll.get("study_id"),
                             "producer": poll.get("producer"), "reason": reason})
        else:
            eligible.append(poll)

    # Process newest studies first. A shared sample can contribute at most once.
    eligible.sort(key=lambda p: (p.get("field_end", ""), p.get("published_at", ""), version_rank(p)), reverse=True)
    seen_studies: set[tuple[str, str]] = set()
    seen_producers: set[tuple[str, str]] = set()
    seen_samples: set[tuple[str, str]] = set()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for poll in eligible:
        metadata = poll.get("metadata") or {}
        key = _question_key(poll)
        producer = str(metadata.get("independent_producer_id") or poll["producer"]).casefold().strip()
        sample = str(metadata.get("shared_sample_id") or poll.get("study_id") or poll.get("id"))
        study = str(poll.get("study_id") or poll.get("id"))
        reason = None
        if comparison_key is not None and key != comparison_key:
            reason = "Different candidate/question comparison series"
        elif (key, study) in seen_studies or (key, sample) in seen_samples:
            reason = "Duplicate or shared survey sample"
        elif (key, producer) in seen_producers:
            reason = "A newer eligible survey from this independent producer is included"
        if reason:
            excluded.append({**evidence(poll), "study_id": poll.get("study_id"),
                             "producer": poll.get("producer"), "reason": reason})
            continue
        seen_studies.add((key, study))
        seen_samples.add((key, sample))
        seen_producers.add((key, producer))
        groups[key].append(poll)

    series = []
    used: list[dict[str, Any]] = []
    for key, selected in sorted(groups.items()):
        summary = _summary(selected)
        used.extend(selected)
        series.append({"comparison_key": key, **summary,
                       "polls": [{**poll, "evidence": evidence(poll)} for poll in selected],
                       "leave_one_producer_out": [
                           {"excluded_producer": p["producer"], **_summary([q for q in selected if q is not p])}
                           for p in selected],
                       "without_partisan_sponsors": _summary([p for p in selected if not p.get("partisan_sponsor")]),
                       "sources": source_refs(selected)})
    single = series[0] if len(series) == 1 else {}
    return {
        "as_of": cutoff.isoformat(), "population": _population(population), "window_days": window_days,
        "question_type": question_type, "ballot_type": ballot_type, "include_partisan": include_partisan,
        "status": single.get("status", "multiple_series" if series else "no_eligible_polls"),
        "producer_count": single.get("producer_count", len(used)),
        "averages": single.get("averages", {}), "series": series,
        "eligible": [{**poll, "evidence": evidence(poll)} for poll in used], "excluded": excluded,
        "sources": source_refs(used),
        "warnings": ["Survey response shares are preserved; undecideds are not reallocated.",
                     "Candidate configurations and survey populations are never pooled together."],
    }
