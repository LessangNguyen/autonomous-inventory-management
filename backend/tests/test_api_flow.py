"""End-to-end API tests: tenant isolation, import, recommendations, agent, PO approval."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


def _upload(client: TestClient, headers: dict, kind: str, filename: str, body: str):
    return client.post(
        f"/api/imports/{kind}",
        headers=headers,
        files={"file": (filename, body.encode("utf-8"), "text/csv")},
    )


def test_health_is_public(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unauthenticated_access_is_rejected(client: TestClient):
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/dashboard/summary").status_code == 401


def test_full_replenishment_flow_with_human_approval(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    product_id = setup_store["product_id"]
    warehouse_id = setup_store["warehouse_id"]

    # 30 days of steady sales + a low inventory snapshot.
    today = date.today()
    sales_csv = "sku,date,quantity\n" + "".join(
        f"TST-001,{(today - timedelta(days=offset)).isoformat()},3\n" for offset in range(30)
    )
    response = _upload(client, headers, "sales", "sales.csv", sales_csv)
    assert response.status_code == 201, response.text
    assert response.json()["rows_ok"] == 30

    inventory_csv = (
        "sku,warehouse_code,on_hand,on_order,committed,date\n"
        f"TST-001,MAIN,2,0,0,{today.isoformat()}\n"
    )
    response = _upload(client, headers, "inventory", "inventory.csv", inventory_csv)
    assert response.status_code == 201, response.text
    assert response.json()["rows_ok"] == 1

    # Recommendations derive from history when no forecast has been run yet.
    response = client.post("/api/recommendations/run", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["generated"] == 1
    assert response.json()["critical"] == 1

    recommendations = client.get(
        "/api/recommendations", headers=headers, params={"only_need": True}
    ).json()
    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation["sku"] == "TST-001"
    assert recommendation["suggested_qty"] >= 5
    assert recommendation["suggested_qty"] % 5 == 0

    # Agent can read and draft, but never approve.
    chat = client.post(
        "/api/agent/chat",
        headers=headers,
        json={"message": "Tạo đơn nhập hàng cho các SKU sắp hết"},
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["status"] == "pending_approval"
    order_id = payload["pending_purchase_order_id"]
    assert order_id is not None

    order = client.get(f"/api/purchase-orders/{order_id}", headers=headers).json()
    assert order["status"] == "pending_approval"
    assert order["source"] == "agent"
    assert order["items"][0]["quantity"] == recommendation["suggested_qty"]

    # Receiving before approval must fail.
    assert client.post(f"/api/purchase-orders/{order_id}/receive", headers=headers).status_code == 400

    approved = client.post(f"/api/purchase-orders/{order_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Double approval is rejected.
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=headers).status_code == 400

    received = client.post(f"/api/purchase-orders/{order_id}/receive", headers=headers)
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"

    inventory = client.get("/api/inventory", headers=headers).json()
    row = next(item for item in inventory if item["product_id"] == product_id)
    assert row["warehouse_id"] == warehouse_id
    # Count 2 today, 3 units sold today (the count is treated as the opening
    # balance at the start of its date), plus the received purchase order.
    assert row["sold_since"] == 3
    assert row["received_since"] == recommendation["suggested_qty"]
    assert row["on_hand"] == 2 - 3 + recommendation["suggested_qty"]

    audit = client.get("/api/audit-logs", headers=headers).json()
    actions = {entry["action"] for entry in audit}
    assert "purchase_order.receive" in actions


def test_inventory_is_derived_from_count_sales_and_receipts(
    client: TestClient, setup_store: dict
):
    """Inventory must roll forward from one physical count, not be imported again."""
    headers = setup_store["headers"]
    product_id = setup_store["product_id"]
    warehouse_id = setup_store["warehouse_id"]
    today = date.today()
    count_day = today - timedelta(days=5)

    inventory_csv = (
        "sku,warehouse_code,on_hand,on_order,committed,date\n"
        f"TST-001,MAIN,100,0,0,{count_day.isoformat()}\n"
    )
    response = _upload(client, headers, "inventory", "inventory.csv", inventory_csv)
    assert response.status_code == 201, response.text

    # 50 units before the count are already included in 100 and must be ignored;
    # 9 units after the count must be subtracted automatically.
    sales_csv = "sku,date,quantity\n" + "".join(
        [
            f"TST-001,{(count_day - timedelta(days=2)).isoformat()},50\n",
            f"TST-001,{(count_day + timedelta(days=1)).isoformat()},3\n",
            f"TST-001,{(today - timedelta(days=1)).isoformat()},4\n",
            f"TST-001,{today.isoformat()},2\n",
        ]
    )
    response = _upload(client, headers, "sales", "sales.csv", sales_csv)
    assert response.status_code == 201, response.text
    assert response.json()["rows_ok"] == 4

    row = next(
        item
        for item in client.get("/api/inventory", headers=headers).json()
        if item["product_id"] == product_id
    )
    assert row["opening_on_hand"] == 100
    assert row["sold_since"] == 9
    assert row["received_since"] == 0
    assert row["on_hand"] == 91
    assert row["has_opening_count"] is True
    assert row["snapshot_date"] == count_day.isoformat()

    order = client.post(
        "/api/purchase-orders",
        headers=headers,
        json={
            "supplier_id": setup_store["supplier_id"],
            "warehouse_id": warehouse_id,
            "items": [{"product_id": product_id, "quantity": 20, "unit_cost": 9000}],
        },
    ).json()
    client.post(f"/api/purchase-orders/{order['id']}/submit", headers=headers)
    client.post(f"/api/purchase-orders/{order['id']}/approve", headers=headers)

    row = next(
        item
        for item in client.get("/api/inventory", headers=headers).json()
        if item["product_id"] == product_id
    )
    # Approved but not received: on hand unchanged, "đang về" carries it.
    assert row["on_hand"] == 91
    assert row["on_order"] == 20

    received = client.post(f"/api/purchase-orders/{order['id']}/receive", headers=headers)
    assert received.status_code == 200, received.text

    row = next(
        item
        for item in client.get("/api/inventory", headers=headers).json()
        if item["product_id"] == product_id
    )
    # Receiving does not write a second snapshot; the derived position moves.
    assert row["opening_on_hand"] == 100
    assert row["sold_since"] == 9
    assert row["received_since"] == 20
    assert row["on_hand"] == 111
    assert row["on_order"] == 0


def test_manual_purchase_order_lifecycle(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    order = client.post(
        "/api/purchase-orders",
        headers=headers,
        json={
            "supplier_id": setup_store["supplier_id"],
            "warehouse_id": setup_store["warehouse_id"],
            "notes": "Đơn thủ công",
            "items": [{"product_id": setup_store["product_id"], "quantity": 10, "unit_cost": 9000}],
        },
    )
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["status"] == "draft"
    assert body["total_amount"] == 90000

    submitted = client.post(f"/api/purchase-orders/{body['id']}/submit", headers=headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_approval"

    cancelled = client.post(f"/api/purchase-orders/{body['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_tenant_isolation(client: TestClient, setup_store: dict):
    headers = setup_store["headers"]
    order = client.post(
        "/api/purchase-orders",
        headers=headers,
        json={
            "warehouse_id": setup_store["warehouse_id"],
            "items": [{"product_id": setup_store["product_id"], "quantity": 5}],
        },
    ).json()

    second = client.post(
        "/api/auth/register",
        json={
            "store_name": "Cửa hàng Khác",
            "full_name": "Chủ Khác",
            "email": "other@test.vn",
            "password": "matkhau123",
        },
    )
    assert second.status_code == 201, second.text
    other_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    assert client.get("/api/products", headers=other_headers).json() == []
    assert client.get(f"/api/purchase-orders/{order['id']}", headers=other_headers).status_code == 404
    assert client.post(f"/api/purchase-orders/{order['id']}/approve", headers=other_headers).status_code == 404


def test_import_template_download(client: TestClient, auth_headers: dict):
    response = client.get("/api/imports/templates/sales", headers=auth_headers)
    assert response.status_code == 200
    assert "attachment; filename=\"template_sales.csv\"" in response.headers["content-disposition"]
    assert "sku,date,quantity" in response.content.decode("utf-8-sig").splitlines()[0]
