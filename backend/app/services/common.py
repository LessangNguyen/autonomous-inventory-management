"""Shared query helpers used by forecasting, the decision engine and the agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesItem,
    SalesTransaction,
    Warehouse,
)
from ai.forecasting.features import fill_daily_series


def default_warehouse(db: Session, tenant_id: int) -> Warehouse | None:
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.tenant_id == tenant_id)
        .order_by(Warehouse.is_default.desc(), Warehouse.id.asc())
        .first()
    )
    return warehouse


def get_or_create_warehouse(
    db: Session, tenant_id: int, code: str | None, name: str | None = None
) -> Warehouse:
    code = (code or "MAIN").strip().upper()
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.tenant_id == tenant_id, Warehouse.code == code)
        .first()
    )
    if warehouse:
        return warehouse
    is_first = db.query(Warehouse).filter(Warehouse.tenant_id == tenant_id).count() == 0
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=code,
        name=name or ("Kho chính" if is_first else f"Kho {code}"),
        is_default=is_first,
    )
    db.add(warehouse)
    db.flush()
    return warehouse


def find_product(db: Session, tenant_id: int, query: str | None) -> Product | None:
    if not query:
        return None
    cleaned = query.strip()
    product = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id, func.lower(Product.sku) == cleaned.lower())
        .first()
    )
    if product:
        return product
    return (
        db.query(Product)
        .filter(
            Product.tenant_id == tenant_id,
            func.lower(Product.name).like(f"%{cleaned.lower()}%"),
        )
        .order_by(Product.id.asc())
        .first()
    )


def latest_inventory_map(
    db: Session, tenant_id: int, warehouse_id: int | None = None
) -> dict[tuple[int, int], InventorySnapshot]:
    """Latest physical stock count per (product, warehouse).

    This is the raw imported baseline. Use :func:`effective_inventory_map` for
    the current stock position, which also applies receipts and sales.
    """
    query = db.query(InventorySnapshot).filter(InventorySnapshot.tenant_id == tenant_id)
    if warehouse_id is not None:
        query = query.filter(InventorySnapshot.warehouse_id == warehouse_id)
    rows = query.order_by(InventorySnapshot.snapshot_date.asc(), InventorySnapshot.id.asc()).all()
    latest: dict[tuple[int, int], InventorySnapshot] = {}
    for row in rows:
        latest[(row.product_id, row.warehouse_id)] = row
    return latest


@dataclass(frozen=True)
class EffectiveInventory:
    """Current stock position derived from a physical count plus movements.

    ``on_hand = opening_on_hand + received_since - sold_since``

    The physical count is the anchor: it is the only value the system cannot
    derive, because absolute stock needs one real-world observation. Every
    movement after the count is applied automatically:

    * received purchase orders (status ``received``), and
    * imported / recorded sales.

    The count date is treated as the opening balance at the start of that day,
    so movements recorded on or after it are included. A newer count replaces
    the previous anchor. See docs/DATA_DICTIONARY.md.
    """

    product_id: int
    warehouse_id: int
    opening_on_hand: float
    received_since: float
    sold_since: float
    on_hand: float
    on_order: float
    committed: float
    snapshot_date: date | None
    has_opening_count: bool

    @property
    def available(self) -> float:
        return self.on_hand + self.on_order - self.committed


def _as_date(value: object) -> date | None:
    """Normalise ``func.date(...)`` results across SQLite/PostgreSQL drivers."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def effective_inventory_map(
    db: Session, tenant_id: int, warehouse_id: int | None = None
) -> dict[tuple[int, int], EffectiveInventory]:
    """Derived on-hand per (product, warehouse).

    Inventory is *calculated*, not imported on every change:
    the latest physical count is rolled forward by received purchase orders and
    by sales. Products without any count appear with an opening balance of 0 and
    ``has_opening_count=False`` so the UI can flag the data-quality gap.
    """
    snapshots = latest_inventory_map(db, tenant_id, warehouse_id)
    default_wh = default_warehouse(db, tenant_id)
    default_wh_id = default_wh.id if default_wh else None

    # (product, warehouse, day) -> quantity received
    received: dict[tuple[int, int, date], float] = {}
    received_query = (
        db.query(
            PurchaseOrderItem.product_id,
            PurchaseOrder.warehouse_id,
            func.date(PurchaseOrder.received_at),
            func.coalesce(func.sum(PurchaseOrderItem.quantity), 0.0),
        )
        .join(PurchaseOrder, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.status == "received",
            PurchaseOrder.received_at.isnot(None),
        )
    )
    if warehouse_id is not None:
        received_query = received_query.filter(PurchaseOrder.warehouse_id == warehouse_id)
    for product_id, wh_id, day, quantity in received_query.group_by(
        PurchaseOrderItem.product_id, PurchaseOrder.warehouse_id, func.date(PurchaseOrder.received_at)
    ).all():
        moved_on = _as_date(day)
        if moved_on is not None and wh_id is not None:
            received[(product_id, wh_id, moved_on)] = float(quantity or 0)

    # (product, warehouse, day) -> quantity sold
    sold: dict[tuple[int, int, date], float] = {}
    sold_query = (
        db.query(
            SalesItem.product_id,
            SalesTransaction.warehouse_id,
            func.date(SalesTransaction.occurred_at),
            func.coalesce(func.sum(SalesItem.quantity), 0.0),
        )
        .join(SalesTransaction, SalesItem.transaction_id == SalesTransaction.id)
        .filter(SalesTransaction.tenant_id == tenant_id)
    )
    for product_id, wh_id, day, quantity in sold_query.group_by(
        SalesItem.product_id, SalesTransaction.warehouse_id, func.date(SalesTransaction.occurred_at)
    ).all():
        moved_on = _as_date(day)
        target_wh = wh_id if wh_id is not None else default_wh_id
        if moved_on is None or target_wh is None:
            continue
        if warehouse_id is not None and target_wh != warehouse_id:
            continue
        sold[(product_id, target_wh, moved_on)] = float(quantity or 0)

    # Open purchase orders = ordered but not yet received ("đang về").
    open_orders: dict[tuple[int, int], float] = {}
    open_query = (
        db.query(
            PurchaseOrderItem.product_id,
            PurchaseOrder.warehouse_id,
            func.coalesce(func.sum(PurchaseOrderItem.quantity), 0.0),
        )
        .join(PurchaseOrder, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.status.in_(("draft", "pending_approval", "approved")),
        )
    )
    if warehouse_id is not None:
        open_query = open_query.filter(PurchaseOrder.warehouse_id == warehouse_id)
    for product_id, wh_id, quantity in open_query.group_by(
        PurchaseOrderItem.product_id, PurchaseOrder.warehouse_id
    ).all():
        open_orders[(product_id, wh_id)] = float(quantity or 0)

    keys = set(snapshots) | {(product_id, wh_id) for product_id, wh_id, _ in received} | set(open_orders)
    if warehouse_id is not None:
        keys = {key for key in keys if key[1] == warehouse_id}

    result: dict[tuple[int, int], EffectiveInventory] = {}
    for product_id, wh_id in keys:
        snapshot = snapshots.get((product_id, wh_id))
        cutoff = snapshot.snapshot_date if snapshot is not None else None

        received_since = sum(
            quantity
            for (pid, key_wh, day), quantity in received.items()
            if pid == product_id and key_wh == wh_id and (cutoff is None or day >= cutoff)
        )
        sold_since = sum(
            quantity
            for (pid, key_wh, day), quantity in sold.items()
            if pid == product_id and key_wh == wh_id and (cutoff is None or day >= cutoff)
        )

        opening = float(snapshot.on_hand) if snapshot is not None else 0.0
        # Prefer live open orders; fall back to an imported on-order balance.
        on_order = open_orders.get(
            (product_id, wh_id), float(snapshot.on_order) if snapshot is not None else 0.0
        )
        result[(product_id, wh_id)] = EffectiveInventory(
            product_id=product_id,
            warehouse_id=wh_id,
            opening_on_hand=round(opening, 2),
            received_since=round(received_since, 2),
            sold_since=round(sold_since, 2),
            on_hand=round(opening + received_since - sold_since, 2),
            on_order=round(on_order, 2),
            committed=round(float(snapshot.committed) if snapshot is not None else 0.0, 2),
            snapshot_date=cutoff,
            has_opening_count=snapshot is not None,
        )
    return result


