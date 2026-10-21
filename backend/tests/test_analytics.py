"""Synthetic fixtures test evidence invariants; they are never application data."""
from __future__ import annotations

from copy import deepcopy

import pytest
from observatory.analytics import (
    historical_analysis,
    poll_analysis,
    run_scenario,
    senate_scenarios,
    state_brief,
)


def observation(value=100, **changes):
    row = {"id": "o1", "source_id": "official", "snapshot_id": "sha-1", "state": "NC",
           "cycle": 2026, "date": "2026-10-20", "election_date": "2026-11-03",
           "metric": "ballots_cast", "value": value, "geography_id": "NC",
           "geography_name": "North Carolina", "geography_type": "state", "mode": "all",
           "time_basis": "reported", "published_at": "2026-10-20T14:00:00Z",
           "observed_at": "2026-10-20T15:00:00Z", "metadata": {}}
    return {**row, **changes}


def poll(producer, a=46, **changes):
    return {"id": producer, "study_id": f"{producer}-oct", "source_id": f"{producer}-release",
            "snapshot_id": "original-pdf", "state": "NC", "cycle": 2026,
            "producer": producer, "publisher": producer, "population": "LV",
            "field_start": "2026-10-10", "field_end": "2026-10-12", "published_at": "2026-10-14",
            "question_type": "vote_choice", "ballot_type": "full_ballot", "partisan_sponsor": False,
            "estimates": [{"candidate": "Candidate A", "value": a}, {"candidate": "Candidate B", "value": 44},
                          {"candidate": "Undecided", "value": 56-a}], "metadata": {}, **changes}


