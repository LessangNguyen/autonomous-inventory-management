from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import (
    AuditLog,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    ReplenishmentRecommendation,
    Supplier,
    User,
    Warehouse,
)
from app.schemas import POItemOut, PurchaseOrderIn, PurchaseOrderOut
from app.services.dashboard import latest_recommendations

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


def _out(db: Session, order: PurchaseOrder) -> PurchaseOrderOut:
    data = PurchaseOrderOut.model_validate(order)
    products = {
        product.id: product
        for product in db.query(Product)
        .filter(Product.id.in_([item.product_id for item in order.items] or [0]))
        .all()
    }
    data.items = [
        POItemOut(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            sku=products[item.product_id].sku if item.product_id in products else None,
            product_name=products[item.product_id].name if item.product_id in products else None,
        )
        for item in order.items
    ]
    supplier = db.get(Supplier, order.supplier_id) if order.supplier_id else None
    warehouse = db.get(Warehouse, order.warehouse_id)
    data.supplier_name = supplier.name if supplier else None
    data.warehouse_name = warehouse.name if warehouse else None
    return data


@router.get("", response_model=list[PurchaseOrderOut])
def list_orders(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PurchaseOrderOut]:
    query = db.query(PurchaseOrder).filter(PurchaseOrder.tenant_id == user.tenant_id)
    if status:
        query = query.filter(PurchaseOrder.status == status)
    orders = query.order_by(PurchaseOrder.created_at.desc()).limit(min(limit, 200)).all()
    return [_out(db, order) for order in orders]


@router.post("", response_model=PurchaseOrderOut, status_code=201)
def create_order(
    payload: PurchaseOrderIn,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> PurchaseOrderOut:
    if not payload.items:
        raise HTTPException(status_code=400, detail="Đơn nhập cần ít nhất một sản phẩm.")
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None or warehouse.tenant_id != user.tenant_id:
        raise HTTPException(status_code=400, detail="Kho không hợp lệ.")
    if payload.supplier_id:
        supplier = db.get(Supplier, payload.supplier_id)
        if supplier is None or supplier.tenant_id != user.tenant_id:
            raise HTTPException(status_code=400, detail="Nhà cung cấp không hợp lệ.")

    products = {
        product.id: product
        for product in db.query(Product)
        .filter(
            Product.tenant_id == user.tenant_id,
            Product.id.in_([item.product_id for item in payload.items]),
        )
        .all()
    }
    missing = [item.product_id for item in payload.items if item.product_id not in products]
    if missing:
        raise HTTPException(status_code=400, detail=f"Sản phẩm không hợp lệ: {missing}")

    order = PurchaseOrder(
        tenant_id=user.tenant_id,
        supplier_id=payload.supplier_id,
        warehouse_id=payload.warehouse_id,
        status="draft",
        source="manual",
        notes=payload.notes,
        created_by=user.id,
    )
    db.add(order)
    db.flush()
    total = 0.0
    for item in payload.items:
        product = products[item.product_id]
        cost = item.unit_cost or product.unit_cost
        db.add(
            PurchaseOrderItem(
                purchase_order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_cost=cost,
            )
        )
        total += item.quantity * cost
    order.total_amount = total
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="purchase_order.create",
            entity="purchase_order",
            entity_id=order.id,
            details={"total_amount": total, "items": len(payload.items)},
        )
    )
    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PurchaseOrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nhập.")
    return _out(db, order)


@router.post("/{order_id}/submit", response_model=PurchaseOrderOut)
def submit_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> PurchaseOrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nhập.")
    if order.status != "draft":
        raise HTTPException(status_code=400, detail="Chỉ gửi duyệt được đơn ở trạng thái nháp.")
    order.status = "pending_approval"
    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.post("/{order_id}/approve", response_model=PurchaseOrderOut)
def approve_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> PurchaseOrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nhập.")
    if order.status not in {"draft", "pending_approval"}:
        raise HTTPException(status_code=400, detail="Đơn không ở trạng thái chờ duyệt.")
    order.status = "approved"
    order.approved_by = user.id
    order.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="purchase_order.approve",
            entity="purchase_order",
            entity_id=order.id,
            details={"total_amount": order.total_amount},
        )
    )
    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.post("/{order_id}/receive", response_model=PurchaseOrderOut)
def receive_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> PurchaseOrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nhập.")
    if order.status != "approved":
        raise HTTPException(status_code=400, detail="Chỉ nhận hàng cho đơn đã phê duyệt.")

    recommendations = {row.product_id: row for row in latest_recommendations(db, user.tenant_id)}
    for item in order.items:
        # Inventory is derived from the count + received POs - sales, so the
        # receipt only needs to flip the order status. Writing another snapshot
        # here would double-count the goods.
        if item.product_id in recommendations:
            recommendations[item.product_id].status = "ordered"

    order.status = "received"
    order.received_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="purchase_order.receive",
            entity="purchase_order",
            entity_id=order.id,
            details={"items": len(order.items)},
        )
    )
    db.commit()
    db.refresh(order)
    return _out(db, order)


@router.post("/{order_id}/cancel", response_model=PurchaseOrderOut)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> PurchaseOrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nhập.")
    if order.status == "received":
        raise HTTPException(status_code=400, detail="Không thể hủy đơn đã nhận hàng.")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return _out(db, order)
