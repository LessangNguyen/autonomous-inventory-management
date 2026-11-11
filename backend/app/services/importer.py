"""CSV / Excel import with row-level validation and a human-readable error report.

Validation strategy: parse the whole file, validate row by row, import only the
valid rows, and persist every rejected row (with row number and reason) so the
store owner can fix the source file and re-upload. Nothing is silently dropped.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    ImportJob,
    ImportSource,
    InventorySnapshot,
    Product,
    SalesItem,
    SalesTransaction,
    Supplier,
)
from app.services.common import get_or_create_warehouse

MAX_ERRORS = 50
REQUIRED_COLUMNS = {
    "products": ["sku", "name"],
    "sales": ["sku", "date", "quantity"],
    "inventory": ["sku", "on_hand"],
    "suppliers": ["name"],
}
TEMPLATE_COLUMNS = {
    "products": [
        "sku", "name", "category", "unit", "unit_cost", "price",
        "supplier_name", "lead_time_days", "moq", "order_multiple",
    ],
    "sales": ["sku", "date", "quantity", "unit_price", "warehouse_code", "external_id"],
    "inventory": ["sku", "warehouse_code", "on_hand", "on_order", "committed", "date"],
    "suppliers": ["name", "email", "lead_time_days", "moq", "order_multiple"],
}


def _normalize_column(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")


def _read_table(filename: str, content: bytes) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        frame = pd.read_excel(BytesIO(content), dtype=str)
    elif lower.endswith(".xls"):
        frame = pd.read_excel(BytesIO(content), dtype=str)
    else:
        try:
            frame = pd.read_csv(BytesIO(content), dtype=str, encoding="utf-8-sig", sep=None, engine="python")
        except UnicodeDecodeError:
            frame = pd.read_csv(BytesIO(content), dtype=str, encoding="cp1258", sep=None, engine="python")
    frame.columns = [_normalize_column(column) for column in frame.columns]
    return frame


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _to_float(value, default: float | None = None) -> float | None:
    text = _clean(value).replace(",", "")
    if text == "":
        return default
    return float(text)


def _to_int(value, default: int | None = None) -> int | None:
    number = _to_float(value)
    if number is None:
        return default
    return int(round(number))


def _to_date(value) -> date | None:
    text = _clean(value)
    if text == "":
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return None
    return parsed.date()


def _job(db: Session, tenant_id: int, user_id: int | None, kind: str, filename: str) -> ImportJob:
    job = ImportJob(tenant_id=tenant_id, kind=kind, filename=filename, created_by=user_id)
    db.add(job)
    db.flush()
    return job


def _track(
    db: Session,
    tenant_id: int,
    job_id: int,
    tracked: set[tuple[str, int, str]],
    entity_type: str,
    entity_id: int,
    action: str = "created",
) -> None:
    key = (entity_type, entity_id, action)
    if key in tracked:
        return
    tracked.add(key)
    db.add(
        ImportSource(
            tenant_id=tenant_id,
            job_id=job_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
        )
    )


def _finish(db: Session, job: ImportJob, total: int, ok: int, errors: list[dict]) -> ImportJob:
    job.rows_total = total
    job.rows_ok = ok
    job.rows_failed = total - ok
    job.errors = errors[:MAX_ERRORS]
    db.commit()
    db.refresh(job)
    return job


def import_file(
    db: Session, tenant_id: int, user_id: int | None, kind: str, filename: str, content: bytes
) -> ImportJob:
    if kind not in REQUIRED_COLUMNS:
        raise ValueError(f"Loại import không hợp lệ: {kind}")

    job = _job(db, tenant_id, user_id, kind, filename)
    try:
        frame = _read_table(filename, content)
    except Exception as exc:
        errors = [{"row": 0, "field": None, "message": f"Không đọc được file: {exc}"}]
        job.status = "failed"
        return _finish(db, job, 0, 0, errors)

    missing = [column for column in REQUIRED_COLUMNS[kind] if column not in frame.columns]
    if missing:
        errors = [
            {
                "row": 0,
                "field": column,
                "message": f"Thiếu cột bắt buộc '{column}'. Cột hợp lệ: {', '.join(TEMPLATE_COLUMNS[kind])}",
            }
            for column in missing
        ]
        job.status = "failed"
        return _finish(db, job, len(frame), 0, errors)

    handlers = {
        "products": _import_products,
        "sales": _import_sales,
        "inventory": _import_inventory,
        "suppliers": _import_suppliers,
    }
    tracked: set[tuple[str, int, str]] = set()
    ok, errors = handlers[kind](db, tenant_id, job.id, frame, tracked)
    job.status = "completed" if ok or not errors else "failed"
    return _finish(db, job, len(frame), ok, errors)


def _import_suppliers(
    db: Session,
    tenant_id: int,
    job_id: int,
    frame: pd.DataFrame,
    tracked: set[tuple[str, int, str]],
) -> tuple[int, list[dict]]:
    ok, errors = 0, []
    cache = {
        supplier.name.lower(): supplier
        for supplier in db.query(Supplier).filter(Supplier.tenant_id == tenant_id).all()
    }
    created_in_job: set[int] = set()
    for index, row in frame.iterrows():
        row_number = index + 2
        name = _clean(row.get("name"))
        if not name:
            errors.append({"row": row_number, "field": "name", "message": "Tên nhà cung cấp bắt buộc."})
            continue
        try:
            lead_time_days = _to_int(row.get("lead_time_days"), 7)
            moq = _to_int(row.get("moq"), 1)
            order_multiple = _to_int(row.get("order_multiple"), 1)
            if lead_time_days is None or lead_time_days < 1:
                raise ValueError("lead_time_days phải >= 1")
            if moq is None or moq < 1:
                raise ValueError("moq phải >= 1")
            if order_multiple is None or order_multiple < 1:
                raise ValueError("order_multiple phải >= 1")

            supplier = cache.get(name.lower())
            if supplier is None:
                supplier = Supplier(
                    tenant_id=tenant_id,
                    name=name,
                    email=_clean(row.get("email")),
                    lead_time_days=lead_time_days,
                    moq=moq,
                    order_multiple=order_multiple,
                )
                db.add(supplier)
                db.flush()
                cache[name.lower()] = supplier
                created_in_job.add(supplier.id)
                _track(db, tenant_id, job_id, tracked, "supplier", supplier.id)
            else:
                supplier.email = _clean(row.get("email")) or supplier.email
                supplier.lead_time_days = lead_time_days
                supplier.moq = moq
                supplier.order_multiple = order_multiple
                if supplier.id not in created_in_job:
                    _track(db, tenant_id, job_id, tracked, "supplier", supplier.id, "updated")
            ok += 1
        except (TypeError, ValueError) as exc:
            errors.append({"row": row_number, "field": "supplier", "message": str(exc)})
    db.flush()
    return ok, errors


def _import_products(
    db: Session,
    tenant_id: int,
    job_id: int,
    frame: pd.DataFrame,
    tracked: set[tuple[str, int, str]],
) -> tuple[int, list[dict]]:
    ok, errors = 0, []
    suppliers = {
        supplier.name.lower(): supplier
        for supplier in db.query(Supplier).filter(Supplier.tenant_id == tenant_id).all()
    }
    existing = {
        product.sku.lower(): product
        for product in db.query(Product).filter(Product.tenant_id == tenant_id).all()
    }
    created_in_job: set[int] = set()

    for index, row in frame.iterrows():
        row_number = index + 2
        try:
            sku = _clean(row.get("sku"))
            name = _clean(row.get("name"))
            if not sku:
                raise ValueError("SKU bắt buộc.")
            if not name:
                raise ValueError("Tên sản phẩm bắt buộc.")

            unit_cost = _to_float(row.get("unit_cost"))
            price = _to_float(row.get("price"))
            if (unit_cost is not None and unit_cost < 0) or (price is not None and price < 0):
                raise ValueError("Giá không được âm.")

            lead_time_days = _to_int(row.get("lead_time_days"))
            moq = _to_int(row.get("moq"))
            order_multiple = _to_int(row.get("order_multiple"))
            for field, value in (
                ("lead_time_days", lead_time_days),
                ("moq", moq),
                ("order_multiple", order_multiple),
            ):
                if value is not None and value < 1:
                    raise ValueError(f"{field} phải >= 1.")

            # Only create/lookup related records after this row has been validated,
            # so a rejected row never leaves partial data behind.
            supplier = None
            supplier_name = _clean(row.get("supplier_name"))
            if supplier_name:
                supplier = suppliers.get(supplier_name.lower())
                if supplier is None:
                    supplier = Supplier(tenant_id=tenant_id, name=supplier_name)
                    db.add(supplier)
                    db.flush()
                    suppliers[supplier_name.lower()] = supplier
                    _track(db, tenant_id, job_id, tracked, "supplier", supplier.id)

            product = existing.get(sku.lower())
            if product is None:
                product = Product(tenant_id=tenant_id, sku=sku, name=name)
                db.add(product)
                db.flush()
                existing[sku.lower()] = product
                created_in_job.add(product.id)
                _track(db, tenant_id, job_id, tracked, "product", product.id)
            elif product.id not in created_in_job:
                _track(db, tenant_id, job_id, tracked, "product", product.id, "updated")

            product.name = name
            product.category = _clean(row.get("category")) or product.category or ""
            product.unit = _clean(row.get("unit")) or product.unit or "cái"
            product.unit_cost = unit_cost if unit_cost is not None else (product.unit_cost or 0)
            product.price = price if price is not None else (product.price or 0)
            product.supplier_id = supplier.id if supplier else product.supplier_id
            product.lead_time_days = (
                lead_time_days if lead_time_days is not None else product.lead_time_days
            )
            product.moq = moq if moq is not None else product.moq
            product.order_multiple = (
                order_multiple if order_multiple is not None else product.order_multiple
            )
            ok += 1
        except (TypeError, ValueError) as exc:
            errors.append({"row": row_number, "field": "product", "message": str(exc)})
    db.flush()
    return ok, errors


def _import_sales(
    db: Session,
    tenant_id: int,
    job_id: int,
    frame: pd.DataFrame,
    tracked: set[tuple[str, int, str]],
) -> tuple[int, list[dict]]:
    ok, errors = 0, []
    products = {
        product.sku.lower(): product
        for product in db.query(Product).filter(Product.tenant_id == tenant_id).all()
    }
    warehouses: dict[str, int] = {}

    for index, row in frame.iterrows():
        row_number = index + 2
        try:
            sku = _clean(row.get("sku"))
            product = products.get(sku.lower())
            if product is None:
                raise ValueError(f"SKU '{sku}' chưa tồn tại. Hãy import sản phẩm trước.")
            occurred = _to_date(row.get("date"))
            if occurred is None:
                raise ValueError("Ngày bán không hợp lệ (định dạng gợi ý: YYYY-MM-DD).")
            quantity = _to_float(row.get("quantity"))
            if quantity is None or quantity <= 0:
                raise ValueError("Số lượng phải lớn hơn 0.")
            unit_price = _to_float(row.get("unit_price"), product.price or 0) or 0

            code = _clean(row.get("warehouse_code")) or "MAIN"
            if code.upper() not in warehouses:
                warehouse = get_or_create_warehouse(db, tenant_id, code)
                warehouses[code.upper()] = warehouse.id

            transaction = SalesTransaction(
                tenant_id=tenant_id,
                external_id=_clean(row.get("external_id")) or None,
                warehouse_id=warehouses[code.upper()],
                occurred_at=datetime.combine(occurred, datetime.min.time()),
                total_amount=quantity * unit_price,
            )
            db.add(transaction)
            db.flush()
            db.add(
                SalesItem(
                    transaction_id=transaction.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )
            _track(db, tenant_id, job_id, tracked, "sales_transaction", transaction.id)
            ok += 1
        except (TypeError, ValueError) as exc:
            errors.append({"row": row_number, "field": "sales", "message": str(exc)})
    db.flush()
    return ok, errors


def _import_inventory(
    db: Session,
    tenant_id: int,
    job_id: int,
    frame: pd.DataFrame,
    tracked: set[tuple[str, int, str]],
) -> tuple[int, list[dict]]:
    ok, errors = 0, []
    products = {
        product.sku.lower(): product
        for product in db.query(Product).filter(Product.tenant_id == tenant_id).all()
    }
    warehouses: dict[str, int] = {}

    for index, row in frame.iterrows():
        row_number = index + 2
        try:
            sku = _clean(row.get("sku"))
            product = products.get(sku.lower())
            if product is None:
                raise ValueError(f"SKU '{sku}' chưa tồn tại. Hãy import sản phẩm trước.")
            code = _clean(row.get("warehouse_code")) or "MAIN"
            if code.upper() not in warehouses:
                warehouse = get_or_create_warehouse(db, tenant_id, code)
                warehouses[code.upper()] = warehouse.id

            on_hand = _to_float(row.get("on_hand"))
            if on_hand is None or on_hand < 0:
                raise ValueError("on_hand phải >= 0.")
            on_order = _to_float(row.get("on_order"), 0) or 0
            committed = _to_float(row.get("committed"), 0) or 0
            if on_order < 0 or committed < 0:
                raise ValueError("on_order và committed không được âm.")
            snapshot_date = _to_date(row.get("date")) or date.today()

            snapshot = InventorySnapshot(
                tenant_id=tenant_id,
                product_id=product.id,
                warehouse_id=warehouses[code.upper()],
                on_hand=on_hand,
                on_order=on_order,
                committed=committed,
                snapshot_date=snapshot_date,
            )
            db.add(snapshot)
            db.flush()
            _track(db, tenant_id, job_id, tracked, "inventory_snapshot", snapshot.id)
            ok += 1
        except (TypeError, ValueError) as exc:
            errors.append({"row": row_number, "field": "inventory", "message": str(exc)})
    db.flush()
    return ok, errors