def test_never_sum_overlapping_states_counties_modes_or_categories():
    rows = [observation(), observation(40, geography_id="NC:A", geography_type="county"),
            observation(60, geography_id="NC:B", geography_type="county"),
            observation(90, mode="mail"), observation(80, category_dimension="age", category="65+")]
    result = historical_analysis(rows, state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert result["latest"]["value"] == 100
    assert result["geography_type"] == "state"


def test_new_york_day_includes_current_evening_retrieval():
    row = observation(published_at=None, observed_at="2026-10-21T02:00:00Z")
    result = historical_analysis([row], state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert result["latest"]["value"] == 100
    assert result["latest"]["days_to_election"] == -14


def test_reported_history_excludes_later_revisions_and_unknown_publication():
    historic = observation(50, cycle=2022, date="2022-10-25", election_date="2022-11-08",
                           published_at="2022-10-25", observed_at="2026-10-20")
    late = observation(80, cycle=2022, date="2022-10-25", election_date="2022-11-08",
                       published_at="2022-10-25", observed_at="2026-10-21", metadata={"is_revision": True})
    unknown = observation(900, cycle=2022, date="2022-10-24", election_date="2022-11-08",
                          published_at=None, observed_at="2026-10-20")
    result = historical_analysis([observation(), historic, late, unknown], state="NC", cycle=2026,
                                 metric="ballots_cast", as_of="2026-10-20")
    assert result["baseline_series"][-1]["value"] == 50
    assert result["matched_comparison"]["change"] == 50
    assert result["baseline_as_of"].startswith("2022-10-25")


def test_matched_geographies_do_not_compare_different_coverage():
    rows = [observation(10, geography_id="NC:A", geography_type="county"),
            observation(100, geography_id="NC:B", geography_type="county"),
            observation(5, geography_id="NC:A", geography_type="county", cycle=2022,
                        date="2022-10-25", election_date="2022-11-08", published_at="2022-10-25"),
            observation(999, geography_id="NC:C", geography_type="county", cycle=2022,
                        date="2022-10-25", election_date="2022-11-08", published_at="2022-10-25")]
    result = historical_analysis(rows, state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    compared = result["matched_comparison"]
    assert compared["matched_count"] == 1
    assert compared["current"] == 10 and compared["baseline"] == 5
    assert compared["current_unmatched"] == ["NC:B"]
    assert compared["baseline_unmatched"] == ["NC:C"]


def test_negative_correction_is_visible_and_coverage_change_is_not_daily_voting():
    rows = [observation(100, date="2026-10-19", published_at="2026-10-19"), observation(98)]
    result = historical_analysis(rows, state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert result["latest"]["newly_reported"] == -2
    assert result["latest"]["is_correction"]
    rows = [observation(10, geography_id="NC:A", geography_type="county", date="2026-10-19"),
            observation(20, geography_id="NC:B", geography_type="county")]
    result = historical_analysis(rows, state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert result["latest"]["newly_reported"] is None
    assert result["latest"]["coverage_changed"]
    assert result["latest"]["carried_forward_count"] == 1


def test_no_undocumented_voting_opportunity_alignment():
    result = historical_analysis([observation()], state="NC", cycle=2026, metric="ballots_cast",
                                 as_of="2026-10-20", alignment="voting_opportunities")
    assert result["baseline_series"] == []
    assert result["current_series"][0]["x"] is None
    assert any("metadata" in warning for warning in result["warnings"])


def test_reconstructed_history_is_not_claimed_as_reported_history():
    historic = observation(50, cycle=2022, date="2022-10-25", election_date="2022-11-08",
                           time_basis="reconstructed", published_at=None, observed_at="2026-10-20")
    current = observation(time_basis="reconstructed")
    result = historical_analysis([current, historic], state="NC", cycle=2026, metric="ballots_cast",
                                 as_of="2026-10-20", time_basis="reconstructed")
    assert result["baseline_series"][-1]["value"] == 50
    assert any("does not establish" in warning for warning in result["warnings"])


def test_reconstructed_event_cutoff_can_use_later_evidence_in_pinned_revision():
    later_evidence = observation(50, date="2026-10-10", published_at="2026-10-20",
                                 observed_at="2026-10-20", time_basis="reconstructed")
    future_event = observation(75, date="2026-10-11", published_at="2026-10-20",
                               observed_at="2026-10-20", time_basis="reconstructed")
    result = historical_analysis([later_evidence, future_event], state="NC", cycle=2026,
                                 metric="ballots_cast", as_of="2026-10-10", time_basis="reconstructed")
    assert result["latest"]["value"] == 50
    assert result["latest"]["date"] == "2026-10-10"
    reported = {**later_evidence, "time_basis": "reported"}
    strict = historical_analysis([reported], state="NC", cycle=2026,
                                 metric="ballots_cast", as_of="2026-10-10", time_basis="reported")
    assert strict["latest"] is None


def test_stale_current_report_anchors_historical_comparison_to_actual_report_day():
    current = observation(100, date="2026-10-19")
    aligned = observation(50, cycle=2022, date="2022-10-24", election_date="2022-11-08",
                          published_at="2022-10-24")
    extra_day = observation(90, cycle=2022, date="2022-10-25", election_date="2022-11-08",
                            published_at="2022-10-25")
    result = historical_analysis([current, aligned, extra_day], state="NC", cycle=2026,
                                 metric="ballots_cast", as_of="2026-10-20")
    assert result["comparison_anchor"]["date"] == "2026-10-19"
    assert result["comparison_anchor"]["age_days"] == 1
    assert result["baseline_as_of"].startswith("2022-10-24")
    assert result["matched_comparison"]["baseline"] == 50
    assert result["matched_comparison"]["ratio"] == 2
    assert any("anchored" in warning for warning in result["warnings"])


def test_asynchronous_geographic_reports_are_explicit_in_matched_comparison():
    rows = [observation(50, geography_id="NC:A", geography_type="county", date="2026-10-19"),
            observation(50, geography_id="NC:B", geography_type="county"),
            observation(20, geography_id="NC:A", geography_type="county", cycle=2022,
                        date="2022-10-25", election_date="2022-11-08", published_at="2022-10-25"),
            observation(20, geography_id="NC:B", geography_type="county", cycle=2022,
                        date="2022-10-25", election_date="2022-11-08", published_at="2022-10-25")]
    result = historical_analysis(rows, state="NC", cycle=2026,
                                 metric="ballots_cast", as_of="2026-10-20")
    assert result["matched_comparison"]["asynchronous"]
    first = result["matched_comparison"]["geographies"][0]
    assert not first["aligned_date_match"]
    assert any("asynchronous" in warning for warning in result["warnings"])


def test_brief_withholds_historical_pace_when_contemporary_baseline_is_at_another_stage():
    current = observation(100)
    earlier = observation(5, cycle=2022, date="2022-10-20", election_date="2022-11-08",
                          published_at="2022-10-20")
    later_revised = observation(80, cycle=2022, date="2022-10-25", election_date="2022-11-08",
                                published_at="2022-11-05")
    result = state_brief([current, earlier, later_revised], [], state="NC", metric="ballots_cast",
                         as_of="2026-10-20")
    historical = next(section for section in result["sections"] if section["id"] == "history")
    assert historical["status"] == "non_comparable"
    assert "withheld" in historical["text"]
    assert "%" not in historical["text"]
    assert historical["sources"]


def test_poll_average_uses_latest_independent_producer_and_release_cutoff():
    surveys = [poll("One", 46), poll("Two", 48), poll("Three", 50),
               poll("One", 52, study_id="one-new", field_start="2026-10-15", field_end="2026-10-16",
                    published_at="2026-10-18"),
               poll("Two", 40, study_id="two-future", published_at="2026-10-22")]
    result = poll_analysis(surveys, state="NC", cycle=2026, as_of="2026-10-20")
    assert result["producer_count"] == 3
    assert result["averages"]["Candidate A"] == 50
    assert len(result["excluded"]) == 2
    assert len(result["series"][0]["leave_one_producer_out"]) == 3
    assert all(item["averages"] == {} for item in result["series"][0]["leave_one_producer_out"])


def test_copublished_sample_is_not_an_extra_producer():
    surveys = [poll("One", metadata={"shared_sample_id": "same"}),
               poll("Two", metadata={"shared_sample_id": "same"}), poll("Three")]
    result = poll_analysis(surveys, as_of="2026-10-20")
    assert result["producer_count"] == 2
    assert result["averages"] == {}
    assert any("shared" in record["reason"] for record in result["excluded"])


def test_poll_question_populations_and_ballots_stay_separate():
    surveys = [poll("One"), poll("Two"), poll("Three"), poll("RV", population="RV"),
               poll("Expectation", question_type="winner_expectation"),
               poll("Alternate", ballot_type="head_to_head")]
    result = poll_analysis(surveys, as_of="2026-10-20")
    assert result["producer_count"] == 3
    assert len(result["excluded"]) == 3


def test_censored_poll_estimate_is_not_converted_to_zero():
    surveys = [poll(name) for name in ("One", "Two", "Three")]
    for survey in surveys:
        survey["estimates"].append({"candidate": "Other", "value": None, "reported": "<1%", "upper_bound": 1})
    result = poll_analysis(surveys, as_of="2026-10-20")
    assert "Other" not in result["averages"]
    assert result["eligible"][0]["estimates"][-1]["value"] is None


def test_candidate_configurations_are_separate_series():
    surveys = [poll(name) for name in ("One", "Two", "Three")]
    alternate = poll("Alternate")
    alternate["estimates"][0]["candidate"] = "Different Candidate"
    result = poll_analysis(surveys + [alternate], as_of="2026-10-20")
    assert result["status"] == "multiple_series"
    assert result["averages"] == {}
    assert len(result["series"]) == 2


def test_generic_response_wording_does_not_fragment_identical_candidate_ballots():
    surveys = [poll("One"), poll("Two"), poll("Three")]
    for index, wording in enumerate(("Don’t know/Refused", "Someone else", "Another party’s candidate")):
        surveys[index]["estimates"][-1]["candidate"] = wording
    result = poll_analysis(surveys, as_of="2026-10-20")
    assert len(result["series"]) == 1
    assert result["averages"]["Candidate A"] == 46
    named_third_party = poll("Four")
    named_third_party["estimates"][-1]["candidate"] = "Named Libertarian Candidate"
    separated = poll_analysis(surveys + [named_third_party], as_of="2026-10-20")
    assert len(separated["series"]) == 2


def test_scenario_requires_explicit_unobserved_early_candidate_support():
    with pytest.raises(ValueError, match="explicit candidate-support"):
        run_scenario({"total_turnout": 1000, "remaining_candidate_share": 55}, observed_total=400)
    with pytest.raises(ValueError, match="below"):
        run_scenario({"total_turnout": 300, "observed_candidate_share": 50}, observed_total=400)
    with pytest.raises(ValueError, match="finite"):
        run_scenario({"total_turnout": float("nan")})


def test_scenario_preserves_totals_and_other_candidates():
    result = run_scenario({"total_turnout": 1000, "observed_candidate_share": 50,
                           "remaining_candidate_share": 60, "remaining_other_share": 5}, observed_total=400)
    assert sum(result["projected_votes"].values()) == pytest.approx(1000)
    assert result["projected_votes"]["candidate_a"] == pytest.approx(560)
    assert result["projected_votes"]["other"] == pytest.approx(30)
    assert result["margin"] == pytest.approx(15)
    assert len(result["sensitivity"]) == 4
    assert len(result["grid"]) == 25
    assert result["status"] == "scenario"


def test_scenario_components_must_form_a_consistent_partition():
    params = {"total_turnout": 1000, "observed_candidate_share": 50,
              "remaining_components": [{"id": "mail", "ballots": 200, "candidate_a_share": 60},
                                       {"id": "in_person", "ballots": 400, "candidate_a_share": 40}]}
    result = run_scenario(params, observed_total=400)
    assert result["projected_votes"]["candidate_a"] == pytest.approx(480)
    broken = deepcopy(params)
    broken["remaining_components"][1]["ballots"] = 500
    with pytest.raises(ValueError, match="sum exactly"):
        run_scenario(broken, observed_total=400)


def test_senate_scenario_requires_special_elections_as_separate_contests():
    result = senate_scenarios([{"race_id": "OH-regular", "winner_caucus": "R"},
                               {"race_id": "OH-special", "winner_caucus": "D"}], holdovers={"D": 48, "R": 50})
    assert result["assigned_seats"] == {"D": 49, "R": 51, "other": 0}
    assert result["probabilities"] is None
    partial = senate_scenarios([{"race_id": "NC"}], holdovers={"D": 40, "R": 50})
    assert partial["unrepresented_seats"] == 9
    assert partial["seat_ranges"]["D"] == {"min": 40, "max": 50}


def test_brief_claims_have_source_references_and_future_composition_is_not_leaked():
    future = observation(10, category_dimension="age", category="65+", published_at="2026-10-22")
    brief = state_brief([observation(), future], [], state="NC", as_of="2026-10-20", metric="ballots_cast")
    assert len(brief["sections"]) == 10
    composition = next(section for section in brief["sections"] if section["id"] == "composition")
    assert composition["status"] == "unavailable"
    facts = [fact for section in brief["sections"] for fact in section["facts"]]
    assert all(fact.get("sources") for fact in facts)
