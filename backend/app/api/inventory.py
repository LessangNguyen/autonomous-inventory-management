from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Product, User, Warehouse
from app.schemas import InventoryRow
from app.services.common import effective_inventory_map

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryRow])
def list_inventory(
    q: str | None = None,
    warehouse_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[InventoryRow]:
    inventory = effective_inventory_map(db, user.tenant_id, warehouse_id)
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.tenant_id == user.tenant_id).all()
    }
    warehouses = {
        warehouse.id: warehouse
        for warehouse in db.query(Warehouse).filter(Warehouse.tenant_id == user.tenant_id).all()
    }

    rows: list[InventoryRow] = []
    for (product_id, wh_id), snapshot in inventory.items():
        product = products.get(product_id)
        warehouse = warehouses.get(wh_id)
        if product is None or warehouse is None:
            continue
        if q:
            needle = q.strip().lower()
            if needle not in product.sku.lower() and needle not in product.name.lower():
                continue
        rows.append(
            InventoryRow(
                product_id=product_id,
                sku=product.sku,
                product_name=product.name,
                warehouse_id=wh_id,
                warehouse_name=warehouse.name,
                opening_on_hand=snapshot.opening_on_hand,
                received_since=snapshot.received_since,
                sold_since=snapshot.sold_since,
                on_hand=snapshot.on_hand,
                on_order=snapshot.on_order,
                committed=snapshot.committed,
                snapshot_date=snapshot.snapshot_date,
                has_opening_count=snapshot.has_opening_count,
            )
        )
    rows.sort(key=lambda row: (row.on_hand, row.sku))
    return rows[: min(limit, 500)]
