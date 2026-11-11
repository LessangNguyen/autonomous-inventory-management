"""Feature engineering for daily SKU demand forecasting."""

from __future__ import annotations

import numpy as np
import pandas as pd

LAGS = (1, 7, 14, 28)
ROLLING_WINDOWS = (7, 28)
FEATURE_COLUMNS = [
    *[f"lag_{lag}" for lag in LAGS],
    *[f"roll_mean_{window}" for window in ROLLING_WINDOWS],
    "dow",
    "month",
    "day",
    "is_weekend",
    "promo",
]


def fill_daily_series(dates: pd.Series, values: pd.Series) -> pd.DataFrame:
    """Aggregate raw transactions to a gap-free daily series (missing day = 0)."""
    frame = pd.DataFrame(
        {"date": pd.to_datetime(dates).dt.normalize(), "y": values.astype(float)}
    )
    frame = frame.groupby("date", as_index=False)["y"].sum()
    if frame.empty:
        return pd.DataFrame(columns=["date", "y"])
    full_range = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")
    frame = frame.set_index("date").reindex(full_range, fill_value=0.0).reset_index()
    frame = frame.rename(columns={"index": "date"})
    frame["y"] = frame["y"].clip(lower=0)
    return frame


def build_training_frame(series: pd.DataFrame) -> pd.DataFrame:
    """Turn a gap-free daily series into a supervised learning table."""
    values = series["y"].to_numpy(dtype=float)
    dates = pd.to_datetime(series["date"])

    rows: list[dict] = []
    for i in range(len(values)):
        if i < max(LAGS):
            continue
        row = {f"lag_{lag}": values[i - lag] for lag in LAGS}
        for window in ROLLING_WINDOWS:
            row[f"roll_mean_{window}"] = float(np.mean(values[i - window : i]))
        row["dow"] = int(dates.iloc[i].dayofweek)
        row["month"] = int(dates.iloc[i].month)
        row["day"] = int(dates.iloc[i].day)
        row["is_weekend"] = int(dates.iloc[i].dayofweek >= 5)
        row["promo"] = float(series["promo"].iloc[i]) if "promo" in series else 0.0
        out_row = dict(row)
        out_row["y"] = values[i]
        out_row["date"] = dates.iloc[i]
        rows.append(out_row)

    return pd.DataFrame(rows)


def make_feature_row(history: np.ndarray, target_date: pd.Timestamp, promo: float = 0.0) -> dict:
    """Build the feature row for a single future day from observed + predicted values."""
    index = len(history)
    row = {f"lag_{lag}": float(history[index - lag]) for lag in LAGS}
    for window in ROLLING_WINDOWS:
        row[f"roll_mean_{window}"] = float(np.mean(history[index - window : index]))
    row["dow"] = int(target_date.dayofweek)
    row["month"] = int(target_date.month)
    row["day"] = int(target_date.day)
    row["is_weekend"] = int(target_date.dayofweek >= 5)
    row["promo"] = promo
    return row