def daily_sales(
    db: Session,
    tenant_id: int,
    product_id: int,
    warehouse_id: int | None = None,
    days: int = 180,
) -> pd.DataFrame:
    start = date.today() - timedelta(days=days)
    query = (
        db.query(SalesTransaction.occurred_at, SalesItem.quantity)
        .join(SalesItem, SalesItem.transaction_id == SalesTransaction.id)
        .filter(
            SalesTransaction.tenant_id == tenant_id,
            SalesItem.product_id == product_id,
            SalesTransaction.occurred_at >= start,
        )
    )
    if warehouse_id is not None:
        query = query.filter(SalesTransaction.warehouse_id == warehouse_id)
    rows = query.all()
    if not rows:
        return pd.DataFrame(columns=["date", "y"])
    dates = pd.Series([row[0] for row in rows])
    values = pd.Series([row[1] for row in rows], dtype=float)
    return fill_daily_series(dates, values)


def latest_forecast_map(db: Session, tenant_id: int) -> dict[int, "Forecast"]:
    from app.models import Forecast

    subquery = (
        db.query(Forecast.product_id, func.max(Forecast.id).label("max_id"))
        .filter(Forecast.tenant_id == tenant_id)
        .group_by(Forecast.product_id)
        .subquery()
    )
    rows = (
        db.query(Forecast)
        .join(subquery, Forecast.id == subquery.c.max_id)
        .all()
    )
    return {row.product_id: row for row in rows}
