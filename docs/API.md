# Tài liệu API

Base URL: `http://localhost:8000/api` · Swagger UI: `http://localhost:8000/docs` · OpenAPI JSON: `/openapi.json`

## 1. Xác thực

- Scheme: `Authorization: Bearer <access_token>` (JWT HS256, hạn 12 giờ).
- Lấy token qua `POST /auth/login` hoặc `POST /auth/register`.
- Mọi endpoint (trừ health/status/login/register) yêu cầu token hợp lệ.
- Vai trò: `owner`, `manager` ghi được nghiệp vụ; `staff` chỉ đọc.

Lỗi chuẩn của FastAPI:

```json
{ "detail": "Thông điệp tiếng Việt" }
```

| Mã | Ý nghĩa |
| --- | --- |
| 400 | Dữ liệu không hợp lệ |
| 401 | Thiếu/hết hạn/sai token |
| 403 | Không đủ quyền |
| 404 | Không tìm thấy hoặc khác tenant |
| 422 | Validate Pydantic thất bại |

## 2. Hệ thống

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| GET | `/api/health` | public | `{status, app, environment}` |
| GET | `/api/dashboard/summary` | đọc | KPI, xu hướng 30 ngày, top rủi ro, cảnh báo mở, đơn chờ |
| GET | `/api/audit-logs?limit=50` | đọc | Nhật ký hành động gần nhất |

## 3. Auth

| Method | Path | Body | Kết quả |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{store_name, full_name, email, password}` | 201 + token + user + tenant_name |
| GET | `/auth/status` | — | `{initialized, registration_open, demo_enabled}` (public) |
| POST | `/auth/login` | `{email, password}` | token + user + tenant_name |
| GET | `/auth/me` | — | user hiện tại |

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": { "id": 1, "email": "owner@example.com", "full_name": "Chủ cửa hàng", "role": "owner", "tenant_id": 1 },
  "tenant_name": "Cửa hàng của bạn"
}
```

## 4. Danh mục

| Method | Path | Quyền | Ghi chú |
| --- | --- | --- | --- |
| GET | `/products?q=&category=&limit=` | đọc | Tìm theo SKU/tên |
| POST | `/products` | owner/manager | 201; SKU trùng → 400 |
| PATCH | `/products/{id}` | owner/manager | Cập nhật toàn bộ trường |
| DELETE | `/products/{id}` | owner/manager | Soft-delete (`is_active=false`) |
| GET | `/suppliers` | đọc | |
| POST | `/suppliers` | owner/manager | |
| GET | `/warehouses` | đọc | |
| POST | `/warehouses` | owner/manager | |

`POST /products` ví dụ:

```json
{
  "sku": "SER-001",
  "name": "Serum Vitamin C 30ml",
  "category": "Chăm sóc da",
  "unit": "chai",
  "unit_cost": 145000,
  "price": 289000,
  "supplier_id": 1,
  "lead_time_days": 5,
  "moq": 12,
  "order_multiple": 6
}
```

## 5. Tồn kho

`GET /inventory?q=&warehouse_id=&limit=200`

Trả về tồn kho **được tính** cho từng cặp SKU–kho:

```
on_hand = opening_on_hand + received_since - sold_since
```

```json
[{
  "product_id": 1, "sku": "SER-001", "product_name": "Serum Vitamin C 30ml",
  "warehouse_id": 1, "warehouse_name": "Kho cửa hàng",
  "opening_on_hand": 120, "received_since": 36, "sold_since": 42,
  "on_hand": 114, "on_order": 12, "committed": 0,
  "snapshot_date": "2026-11-01", "has_opening_count": true
}]
```

- `opening_on_hand`: số dư tại mốc kiểm kê gần nhất (import `inventory`).
- `received_since` / `sold_since`: phát sinh sau mốc (đơn nhập đã nhận / hàng bán).
- `on_order`: số lượng trên các đơn `draft`, `pending_approval`, `approved`.
- `has_opening_count=false`: SKU chưa có tồn đầu kỳ; tồn hiện tại chỉ là net phát sinh,
  nên import tồn kho một lần để có con số tuyệt đối.

## 6. Import

