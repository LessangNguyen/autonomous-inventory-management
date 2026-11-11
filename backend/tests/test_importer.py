"""Tests for the CSV/Excel importer: validation, row-level errors, no partial writes."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Product, SalesItem, Supplier, Tenant
from app.services.importer import import_file


def _tenant() -> int:
    with SessionLocal() as db:
        tenant = Tenant(name="Import Test")
        db.add(tenant)
        db.commit()
        return tenant.id


def test_product_import_reports_errors_without_partial_rows(db_schema):
    tenant_id = _tenant()
    csv = (
        "sku,name,unit_cost,price\n"
        "OK-001,Sản phẩm hợp lệ,10000,20000\n"
        "BAD-002,Sản phẩm giá âm,-1000,20000\n"
        ",Thiếu SKU,1000,2000\n"
        "BAD-003,,1000,2000\n"
    )

    with SessionLocal() as db:
        job = import_file(db, tenant_id, None, "products", "products.csv", csv.encode("utf-8"))

    assert job.rows_total == 4
    assert job.rows_ok == 1
    assert job.rows_failed == 3
    assert job.status == "completed"  # valid rows were imported; failures are reported
    assert {error["row"] for error in job.errors} == {3, 4, 5}

    with SessionLocal() as db:
        skus = {row.sku for row in db.scalars(select(Product).where(Product.tenant_id == tenant_id))}
    assert skus == {"OK-001"}, "invalid rows must not be persisted"


def test_sales_import_requires_existing_sku_and_positive_quantity(db_schema):
    tenant_id = _tenant()
    with SessionLocal() as db:
        db.add(Product(tenant_id=tenant_id, sku="SKU-1", name="Sản phẩm", price=1000))
        db.commit()

    today = date.today()
    csv = (
        "sku,date,quantity\n"
        f"SKU-1,{today.isoformat()},3\n"
        f"SKU-1,{(today - timedelta(days=1)).isoformat()},0\n"
        f"UNKNOWN,{today.isoformat()},2\n"
        f"SKU-1,not-a-date,2\n"
    )
    with SessionLocal() as db:
        job = import_file(db, tenant_id, None, "sales", "sales.csv", csv.encode("utf-8"))

    assert (job.rows_ok, job.rows_failed) == (1, 3)
    with SessionLocal() as db:
        items = db.scalars(select(SalesItem)).all()
    assert len(items) == 1
    assert items[0].quantity == 3


def test_supplier_import_validates_lead_time_before_insert(db_schema):
    tenant_id = _tenant()
    csv = "name,lead_time_days,moq,order_multiple\nNCC Tốt,5,10,5\nNCC Sai,0,10,5\n"

    with SessionLocal() as db:
        job = import_file(db, tenant_id, None, "suppliers", "suppliers.csv", csv.encode("utf-8"))

    assert (job.rows_ok, job.rows_failed) == (1, 1)
    with SessionLocal() as db:
        names = {row.name for row in db.scalars(select(Supplier).where(Supplier.tenant_id == tenant_id))}
    assert names == {"NCC Tốt"}


def test_inventory_import_accepts_negative_on_hand_as_error(db_schema):
    tenant_id = _tenant()
    with SessionLocal() as db:
        db.add(Product(tenant_id=tenant_id, sku="INV-1", name="Sản phẩm kho"))
        db.commit()

    csv = "sku,on_hand,on_order,committed\nINV-1,10,2,1\nINV-1,-5,0,0\n"
    with SessionLocal() as db:
        job = import_file(db, tenant_id, None, "inventory", "inventory.csv", csv.encode("utf-8"))

    assert (job.rows_ok, job.rows_failed) == (1, 1)
    assert "on_hand" in job.errors[0]["message"].lower()
