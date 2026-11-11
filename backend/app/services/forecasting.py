"""Forecasting orchestration: build series from the database, run the model,
persist auditable forecast rows."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Forecast, Product
from app.services.common import daily_sales, default_warehouse, effective_inventory_map
from ai.forecasting.engine import MODEL_VERSION, forecast_series


def run_forecasts(
    db: Session,
    tenant_id: int,
    horizon_days: int = 30,
    product_ids: list[int] | None = None,
    history_days: int = 180,
) -> dict:
    started = time.perf_counter()
    warehouse = default_warehouse(db, tenant_id)
    if warehouse is None:
        return {
            "products_processed": 0,
            "products_skipped": 0,
            "horizon_days": horizon_days,
            "model_version": MODEL_VERSION,
            "avg_mae": None,
            "avg_wape": None,
            "baseline_avg_mae": None,
            "improvement_pct": None,
            "duration_ms": 0,
            "notes": ["Chưa có kho. Hãy import dữ liệu hoặc tạo kho trước."],
        }

    query = db.query(Product).filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
    if product_ids:
        query = query.filter(Product.id.in_(product_ids))
    products = query.order_by(Product.id.asc()).all()

    inventories = effective_inventory_map(db, tenant_id, warehouse.id)
    processed = 0
    skipped = 0
    maes: list[float] = []
    wapes: list[float] = []
    baseline_maes: list[float] = []
    notes: list[str] = []

    for product in products:
        series = daily_sales(db, tenant_id, product.id, warehouse.id, history_days)
        if series.empty or len(series) < 7:
            skipped += 1
            notes.append(f"{product.sku}: không đủ dữ liệu bán hàng.")
            continue
        result = forecast_series(series, horizon=horizon_days)
        record = Forecast(
            tenant_id=tenant_id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            horizon_days=horizon_days,
            predicted_qty=result.predicted_qty,
            daily_series=result.daily_series,
            model_name=result.model_name,
            model_version=result.model_version,
            mae=result.mae,
            rmse=result.rmse,
            wape=result.wape,
            baseline_mae=result.baseline_mae,
            confidence=result.confidence,
            trained_until=series["date"].max().date(),
        )
        db.add(record)
        processed += 1
        if result.mae is not None:
            maes.append(result.mae)
        if result.wape is not None:
            wapes.append(result.wape)
        if result.baseline_mae is not None:
            baseline_maes.append(result.baseline_mae)
        if result.notes:
            notes.extend(f"{product.sku}: {note}" for note in result.notes)

    # Keep stale inventory rows out of the way and store a fresh snapshot baseline
    # only if the tenant has never imported inventory at all.
    if not inventories and processed:
        notes.append("Chưa có tồn kho; đề xuất nhập hàng sẽ dùng tồn kho = 0.")

    db.commit()
    duration = int((time.perf_counter() - started) * 1000)
    avg_mae = round(sum(maes) / len(maes), 4) if maes else None
    baseline_avg = round(sum(baseline_maes) / len(baseline_maes), 4) if baseline_maes else None
    improvement = None
    if avg_mae is not None and baseline_avg and baseline_avg > 0:
        improvement = round((baseline_avg - avg_mae) / baseline_avg * 100, 2)

    return {
        "products_processed": processed,
        "products_skipped": skipped,
        "horizon_days": horizon_days,
        "model_version": MODEL_VERSION,
        "avg_mae": avg_mae,
        "avg_wape": round(sum(wapes) / len(wapes), 4) if wapes else None,
        "baseline_avg_mae": baseline_avg,
        "improvement_pct": improvement,
        "duration_ms": duration,
        "notes": notes[:20],
    }
