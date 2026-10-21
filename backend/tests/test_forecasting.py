"""Simulation fixtures are synthetic and cannot pass the live publication gate."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from observatory.analytics import (
    backtest_forecasts,
    fit_error_parameters,
    forecast_race,
    forecast_senate,
    simulate_race,
)


def inputs(**changes):
    return {"state": "NC", "cycle": 2026, "election_system": "plurality", "election_date": "2026-11-03",
            "cutoff": "2026-10-20", "polling_margin": 2.0, "polling_available_at": "2026-10-19",
            "fundamentals_margin": -1.0, "fundamentals_available_at": "2026-09-01",
            "sources": [{"source_id": "synthetic-fixture", "available_at": "2026-09-01"}], **changes}


def cases():
    result = []
    for cycle, election in ((2018, date(2018, 11, 6)), (2022, date(2022, 11, 8))):
        for index in range(3):
            for horizon in (30, 14, 7, 1):
                cutoff = (election - timedelta(days=horizon)).isoformat()
                result.append({"race_id": f"fixture-{index}", "state": "NC", "cycle": cycle,
                               "election_date": election.isoformat(), "cutoff": cutoff,
                               "result_margin": (index - 1) * 4 + 1, "result_published_at": f"{cycle}-12-01",
                               "data_origin": "synthetic",
                               "inputs": inputs(cycle=cycle, election_date=election.isoformat(), cutoff=cutoff,
                                                polling_margin=(index - 1) * 4 + 2, fundamentals_margin=(index - 1) * 4,
                                                polling_available_at=cutoff, fundamentals_available_at=f"{cycle}-08-01",
                                                sources=[{"source_id": "synthetic", "available_at": f"{cycle}-08-01"}])})
    return result


def test_actual_student_t_simulation_is_reproducible_and_bounded():
    a = simulate_race(inputs(), seed=7, simulations=5000)
    b = simulate_race(inputs(), seed=7, simulations=5000)
    np.testing.assert_array_equal(a["draws"], b["draws"])
    assert a["projected_margin"] == pytest.approx(1.4)
    assert a["interval_95"][0] < a["interval_80"][0] < a["median_margin"]
    assert a["interval_95"][1] > a["interval_80"][1] > a["median_margin"]
    assert all(-100 <= value <= 100 for value in a["draws"])
    assert sum(point["probability"] for point in a["distribution"]) == pytest.approx(1)


def test_unvalidated_live_probabilities_are_withheld_even_with_inputs():
    result = forecast_race(inputs(), seed=7, simulations=1000)
    assert result["status"] == "awaiting_validation"
    assert result["probabilities"] is None
    assert not result["publishable"]
    assert "candidate_a_win_probability" not in result


@pytest.mark.parametrize("state", ["AK", "ME", "GA"])
def test_counting_system_is_never_silently_treated_as_plurality(state):
    data = inputs(state=state)
    data.pop("election_system")
    result = forecast_race(data)
    assert result["status"] == "unsupported_electoral_system"
    assert result["probabilities"] is None


def test_late_poll_inputs_are_rejected():
    with pytest.raises(ValueError, match="after the cutoff"):
        forecast_race(inputs(polling_available_at="2026-10-21"))


def test_rolling_backtest_has_scores_and_never_trains_on_same_or_later_cycle():
    output = backtest_forecasts(cases(), simulations=1000, seed=91)
    assert output["case_count"] == 24
    assert output["metrics"]["combined"]["mae"] is not None
    assert output["metrics"]["combined"]["coverage_80"] is not None
    assert set(output["by_horizon"]) == {"1", "7", "14", "30"}
    assert all(all(cycle < row["cycle"] for cycle in row["training_cycles"]) for row in output["predictions"])
    assert len(output["artifact_hash"]) == 64
    assert output["status"] == "insufficient_validation"
    assert not output["historical_only"]
    assert output["validated_horizons"] == []
    assert sum(item["count"] for item in output["calibration"]) == output["case_count"]


def test_backtest_excludes_leakage_and_duplicates_with_reasons():
    fixtures = cases()
    bad = {**fixtures[0], "inputs": {**fixtures[0]["inputs"], "polling_available_at": "2026-10-20"}}
    output = backtest_forecasts([bad, fixtures[1], fixtures[1]], simulations=1000)
    assert output["case_count"] == 1
    assert len(output["excluded"]) == 2
    assert any("after the cutoff" in row["reason"] for row in output["excluded"])
    assert any("Duplicate" in row["reason"] for row in output["excluded"])


def test_empirical_fit_deduplicates_repeated_horizons():
    fit = fit_error_parameters(cases())
    assert fit["training_races"] == 6
    assert fit["training_cycles"] == [2018, 2022]


def test_chamber_probabilities_require_complete_universe_and_separate_validation():
    output = forecast_senate([{"race_id": "NC", "inputs": inputs(), "candidate_a_caucus": "D", "candidate_b_caucus": "R"}],
                             holdovers={"D": 40, "R": 40}, vice_president_caucus="R")
    assert output["probabilities"] is None
    assert not output["publishable"]
    assert any("100" in reason for reason in output["reasons"])


def test_validation_artifact_cannot_be_faked_with_a_status_string():
    forged = {"status": "validated", "model_version": "eb-student-t-v1", "historical_only": True,
              "case_count": 24, "validated_horizons": [14], "parameters": {}, "artifact_hash": "forged"}
    output = forecast_race(inputs(), validation=forged)
    assert output["probabilities"] is None
    assert any("integrity" in reason for reason in output["reasons"])
