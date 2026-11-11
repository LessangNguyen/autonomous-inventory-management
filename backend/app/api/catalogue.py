from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import AuditLog, Product, Supplier, User, Warehouse
from app.schemas import ProductIn, ProductOut, SupplierIn, SupplierOut, WarehouseIn, WarehouseOut

router = APIRouter(prefix="/api", tags=["catalogue"])


def _product_out(product: Product) -> ProductOut:
    data = ProductOut.model_validate(product)
    data.supplier_name = product.supplier.name if product.supplier else None
    return data


@router.get("/products", response_model=list[ProductOut])
def list_products(
    q: str | None = None,
    category: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProductOut]:
    query = db.query(Product).filter(Product.tenant_id == user.tenant_id)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(func.lower(Product.sku).like(like), func.lower(Product.name).like(like))
        )
    if category:
        query = query.filter(Product.category == category)
    products = query.order_by(Product.sku.asc()).limit(min(limit, 500)).all()
    return [_product_out(product) for product in products]


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductIn,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> ProductOut:
    exists = (
        db.query(Product)
        .filter(Product.tenant_id == user.tenant_id, func.lower(Product.sku) == payload.sku.lower())
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="SKU đã tồn tại.")
    if payload.supplier_id and not db.get(Supplier, payload.supplier_id):
        raise HTTPException(status_code=400, detail="Nhà cung cấp không hợp lệ.")
    product = Product(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(product)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="product.create",
            entity="product",
            entity_id=product.id,
            details={"sku": product.sku},
        )
    )
    db.commit()
    db.refresh(product)
    return _product_out(product)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductIn,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None or product.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    for field, value in payload.model_dump().items():
        setattr(product, field, value)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="product.update",
            entity="product",
            entity_id=product.id,
            details={"sku": product.sku},
        )
    )
    db.commit()
    db.refresh(product)
    return _product_out(product)


@router.delete("/products/{product_id}", status_code=204)
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> None:
    product = db.get(Product, product_id)
    if product is None or product.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    product.is_active = False
    db.commit()


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Supplier]:
    return (
        db.query(Supplier)
        .filter(Supplier.tenant_id == user.tenant_id)
        .order_by(Supplier.name.asc())
        .all()
    )


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(
    payload: SupplierIn,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> Supplier:
    supplier = Supplier(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Warehouse]:
    return (
        db.query(Warehouse)
        .filter(Warehouse.tenant_id == user.tenant_id)
        .order_by(Warehouse.id.asc())
        .all()
    )


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(
    payload: WarehouseIn,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> Warehouse:
    warehouse = Warehouse(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse
