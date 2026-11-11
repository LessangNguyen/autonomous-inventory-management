from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import Product, ReplenishmentRecommendation, User
from app.schemas import RecommendationOut, RecommendationRunResult
from app.services.common import effective_inventory_map
from app.services.dashboard import latest_recommendations
from app.services.inventory_engine import run_recommendations

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class StatusUpdate(BaseModel):
    status: str


@router.post("/run", response_model=RecommendationRunResult)
def recompute(
    db: Session = Depends(get_db), user: User = Depends(writer)
) -> RecommendationRunResult:
    result = run_recommendations(db, user.tenant_id)
    return RecommendationRunResult(**result)


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    q: str | None = None,
    risk: str | None = None,
    only_need: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RecommendationOut]:
    rows = latest_recommendations(db, user.tenant_id)
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.tenant_id == user.tenant_id).all()
    }
    inventory = effective_inventory_map(db, user.tenant_id)

    items: list[RecommendationOut] = []
    for row in rows:
        product = products.get(row.product_id)
        if product is None:
            continue
        if q:
            needle = q.strip().lower()
            if needle not in product.sku.lower() and needle not in product.name.lower():
                continue
        if risk and row.stockout_risk != risk:
            continue
        if only_need and row.suggested_qty <= 0:
            continue
        snapshot = inventory.get((row.product_id, row.warehouse_id))
        data = RecommendationOut.model_validate(row)
        data.sku = product.sku
        data.product_name = product.name
        data.on_hand = snapshot.on_hand if snapshot else 0
        data.unit_cost = product.unit_cost
        items.append(data)

    items.sort(
        key=lambda item: (RISK_ORDER.get(item.stockout_risk, 9), -item.suggested_qty)
    )
    return items[: min(limit, 500)]


@router.patch("/{recommendation_id}/status", response_model=RecommendationOut)
def update_status(
    recommendation_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> RecommendationOut:
    if payload.status not in {"open", "ordered", "dismissed"}:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ.")
    row = db.get(ReplenishmentRecommendation, recommendation_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đề xuất.")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    product = db.get(Product, row.product_id)
    data = RecommendationOut.model_validate(row)
    data.sku = product.sku if product else None
    data.product_name = product.name if product else None
    return data
