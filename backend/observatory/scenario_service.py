"""Adapt turnout/method assumptions to the shared, constrained scenario engine."""
from __future__ import annotations

from .analytics import run_scenario
from .analytics.common import finite_number
from .domain import ResearchQuery
from .registry import state_info
from .service import workspace


def calculate_scenario(database, body: dict) -> dict:
    query_keys = set(ResearchQuery.model_fields)
    query_payload = {key: value for key, value in body.items() if key in query_keys}
    query_payload.update(body.get("query") or {})
    query_payload["as_of"] = query_payload.get("as_of") or None
    query = ResearchQuery.model_validate(query_payload)
    try:
        state_info(query.state)
    except StopIteration as exc:
        raise ValueError("Unknown scenario state") from exc
    evidence = workspace(database, query)
    selected_total = evidence["summary"]["total"]
    valid_ballot_measure = query.metric in {"ballots_cast", "ballots_accepted"} and evidence["summary"]["unit"] == "ballots"
    measured = selected_total if valid_ballot_measure else None
    requested = body.get("observed_ballots", body.get("observed_total"))
    if measured is not None and requested is not None and abs(finite_number(requested, "observed_ballots") - measured) > 1e-6:
        raise ValueError("The supplied observed-ballot count conflicts with the pinned evidence")
    observed = float(measured if measured is not None else requested or 0)
    if observed < 0:
        raise ValueError("Observed/hypothetical starting ballots cannot be negative")
    if "total_turnout" in body:
        result = run_scenario(body, observed_total=observed)
        result.update({"state": query.state, "revision": evidence["revision"], "query": evidence["query"],
                       "observed_ballots": observed, "measured_observed_total": measured,
                       "evidence_status": "reported" if measured is not None else "entirely_hypothetical"})
        return result

    total = finite_number(body.get("final_turnout"), "final_turnout")
    shares = {key: finite_number(body.get(key, default), key) for key, default in (
        ("early_share", .5), ("early_support", .5), ("election_day_support", .5),
        ("undecided_share", 0), ("undecided_allocation", .5))}
    if not all(0 <= value <= 1 for value in shares.values()):
        raise ValueError("Scenario shares must be proportions between zero and one")

    def run(turnout: float, assumptions: dict) -> dict:
        early_count = turnout * assumptions["early_share"]
        if early_count + 1e-6 < observed:
            raise ValueError("Assumed final early ballots cannot be below the reported/hypothetical starting count")
        components = [{"id": "remaining_early", "ballots": max(0, early_count - observed), "candidate_a_share": assumptions["early_support"] * 100},
                      {"id": "election_day", "ballots": turnout * (1 - assumptions["early_share"]), "candidate_a_share": assumptions["election_day_support"] * 100}]
        return run_scenario({"total_turnout": turnout, "observed_candidate_share": assumptions["early_support"] * 100,
                             "undecided_share": assumptions["undecided_share"] * 100,
                             "undecided_allocation": assumptions["undecided_allocation"] * 100,
                             "remaining_components": components}, observed_total=observed)

    result = run(total, shares)
    grid = []
    for factor in (.8, .9, 1, 1.1, 1.2):
        turnout = total * factor
        if turnout * shares["early_share"] < observed:
            continue
        for offset in (-.1, -.05, 0, .05, .1):
            support = min(1, max(0, shares["election_day_support"] + offset))
            cell = run(turnout, {**shares, "election_day_support": support})
            grid.append({"turnout": turnout, "election_day_support": support * 100,
                         "margin": cell["margin"], "candidate_a_share": cell["candidate_a_share"]})
    sensitivity = []
    for key, amount in (("early_share", .1), ("early_support", .05), ("election_day_support", .05), ("undecided_allocation", .1)):
        lo, hi = max(0, shares[key] - amount), min(1, shares[key] + amount)
        if key == "early_share":
            lo = max(lo, observed / total if total else 0)
        low, high = run(total, {**shares, key: lo}), run(total, {**shares, key: hi})
        sensitivity.append({"parameter": key, "low": lo, "high": hi, "low_margin": low["margin"], "high_margin": high["margin"]})
    result.update({"state": query.state, "revision": evidence["revision"], "query": evidence["query"],
                   "observed_ballots": observed, "measured_observed_total": measured,
                   "selected_metric_total": selected_total,
                   "early_ballots": total * shares["early_share"], "election_day_ballots": total * (1 - shares["early_share"]),
                   "candidate_a_votes": result["projected_votes"]["candidate_a"], "candidate_b_votes": result["projected_votes"]["candidate_b"],
                   "components": [{"name": "Early participation", "ballots": total * shares["early_share"], "assumed_A_support_pct": shares["early_support"] * 100},
                                  {"name": "Election Day participation", "ballots": total * (1 - shares["early_share"]), "assumed_A_support_pct": shares["election_day_support"] * 100}],
                   "sensitivity": sensitivity, "grid": grid,
                   "evidence_status": "reported" if measured is not None else "entirely_hypothetical"})
    if not valid_ballot_measure:
        result["warnings"].append("The selected metric is not an observed cast/accepted ballot count and cannot constrain turnout. Any starting count supplied here is hypothetical.")
    return result
