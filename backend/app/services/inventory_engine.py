"""Inventory decision engine.

Formulas (documented in docs/MODEL_EVALUATION.md):

    safety_stock      = z(service_level) * sigma_daily * sqrt(lead_time)
    reorder_point     = avg_daily * lead_time + safety_stock
    inventory_position= on_hand + on_order - committed
    target_stock      = avg_daily * (lead_time + review_period) + safety_stock
    suggested_qty     = round_up(max(0, target - position), order_multiple)

Business constraints applied afterwards: MOQ, packing multiple, on-order stock
and committed stock. Perishable/budget constraints are out of scope for MVP.
"""

from __future__ import annotations

import math
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Alert,
    InventorySnapshot,
    Product,
    ReplenishmentRecommendation,
)
from app.services.common import (
    daily_sales,
    default_warehouse,
    effective_inventory_map,
    latest_forecast_map,
)

_Z_TABLE = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.96, 0.98: 2.0537, 0.99: 2.3263}


def z_value(service_level: float) -> float:
    if service_level in _Z_TABLE:
        return _Z_TABLE[service_level]
    try:  # scipy ships with scikit-learn, so this normally succeeds
        from scipy.stats import norm

        return float(norm.ppf(service_level))
    except Exception:
        return 1.6449


def round_up_to_multiple(value: float, multiple: int) -> float:
    if multiple is None or multiple <= 1:
        return math.ceil(value)
    return float(math.ceil(value / multiple) * multiple)


def compute_recommendation(
    *,
    avg_daily_demand: float,
    demand_std: float,
    lead_time_days: int,
    on_hand: float,
    on_order: float,
    committed: float,
    service_level: float,
    review_period_days: int,
    moq: int = 1,
    order_multiple: int = 1,
) -> dict:
    avg_daily_demand = max(float(avg_daily_demand), 0.0)
    lead_time_days = max(int(lead_time_days), 1)
    safety_stock = z_value(service_level) * demand_std * math.sqrt(lead_time_days)
    reorder_point = avg_daily_demand * lead_time_days + safety_stock
    inventory_position = on_hand + on_order - committed
    target_stock = avg_daily_demand * (lead_time_days + review_period_days) + safety_stock
    raw_quantity = max(0.0, target_stock - inventory_position)

    suggested_qty = 0.0
    if raw_quantity > 0:
        suggested_qty = round_up_to_multiple(raw_quantity, order_multiple)
        suggested_qty = max(suggested_qty, float(moq or 1))

    days_of_inventory = (
        round(on_hand / avg_daily_demand, 1) if avg_daily_demand > 0 else None
    )

    if inventory_position <= 0:
        risk = "critical"
    elif avg_daily_demand > 0 and (days_of_inventory or 0) < lead_time_days:
        risk = "critical"
    elif inventory_position < reorder_point:
        risk = "high"
    elif (
        avg_daily_demand > 0
        and (days_of_inventory or 0) < lead_time_days + review_period_days
    ):
        risk = "medium"
    else:
        risk = "low"

    return {
        "avg_daily_demand": round(avg_daily_demand, 3),
        "demand_std": round(demand_std, 3),
        "lead_time_days": lead_time_days,
        "safety_stock": round(safety_stock, 2),
        "reorder_point": round(reorder_point, 2),
        "inventory_position": round(inventory_position, 2),
        "target_stock": round(target_stock, 2),
        "suggested_qty": round(suggested_qty, 2),
        "days_of_inventory": days_of_inventory,
        "stockout_risk": risk,
    }


def _upsert_alerts(db: Session, tenant_id: int, alerts: list[dict]) -> None:
    for item in alerts:
        exists = (
            db.query(Alert.id)
            .filter(
                Alert.tenant_id == tenant_id,
                Alert.type == item["type"],
                Alert.status == "open",
                Alert.product_id == item.get("product_id"),
            )
            .first()
        )
        if exists:
            continue
        db.add(Alert(tenant_id=tenant_id, **item))


