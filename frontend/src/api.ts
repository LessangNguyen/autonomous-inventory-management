const TOKEN_KEY = "aim_token";
const USER_KEY = "aim_user";
const TENANT_KEY = "aim_tenant";

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  tenant_id: number;
};

export type KpiCard = {
  label: string;
  value: number;
  unit: string;
  delta_pct: number | null;
  hint: string;
};

export type SalesPoint = { date: string; revenue: number; units: number };

export type RiskItem = {
  product_id: number;
  sku: string;
  product_name: string;
  on_hand: number;
  days_of_inventory: number | null;
  stockout_risk: string;
  suggested_qty: number;
};

export type DashboardSummary = {
  kpis: KpiCard[];
  sales_trend: SalesPoint[];
  top_risks: RiskItem[];
  open_alerts: number;
  pending_orders: number;
  last_forecast_at: string | null;
  total_products: number;
};

export type Product = {
  id: number;
  sku: string;
  name: string;
  category: string;
  unit: string;
  unit_cost: number;
  price: number;
  supplier_id: number | null;
  supplier_name: string | null;
  lead_time_days: number | null;
  moq: number | null;
  order_multiple: number | null;
  is_active: boolean;
};

export type Supplier = {
  id: number;
  name: string;
  email: string;
  lead_time_days: number;
  moq: number;
  order_multiple: number;
};

export type Warehouse = {
  id: number;
  code: string;
  name: string;
  location: string;
  is_default: boolean;
};

export type Recommendation = {
  id: number;
  product_id: number;
  warehouse_id: number;
  sku: string;
  product_name: string;
  as_of: string;
  avg_daily_demand: number;
  demand_std: number;
  lead_time_days: number;
  safety_stock: number;
  reorder_point: number;
  inventory_position: number;
  target_stock: number;
  suggested_qty: number;
  days_of_inventory: number | null;
  stockout_risk: string;
  status: string;
  on_hand: number;
  unit_cost: number;
};

export type Forecast = {
  id: number;
  product_id: number;
  warehouse_id: number;
  sku: string | null;
  product_name: string | null;
  horizon_days: number;
  predicted_qty: number;
  daily_series: number[];
  model_name: string;
  model_version: string;
  mae: number | null;
  rmse: number | null;
  wape: number | null;
  baseline_mae: number | null;
  confidence: string;
  trained_until: string | null;
  created_at: string;
};

export type ForecastRunResult = {
  products_processed: number;
  products_skipped: number;
  horizon_days: number;
  model_version: string;
  avg_mae: number | null;
  avg_wape: number | null;
  baseline_avg_mae: number | null;
  improvement_pct: number | null;
  duration_ms: number;
  notes: string[];
};

export type Alert = {
  id: number;
  product_id: number | null;
  sku: string | null;
  type: string;
  severity: string;
  message: string;
  status: string;
  created_at: string;
};

export type POItem = {
  id: number;
  product_id: number;
  quantity: number;
  unit_cost: number;
  sku: string | null;
  product_name: string | null;
};

export type PurchaseOrder = {
  id: number;
  supplier_id: number | null;
  supplier_name: string | null;
  warehouse_id: number;
  warehouse_name: string | null;
  status: string;
  source: string;
  total_amount: number;
  notes: string;
  items: POItem[];
  created_at: string;
  approved_at: string | null;
};

export type ImportJob = {
  id: number;
  kind: string;
  filename: string;
  status: string;
  rows_total: number;
  rows_ok: number;
  rows_failed: number;
  errors: { row: number; field?: string | null; message: string }[];
  created_at: string;
};

export type ImportDeleteCounts = {
  products: number;
  suppliers: number;
  sales_transactions: number;
  inventory_snapshots: number;
  forecasts: number;
  recommendations: number;
  alerts: number;
};

export type ImportDeleteSkip = {
  entity_type: string;
  entity_id: number;
  label: string;
  reason: string;
};

export type ImportDeletePreview = {
  job_id: number;
  kind: string;
  filename: string;
  status: string;
  rows_ok: number;
  will_delete: ImportDeleteCounts;
  skipped: ImportDeleteSkip[];
  updated_entities: number;
  legacy: boolean;
  notes: string[];
};

export type ImportDeleteResult = ImportDeletePreview & { status: string };

