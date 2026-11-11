from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import Alert, Product, User
from app.schemas import AlertOut
from app.services.inventory_engine import run_anomaly_detection

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertStatusUpdate(BaseModel):
    status: str


@router.get("", response_model=list[AlertOut])
def list_alerts(
    status: str = "open",
    severity: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AlertOut]:
    query = db.query(Alert).filter(Alert.tenant_id == user.tenant_id)
    if status != "all":
        query = query.filter(Alert.status == status)
    if severity:
        query = query.filter(Alert.severity == severity)
    alerts = query.order_by(Alert.created_at.desc()).limit(min(limit, 300)).all()
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.tenant_id == user.tenant_id).all()
    }
    output = []
    for alert in alerts:
        data = AlertOut.model_validate(alert)
        data.sku = products[alert.product_id].sku if alert.product_id in products else None
        output.append(data)
    return output


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert(
    alert_id: int,
    payload: AlertStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> AlertOut:
    if payload.status not in {"open", "acked", "resolved"}:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ.")
    alert = db.get(Alert, alert_id)
    if alert is None or alert.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
    alert.status = payload.status
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/scan")
def scan_anomalies(
    db: Session = Depends(get_db), user: User = Depends(writer)
) -> dict:
    created = run_anomaly_detection(db, user.tenant_id)
    return {"alerts_created": created}
