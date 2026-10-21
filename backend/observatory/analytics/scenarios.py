"""Explicit, constrained what-if arithmetic. These outputs are never forecasts."""
from __future__ import annotations

from typing import Any

from .common import finite_number


def _percentage(params: dict[str, Any], key: str, default: float) -> float:
    value = finite_number(params.get(key, default), key)
    if not 0 <= value <= 100:
        raise ValueError(f"{key} must be between 0 and 100 percent")
    return value


def _compute(params: dict[str, Any], observed: float) -> dict[str, float]:
    total = finite_number(params.get("total_turnout"), "total_turnout")
    if total <= 0:
        raise ValueError("total_turnout must be positive")
    if total < observed:
        raise ValueError("Assumed final turnout cannot be below already observed ballots")
    remaining = total - observed
    a_observed = _percentage(params, "observed_candidate_share", 50)
    other_observed = _percentage(params, "observed_other_share", 0)
    if a_observed + other_observed > 100:
        raise ValueError("Observed-ballot support assumptions cannot exceed 100 percent")
    undecided = _percentage(params, "undecided_share", 0)
    allocate = _percentage(params, "undecided_allocation", 50)
    a_remaining = _percentage(params, "remaining_candidate_share", 50)
    other_remaining = _percentage(params, "remaining_other_share", 0)
    if a_remaining + other_remaining > 100:
        raise ValueError("Remaining decided-ballot support assumptions cannot exceed 100 percent")
    remaining_a = remaining * ((1 - undecided / 100) * a_remaining / 100 + undecided / 100 * allocate / 100)
    remaining_other = remaining * (1 - undecided / 100) * other_remaining / 100
    components = params.get("remaining_components")
    if components:
        if not isinstance(components, list):
            raise ValueError("remaining_components must be a list")
        component_total = 0.0
        remaining_a, remaining_other = 0.0, 0.0
        identifiers = set()
        for component in components:
            identifier = str(component.get("id", component.get("name", "")))
            if not identifier or identifier in identifiers:
                raise ValueError("Scenario components require distinct named identifiers")
            identifiers.add(identifier)
            ballots = finite_number(component.get("ballots"), "Component ballots")
            if ballots < 0:
                raise ValueError("Component ballot counts cannot be negative")
            component_total += ballots
            a = _percentage(component, "candidate_a_share", a_remaining)
            other = _percentage(component, "other_share", other_remaining)
            u = _percentage(component, "undecided_share", undecided)
            alloc = _percentage(component, "undecided_allocation", allocate)
            if a + other > 100:
                raise ValueError("Component decided-ballot shares cannot exceed 100 percent")
            remaining_a += ballots * ((1 - u / 100) * a / 100 + u / 100 * alloc / 100)
            remaining_other += ballots * (1 - u / 100) * other / 100
        if abs(component_total - remaining) > max(1e-6, remaining * 1e-9):
            raise ValueError("Component ballot counts must sum exactly to the assumed remaining ballots")
    a_votes = observed * a_observed / 100 + remaining_a
    other_votes = observed * other_observed / 100 + remaining_other
    b_votes = total - a_votes - other_votes
    return {
        "total_turnout": total, "remaining_ballots": remaining,
        "candidate_a": a_votes, "candidate_b": b_votes, "other": other_votes,
        "candidate_a_share": 100 * a_votes / total, "candidate_b_share": 100 * b_votes / total,
        "other_share": 100 * other_votes / total, "margin": 100 * (a_votes - b_votes) / total,
    }


def run_scenario(params: dict[str, Any], *, observed_total: float = 0) -> dict[str, Any]:
    """Parameters use percentages (50 means 50%). A margin is A minus B in points.

    `observed_candidate_share` is an explicit assumption, never supplied from
    registration totals. Components may partition either remaining modes OR
    remaining geographies, not both overlapping partitions.
    """
    observed = finite_number(observed_total, "observed_total")
    if observed < 0:
        raise ValueError("observed_total cannot be negative")
    if "observed_total" in params:
        requested = finite_number(params["observed_total"], "observed_total")
        if observed != 0 and requested != observed:
            raise ValueError("Scenario observed total differs from selected evidence")
        observed = requested
    if observed > 0 and "observed_candidate_share" not in params:
        raise ValueError("Supply an explicit candidate-support assumption for already observed ballots")
    normalized = {
        "total_turnout": finite_number(params.get("total_turnout"), "total_turnout"),
        "observed_total": observed,
        "observed_candidate_share": _percentage(params, "observed_candidate_share", 50),
        "observed_other_share": _percentage(params, "observed_other_share", 0),
        "remaining_candidate_share": _percentage(params, "remaining_candidate_share", 50),
        "remaining_other_share": _percentage(params, "remaining_other_share", 0),
        "undecided_share": _percentage(params, "undecided_share", 0),
        "undecided_allocation": _percentage(params, "undecided_allocation", 50),
    }
    if params.get("remaining_components"):
        normalized["remaining_components"] = params["remaining_components"]
    result = _compute(normalized, observed)
    sensitivity = []
    grid = []
    if not normalized.get("remaining_components"):
        for parameter, amount, lower, upper in (
            ("total_turnout", normalized["total_turnout"] * 0.1, max(observed, 1), float("inf")),
            ("remaining_candidate_share", 5, 0, 100 - normalized["remaining_other_share"]),
            ("observed_candidate_share", 5, 0, 100 - normalized["observed_other_share"]),
            ("undecided_allocation", 10, 0, 100),
        ):
            base = normalized[parameter]
            lo, hi = max(lower, base - amount), min(upper, base + amount)
            low = _compute({**normalized, parameter: lo}, observed)
            high = _compute({**normalized, parameter: hi}, observed)
            sensitivity.append({"parameter": parameter, "low": lo, "high": hi,
                                "low_margin": low["margin"], "high_margin": high["margin"]})
        for turnout_factor in (0.8, 0.9, 1.0, 1.1, 1.2):
            turnout = max(observed, normalized["total_turnout"] * turnout_factor, 1)
            for offset in (-10, -5, 0, 5, 10):
                support = min(100 - normalized["remaining_other_share"],
                              max(0, normalized["remaining_candidate_share"] + offset))
                cell = _compute({**normalized, "total_turnout": turnout, "remaining_candidate_share": support}, observed)
                grid.append({"turnout": turnout, "remaining_candidate_share": support, "margin": cell["margin"],
                             "candidate_a_share": cell["candidate_a_share"]})
    warnings = [
        "This is conditional arithmetic, not a forecast or observed candidate vote count.",
        "Support assumptions for reported early ballots are unobserved unless backed by actual candidate results.",
        "Undecided allocation assumes all remaining undecideds choose candidate A or B; other support is explicit.",
    ]
    if normalized.get("remaining_components"):
        warnings.append("Component counts must form one disjoint partition; automatic global sensitivity is disabled.")
    return {
        "status": "scenario", "label": str(params.get("name", "Turnout and support scenario")),
        "parameters": normalized, "observed_total": observed, "remaining_ballots": result["remaining_ballots"],
        "projected_votes": {"candidate_a": result["candidate_a"], "candidate_b": result["candidate_b"], "other": result["other"]},
        "total_turnout": result["total_turnout"], "candidate_a_share": result["candidate_a_share"],
        "candidate_b_share": result["candidate_b_share"], "other_share": result["other_share"],
        "margin": result["margin"], "sensitivity": sensitivity, "grid": grid,
        "assumptions": {key: value for key, value in normalized.items() if key != "observed_total"},
        "warnings": warnings, "sources": [],
    }


def senate_scenarios(
    races: list[dict[str, Any]], *, holdovers: dict[str, int],
    simulations: int = 20000, seed: int = 2026,
) -> dict[str, Any]:
    """Deterministic seat bounds/scenarios, never probabilities from incomplete inputs.

    Each contest is a distinct `race_id` with optional explicit `winner_caucus`.
    Unknown races produce ranges. Every seat must be represented exactly once.
    Probabilistic joint modeling is implemented separately in forecast_senate.
    """
    del simulations  # Kept in the public signature for the shared chamber interface.
    counts = {"D": 0, "R": 0, "other": 0}
    for party, raw in holdovers.items():
        count = finite_number(raw, f"{party} holdovers")
        if count < 0 or count != int(count):
            raise ValueError("Holdover counts must be nonnegative integers")
        counts[party if party in {"D", "R"} else "other"] += int(count)
    seen = set()
    unknown = []
    for race in races:
        race_id = race.get("race_id") or race.get("id")
        if not race_id or race_id in seen:
            raise ValueError("Every contest must have a distinct race_id, including special elections")
        seen.add(race_id)
        winner = race.get("winner_caucus")
        if winner in {"D", "R", "other"}:
            counts[winner] += 1
        else:
            unknown.append(race_id)
    represented = sum(counts.values()) + len(unknown)
    if represented > 100:
        raise ValueError("Holdovers and contests together cannot exceed 100 Senate seats")
    missing = 100 - represented
    unassigned = len(unknown) + missing
    return {
        "status": "scenario" if unassigned == 0 else "incomplete_scenario",
        "probabilities": None, "seed": seed, "assigned_seats": counts,
        "seat_ranges": {party: {"min": count, "max": count + unassigned} for party, count in counts.items()},
        "unknown_races": unknown, "unrepresented_seats": missing, "represented_seats": represented,
        "control_threshold": 51,
        "warnings": ["Seat ranges are logical bounds, not probabilities.",
                     "A 50–50 chamber requires an explicit vice-presidential tie-breaking assumption.",
                     "Independent candidates require an explicit caucus assignment."],
    }
