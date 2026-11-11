"""Anomaly detection for demand and stock signals.

Rules run first because they are explainable to a store owner. Isolation Forest
is used as a second opinion on the same series, and every flag is advisory: a
human still decides whether it is a data error, a promotion or a real trend.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Anomaly:
    date: str
    value: float
    severity: str  # info | warning | critical
    reason: str
    method: str


def _rule_anomalies(series: pd.DataFrame, z_threshold: float = 3.0) -> list[Anomaly]:
    if len(series) < 14:
        return []
    frame = series.copy()
    frame["dow"] = pd.to_datetime(frame["date"]).dt.dayofweek
    frame["expected"] = (
        frame.groupby("dow")["y"].transform(lambda values: values.shift(1).rolling(4, min_periods=2).mean())
    )
    frame["expected"] = frame["expected"].fillna(frame["y"].rolling(7, min_periods=3).mean())
    std = frame["y"].std(ddof=0) or 1.0
    frame["z"] = (frame["y"] - frame["expected"]) / std

    anomalies: list[Anomaly] = []
    for _, row in frame.tail(90).iterrows():
        if pd.isna(row["expected"]):
            continue
        if abs(row["z"]) < z_threshold:
            continue
        severity = "warning" if abs(row["z"]) < z_threshold * 1.5 else "critical"
        direction = "tăng" if row["z"] > 0 else "giảm"
        anomalies.append(
            Anomaly(
                date=pd.Timestamp(row["date"]).date().isoformat(),
                value=round(float(row["y"]), 2),
                severity=severity,
                reason=(
                    f"Doanh số {direction} bất thường so với cùng thứ trong tuần "
                    f"(z={row['z']:.1f}). Cần kiểm tra khuyến mãi, nhập liệu hoặc mất đơn."
                ),
                method="rule_zscore",
            )
        )
    return anomalies[-10:]


def _isolation_forest_anomalies(series: pd.DataFrame) -> list[Anomaly]:
    if len(series) < 30:
        return []
    try:
        from sklearn.ensemble import IsolationForest
    except Exception:  # pragma: no cover
        return []

    frame = series.copy().reset_index(drop=True)
    frame["dow"] = pd.to_datetime(frame["date"]).dt.dayofweek
    frame["roll_mean"] = frame["y"].rolling(7, min_periods=3).mean()
    frame["roll_std"] = frame["y"].rolling(7, min_periods=3).std().fillna(0)
    features = frame[["y", "dow", "roll_mean", "roll_std"]].fillna(0)

    model = IsolationForest(contamination=0.05, random_state=42)
    flags = model.fit_predict(features)
    anomalies: list[Anomaly] = []
    for index in np.where(flags == -1)[0][-5:]:
        row = frame.iloc[index]
        anomalies.append(
            Anomaly(
                date=pd.Timestamp(row["date"]).date().isoformat(),
                value=round(float(row["y"]), 2),
                severity="info",
                reason="Mẫu bán hàng khác biệt so với phần còn lại của chuỗi (Isolation Forest).",
                method="isolation_forest",
            )
        )
    return anomalies


def detect(series: pd.DataFrame) -> list[Anomaly]:
    """Return de-duplicated anomalies, newest first, rules taking precedence."""
    anomalies = _rule_anomalies(series)
    known = {(item.date, item.method) for item in anomalies}
    for item in _isolation_forest_anomalies(series):
        if (item.date, item.method) not in known:
            anomalies.append(item)
    return sorted(anomalies, key=lambda item: item.date, reverse=True)[:12]
