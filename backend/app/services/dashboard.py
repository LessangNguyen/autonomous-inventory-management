"""Dashboard aggregation used by the UI and the agent overview tool."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Forecast,
    InventorySnapshot,
    Product,
    PurchaseOrder,
    ReplenishmentRecommendation,
    SalesItem,
    SalesTransaction,
    Warehouse,
)
from app.services.common import default_warehouse, effective_inventory_map

RISK_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _revenue_between(db: Session, tenant_id: int, start: date, end: date) -> tuple[float, float]:
    revenue = (
        db.query(func.coalesce(func.sum(SalesTransaction.total_amount), 0.0))
        .filter(
            SalesTransaction.tenant_id == tenant_id,
            SalesTransaction.occurred_at >= start,
            SalesTransaction.occurred_at < end,
        )
        .scalar()
        or 0.0
    )
    units = (
        db.query(func.coalesce(func.sum(SalesItem.quantity), 0.0))
        .join(SalesTransaction, SalesItem.transaction_id == SalesTransaction.id)
        .filter(
            SalesTransaction.tenant_id == tenant_id,
            SalesTransaction.occurred_at >= start,
            SalesTransaction.occurred_at < end,
        )
        .scalar()
        or 0.0
    )
    return float(revenue), float(units)


def latest_recommendations(db: Session, tenant_id: int) -> list[ReplenishmentRecommendation]:
    subquery = (
        db.query(
            ReplenishmentRecommendation.product_id,
            func.max(ReplenishmentRecommendation.id).label("max_id"),
        )
        .filter(ReplenishmentRecommendation.tenant_id == tenant_id)
        .group_by(ReplenishmentRecommendation.product_id)
        .subquery()
    )
    return (
        db.query(ReplenishmentRecommendation)
        .join(subquery, ReplenishmentRecommendation.id == subquery.c.max_id)
        .all()
    )


def build_summary(db: Session, tenant_id: int) -> dict:
    today = date.today()
    revenue_30, units_30 = _revenue_between(db, tenant_id, today - timedelta(days=30), today + timedelta(days=1))
    revenue_prev, _ = _revenue_between(
        db, tenant_id, today - timedelta(days=60), today - timedelta(days=30)
    )
    revenue_delta = round((revenue_30 - revenue_prev) / revenue_prev * 100, 1) if revenue_prev else None

    inventory = effective_inventory_map(db, tenant_id)
    products = {product.id: product for product in db.query(Product).filter(Product.tenant_id == tenant_id).all()}
    stock_value = sum(
        snapshot.on_hand * (products[product_id].unit_cost if product_id in products else 0)
        for (product_id, _), snapshot in inventory.items()
    )
    on_hand_total = sum(snapshot.on_hand for snapshot in inventory.values())

    recommendations = latest_recommendations(db, tenant_id)
    risk_rows = [row for row in recommendations if row.stockout_risk in {"critical", "high"}]
    need_order = [row for row in recommendations if row.suggested_qty > 0]
    avg_days = (
        sum(row.days_of_inventory for row in recommendations if row.days_of_inventory is not None)
        / max(1, len([row for row in recommendations if row.days_of_inventory is not None]))
        if recommendations
        else 0
    )

    alerts_open = db.query(Alert).filter(Alert.tenant_id == tenant_id, Alert.status == "open").count()
    pending_orders = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.status.in_(["draft", "pending_approval"]))
        .count()
    )
    last_forecast = (
        db.query(func.max(Forecast.created_at)).filter(Forecast.tenant_id == tenant_id).scalar()
    )

    trend_rows = (
        db.query(
            func.date(SalesTransaction.occurred_at).label("day"),
            func.coalesce(func.sum(SalesTransaction.total_amount), 0.0).label("revenue"),
            func.coalesce(func.sum(SalesItem.quantity), 0.0).label("units"),
        )
        .join(SalesItem, SalesItem.transaction_id == SalesTransaction.id)
        .filter(
            SalesTransaction.tenant_id == tenant_id,
            SalesTransaction.occurred_at >= today - timedelta(days=29),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    by_day = {str(row.day): (float(row.revenue), float(row.units)) for row in trend_rows}
    sales_trend = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        revenue, units = by_day.get(day.isoformat(), (0.0, 0.0))
        sales_trend.append({"date": day, "revenue": round(revenue, 2), "units": round(units, 2)})

    ranked = sorted(
        recommendations,
        key=lambda row: (RISK_PRIORITY.get(row.stockout_risk, 0), row.suggested_qty),
        reverse=True,
    )[:6]
    top_risks = []
    for row in ranked:
        product = products.get(row.product_id)
        snapshot = inventory.get((row.product_id, row.warehouse_id))
        top_risks.append(
            {
                "product_id": row.product_id,
                "sku": product.sku if product else f"#{row.product_id}",
                "product_name": product.name if product else "",
                "on_hand": round(snapshot.on_hand, 2) if snapshot else 0.0,
                "days_of_inventory": row.days_of_inventory,
                "stockout_risk": row.stockout_risk,
                "suggested_qty": row.suggested_qty,
            }
        )

    return {
        "kpis": [
            {
                "label": "Doanh thu 30 ngày",
                "value": round(revenue_30, 0),
                "unit": "đ",
                "delta_pct": revenue_delta,
                "hint": f"{units_30:,.0f} sản phẩm đã bán",
            },
            {
                "label": "Giá trị tồn kho",
                "value": round(stock_value, 0),
                "unit": "đ",
                "hint": f"{on_hand_total:,.0f} đơn vị trong kho",
            },
            {
                "label": "SKU cần nhập",
                "value": float(len(need_order)),
                "unit": "SKU",
                "hint": f"{len(risk_rows)} SKU nguy cơ hết hàng",
            },
            {
                "label": "Ngày tồn kho TB",
                "value": round(avg_days, 1),
                "unit": "ngày",
                "hint": "Trung bình theo SKU có dự báo",
            },
        ],
        "sales_trend": sales_trend,
        "top_risks": top_risks,
        "open_alerts": alerts_open,
        "pending_orders": pending_orders,
        "last_forecast_at": last_forecast,
        "total_products": len(products),
    }


def overview_text(summary: dict) -> str:
    kpis = {card["label"]: card for card in summary["kpis"]}
    revenue = kpis.get("Doanh thu 30 ngày", {})
    stock = kpis.get("Giá trị tồn kho", {})
    need = kpis.get("SKU cần nhập", {})
    lines = [
        "**Tổng quan cửa hàng**",
        f"- Doanh thu 30 ngày: {revenue.get('value', 0):,.0f} đ",
        f"- Giá trị tồn kho: {stock.get('value', 0):,.0f} đ",
        f"- SKU cần nhập: {need.get('value', 0):.0f}",
        f"- Cảnh báo đang mở: {summary['open_alerts']}",
        f"- Đơn nhập chờ xử lý: {summary['pending_orders']}",
    ]
    if summary["top_risks"]:
        lines.append("\n**SKU rủi ro cao nhất**")
        for risk in summary["top_risks"][:5]:
            days = risk["days_of_inventory"]
            days_text = f"{days:.0f} ngày tồn" if days is not None else "chưa đủ dữ liệu"
            lines.append(
                f"- {risk['sku']} ({risk['product_name']}): tồn {risk['on_hand']:.0f}, "
                f"{days_text}, đề xuất nhập {risk['suggested_qty']:.0f} (rủi ro {risk['stockout_risk']})"
            )
    return "\n".join(lines)