| Method | Path | Body | Mô tả |
| --- | --- | --- | --- |
| GET | `/imports/templates/{kind}` | — | Tải CSV mẫu (`products`, `sales`, `inventory`, `suppliers`) |
| POST | `/imports/{kind}` | multipart `file` | 201 + `ImportJob` (rows_ok, errors) |
| GET | `/imports?limit=` | — | Lịch sử import (gồm `status=reverted` / `partial`) |
| GET | `/imports/{id}` | — | Chi tiết một job |
| GET | `/imports/{id}/deletion-preview` | — | Xem trước dữ liệu sẽ xóa / dữ liệu bị giữ lại |
| DELETE | `/imports/{id}` | — | Hoàn tác các dòng do job này tạo (ghi audit log) |

`DELETE` chỉ xóa dữ liệu **do lần import đó tạo ra**. Sản phẩm/nhà cung cấp đang
được bán hàng, tồn kho hoặc đơn nhập tham chiếu sẽ được giữ lại và trả trong
`skipped`; xóa lần import liên quan trước rồi thử lại. Dòng chỉ *cập nhật* dữ
liệu đã tồn tại không thể khôi phục giá trị cũ (hệ thống không lưu snapshot),
nên được giữ nguyên và báo trong `notes`.

Job tạo **trước khi bật theo dõi nguồn** (không có `import_sources`) dùng chế
độ dự phòng: xóa toàn bộ dữ liệu cùng loại của tenant. Preview trả
`legacy=true` và cảnh báo rõ; nên xóa theo thứ tự bán hàng → tồn kho → sản
phẩm → nhà cung cấp để tránh bị chặn bởi tham chiếu.

Dự báo, đề xuất nhập hàng và cảnh báo đang mở của các sản phẩm bị ảnh hưởng
được xóa để tránh số liệu cũ; chạy lại dự báo sau khi xóa.

```json
{
  "job_id": 7, "kind": "sales", "filename": "sales-wrong.csv",
  "status": "completed", "rows_ok": 98,
  "will_delete": {
    "products": 0, "suppliers": 0, "sales_transactions": 98,
    "inventory_snapshots": 0, "forecasts": 12,
    "recommendations": 12, "alerts": 3
  },
  "skipped": [],
  "updated_entities": 0,
  "notes": ["Dự báo, đề xuất và cảnh báo liên quan sẽ bị xóa ..."]
}
```

Giới hạn: `.csv`, `.xlsx`, `.xlsm`, ≤ 25 MB. Lỗi được trả theo dòng:

```json
{
  "id": 7, "kind": "sales", "filename": "sales.csv", "status": "completed",
  "rows_total": 100, "rows_ok": 98, "rows_failed": 2,
  "errors": [
    {"row": 14, "field": "sales", "message": "SKU 'ABC' chưa tồn tại. Hãy import sản phẩm trước."},
    {"row": 31, "field": "sales", "message": "Số lượng phải lớn hơn 0."}
  ]
}
```

## 7. Dự báo

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| POST | `/forecasts/run` | owner/manager | Train + dự báo, lưu kết quả |
| GET | `/forecasts?product_id=&limit=` | đọc | Dự báo mới nhất theo SKU (hoặc 20 bản gần nhất của 1 SKU) |
| GET | `/forecasts/models` | đọc | Số SKU theo mô hình được chọn |
| GET | `/forecasts/{id}/detail` | đọc | Chi tiết một bản dự báo |

Request:

```json
{ "horizon_days": 30, "product_ids": null, "history_days": 180 }
```

`horizon_days ∈ {7, 14, 30}`; `history_days ∈ [28, 730]`.

Kết quả chạy:

```json
{
  "products_processed": 24, "products_skipped": 0, "horizon_days": 30,
  "model_version": "v1.0", "avg_mae": 11.42, "avg_wape": 0.5465,
  "baseline_avg_mae": 11.63, "improvement_pct": 6.36,
  "duration_ms": 13060, "notes": []
}
```

> Số liệu trên lấy từ lần chạy dữ liệu synthetic trên máy phát triển; không phải
> cam kết độ chính xác thương mại.

