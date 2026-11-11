"""Forecast accuracy metrics.

WAPE is the primary metric because it behaves well for intermittent demand
(products with many zero-sale days), where MAPE explodes.
"""

from __future__ import annotations

import numpy as np


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.size == 0:
        return 0.0
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def wape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Weighted absolute percentage error. None when actual demand is all zero."""
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    denominator = float(np.sum(np.abs(actual)))
    if denominator == 0:
        return None
    return float(np.sum(np.abs(actual - predicted)) / denominator)


def summarize(actual: np.ndarray, predicted: np.ndarray) -> dict:
    return {
        "mae": round(mae(actual, predicted), 4),
        "rmse": round(rmse(actual, predicted), 4),
        "wape": (lambda value: None if value is None else round(value, 4))(
            wape(actual, predicted)
        ),
        "n": int(len(actual)),
    }
