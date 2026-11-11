# Kiến trúc hệ thống

## 1. Tổng quan

Hệ thống gồm ba tiến trình độc lập, giao tiếp qua HTTP/JSON:

```
Browser (React SPA)
   │  /api/*  (JWT Bearer)
   ▼
FastAPI (uvicorn) ── SQLAlchemy ── SQLite (dev) / PostgreSQL (compose)
   │
   ├── ai/forecasting        # chuỗi thời gian, chọn mô hình
   ├── ai/anomaly_detection  # z-score + Isolation Forest
   └── ai/agents             # RuleRouter / LLM tool-calling
```

Không có worker/queue riêng trong MVP: dự báo chạy đồng bộ trong request và được
ghi thành các bản ghi `forecasts`. Với 24 SKU, một lần chạy mất ~13 giây trên máy
phát triển; khi mở rộng nên chuyển sang background job.

## 2. Thành phần

### 2.1. Backend (`backend/app`)

| Lớp | Trách nhiệm |
| --- | --- |
| `api/` | Router HTTP, kiểm tra quyền, map lỗi sang mã HTTP |
| `core/` | Cấu hình (pydantic-settings), engine/session, JWT, dependency auth |
| `models/` | ORM SQLAlchemy; mọi bảng nghiệp vụ có `tenant_id` |
| `schemas/` | Pydantic request/response, validate đầu vào |
| `services/` | Logic nghiệp vụ thuần: import, dự báo, quyết định, agent, seed, dashboard |

Quy ước: router **không** chứa công thức; mọi tính toán nằm trong `services/` để test được.

### 2.2. AI package (`ai/`, dùng chung cấp repo)

| Module | Vai trò |
| --- | --- |
| `forecasting/features.py` | Làm sạch chuỗi ngày, lag/rolling/calendar features |
| `forecasting/baselines.py` | Moving average, seasonal naive |
| `forecasting/metrics.py` | MAE, RMSE, WAPE, confidence |
| `forecasting/engine.py` | Backtest giữ trật tự thời gian, chọn mô hình, dự báo đệ quy |
| `anomaly_detection/detector.py` | Z-score theo thứ trong tuần + Isolation Forest |
| `agents/tools.py` | Tool allowlist, thực thi qua service layer |
| `agents/router.py` | Router ý định tiếng Việt xác định (offline) |
| `agents/graph.py` | Vòng lặp LLM/LangGraph tuỳ chọn |

`backend/app/__init__.py` thêm thư mục gốc repo vào `sys.path` để `ai.*` import được
khi chạy từ `backend/`.

### 2.3. Frontend (`frontend/src`)

- React 18 + TypeScript + Vite, React Router.
- `api.ts`: fetch wrapper, lưu token trong `localStorage`, xử lý 401 (`aim:unauthorized`).
- 8 trang: Tổng quan, Dự báo, Đề xuất, Đơn nhập, Sản phẩm & kho, Nhập dữ liệu, Cảnh báo, Trợ lý AI.
- Chart bằng `recharts`; CSS thuần trong `styles.css` (không phụ thuộc UI kit).

## 3. Mô hình dữ liệu (rút gọn)

```
Tenant 1─* User
Tenant 1─* Warehouse, Supplier, Product
Product 1─* InventorySnapshot   (tồn đầu kỳ: on_hand, on_order, committed, snapshot_date)
Product 1─* SalesItem           (trừ tồn sau mốc)
Product 1─* PurchaseOrderItem   (cộng tồn khi đơn received)
SalesTransaction 1─* SalesItem *─1 Product
Product 1─* Forecast            (horizon, daily_series JSON, metrics)
Product 1─* ReplenishmentRecommendation (as_of, ROP, safety stock, suggested_qty)
PurchaseOrder 1─* PurchaseOrderItem *─1 Product
Tenant 1─* Alert, AgentRun, AuditLog, ImportJob
```

Chi tiết từng cột: [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).

## 4. Luồng chính

### 4.1. Import dữ liệu

```
Upload CSV/XLSX → đọc bảng → chuẩn hoá tên cột → validate từng dòng
→ ghi dòng hợp lệ → lưu ImportJob (rows_ok, rows_failed, errors[≤50])
```

Không có dòng nào bị “im lặng bỏ qua”: mọi lỗi trả về số dòng và lý do.

### 4.2. Dự báo

```
POST /forecasts/run
 → lấy chuỗi bán hàng ngày (warehouse mặc định, history_days)
 → nếu < 7 ngày: skip + note
 → features + baseline + HGB, backtest 28 ngày cuối
 → chọn mô hình nếu ML cải thiện MAE > 2%
 → dự báo đệ quy horizon ngày
 → lưu Forecast (model, metrics, daily_series, trained_until)
```

### 4.3. Đề xuất nhập hàng

```
GET forecast mới nhất + tồn kho suy ra (mốc + nhập − bán)
 → compute_recommendation(...)  (safety stock, ROP, target, MOQ, multiple)
 → upsert ReplenishmentRecommendation cho ngày hiện tại
 → tạo alert stockout_risk / overstock
```

### 4.4. Đơn nhập hàng (human-in-the-loop)

```
draft ──submit──► pending_approval ──approve(owner|manager)──► approved
                                                   │
                                                   └──receive──► received (tồn kho suy ra tăng)
draft/pending_approval ──cancel──► cancelled
```

`receive` chỉ đánh dấu đơn đã nhận và ghi audit log; tồn kho được tính lại từ phát sinh
(`tồn đầu kỳ + đã nhận − đã bán`), nên không ghi thêm snapshot và không bị cộng trùng.
Agent chỉ có thể tạo `draft`/`pending_approval`; không có tool duyệt hay nhận hàng.

## 5. Bảo mật & cô lập dữ liệu

- Mật khẩu: PBKDF2-HMAC-SHA256 với salt ngẫu nhiên; không lưu plaintext.
- JWT HS256, token chứa `sub`, `tenant_id`, `role`, hạn 12 giờ.
- Mọi query nghiệp vụ lọc `tenant_id` của user hiện tại.
- RBAC: `owner` (toàn quyền), `manager` (ghi nghiệp vụ, duyệt đơn), `staff` (chỉ đọc).
- Audit log cho hành động ghi quan trọng (tạo/duyệt/nhận/huỷ đơn, chạy agent…).
- CORS giới hạn theo `CORS_ORIGINS`.
- PostgreSQL RLS là hạng mục production hoá (chưa bật mặc định).

## 6. Quyết định thiết kế

| Quyết định | Lý do |
| --- | --- |
| SQLite mặc định | Chạy được ngay, không cần hạ tầng; compose đổi sang Postgres |
| Dự báo theo yêu cầu, không lúc khởi động | API khởi động < 4 giây; tránh train lặp lại |
| Baseline fallback | SKU ít dữ liệu vẫn có dự báo hợp lý, không “bịa” ML |
| RuleRouter mặc định | Chạy offline ổn định, tránh phụ thuộc API key/chi phí |
| Lưu `daily_series` JSON | Audit được từng ngày dự báo; hiển thị chart không cần tính lại |
| Dùng `date` cho ngày bán | Tránh lệch múi giờ khi group theo ngày |

## 7. Mở rộng đề xuất

- Chuyển dự báo sang background job (Celery/RQ/Arq) + cache kết quả.
- Bật PostgreSQL RLS và mã hoá dữ liệu nhạy cảm.
- Thêm refresh token, SSO, audit export.
- Tối ưu tồn kho đa kho (transportation problem) và ràng buộc ngân sách/hạn dùng.