## 8. Đề xuất nhập hàng

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| POST | `/recommendations/run` | owner/manager | Tính lại toàn bộ đề xuất cho hôm nay |
| GET | `/recommendations?q=&risk=&only_need=&limit=` | đọc | Danh sách đề xuất mới nhất, sort theo rủi ro |
| PATCH | `/recommendations/{id}/status` | owner/manager | `{ "status": "open" \| "ordered" \| "dismissed" }` |

```json
{
  "id": 12, "product_id": 1, "warehouse_id": 1, "as_of": "2026-11-10",
  "avg_daily_demand": 3.42, "demand_std": 2.11, "lead_time_days": 5,
  "safety_stock": 5.76, "reorder_point": 22.86, "inventory_position": 15,
  "target_stock": 46.74, "suggested_qty": 42, "days_of_inventory": 1.2,
  "stockout_risk": "critical", "status": "open",
  "sku": "SER-001", "product_name": "Serum Vitamin C 30ml", "on_hand": 4, "unit_cost": 145000
}
```

## 9. Đơn nhập hàng

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| GET | `/purchase-orders?status=&limit=` | đọc | Danh sách đơn |
| POST | `/purchase-orders` | owner/manager | Tạo đơn `draft` |
| GET | `/purchase-orders/{id}` | đọc | Chi tiết |
| POST | `/purchase-orders/{id}/submit` | owner/manager | `draft` → `pending_approval` |
| POST | `/purchase-orders/{id}/approve` | owner/manager | `pending_approval` → `approved` |
| POST | `/purchase-orders/{id}/receive` | owner/manager | `approved` → `received`; tồn kho tự cộng qua phát sinh |
| POST | `/purchase-orders/{id}/cancel` | owner/manager | Huỷ khi chưa nhận |

Tạo đơn:

```json
{
  "supplier_id": 1,
  "warehouse_id": 1,
  "notes": "Bổ sung hàng tuần",
  "items": [
    { "product_id": 1, "quantity": 42, "unit_cost": 145000 },
    { "product_id": 8, "quantity": 18, "unit_cost": 70000 }
  ]
}
```

Chuyển trạng thái sai (ví dụ nhận đơn `draft`) trả 400. `receive` ghi audit log
`purchase_order.receive` và cộng `on_hand` trong cùng transaction.

## 10. Cảnh báo

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| GET | `/alerts?status=open&severity=&limit=100` | đọc | `status=all` để lấy tất cả |
| PATCH | `/alerts/{id}` | owner/manager | `{ "status": "open" \| "acked" \| "resolved" }` |
| POST | `/alerts/scan` | owner/manager | Quét bất thường doanh số, trả `{alerts_created}` |

## 11. Trợ lý AI

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| POST | `/agent/chat` | đọc (có thể tạo nháp) | `{ "message": "..." }` |
| GET | `/agent/runs?limit=20` | đọc | Lịch sử hỏi đáp + tool calls |

```json
{
  "run_id": 4,
  "answer": "Mình đã tạo **đơn nhập nháp #1** với 5 SKU...",
  "tool_calls": [
    { "tool": "recommend_replenishment", "arguments": {"query": "", "limit": 5}, "result_summary": "...", "ok": true }
  ],
  "status": "pending_approval",
  "pending_purchase_order_id": 1,
  "model": "rule_router",
  "latency_ms": 6
}
```

Agent **không** có endpoint duyệt/nhận hàng. Đơn do agent tạo luôn ở trạng thái
`pending_approval` và phải được duyệt qua `/purchase-orders/{id}/approve`.

## 12. Mã lỗi nghiệp vụ thường gặp

| Tình huống | Mã | `detail` |
| --- | --- | --- |
| Sai mật khẩu | 401 | `Email hoặc mật khẩu không đúng.` |
| SKU trùng | 400 | `SKU đã tồn tại.` |
| Import sai loại file | 400 | `Chỉ hỗ trợ file .csv, .xlsx hoặc .xlsm.` |
| Duyệt đơn sai trạng thái | 400 | `Chỉ duyệt được đơn đang chờ phê duyệt.` |
| Nhận đơn chưa duyệt | 400 | `Chỉ nhận hàng cho đơn đã phê duyệt.` |
| Tenant khác | 404 | `Không tìm thấy ...` |
