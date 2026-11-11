"""Simple, explainable baselines. Every ML model must beat these to be used."""

from __future__ import annotations

import numpy as np


def moving_average_forecast(history: np.ndarray, horizon: int, window: int = 7) -> np.ndarray:
    """Flat forecast at the mean of the last ``window`` days."""
    if len(history) == 0:
        return np.zeros(horizon)
    level = float(np.mean(history[-min(window, len(history)) :]))
    return np.full(horizon, level, dtype=float)


def seasonal_naive_forecast(history: np.ndarray, horizon: int, season: int = 7) -> np.ndarray:
    """Repeat the last observed week (weekly seasonality)."""
    if len(history) == 0:
        return np.zeros(horizon)
    season = min(season, len(history))
    tail = history[-season:]
    repeats = int(np.ceil(horizon / season))
    return np.tile(tail, repeats)[:horizon].astype(float)
