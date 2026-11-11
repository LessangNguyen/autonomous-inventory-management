"""Reverting a wrong import: source tracking, dependency safety, tenant isolation."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models import ImportSource


def _forget_sources(job_id: int) -> None:
    """Simulate a job created before import source tracking existed."""
    db = SessionLocal()
    try:
        db.query(ImportSource).filter(ImportSource.job_id == job_id).delete()
        db.commit()
    finally:
        db.close()


def _upload(client: TestClient, headers: dict, kind: str, filename: str, body: str):
    return client.post(
        f"/api/imports/{kind}",
        headers=headers,
        files={"file": (filename, body.encode("utf-8"), "text/csv")},
    )


def test_delete_sales_import_restores_derived_inventory_and_clears_derived_data(
    client: TestClient, setup_store: dict
):
    headers = setup_store["headers"]
    product_id = setup_store["product_id"]
    today = date.today()
    count_day = today - timedelta(days=3)

    sales_csv = "sku,date,quantity\n" + "".join(
        f"TST-001,{(today - timedelta(days=offset)).isoformat()},2\n" for offset in range(3)
    )
    sales_job = _upload(client, headers, "sales", "sales-wrong.csv", sales_csv)
    assert sales_job.status_code == 201, sales_job.text
    sales_job_id = sales_job.json()["id"]

    inventory_csv = (
        "sku,warehouse_code,on_hand,on_order,committed,date\n"
        f"TST-001,MAIN,100,0,0,{count_day.isoformat()}\n"
    )
    inventory_job = _upload(client, headers, "inventory", "inventory.csv", inventory_csv)
    assert inventory_job.status_code == 201, inventory_job.text

    assert client.post("/api/recommendations/run", headers=headers).status_code == 200

    before = next(
        row
        for row in client.get("/api/inventory", headers=headers).json()
        if row["product_id"] == product_id
    )
    assert before["sold_since"] == 6
    assert before["on_hand"] == 94

    preview = client.get(f"/api/imports/{sales_job_id}/deletion-preview", headers=headers)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["kind"] == "sales"
    assert body["will_delete"]["sales_transactions"] == 3
    assert body["will_delete"]["recommendations"] >= 1
    assert body["skipped"] == []

    deleted = client.delete(f"/api/imports/{sales_job_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    result = deleted.json()
    assert result["status"] == "reverted"
    assert result["will_delete"]["sales_transactions"] == 3

    after = next(
        row
        for row in client.get("/api/inventory", headers=headers).json()
        if row["product_id"] == product_id
    )
    assert after["sold_since"] == 0
    assert after["on_hand"] == 100

    assert client.get("/api/recommendations", headers=headers).json() == []

    history = client.get("/api/imports", headers=headers).json()
    assert next(job for job in history if job["id"] == sales_job_id)["status"] == "reverted"

    audit = client.get("/api/audit-logs", headers=headers).json()
    assert "import.revert" in {entry["action"] for entry in audit}

    assert client.delete(f"/api/imports/{sales_job_id}", headers=headers).status_code == 400


def test_delete_products_import_removes_created_products(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    product_csv = (
        "sku,name,category,unit,unit_cost,price,supplier_name,lead_time_days,moq,order_multiple\n"
        "NEW-001,Sản phẩm nhập sai,Chăm sóc da,chai,10000,20000,NCC Mới,5,6,6\n"
    )
    job = _upload(client, headers, "products", "products-wrong.csv", product_csv)
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    products = client.get("/api/products", headers=headers).json()
    assert any(product["sku"] == "NEW-001" for product in products)
    assert any(supplier["name"] == "NCC Mới" for supplier in client.get("/api/suppliers", headers=headers).json())

    preview = client.get(f"/api/imports/{job_id}/deletion-preview", headers=headers).json()
    assert preview["will_delete"]["products"] == 1
    # The supplier was created by the same file, so it is removed too.
    assert preview["will_delete"]["suppliers"] == 1

    deleted = client.delete(f"/api/imports/{job_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["will_delete"]["products"] == 1

    products = client.get("/api/products", headers=headers).json()
    assert not any(product["sku"] == "NEW-001" for product in products)
    assert not any(supplier["name"] == "NCC Mới" for supplier in client.get("/api/suppliers", headers=headers).json())


def test_product_with_sales_is_kept_and_reported(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    product_csv = "sku,name,price\nREF-001,Sản phẩm có tham chiếu,20000\n"
    job = _upload(client, headers, "products", "products-ref.csv", product_csv)
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    sales_csv = "sku,date,quantity\nREF-001,2026-11-01,2\n"
    assert _upload(client, headers, "sales", "sales-ref.csv", sales_csv).status_code == 201

    preview = client.get(f"/api/imports/{job_id}/deletion-preview", headers=headers).json()
    assert preview["will_delete"]["products"] == 0
    assert preview["skipped"][0]["entity_type"] == "product"
    assert preview["skipped"][0]["label"] == "REF-001"

    blocked = client.delete(f"/api/imports/{job_id}", headers=headers)
    assert blocked.status_code == 400
    assert "Không còn dữ liệu" in blocked.json()["detail"]
    assert any(
        product["sku"] == "REF-001" for product in client.get("/api/products", headers=headers).json()
    )


def test_legacy_job_falls_back_to_full_kind_cleanup(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    sales_csv = "sku,date,quantity\n" + "".join(
        f"TST-001,{(date.today() - timedelta(days=offset)).isoformat()},1\n"
        for offset in range(4)
    )
    job = _upload(client, headers, "sales", "legacy-sales.csv", sales_csv)
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    _forget_sources(job_id)

    preview = client.get(f"/api/imports/{job_id}/deletion-preview", headers=headers)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["will_delete"]["sales_transactions"] == 4
    assert any("toàn bộ" in note for note in body["notes"])

    deleted = client.delete(f"/api/imports/{job_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "reverted"
    assert client.get("/api/inventory", headers=headers).json() == []
    history = client.get("/api/imports", headers=headers).json()
    assert next(item for item in history if item["id"] == job_id)["status"] == "reverted"


def test_import_deletion_is_tenant_scoped(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    job = _upload(
        client,
        headers,
        "products",
        "tenant-a.csv",
        "sku,name,price\nTENANT-A,Sản phẩm A,1000\n",
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    second = client.post(
        "/api/auth/register",
        json={
            "store_name": "Cửa hàng Khác",
            "full_name": "Chủ Khác",
            "email": "other-delete@test.vn",
            "password": "matkhau123",
        },
    )
    assert second.status_code == 201, second.text
    other_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    assert (
        client.get(f"/api/imports/{job_id}/deletion-preview", headers=other_headers).status_code
        == 404
    )
    assert client.delete(f"/api/imports/{job_id}", headers=other_headers).status_code == 404
