from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / tenants ----------
class RegisterRequest(BaseModel):
    store_name: str = Field(min_length=2, max_length=160)
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant_name: str


# ---------- catalogue ----------
class SupplierIn(BaseModel):
    name: str
    email: str = ""
    lead_time_days: int = 7
    moq: int = 1
    order_multiple: int = 1


class SupplierOut(ORMModel):
    id: int
    name: str
    email: str
    lead_time_days: int
    moq: int
    order_multiple: int


class ProductIn(BaseModel):
    sku: str
    name: str
    category: str = ""
    unit: str = "cái"
    unit_cost: float = 0
    price: float = 0
    supplier_id: int | None = None
    lead_time_days: int | None = None
    moq: int | None = None
    order_multiple: int | None = None
    is_active: bool = True


class ProductOut(ORMModel):
    id: int
    sku: str
    name: str
    category: str
    unit: str
    unit_cost: float
    price: float
    supplier_id: int | None
    lead_time_days: int | None
    moq: int | None
    order_multiple: int | None
    is_active: bool
    supplier_name: str | None = None


class WarehouseIn(BaseModel):
    code: str
    name: str
    location: str = ""
    is_default: bool = False


class WarehouseOut(ORMModel):
    id: int
    code: str
    name: str
    location: str
    is_default: bool


class InventoryRow(BaseModel):
    product_id: int
    sku: str
    product_name: str
    warehouse_id: int
    warehouse_name: str
    opening_on_hand: float = 0
    received_since: float = 0
    sold_since: float = 0
    on_hand: float
    on_order: float
    committed: float
    snapshot_date: date | None = None
    has_opening_count: bool = True


# ---------- forecasting ----------
class ForecastRunRequest(BaseModel):
    horizon_days: Literal[7, 14, 30] = 30
    product_ids: list[int] | None = None
    history_days: int = Field(default=180, ge=28, le=730)


class ForecastOut(ORMModel):
    id: int
    product_id: int
    warehouse_id: int
    horizon_days: int
    predicted_qty: float
    daily_series: list[float]
    model_name: str
    model_version: str
    mae: float | None
    rmse: float | None
    wape: float | None
    baseline_mae: float | None
    confidence: str
    trained_until: date | None
    created_at: datetime
    sku: str | None = None
    product_name: str | None = None


class ForecastRunResult(BaseModel):
    products_processed: int
    products_skipped: int
    horizon_days: int
    model_version: str
    avg_mae: float | None
    avg_wape: float | None
    baseline_avg_mae: float | None
    improvement_pct: float | None
    duration_ms: int
    notes: list[str] = []


# ---------- recommendations ----------
class RecommendationOut(ORMModel):
    id: int
    product_id: int
    warehouse_id: int
    as_of: date
    avg_daily_demand: float
    demand_std: float
    lead_time_days: int
    safety_stock: float
    reorder_point: float
    inventory_position: float
    target_stock: float
    suggested_qty: float
    days_of_inventory: float | None
    stockout_risk: str
    status: str
    sku: str | None = None
    product_name: str | None = None
    on_hand: float | None = None
    unit_cost: float | None = None


class RecommendationRunResult(BaseModel):
    generated: int
    critical: int
    high: int
    duration_ms: int


# ---------- alerts ----------
class AlertOut(ORMModel):
    id: int
    product_id: int | None
    warehouse_id: int | None
    type: str
    severity: str
    message: str
    status: str
    created_at: datetime
    sku: str | None = None


# ---------- purchase orders ----------
class POItemIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    unit_cost: float = 0


class PurchaseOrderIn(BaseModel):
    supplier_id: int | None = None
    warehouse_id: int
    notes: str = ""
    items: list[POItemIn]


class POItemOut(ORMModel):
    id: int
    product_id: int
    quantity: float
    unit_cost: float
    sku: str | None = None
    product_name: str | None = None


class PurchaseOrderOut(ORMModel):
    id: int
    supplier_id: int | None
    warehouse_id: int
    status: str
    source: str
    total_amount: float
    notes: str
    created_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime
    items: list[POItemOut] = []
    supplier_name: str | None = None
    warehouse_name: str | None = None


# ---------- imports ----------
class ImportErrorRow(BaseModel):
    row: int
    field: str | None = None
    message: str


class ImportJobOut(ORMModel):
    id: int
    kind: str
    filename: str
    status: str
    rows_total: int
    rows_ok: int
    rows_failed: int
    errors: list[dict[str, Any]]
    created_at: datetime


class ImportDeleteCounts(BaseModel):
    products: int = 0
    suppliers: int = 0
    sales_transactions: int = 0
    inventory_snapshots: int = 0
    forecasts: int = 0
    recommendations: int = 0
    alerts: int = 0


class ImportDeleteSkip(BaseModel):
    entity_type: str
    entity_id: int
    label: str
    reason: str


class ImportDeletePreview(BaseModel):
    job_id: int
    kind: str
    filename: str
    status: str
    rows_ok: int
    will_delete: ImportDeleteCounts
    skipped: list[ImportDeleteSkip]
    updated_entities: int = 0
    legacy: bool = False
    notes: list[str] = []


class ImportDeleteResult(ImportDeletePreview):
    status: str = "reverted"


# ---------- agent ----------
class AgentChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result_summary: str
    ok: bool = True


class AgentChatResponse(BaseModel):
    run_id: int
    answer: str
    tool_calls: list[ToolCallRecord]
    status: str
    pending_purchase_order_id: int | None = None
    model: str
    latency_ms: int


# ---------- dashboard ----------
class KpiCard(BaseModel):
    label: str
    value: float
    unit: str = ""
    delta_pct: float | None = None
    hint: str = ""


class RiskItem(BaseModel):
    product_id: int
    sku: str
    product_name: str
    on_hand: float
    days_of_inventory: float | None
    stockout_risk: str
    suggested_qty: float


class SalesPoint(BaseModel):
    date: date
    revenue: float
    units: float


class DashboardSummary(BaseModel):
    kpis: list[KpiCard]
    sales_trend: list[SalesPoint]
    top_risks: list[RiskItem]
    open_alerts: int
    pending_orders: int
    last_forecast_at: datetime | None
    total_products: int = 0
