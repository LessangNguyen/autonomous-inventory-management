from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import Forecast, Product, User
from app.schemas import ForecastOut, ForecastRunRequest, ForecastRunResult
from app.services.common import latest_forecast_map
from app.services.forecasting import run_forecasts

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


@router.post("/run", response_model=ForecastRunResult)
def run_forecast(
    payload: ForecastRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> ForecastRunResult:
    result = run_forecasts(
        db,
        user.tenant_id,
        horizon_days=payload.horizon_days,
        product_ids=payload.product_ids,
        history_days=payload.history_days,
    )
    return ForecastRunResult(**result)


@router.get("", response_model=list[ForecastOut])
def list_forecasts(
    product_id: int | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ForecastOut]:
    if product_id is not None:
        rows = (
            db.query(Forecast)
            .filter(Forecast.tenant_id == user.tenant_id, Forecast.product_id == product_id)
            .order_by(Forecast.created_at.desc())
            .limit(20)
            .all()
        )
        if not rows:
            return []
        products = {product.id: product for product in db.query(Product).filter(Product.id == product_id).all()}
        result = []
        for row in rows:
            data = ForecastOut.model_validate(row)
            product = products.get(row.product_id)
            data.sku = product.sku if product else None
            data.product_name = product.name if product else None
            result.append(data)
        return result

    latest = latest_forecast_map(db, user.tenant_id)
    rows = sorted(latest.values(), key=lambda row: row.product_id)[: min(limit, 500)]
    if not rows:
        return []
    products = {
        product.id: product
        for product in db.query(Product)
        .filter(Product.tenant_id == user.tenant_id)
        .all()
    }
    output = []
    for row in rows:
        data = ForecastOut.model_validate(row)
        product = products.get(row.product_id)
        data.sku = product.sku if product else None
        data.product_name = product.name if product else None
        output.append(data)
    return output


@router.get("/models")
def model_usage(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    rows = (
        db.query(Forecast.model_name, func.count(Forecast.id))
        .filter(Forecast.tenant_id == user.tenant_id)
        .group_by(Forecast.model_name)
        .all()
    )
    return [{"model": row[0], "count": row[1]} for row in rows]


@router.get("/{forecast_id}/detail", response_model=ForecastOut)
def get_forecast(
    forecast_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ForecastOut:
    row = db.get(Forecast, forecast_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự báo.")
    product = db.get(Product, row.product_id)
    data = ForecastOut.model_validate(row)
    data.sku = product.sku if product else None
    data.product_name = product.name if product else None
    return data