export type AgentToolCall = {
  tool: string;
  arguments: Record<string, unknown>;
  result_summary: string;
  ok: boolean;
};

export type AgentResponse = {
  run_id: number;
  answer: string;
  tool_calls: AgentToolCall[];
  status: string;
  pending_purchase_order_id: number | null;
  model: string;
  latency_ms: number;
};

export const session = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get user(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  },
  get tenant(): string {
    return localStorage.getItem(TENANT_KEY) ?? "";
  },
  save(token: string, user: User, tenant: string) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    localStorage.setItem(TENANT_KEY, tenant);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TENANT_KEY);
  },
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = session.token;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`/api${path}`, { ...options, headers });
  if (response.status === 401) {
    session.clear();
    if (!path.startsWith("/auth/")) {
      window.dispatchEvent(new Event("aim:unauthorized"));
    }
  }
  if (!response.ok) {
    let detail = "Đã có lỗi xảy ra.";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  authStatus: () =>
    request<{
      initialized: boolean;
      registration_open: boolean;
      demo_enabled: boolean;
      demo_email?: string;
      demo_password?: string;
    }>("/auth/status"),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User; tenant_name: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (payload: { store_name: string; full_name: string; email: string; password: string }) =>
    request<{ access_token: string; user: User; tenant_name: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),
  products: (q = "") => request<Product[]>(`/products${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  createProduct: (payload: Partial<Product>) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(payload) }),
  suppliers: () => request<Supplier[]>("/suppliers"),
  warehouses: () => request<Warehouse[]>("/warehouses"),
  inventory: (q = "") => request<Array<Record<string, unknown>>>(`/inventory${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  recommendations: (onlyNeed = false) =>
    request<Recommendation[]>(`/recommendations?only_need=${onlyNeed}&limit=300`),
  runRecommendations: () =>
    request<{ generated: number; critical: number; high: number; duration_ms: number }>(
      "/recommendations/run",
      { method: "POST" },
    ),
  updateRecommendation: (id: number, status: string) =>
    request<Recommendation>(`/recommendations/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  forecasts: () => request<Forecast[]>("/forecasts"),
  forecastFor: (productId: number) => request<Forecast[]>(`/forecasts?product_id=${productId}`),
  runForecasts: (horizon = 30) =>
    request<ForecastRunResult>("/forecasts/run", {
      method: "POST",
      body: JSON.stringify({ horizon_days: horizon, history_days: 180 }),
    }),
  alerts: (status = "open") => request<Alert[]>(`/alerts?status=${status}`),
  updateAlert: (id: number, status: string) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  scanAnomalies: () => request<{ alerts_created: number }>("/alerts/scan", { method: "POST" }),
  orders: () => request<PurchaseOrder[]>("/purchase-orders"),
  createOrder: (payload: {
    warehouse_id: number;
    supplier_id?: number | null;
    notes?: string;
    items: { product_id: number; quantity: number; unit_cost?: number }[];
  }) => request<PurchaseOrder>("/purchase-orders", { method: "POST", body: JSON.stringify(payload) }),
  approveOrder: (id: number) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/approve`, { method: "POST" }),
  receiveOrder: (id: number) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/receive`, { method: "POST" }),
  cancelOrder: (id: number) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/cancel`, { method: "POST" }),
  submitOrder: (id: number) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/submit`, { method: "POST" }),
  agentChat: (message: string) =>
    request<AgentResponse>("/agent/chat", { method: "POST", body: JSON.stringify({ message }) }),
  imports: () => request<ImportJob[]>("/imports"),
  uploadImport: (kind: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportJob>(`/imports/${kind}`, { method: "POST", body: form });
  },
  previewImportDeletion: (jobId: number) =>
    request<ImportDeletePreview>(`/imports/${jobId}/deletion-preview`),
  deleteImport: (jobId: number) =>
    request<ImportDeleteResult>(`/imports/${jobId}`, { method: "DELETE" }),
  templateUrl: (kind: string) => `/api/imports/templates/${kind}`,
  auditLogs: () =>
    request<Array<{ id: number; action: string; entity: string; details: Record<string, unknown>; created_at: string }>>(
      "/audit-logs",
    ),
};

export const formatVnd = (value: number) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(value) + " đ";

export const formatNumber = (value: number, digits = 0) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(value);

export const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString("vi-VN") : "—";