def run_recommendations(db: Session, tenant_id: int) -> dict:
    started = time.perf_counter()
    warehouse = default_warehouse(db, tenant_id)
    if warehouse is None:
        return {"generated": 0, "critical": 0, "high": 0, "duration_ms": 0}

    products = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
        .all()
    )
    inventory = effective_inventory_map(db, tenant_id, warehouse.id)
    forecasts = latest_forecast_map(db, tenant_id)

    # Recompute the open snapshot; keep ordered/dismissed rows as decision history.
    db.query(ReplenishmentRecommendation).filter(
        ReplenishmentRecommendation.tenant_id == tenant_id,
        ReplenishmentRecommendation.status == "open",
    ).delete(synchronize_session=False)

    generated = critical = high = 0
    alerts: list[dict] = []

    for product in products:
        snapshot = inventory.get((product.id, warehouse.id))
        forecast = forecasts.get(product.id)
        history = daily_sales(db, tenant_id, product.id, warehouse.id, settings.forecast_history_days)

        if forecast and forecast.daily_series:
            series = [float(value) for value in forecast.daily_series]
            avg_daily = sum(series) / len(series)
            mean = avg_daily
            variance = sum((value - mean) ** 2 for value in series) / len(series)
            demand_std = math.sqrt(variance)
        elif not history.empty:
            values = history["y"].astype(float)
            avg_daily = float(values.mean())
            demand_std = float(values.std(ddof=0))
        else:
            continue

        if avg_daily <= 0 and (snapshot is None or snapshot.on_hand <= 0):
            continue

        on_hand = float(snapshot.on_hand) if snapshot else 0.0
        on_order = float(snapshot.on_order) if snapshot else 0.0
        committed = float(snapshot.committed) if snapshot else 0.0
        lead_time = product.lead_time_days or (
            product.supplier.lead_time_days if product.supplier else settings.default_lead_time_days
        )
        moq = product.moq or (product.supplier.moq if product.supplier else settings.default_moq)
        multiple = product.order_multiple or (
            product.supplier.order_multiple if product.supplier else settings.default_order_multiple
        )

        result = compute_recommendation(
            avg_daily_demand=avg_daily,
            demand_std=demand_std,
            lead_time_days=lead_time,
            on_hand=on_hand,
            on_order=on_order,
            committed=committed,
            service_level=settings.service_level,
            review_period_days=settings.review_period_days,
            moq=moq,
            order_multiple=multiple,
        )

        db.add(
            ReplenishmentRecommendation(
                tenant_id=tenant_id,
                product_id=product.id,
                warehouse_id=warehouse.id,
                avg_daily_demand=result["avg_daily_demand"],
                demand_std=result["demand_std"],
                lead_time_days=result["lead_time_days"],
                safety_stock=result["safety_stock"],
                reorder_point=result["reorder_point"],
                inventory_position=result["inventory_position"],
                target_stock=result["target_stock"],
                suggested_qty=result["suggested_qty"],
                days_of_inventory=result["days_of_inventory"],
                stockout_risk=result["stockout_risk"],
            )
        )
        generated += 1
        if result["stockout_risk"] == "critical":
            critical += 1
            alerts.append(
                {
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "type": "stockout_risk",
                    "severity": "critical",
                    "message": (
                        f"{product.sku} có nguy cơ hết hàng: tồn khả dụng "
                        f"{result['inventory_position']:.0f}, ROP {result['reorder_point']:.0f}."
                    ),
                }
            )
        elif result["stockout_risk"] == "high":
            high += 1
            alerts.append(
                {
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "type": "stockout_risk",
                    "severity": "warning",
                    "message": (
                        f"{product.sku} dưới điểm đặt hàng lại "
                        f"({result['inventory_position']:.0f} < {result['reorder_point']:.0f})."
                    ),
                }
            )
        if (
            result["days_of_inventory"] is not None
            and result["days_of_inventory"] > 90
            and on_hand > 0
        ):
            alerts.append(
                {
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "type": "overstock",
                    "severity": "info",
                    "message": (
                        f"{product.sku} tồn kho {result['days_of_inventory']:.0f} ngày bán — "
                        "cân nhắc giảm nhập hoặc xử lý hàng chậm luân chuyển."
                    ),
                }
            )

    _upsert_alerts(db, tenant_id, alerts)
    db.commit()
    return {
        "generated": generated,
        "critical": critical,
        "high": high,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def run_anomaly_detection(db: Session, tenant_id: int) -> int:
    """Detect unusual daily sales and raise advisory alerts."""
    from ai.anomaly_detection.detector import detect

    warehouse = default_warehouse(db, tenant_id)
    products = db.query(Product).filter(Product.tenant_id == tenant_id).all()
    created = 0
    for product in products:
        history = daily_sales(db, tenant_id, product.id, warehouse.id if warehouse else None, 120)
        if history.empty or len(history) < 21:
            continue
        for anomaly in detect(history)[:2]:
            exists = (
                db.query(Alert.id)
                .filter(
                    Alert.tenant_id == tenant_id,
                    Alert.product_id == product.id,
                    Alert.type == "anomaly",
                    Alert.status == "open",
                )
                .first()
            )
            if exists:
                break
            db.add(
                Alert(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    warehouse_id=warehouse.id if warehouse else None,
                    type="anomaly",
                    severity=anomaly.severity,
                    message=f"{product.sku} ngày {anomaly.date}: {anomaly.reason}",
                )
            )
            created += 1
    db.commit()
    return created
