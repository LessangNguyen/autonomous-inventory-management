"""SQLAlchemy ORM models.

Every business table carries a ``tenant_id`` so that data isolation can be
enforced both at the query layer and (via PostgreSQL RLS in production) at the
database layer. See docs/DATA_DICTIONARY.md for field definitions.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    plan = Column(String(32), default="trial", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(160), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), default="owner", nullable=False)  # owner | manager | staff
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="users")


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouse_code"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name = Column(String(160), nullable=False)
    location = Column(String(255), default="")
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_supplier_name"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    email = Column(String(255), default="")
    lead_time_days = Column(Integer, default=7, nullable=False)
    moq = Column(Integer, default=1, nullable=False)
    order_multiple = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_sku"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    sku = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(120), default="")
    unit = Column(String(32), default="cái")
    unit_cost = Column(Float, default=0, nullable=False)
    price = Column(Float, default=0, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    lead_time_days = Column(Integer, nullable=True)  # overrides supplier lead time
    moq = Column(Integer, nullable=True)
    order_multiple = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    supplier = relationship("Supplier")


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    on_hand = Column(Float, default=0, nullable=False)
    on_order = Column(Float, default=0, nullable=False)
    committed = Column(Float, default=0, nullable=False)
    snapshot_date = Column(Date, default=date.today, nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class SalesTransaction(Base):
    __tablename__ = "sales_transactions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    external_id = Column(String(80), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    occurred_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    total_amount = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class SalesItem(Base):
    __tablename__ = "sales_items"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("sales_transactions.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Float, default=0, nullable=False)
    unit_price = Column(Float, default=0, nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(String(32), default="draft", nullable=False, index=True)
    # draft | pending_approval | approved | received | cancelled
    source = Column(String(32), default="manual", nullable=False)  # manual | agent | recommendation
    total_amount = Column(Float, default=0, nullable=False)
    notes = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    items = relationship(
        "PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(
        Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0, nullable=False)

    order = relationship("PurchaseOrder", back_populates="items")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    horizon_days = Column(Integer, nullable=False)
    predicted_qty = Column(Float, nullable=False)
    daily_series = Column(JSON, default=list, nullable=False)
    model_name = Column(String(64), nullable=False)
    model_version = Column(String(64), default="v1", nullable=False)
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    wape = Column(Float, nullable=True)
    baseline_mae = Column(Float, nullable=True)
    confidence = Column(String(16), default="medium", nullable=False)  # low | medium | high
    trained_until = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ReplenishmentRecommendation(Base):
    __tablename__ = "replenishment_recommendations"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    as_of = Column(Date, default=date.today, nullable=False, index=True)
    avg_daily_demand = Column(Float, nullable=False)
    demand_std = Column(Float, nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    safety_stock = Column(Float, nullable=False)
    reorder_point = Column(Float, nullable=False)
    inventory_position = Column(Float, nullable=False)
    target_stock = Column(Float, nullable=False)
    suggested_qty = Column(Float, nullable=False)
    days_of_inventory = Column(Float, nullable=True)
    stockout_risk = Column(String(16), default="low", nullable=False)  # low|medium|high|critical
    status = Column(String(16), default="open", nullable=False)  # open | ordered | dismissed
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    type = Column(String(48), nullable=False)  # stockout_risk | overstock | anomaly | data_quality
    severity = Column(String(16), default="warning", nullable=False)  # info|warning|critical
    message = Column(Text, nullable=False)
    status = Column(String(16), default="open", nullable=False)  # open | acked | resolved
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False, default="")
    tool_calls = Column(JSON, default=list, nullable=False)
    status = Column(String(32), default="completed", nullable=False)  # completed | pending_approval | error
    model = Column(String(64), default="router", nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False)
    entity = Column(String(80), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)  # products | sales | inventory | suppliers
    filename = Column(String(255), nullable=False)
    status = Column(String(16), default="completed", nullable=False)  # completed | failed | partial | reverted
    rows_total = Column(Integer, default=0, nullable=False)
    rows_ok = Column(Integer, default=0, nullable=False)
    rows_failed = Column(Integer, default=0, nullable=False)
    errors = Column(JSON, default=list, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ImportSource(Base):
    """Links rows created or updated by an import job so the job can be reverted.

    ``entity_type`` is one of ``product``, ``supplier``,
    ``sales_transaction`` or ``inventory_snapshot``. Only rows created by the
    job are deleted on revert; rows that merely updated existing data are kept
    and reported to the user (their previous values are not snapshotted).
    """

    __tablename__ = "import_sources"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String(16), default="created", nullable=False)  # created | updated
    created_at = Column(DateTime, default=utcnow, nullable=False)
