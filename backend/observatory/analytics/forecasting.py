"""Reproducible empirical-Bayes simulations and cutoff-safe historical evaluation.

Live probabilities are withheld until an actual historical evaluation passes the
documented gate. The simulator is useful independently for explicit experiments;
its existence is never described as validation.
"""
from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from math import log, sqrt
from statistics import mean
from typing import Any

import numpy as np

from .common import day, finite_number, instant

MODEL_VERSION = "eb-student-t-v1"
DEFAULT_PARAMETERS = {
    "poll_error_sd": 4.0, "fundamentals_error_sd": 8.0,
    "poll_bias": 0.0, "fundamentals_bias": 0.0,
    "residual_error_floor": 2.5, "national_error_fraction": 0.6, "degrees_of_freedom": 5.0,
}
SUPPORTED_SYSTEMS = {"plurality"}
HORIZONS = (30, 14, 7, 1)


def _system(inputs: dict[str, Any]) -> str:
    # Omission cannot accidentally turn a known non-plurality race into a
    # supported eventual-winner model.
    return str(inputs.get("election_system") or {
        "AK": "ranked_choice", "ME": "ranked_choice", "GA": "runoff",
    }.get(inputs.get("state"), "plurality"))


def _manifest_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _validate_inputs(inputs: dict[str, Any], *, require_times: bool = False) -> dict[str, Any]:
    result = dict(inputs)
    if _system(result) not in SUPPORTED_SYSTEMS:
        raise ValueError("This model does not support ranked-choice transfers or runoff resolution")
    for key in ("polling_margin", "fundamentals_margin"):
        if result.get(key) is not None:
            value = finite_number(result[key], key)
            if not -100 <= value <= 100:
                raise ValueError(f"{key} must be a candidate margin between -100 and 100 percentage points")
            result[key] = value
    if result.get("fundamentals_margin") is None:
        raise ValueError("A sourced fundamentals_margin prior is required")
    cutoff = instant(result.get("cutoff"), end_of_day=True)
    if require_times and cutoff is None:
        raise ValueError("Historical cases require an explicit information cutoff")
    for key in ("polling", "fundamentals"):
        if result.get(f"{key}_margin") is None:
            continue
        published = instant(result.get(f"{key}_available_at"), end_of_day=True)
        if require_times and published is None:
            raise ValueError(f"Historical {key} inputs require an established availability time")
        if cutoff is not None and published is not None and published > cutoff:
            raise ValueError(f"{key} inputs contain information published after the cutoff")
    for source in result.get("sources", []):
        if (isinstance(source, dict) and source.get("available_at") and cutoff
                and instant(source["available_at"], end_of_day=True) > cutoff):
            raise ValueError("An input source was not available at the information cutoff")
    return result


