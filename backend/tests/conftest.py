"""Pytest configuration: isolated SQLite database, demo seeding disabled."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DB = BACKEND_DIR / "test_inventory.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["SECRET_KEY"] = "pytest-secret-key-not-for-production"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["LLM_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db_schema():
    """Fresh schema for every test; no demo tenant."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_schema):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "store_name": "Cửa hàng Test",
            "full_name": "Người Kiểm Thử",
            "email": "owner@test.vn",
            "password": "matkhau123",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def setup_store(client: TestClient, auth_headers: dict[str, str]) -> dict:
    """Tenant with one warehouse and one product ready for inventory/ordering."""
    warehouses = client.get("/api/warehouses", headers=auth_headers)
    assert warehouses.status_code == 200, warehouses.text
    assert warehouses.json(), "registration must create a default warehouse"
    warehouse = warehouses.json()[0]

    supplier = client.post(
        "/api/suppliers",
        headers=auth_headers,
        json={"name": "NCC Test", "lead_time_days": 3, "moq": 5, "order_multiple": 5},
    )
    assert supplier.status_code == 201, supplier.text

    product = client.post(
        "/api/products",
        headers=auth_headers,
        json={
            "sku": "TST-001",
            "name": "Sản phẩm kiểm thử",
            "unit": "cái",
            "unit_cost": 10000,
            "price": 20000,
            "supplier_id": supplier.json()["id"],
            "lead_time_days": 3,
            "moq": 5,
            "order_multiple": 5,
        },
    )
    assert product.status_code == 201, product.text

    return {
        "headers": auth_headers,
        "warehouse_id": warehouse["id"],
        "supplier_id": supplier.json()["id"],
        "product_id": product.json()["id"],
        "sku": "TST-001",
    }
