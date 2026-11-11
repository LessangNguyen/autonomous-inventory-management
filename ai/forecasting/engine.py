"""Per-SKU demand forecasting engine.

Design principles
-----------------
* Always ship a baseline. A gradient-boosting model is only selected when it
  beats the best baseline by a meaningful margin on a time-ordered holdout.
* Validate with a recursive, expanding-window style backtest: the model never
  sees the validation window, and multi-step forecasts are generated step by
  step using its own predictions.
* Record model name, metrics and version so every number shown in the product
  can be audited later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ai.forecasting.baselines import (
    moving_average_forecast,
    seasonal_naive_forecast,
)
from ai.forecasting.features import (
    FEATURE_COLUMNS,
    build_training_frame,
    make_feature_row,
)
from ai.forecasting.metrics import mae, rmse, wape

MODEL_VERSION = "v1.0"
MIN_HISTORY_DAYS = 28
VALIDATION_DAYS = 28
MIN_ML_IMPROVEMENT = 0.02  # ML must cut MAE by >= 2% vs. the best baseline


@dataclass
class ForecastResult:
    daily_series: list[float]
    predicted_qty: float
    model_name: str
    model_version: str = MODEL_VERSION
    mae: float | None = None
    rmse: float | None = None
    wape: float | None = None
    baseline_mae: float | None = None
    confidence: str = "low"
    trained_until: str | None = None
    notes: list[str] = field(default_factory=list)


def _make_regressor():
    try:  # LightGBM is optional, faster and usually slightly more accurate.
        from lightgbm import LGBMRegressor

        return (
            LGBMRegressor(
                n_estimators=250,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=5,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=1.0,
                verbose=-1,
                random_state=42,
            ),
            "lightgbm",
        )
    except Exception:  # pragma: no cover - depends on optional install
        from sklearn.ensemble import HistGradientBoostingRegressor

        return (
            HistGradientBoostingRegressor(
                max_iter=160,
                learning_rate=0.08,
                max_leaf_nodes=15,
                min_samples_leaf=4,
                l2_regularization=1.0,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=8,
                random_state=42,
            ),
            "hist_gradient_boosting",
        )


def _train_gb(series: pd.DataFrame):
    frame = build_training_frame(series)
    if len(frame) < 14:
        return None, None
    model, library = _make_regressor()
    model.fit(frame[FEATURE_COLUMNS], frame["y"].clip(lower=0))
    return model, library


def _recursive_gb_forecast(
    model, history: np.ndarray, last_date: pd.Timestamp, horizon: int
) -> np.ndarray:
    working = list(history.astype(float))
    predictions: list[float] = []
    for step in range(1, horizon + 1):
        target_date = last_date + pd.Timedelta(days=step)
        row = make_feature_row(np.asarray(working), target_date)
        value = float(model.predict(pd.DataFrame([row])[FEATURE_COLUMNS])[0])
        value = max(value, 0.0)
        predictions.append(value)
        working.append(value)
    return np.asarray(predictions, dtype=float)


def _confidence(history_days: int, error: float | None) -> str:
    if history_days < MIN_HISTORY_DAYS:
        return "low"
    if error is None:
        return "medium" if history_days >= 60 else "low"
    if history_days >= 60 and error <= 0.30:
        return "high"
    if error <= 0.60:
        return "medium"
    return "low"


def forecast_series(series: pd.DataFrame, horizon: int = 30) -> ForecastResult:
    """Forecast ``horizon`` days for one product/warehouse daily demand series."""
    if series is None or len(series) == 0:
        return ForecastResult([0.0] * horizon, 0.0, "none", confidence="low",
                              notes=["Không có dữ liệu bán hàng."])

    series = series.sort_values("date").reset_index(drop=True)
    values = series["y"].to_numpy(dtype=float)
    last_date = pd.to_datetime(series["date"].iloc[-1])
    history_days = len(values)
    notes: list[str] = []

    if values.sum() == 0:
        return ForecastResult([0.0] * horizon, 0.0, "zero_demand", confidence="low",
                              trained_until=last_date.date().isoformat(),
                              notes=["SKU không phát sinh bán trong lịch sử."])

    if history_days < MIN_HISTORY_DAYS:
        values_series = moving_average_forecast(values, horizon, window=7)
        return ForecastResult(
            daily_series=[round(float(v), 2) for v in values_series],
            predicted_qty=round(float(values_series.sum()), 2),
            model_name="moving_average",
            confidence="low",
            trained_until=last_date.date().isoformat(),
            notes=[f"Chỉ có {history_days} ngày dữ liệu (< {MIN_HISTORY_DAYS}); dùng baseline."],
        )

    validation_days = min(VALIDATION_DAYS, max(7, history_days // 4))
    cutoff = history_days - validation_days
    train_values = values[:cutoff]
    actual = values[cutoff:]
    train_series = series.iloc[:cutoff].copy()

    candidates: dict[str, tuple[np.ndarray | None, object | None]] = {}
    candidates["moving_average"] = (
        moving_average_forecast(train_values, validation_days, window=7),
        None,
    )
    candidates["seasonal_naive"] = (
        seasonal_naive_forecast(train_values, validation_days, season=7),
        None,
    )

    gb_model, gb_library = _train_gb(train_series)
    gb_errors: np.ndarray | None = None
    if gb_model is not None:
        gb_errors = _recursive_gb_forecast(
            gb_model, train_values, pd.to_datetime(train_series["date"].iloc[-1]), validation_days
        )
        candidates[f"gbm_{gb_library}"] = (gb_errors, gb_model)

    scores = {
        name: mae(actual, pred)
        for name, (pred, _) in candidates.items()
        if pred is not None
    }
    best_baseline = min(
        scores.get("moving_average", np.inf), scores.get("seasonal_naive", np.inf)
    )
    best_model_name = min(scores, key=scores.get)
    best_model = candidates[best_model_name][1]

    # Guardrail: keep the explainable baseline unless ML clearly wins.
    gb_names = [name for name in scores if name.startswith("gbm_")]
    if gb_names:
        gb_name = min(gb_names, key=lambda name: scores[name])
        if scores[gb_name] < best_baseline * (1 - MIN_ML_IMPROVEMENT):
            best_model_name = gb_name
            best_model = candidates[gb_name][1]
        else:
            best_model_name = (
                "moving_average"
                if scores.get("moving_average", np.inf) <= scores.get("seasonal_naive", np.inf)
                else "seasonal_naive"
            )
            best_model = None
            notes.append("Mô hình ML không vượt baseline đủ 2%; giữ baseline.")

    if best_model is None and best_model_name == "seasonal_naive":
        final_values = seasonal_naive_forecast(values, horizon, season=7)
    elif best_model is None:
        final_values = moving_average_forecast(values, horizon, window=7)
    else:
        # Refit on the full history (including the validation window) before the
        # final forecast so the deployed model uses all available data.
        best_model, _ = _train_gb(series)
        if best_model is None:  # extremely defensive: series shrank between fits
            final_values = moving_average_forecast(values, horizon, window=7)
            best_model_name = "moving_average"
        else:
            final_values = _recursive_gb_forecast(best_model, values, last_date, horizon)

    val_pred = candidates.get(best_model_name, (None, None))[0]
    if val_pred is None:
        val_pred = candidates["seasonal_naive"][0]

    error_wape = wape(actual, val_pred)
    return ForecastResult(
        daily_series=[round(float(max(v, 0)), 2) for v in final_values],
        predicted_qty=round(float(np.clip(final_values, 0, None).sum()), 2),
        model_name=best_model_name,
        mae=round(mae(actual, val_pred), 4),
        rmse=round(rmse(actual, val_pred), 4),
        wape=None if error_wape is None else round(error_wape, 4),
        baseline_mae=round(float(best_baseline), 4) if np.isfinite(best_baseline) else None,
        confidence=_confidence(history_days, error_wape),
        trained_until=last_date.date().isoformat(),
        notes=notes,
    )
