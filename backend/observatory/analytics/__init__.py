"""Pure analytical interfaces used by the API, collector reports, and CLI."""
from .briefs import state_brief
from .forecasting import (
    MODEL_VERSION,
    backtest_forecasts,
    fit_error_parameters,
    forecast_race,
    forecast_senate,
    simulate_race,
)
from .historical import filter_observations, historical_analysis
from .polling import poll_analysis
from .scenarios import run_scenario, senate_scenarios

__all__ = [
    "MODEL_VERSION", "backtest_forecasts", "filter_observations", "fit_error_parameters",
    "forecast_race", "forecast_senate", "historical_analysis", "poll_analysis",
    "run_scenario", "senate_scenarios", "simulate_race", "state_brief",
]