def fit_error_parameters(training_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Empirical errors from older completed cycles only; caller supplies the split.

    Each race appears once per cycle so densely repeated horizons cannot dominate
    the empirical prior. Bias estimates shrink toward zero by five prior cases.
    """
    unique: dict[tuple[Any, Any], dict[str, Any]] = {}
    for case in training_cases:
        key = (case.get("cycle"), case.get("race_id", case.get("state")))
        previous = unique.get(key)
        # Use the observation closest to Election Day for scale training; horizon
        # specific backtests still evaluate all requested horizons separately.
        if previous is None or str(case.get("cutoff", "")) > str(previous.get("cutoff", "")):
            unique[key] = case
    poll_errors, fundamentals_errors = [], []
    for case in unique.values():
        inputs = case.get("inputs", case)
        result = float(case["result_margin"])
        if inputs.get("polling_margin") is not None:
            poll_errors.append(float(inputs["polling_margin"]) - result)
        if inputs.get("fundamentals_margin") is not None:
            fundamentals_errors.append(float(inputs["fundamentals_margin"]) - result)
    params = dict(DEFAULT_PARAMETERS)
    for prefix, errors, floor in (("poll", poll_errors, 2.0), ("fundamentals", fundamentals_errors, 4.0)):
        if len(errors) >= 5:
            bias = sum(errors) / (len(errors) + 5)
            params[f"{prefix}_bias"] = bias
            params[f"{prefix}_error_sd"] = max(floor, sqrt(mean((error - bias) ** 2 for error in errors)))
    params["training_races"] = len(unique)
    params["training_cycles"] = sorted({int(case["cycle"]) for case in unique.values()})
    return params


def simulate_race(
    inputs: dict[str, Any], *, parameters: dict[str, Any] | None = None,
    simulations: int = 20000, seed: int = 2026,
    national_errors: np.ndarray | None = None,
) -> dict[str, Any]:
    """Low-level experimental computation; no publication authorization is implied."""
    if not 1000 <= simulations <= 1_000_000:
        raise ValueError("simulations must be between 1,000 and 1,000,000")
    values = _validate_inputs(inputs)
    params = {**DEFAULT_PARAMETERS, **(parameters or {})}
    df = finite_number(params["degrees_of_freedom"], "degrees_of_freedom")
    if df <= 2:
        raise ValueError("Student-t degrees of freedom must exceed two for finite variance")
    for key in ("poll_error_sd", "fundamentals_error_sd", "residual_error_floor"):
        if finite_number(params[key], key) <= 0:
            raise ValueError(f"{key} must be positive")
    national_fraction = finite_number(params["national_error_fraction"], "national_error_fraction")
    if not 0 <= national_fraction <= 1:
        raise ValueError("national_error_fraction must be between zero and one")
    prior = float(values["fundamentals_margin"]) - float(params["fundamentals_bias"])
    prior_var = float(params["fundamentals_error_sd"]) ** 2
    polling = values.get("polling_margin")
    if polling is None:
        center, posterior_var, polling_weight = prior, prior_var, 0.0
    else:
        likelihood = float(polling) - float(params["poll_bias"])
        poll_var = float(params["poll_error_sd"]) ** 2
        posterior_var = 1 / (1 / prior_var + 1 / poll_var)
        center = posterior_var * (prior / prior_var + likelihood / poll_var)
        polling_weight = prior_var / (prior_var + poll_var)
    sigma = sqrt(posterior_var + float(params["residual_error_floor"]) ** 2)
    rng = np.random.default_rng(seed)
    # Standard-t variance is df/(df-2); rescale to the stated error SD.
    rescale = sqrt((df - 2) / df)
    national = (rng.standard_t(df, simulations) * rescale if national_errors is None else national_errors)
    if len(national) != simulations:
        raise ValueError("Shared national error vector does not match the simulation count")
    individual = rng.standard_t(df, simulations) * rescale
    draws = np.clip(center + sigma * (national_fraction * national
                                     + sqrt(1 - national_fraction ** 2) * individual), -100, 100)
    quantiles = np.quantile(draws, [0.025, 0.1, 0.5, 0.9, 0.975])
    hist, bins = np.histogram(draws, bins=41, range=(-100, 100), density=False)
    return {
        "model_version": MODEL_VERSION, "seed": seed, "simulations": simulations,
        "projected_margin": center, "median_margin": float(quantiles[2]),
        "candidate_a_win_probability": float(np.mean(draws > 0)),
        "candidate_b_win_probability": float(np.mean(draws < 0)),
        "interval_80": [float(quantiles[1]), float(quantiles[3])],
        "interval_95": [float(quantiles[0]), float(quantiles[4])],
        "standard_deviation": sigma, "polling_weight": polling_weight,
        "fundamentals_weight": 1 - polling_weight,
        "distribution": [{"margin": float((bins[i] + bins[i + 1]) / 2),
                          "probability": int(count) / simulations} for i, count in enumerate(hist)],
        "parameters": params,
        "draws": draws,  # Internal consumers strip this; JSON APIs never return raw arrays.
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "draws"}


def _validation_gate(validation: dict[str, Any] | None, inputs: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if _system(inputs) not in SUPPORTED_SYSTEMS:
        reasons.append("Eventual-winner modeling for ranked-choice or runoff elections is unsupported.")
    if not validation or validation.get("status") != "validated":
        reasons.append("No passing historical validation artifact has been supplied.")
    elif validation.get("model_version") != MODEL_VERSION:
        reasons.append("Validation belongs to a different model version.")
    else:
        valid_horizons = set(validation.get("validated_horizons", []))
        if inputs.get("cutoff") and inputs.get("election_date"):
            horizon = (day(inputs["election_date"]) - day(inputs["cutoff"])).days
            if horizon not in valid_horizons:
                reasons.append("This forecast horizon has not passed historical evaluation.")
        else:
            reasons.append("Live forecasts require an election date and an explicit cutoff.")
        if not validation.get("historical_only") or validation.get("case_count", 0) < 20:
            reasons.append("Validation lacks sufficient non-synthetic historical cases.")
        payload = {key: value for key, value in validation.items() if key != "artifact_hash"}
        if validation.get("artifact_hash") != _manifest_hash(payload):
            reasons.append("Validation artifact integrity check failed.")
        training_cycles = validation.get("parameters", {}).get("training_cycles", [])
        if inputs.get("cycle") and any(int(cycle) >= int(inputs["cycle"]) for cycle in training_cycles):
            reasons.append("Calibration includes this election cycle or a later one.")
    return not reasons, reasons


def forecast_race(
    inputs: dict[str, Any], *, validation: dict[str, Any] | None = None,
    seed: int = 2026, simulations: int = 20000,
) -> dict[str, Any]:
    allowed, reasons = _validation_gate(validation, inputs)
    manifest = {"model_version": MODEL_VERSION, "inputs": inputs, "seed": seed,
                "simulations": simulations, "validation_hash": (validation or {}).get("artifact_hash")}
    if _system(inputs) not in SUPPORTED_SYSTEMS:
        return {"status": "unsupported_electoral_system", "publishable": False, "probabilities": None,
                "reasons": reasons, "manifest": manifest, "manifest_hash": _manifest_hash(manifest)}
    if inputs.get("fundamentals_margin") is None:
        return {"status": "missing_inputs", "publishable": False, "probabilities": None,
                "reasons": reasons + ["A sourced fundamentals prior and historical calibration are required."],
                "manifest": manifest, "manifest_hash": _manifest_hash(manifest)}
    # Enforce timestamps even before performing an experimental calculation.
    validated_inputs = _validate_inputs(inputs, require_times=True)
    if not allowed:
        return {"status": "awaiting_validation", "publishable": False, "probabilities": None,
                "reasons": reasons, "manifest": manifest, "manifest_hash": _manifest_hash(manifest),
                "method": "Empirical-Bayes polling plus fundamentals with Student-t national and race errors"}
    result = simulate_race(validated_inputs, parameters=validation.get("parameters"),
                           seed=seed, simulations=simulations)
    return {"status": "validated", "publishable": True,
            "probabilities": {"candidate_a": result["candidate_a_win_probability"],
                              "candidate_b": result["candidate_b_win_probability"]},
            **_public_result(result), "manifest": manifest, "manifest_hash": _manifest_hash(manifest),
            "reasons": [], "warnings": ["Historical validation cannot guarantee future calibration.",
                                          "Early-vote composition is excluded from this model."]}


def _scores(rows: list[dict[str, Any]], model: str = "combined") -> dict[str, Any]:
    if not rows:
        return {"count": 0, "mae": None, "brier": None, "log_loss": None,
                "coverage_80": None, "coverage_95": None}
    errors, briers, logs, cover80, cover95 = [], [], [], [], []
    for row in rows:
        prediction = row[model]
        actual = row["result_margin"]
        p = min(1 - 1e-9, max(1e-9, prediction["candidate_a_win_probability"]))
        outcome = float(actual > 0)
        errors.append(abs(prediction["projected_margin"] - actual))
        briers.append((p - outcome) ** 2)
        logs.append(-(outcome * log(p) + (1 - outcome) * log(1 - p)))
        cover80.append(float(prediction["interval_80"][0] <= actual <= prediction["interval_80"][1]))
        cover95.append(float(prediction["interval_95"][0] <= actual <= prediction["interval_95"][1]))
    return {"count": len(rows), "mae": mean(errors), "brier": mean(briers), "log_loss": mean(logs),
            "coverage_80": mean(cover80), "coverage_95": mean(cover95)}


def backtest_forecasts(
    cases: list[dict[str, Any]], *, seed: int = 2026, simulations: int = 20000,
) -> dict[str, Any]:
    """Evaluate timestamped historical inputs using older cycles for scale fitting.

    Case schema: race_id,state,cycle,election_date,cutoff,result_margin,
    result_published_at,data_origin='historical',inputs={polling_margin,
    polling_available_at,fundamentals_margin,fundamentals_available_at,sources}.
    Each horizon/race combination is evaluated once; source provenance is required
    for a historical validation gate, but synthetic fixtures can exercise the tool.
    """
    prepared, excluded = [], []
    seen = set()
    for case in cases:
        try:
            result = finite_number(case.get("result_margin"), "result_margin")
            if not -100 <= result <= 100 or result == 0:
                raise ValueError("Historical results must identify a winner with a valid signed margin")
            cutoff = instant(case.get("cutoff"), end_of_day=True)
            election = day(case["election_date"])
            if cutoff is None or day(cutoff) >= election:
                raise ValueError("Backtests require a cutoff before Election Day")
            result_at = instant(case.get("result_published_at"), end_of_day=True)
            if result_at is None or result_at <= cutoff:
                raise ValueError("Historical cases require a result publication date after the forecast cutoff")
            horizon = (election - day(cutoff)).days
            if horizon not in HORIZONS:
                raise ValueError("Supported backtest horizons are 30, 14, 7, and 1 days")
            cycle = int(case["cycle"])
            if election.year != cycle:
                raise ValueError("Election date does not match the case cycle")
            race_id = case.get("race_id")
            if not race_id:
                raise ValueError("A stable race_id is required")
            key = (race_id, cycle, horizon)
            if key in seen:
                raise ValueError("Duplicate race/cycle/horizon case")
            inputs = {**case.get("inputs", {}), "cutoff": case["cutoff"], "cycle": cycle,
                      "election_date": case["election_date"], "state": case.get("state")}
            inputs = _validate_inputs(inputs, require_times=True)
            if inputs.get("polling_margin") is None:
                raise ValueError("A polling input is required for identical-set baseline comparisons")
            prepared.append({**case, "inputs": inputs, "horizon": horizon, "result_margin": result})
            seen.add(key)
        except (KeyError, TypeError, ValueError) as exc:
            excluded.append({"race_id": case.get("race_id"), "cutoff": case.get("cutoff"), "reason": str(exc)})
    prepared.sort(key=lambda c: (int(c["cycle"]), c["race_id"], -c["horizon"]))
    predictions = []
    by_horizon: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, case in enumerate(prepared):
        # Strict older-cycle fitting prevents contemporaneous results leaking
        # across races and repeatedly sampled horizons.
        training = [c for c in prepared if int(c["cycle"]) < int(case["cycle"])
                    and instant(c["result_published_at"], end_of_day=True)
                    <= instant(case["cutoff"], end_of_day=True)]
        params = fit_error_parameters(training)
        combined = simulate_race(case["inputs"], parameters=params, simulations=simulations, seed=seed + index)
        funda = simulate_race({**case["inputs"], "polling_margin": None}, parameters=params,
                              simulations=simulations, seed=seed + index)
        # A diffuse prior makes the polling-only baseline's center exactly its
        # bias-adjusted input; restore the center and draw offsets explicitly.
        polling = simulate_race({**case["inputs"], "fundamentals_margin": case["inputs"]["polling_margin"]},
                                parameters={**params, "fundamentals_bias": params["poll_bias"],
                                            "fundamentals_error_sd": 1_000_000},
                                simulations=simulations, seed=seed + index)
        row = {"race_id": case["race_id"], "state": case.get("state"), "cycle": case["cycle"],
               "cutoff": case["cutoff"], "horizon": case["horizon"], "result_margin": case["result_margin"],
               "training_cycles": params["training_cycles"], "training_races": params["training_races"],
               "combined": _public_result(combined), "polling_only": _public_result(polling),
               "fundamentals_only": _public_result(funda)}
        predictions.append(row)
        by_horizon[case["horizon"]].append(row)
    metrics = {model: _scores(predictions, model) for model in ("combined", "polling_only", "fundamentals_only")}
    horizon_metrics = {str(h): {model: _scores(rows, model) for model in metrics} for h, rows in sorted(by_horizon.items())}
    cycles = sorted({int(c["cycle"]) for c in prepared})
    historical_only = bool(prepared) and all(c.get("data_origin") == "historical"
                                           and c["inputs"].get("sources") for c in prepared)
    gate_reasons = []
    if len(prepared) < 20:
        gate_reasons.append("At least 20 held-out race/horizon cases are required.")
    if len(cycles) < 2:
        gate_reasons.append("At least two election cycles are required.")
    if not historical_only:
        gate_reasons.append("Every case must have actual historical origin and source provenance; fixtures cannot validate forecasts.")
    valid_horizons = []
    for horizon in HORIZONS:
        rows = by_horizon.get(horizon, [])
        scores = _scores(rows)
        passes = len(rows) >= 3 and len({r["cycle"] for r in rows}) >= 2
        if passes:
            for baseline in ("polling_only", "fundamentals_only"):
                baseline_score = _scores(rows, baseline)
                passes = passes and scores["brier"] <= baseline_score["brier"] + 1e-9
                passes = passes and scores["mae"] <= baseline_score["mae"] + 1e-9
            passes = passes and scores["coverage_80"] >= 0.65 and scores["coverage_95"] >= 0.85
        if passes:
            valid_horizons.append(horizon)
        else:
            gate_reasons.append(f"The {horizon}-day horizon lacks coverage, calibration, or improvement over both baselines.")
    if excluded:
        gate_reasons.append("Some submitted cases were excluded; inspect the exclusions before publication.")
    # A caller may publish only passing horizon(s), provided global evidence is adequate.
    global_pass = len(prepared) >= 20 and len(cycles) >= 2 and historical_only and bool(valid_horizons) and not excluded
    bins = []
    for index in range(10):
        lo, hi = index / 10, (index + 1) / 10
        rows = [r for r in predictions if lo <= r["combined"]["candidate_a_win_probability"]
                and (r["combined"]["candidate_a_win_probability"] < hi
                     or (index == 9 and r["combined"]["candidate_a_win_probability"] <= hi))]
        bins.append({"lower": float(lo), "upper": float(lo + 0.1), "count": len(rows),
                     "mean_probability": mean(r["combined"]["candidate_a_win_probability"] for r in rows) if rows else None,
                     "observed_frequency": mean(float(r["result_margin"] > 0) for r in rows) if rows else None})
    artifact = {
        "status": "validated" if global_pass else "insufficient_validation", "model_version": MODEL_VERSION,
        "case_count": len(prepared), "cycles": cycles, "historical_only": historical_only,
        "validated_horizons": valid_horizons if global_pass else [], "metrics": metrics,
        "by_horizon": horizon_metrics, "calibration": bins, "predictions": predictions,
        "excluded": excluded, "reasons": gate_reasons,
        "parameters": fit_error_parameters(prepared), "seed": seed, "simulations": simulations,
        "case_manifest_hash": _manifest_hash(prepared),
        "chamber_correlation_validated": False,
        "warnings": ["Repeated horizons for the same race are not independent evidence.",
                     "Minimum sample gates do not establish universal calibration.",
                     "National-error correlation requires separate complete-universe validation."],
    }
    artifact["artifact_hash"] = _manifest_hash(artifact)
    return artifact


def forecast_senate(
    races: list[dict[str, Any]], *, holdovers: dict[str, int],
    validation: dict[str, Any] | None = None, seed: int = 2026, simulations: int = 20000,
    vice_president_caucus: str | None = None,
) -> dict[str, Any]:
    """Joint national/race-error chamber simulator, with a stricter release gate.

    Races contain race_id, candidate_a_caucus, candidate_b_caucus, and inputs.
    Every contested seat and each holdover must be represented exactly once.
    Current backtest artifacts intentionally cannot validate chamber correlation.
    """
    reasons = []
    if not validation or not validation.get("chamber_correlation_validated"):
        reasons.append("Complete-universe correlated chamber evaluation has not been supplied.")
    if any(finite_number(value, "Holdovers") < 0 or float(value) != int(value) for value in holdovers.values()):
        reasons.append("Holdover counts must be nonnegative integers.")
    if set(holdovers) - {"D", "R"}:
        reasons.append("Independent holdovers require an explicit D or R caucus assignment.")
    if sum(int(value) for value in holdovers.values()) + len(races) != 100:
        reasons.append("Holdovers and contests must represent exactly 100 distinct seats.")
    identifiers = [r.get("race_id") for r in races]
    if any(identifier is None for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        reasons.append("Contest identifiers are missing or duplicated.")
    for race in races:
        allowed, why = _validation_gate(validation, race.get("inputs", {}))
        if not allowed:
            reasons.extend(f"{race.get('race_id', 'Race')}: {reason}" for reason in why)
        if race.get("candidate_a_caucus") not in {"D", "R"} or race.get("candidate_b_caucus") not in {"D", "R"}:
            reasons.append("Every eventual winner needs an explicit supported caucus assignment.")
    if vice_president_caucus not in {"D", "R"}:
        reasons.append("An explicit vice-presidential caucus is required for 50–50 control.")
    if reasons:
        return {"status": "awaiting_chamber_validation", "publishable": False, "probabilities": None,
                "reasons": list(dict.fromkeys(reasons)), "model_version": MODEL_VERSION}
    parameters = validation["parameters"]
    rng = np.random.default_rng(seed)
    df = float(parameters["degrees_of_freedom"])
    shared_errors = rng.standard_t(df, simulations) * sqrt((df - 2) / df)
    d_seats = np.full(simulations, int(holdovers.get("D", 0)))
    for index, race in enumerate(races):
        national = shared_errors if race["candidate_a_caucus"] == "D" else -shared_errors
        draws = simulate_race(race["inputs"], parameters=parameters, simulations=simulations,
                              seed=seed + index + 1, national_errors=national)["draws"]
        d_seats += np.where(draws > 0, race["candidate_a_caucus"] == "D", race["candidate_b_caucus"] == "D")
    threshold = 50 if vice_president_caucus == "D" else 51
    distribution = [{"democratic_seats": seats, "probability": float(np.mean(d_seats == seats))}
                    for seats in range(101) if np.any(d_seats == seats)]
    return {"status": "validated", "publishable": True, "seed": seed, "simulations": simulations,
            "probabilities": {"democratic_control": float(np.mean(d_seats >= threshold)),
                              "republican_control": float(np.mean(d_seats < threshold))},
            "distribution": distribution, "validation_hash": validation["artifact_hash"],
            "warnings": ["Control probabilities depend on stated caucus and vice-presidential assumptions."]}
