"""Demo seed: a realistic cosmetics / mini-mart store so the product is usable
immediately after ``docker compose up``.

The data is SYNTHETIC. It is labelled as such everywhere it surfaces and must
never be used to claim commercial forecasting accuracy.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    InventorySnapshot,
    Product,
    SalesItem,
    SalesTransaction,
    Supplier,
    Tenant,
    User,
    Warehouse,
)

DAYS = 200
SEED = 42

SUPPLIERS = [
    ("Công ty Mỹ phẩm Ánh Dương", 5, 12, 6),
    ("Nhà phân phối Thực phẩm Xanh", 3, 24, 12),
    ("Tổng kho Gia dụng Việt", 7, 6, 6),
]

PRODUCTS = [
    # sku, name, category, unit, cost, price, supplier_index, lead_time, moq, multiple, base_daily, trend, zero_prob
    ("SER-001", "Serum Vitamin C 30ml", "Chăm sóc da", "chai", 145000, 289000, 0, 5, 12, 6, 3.2, 0.25, 0.05),
    ("SUN-002", "Kem chống nắng SPF50+", "Chăm sóc da", "tuýp", 98000, 199000, 0, 5, 12, 6, 4.5, 0.4, 0.03),
    ("CLE-003", "Sữa rửa mặt dịu nhẹ", "Chăm sóc da", "tuýp", 62000, 135000, 0, 5, 24, 12, 5.5, 0.1, 0.02),
    ("TON-004", "Toner hoa hồng 250ml", "Chăm sóc da", "chai", 85000, 175000, 0, 5, 12, 6, 2.8, 0.2, 0.08),
    ("MAS-005", "Mặt nạ giấy (hộp 10)", "Chăm sóc da", "hộp", 45000, 99000, 0, 5, 20, 10, 3.6, 0.0, 0.06),
    ("LIP-006", "Son môi kem lì", "Trang điểm", "thỏi", 55000, 149000, 0, 5, 12, 12, 2.4, -0.1, 0.1),
    ("FOU-007", "Phấn nền lâu trôi 24h", "Trang điểm", "hộp", 120000, 265000, 0, 5, 6, 6, 1.8, 0.05, 0.12),
    ("MAS-008", "Mascara không lem", "Trang điểm", "cây", 70000, 165000, 0, 5, 12, 6, 2.0, 0.0, 0.15),
    ("SHA-009", "Dầu gội thảo dược 500ml", "Chăm sóc tóc", "chai", 78000, 159000, 0, 5, 12, 6, 4.2, 0.15, 0.03),
    ("CON-010", "Dầu xả phục hồi 500ml", "Chăm sóc tóc", "chai", 82000, 169000, 0, 5, 12, 6, 3.1, 0.15, 0.05),
    ("KER-011", "Ủ tóc keratin 250g", "Chăm sóc tóc", "hũ", 95000, 210000, 0, 5, 6, 6, 1.2, 0.0, 0.2),
    ("BOD-012", "Sữa tắm trắng da 1L", "Chăm sóc cơ thể", "chai", 88000, 179000, 0, 5, 12, 6, 3.4, 0.05, 0.04),
    ("HAN-013", "Nước rửa tay 500ml", "Chăm sóc cơ thể", "chai", 35000, 79000, 0, 5, 24, 12, 2.2, -0.2, 0.1),
    ("MSK-014", "Khẩu trang y tế (hộp 50)", "Chăm sóc cơ thể", "hộp", 25000, 55000, 2, 7, 24, 12, 2.9, -0.4, 0.08),
    ("WAT-015", "Nước suối 500ml (lốc 6)", "Đồ uống", "lốc", 28000, 45000, 1, 3, 24, 12, 8.5, 0.2, 0.01),
    ("COF-016", "Cà phê lon 330ml", "Đồ uống", "lon", 12000, 22000, 1, 3, 48, 24, 12.0, 0.3, 0.01),
    ("TEA-017", "Trà xanh chai 500ml", "Đồ uống", "chai", 9000, 18000, 1, 3, 48, 24, 9.5, 0.1, 0.02),
    ("BIS-018", "Bánh quy bơ 300g", "Thực phẩm", "hộp", 32000, 65000, 1, 3, 12, 6, 3.8, 0.0, 0.05),
    ("CAS-019", "Hạt điều rang muối 250g", "Thực phẩm", "gói", 55000, 115000, 1, 3, 12, 6, 2.1, 0.1, 0.1),
    ("CAN-020", "Nến thơm phòng", "Gia dụng", "hũ", 48000, 119000, 2, 7, 6, 6, 1.1, 0.0, 0.25),
    ("BAG-021", "Túi giữ nhiệt", "Gia dụng", "cái", 65000, 149000, 2, 7, 6, 6, 0.9, 0.05, 0.3),
    ("BOT-022", "Bình nước thể thao 750ml", "Gia dụng", "cái", 52000, 129000, 2, 7, 6, 6, 1.4, 0.1, 0.2),
    ("CAB-023", "Dây sạc USB-C 1m", "Phụ kiện", "cái", 38000, 95000, 2, 7, 12, 12, 2.6, 0.2, 0.12),
    ("EAR-024", "Tai nghe có dây", "Phụ kiện", "cái", 42000, 119000, 2, 7, 6, 6, 0.7, 0.0, 0.35),
]


def _daily_demand(
    rng: np.random.Generator, base: float, trend: float, zero_prob: float, day_index: int
) -> float:
    weekday = 1 + 0.18 * math.sin(day_index * 2 * math.pi / 7)
    growth = 1 + trend * (day_index / DAYS)
    promo = 1.6 if day_index % 45 in {10, 11, 12} else 1.0
    noise = rng.gamma(shape=4.0, scale=0.25)
    if rng.random() < zero_prob:
        return 0.0
    return max(0.0, round(base * weekday * growth * promo * noise, 2))


def seed_demo(db: Session) -> int | None:
    """Create the demo tenant once. Returns the tenant id when seeded."""
    existing_tenant = db.query(Tenant).filter(Tenant.name == "Cửa hàng Demo").first()
    if existing_tenant:
        demo_user = db.query(User).filter(User.email == "demo@inventory.ai").first()
        if not demo_user:
            db.add(
                User(
                    tenant_id=existing_tenant.id,
                    email="demo@inventory.ai",
                    full_name="Khách hàng Demo",
                    hashed_password=hash_password("demo1234"),
                    role="owner",
                )
            )
            db.commit()
        return None

    tenant = Tenant(name="Cửa hàng Demo", plan="professional")
    db.add(tenant)
    db.flush()

    db.add(
        User(
            tenant_id=tenant.id,
            email="demo@inventory.ai",
            full_name="Khách hàng Demo",
            hashed_password=hash_password("demo1234"),
            role="owner",
        )
    )

    warehouse = Warehouse(
        tenant_id=tenant.id, code="MAIN", name="Kho cửa hàng", location="Quận 1, TP.HCM", is_default=True
    )
    db.add(warehouse)
    db.flush()

    suppliers: list[Supplier] = []
    for index, (name, lead_time, moq, multiple) in enumerate(SUPPLIERS):
        supplier = Supplier(
            tenant_id=tenant.id,
            name=name,
            lead_time_days=lead_time,
            moq=moq,
            order_multiple=multiple,
            email=f"order{index + 1}@supplier.vn",
        )
        db.add(supplier)
        suppliers.append(supplier)
    db.flush()

    rng = np.random.default_rng(SEED)
    random.seed(SEED)
    today = date.today()

    history: dict[int, float] = {}
    for (
        sku, name, category, unit, cost, price, supplier_index, lead_time, moq, multiple,
        base, trend, zero_prob,
    ) in PRODUCTS:
        product = Product(
            tenant_id=tenant.id,
            sku=sku,
            name=name,
            category=category,
            unit=unit,
            unit_cost=cost,
            price=price,
            supplier_id=suppliers[supplier_index].id,
            lead_time_days=lead_time,
            moq=moq,
            order_multiple=multiple,
            is_active=True,
        )
        db.add(product)
        db.flush()

        total = 0.0
        for offset in range(DAYS, 0, -1):
            day = today - timedelta(days=offset)
            day_index = DAYS - offset
            quantity = _daily_demand(rng, base, trend, zero_prob, day_index)
            if quantity <= 0:
                continue
            transaction = SalesTransaction(
                tenant_id=tenant.id,
                warehouse_id=warehouse.id,
                occurred_at=datetime.combine(day, datetime.min.time())
                + timedelta(hours=10 + day_index % 8),
                total_amount=round(quantity * price, 2),
            )
            db.add(transaction)
            db.flush()
            db.add(
                SalesItem(
                    transaction_id=transaction.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=price,
                )
            )
            total += quantity
        history[product.id] = total / DAYS

    # Inventory roughly covers lead time + review window, with deliberate risk cases.
    for index, product in enumerate(
        db.query(Product).filter(Product.tenant_id == tenant.id).order_by(Product.id).all()
    ):
        average = history.get(product.id, 1.0) or 1.0
        lead_time = product.lead_time_days or 7
        coverage = random.uniform(1.1, 2.4) * (lead_time + 7)
        if index % 7 == 0:  # every 7th SKU is close to a stock-out
            coverage = random.uniform(0.2, 0.9) * lead_time
        on_hand = max(0.0, round(average * coverage))
        db.add(
            InventorySnapshot(
                tenant_id=tenant.id,
                product_id=product.id,
                warehouse_id=warehouse.id,
                on_hand=on_hand,
                on_order=round(average * random.choice([0, 0, 3, 7])),
                committed=round(average * random.choice([0, 0, 1, 2])),
                snapshot_date=today,
            )
        )

    db.commit()
    return tenant.id
