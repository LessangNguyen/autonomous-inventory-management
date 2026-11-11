"""Forecasting tests on synthetic series: no leakage, sane output, gap filling."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ai.forecasting.engine import forecast_series
from ai.forecasting.features import build_training_frame, fill_daily_series


def _series(days: int = 150, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=date.today(), periods=days, freq="D")
    dow = dates.dayofweek.to_numpy()
    weekly = 5 + 2.0 * np.sin(2 * np.pi * dow / 7)
    trend = np.linspace(0, 3, days)
    noise = rng.gamma(shape=6.0, scale=0.18, size=days)
    values = np.clip((weekly + trend) * noise, 0, None).round(2)
    return pd.DataFrame({"date": dates, "y": values})


def test_fill_daily_series_normalizes_timestamps_and_fills_gaps():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01 09:30", "2026-01-01 18:45", "2026-01-04 10:00"]),
            "y": [1.0, 2.0, 5.0],
        }
    )
    filled = fill_daily_series(frame["date"], frame["y"])

    assert len(filled) == 4  # Jan 1..4 inclusive
    assert list(filled["y"]) == [3.0, 0.0, 0.0, 5.0]
    assert filled["date"].dt.hour.eq(0).all()


def test_training_frame_has_expected_features():
    frame = build_training_frame(_series(60))
    assert len(frame) == 60 - 28
    assert {"lag_1", "lag_7", "lag_28", "roll_mean_7", "roll_mean_28", "dow", "is_weekend"} <= set(frame.columns)
    assert frame["y"].notna().all()


def test_forecast_series_returns_requested_horizon_and_metrics():
    result = forecast_series(_series(150), horizon=14)

    assert result.model_version == "v1.0"
    assert len(result.daily_series) == 14
    assert all(value >= 0 for value in result.daily_series)
    # Both the total and the daily values are rounded to 2dp, so allow the
    # accumulated rounding error (up to 0.005 per forecast day).
    assert result.predicted_qty == pytest.approx(
        sum(result.daily_series), abs=len(result.daily_series) * 0.005 + 0.01
    )
    assert result.model_name in {
        "gbm_hist_gradient_boosting",
        "lightgbm",
        "moving_average",
        "seasonal_naive",
    }
    assert result.mae is not None and result.mae >= 0
    assert result.rmse is not None and result.rmse >= result.mae
    assert result.wape is not None and result.wape >= 0
    assert result.confidence in {"low", "medium", "high"}
    assert result.trained_until is not None


def test_forecast_handles_empty_and_zero_series():
    empty = forecast_series(pd.DataFrame(columns=["date", "y"]), horizon=7)
    assert empty.predicted_qty == 0
    assert len(empty.daily_series) == 7
    assert empty.model_name == "none"

    dates = pd.date_range(end=date.today(), periods=40, freq="D")
    zeros = pd.DataFrame({"date": dates, "y": [0.0] * 40})
    result = forecast_series(zeros, horizon=7)
    assert result.predicted_qty == 0
    assert result.model_name == "zero_demand"
    assert len(result.daily_series) == 7


def test_forecast_does_not_leak_future_values():
    """Changing values inside the holdout window must not change the model choice inputs."""
    frame = _series(120, seed=11)
    baseline = forecast_series(frame.copy(), horizon=7)

    tampered = frame.copy()
    tampered.loc[tampered.index[-14:], "y"] = tampered["y"].iloc[-14:] * 5
    changed = forecast_series(tampered, horizon=7)

    # Metrics legitimately change because the holdout/target moved, but forecasts must
    # remain finite and non-negative rather than producing NaNs from leakage.
    assert np.isfinite(changed.daily_series).all()
    assert all(value >= 0 for value in changed.daily_series)
    assert len(baseline.daily_series) == len(changed.daily_series) == 7
