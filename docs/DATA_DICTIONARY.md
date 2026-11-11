# Từ điển dữ liệu

Tất cả bảng nghiệp vụ có `tenant_id` để cô lập dữ liệu theo cửa hàng.
Timestamp lưu UTC (naive) và được hiển thị theo giờ trình duyệt; ngày nghiệp vụ dùng `DATE`.

## tenants

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| name | varchar(160) | Tên cửa hàng |
| plan | varchar(32) | `trial` / `professional` |
| created_at | datetime | |

## users

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK → tenants | |
| email | varchar(255) unique | Dùng đăng nhập |
| full_name | varchar(160) | |
| hashed_password | varchar(255) | PBKDF2-HMAC-SHA256 |
| role | varchar(32) | `owner` / `manager` / `staff` |
| is_active | bool | |
| created_at | datetime | |

## warehouses

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| code | varchar(40) | Duy nhất trong tenant |
| name | varchar(160) | |
| location | varchar(255) | |
| is_default | bool | Kho dùng cho dự báo/đề xuất |

## suppliers

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| name | varchar(160) | Duy nhất trong tenant |
| email | varchar(255) | |
| lead_time_days | int | Mặc định 7 |
| moq | int | Số lượng đặt tối thiểu |
| order_multiple | int | Bội số đóng gói |

## products

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| sku | varchar(64) | Duy nhất trong tenant |
| name | varchar(255) | |
| category | varchar(120) | |
| unit | varchar(32) | `cái`, `chai`, `hộp`… |
| unit_cost | float | Giá vốn |
| price | float | Giá bán |
| supplier_id | int FK nullable | |
| lead_time_days | int nullable | Ghi đè lead time NCC |
| moq | int nullable | Ghi đè MOQ NCC |
| order_multiple | int nullable | Ghi đè bội số NCC |
| is_active | bool | |
| created_at | datetime | |

## inventory_snapshots

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| product_id | int FK | |
| warehouse_id | int FK | |
| on_hand | float | Tồn thực tế tại mốc kiểm kê (tồn đầu kỳ) |
| on_order | float | Đang về tại thời điểm chụp (dùng khi không có đơn mở) |
| committed | float | Đã cam kết/giữ cho khách |
| snapshot_date | date | Ngày chụp; bản ghi mới nhất là mốc tính tồn |
| created_at | datetime | |

Tồn kho hiện tại **không đọc trực tiếp** từ bảng này mà được suy ra:

```
on_hand = mốc on_hand + hàng nhận sau mốc − hàng bán sau mốc
inventory_position = on_hand + on_order − committed
```

`on_order` lấy từ các đơn nhập `draft` / `pending_approval` / `approved`. Ngày chụp được
hiểu là đầu ngày, nên phát sinh trong cùng ngày vẫn được cộng/trừ.

## sales_transactions / sales_items

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| sales_transactions.id | int PK | |
| tenant_id | int FK | |
| external_id | varchar(80) | Mã hoá đơn nguồn (tuỳ chọn) |
| warehouse_id | int FK nullable | |
| occurred_at | datetime | Thời điểm bán |
| total_amount | float | Tổng tiền |
| sales_items.transaction_id | int FK | |
| sales_items.product_id | int FK | |
| sales_items.quantity | float | Số lượng bán |
| sales_items.unit_price | float | Giá bán tại thời điểm đó |

## forecasts

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| product_id | int FK | |
| warehouse_id | int FK | |
| horizon_days | int | 7 / 14 / 30 |
| predicted_qty | float | Tổng nhu cầu dự báo |
| daily_series | json | Mảng số lượng từng ngày, dài `horizon_days` |
| model_name | varchar(64) | `moving_average`, `seasonal_naive`, `gbm_hist_gradient_boosting` |
| model_version | varchar(64) | `v1.0` |
| mae / rmse / wape | float nullable | Backtest 28 ngày |
| baseline_mae | float nullable | MAE baseline tốt nhất |
| confidence | varchar(16) | `low` / `medium` / `high` |
| trained_until | date | Ngày cuối của chuỗi huấn luyện |
| created_at | datetime | |

## replenishment_recommendations

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| product_id / warehouse_id | int FK | |
| as_of | date | Ngày tính |
| avg_daily_demand | float | Nhu cầu bình quân/ngày |
| demand_std | float | Độ lệch chuẩn nhu cầu/ngày |
| lead_time_days | int | Lead time hiệu lực |
| safety_stock | float | |
| reorder_point | float | |
| inventory_position | float | |
| target_stock | float | |
| suggested_qty | float | Đã làm tròn MOQ/bội số |
| days_of_inventory | float nullable | `on_hand / avg_daily_demand` |
| stockout_risk | varchar(16) | `low` / `medium` / `high` / `critical` |
| status | varchar(16) | `open` / `ordered` / `dismissed` |
| created_at | datetime | |

## purchase_orders / purchase_order_items

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| purchase_orders.id | int PK | |
| tenant_id | int FK | |
| supplier_id | int FK nullable | |
| warehouse_id | int FK | Kho nhận |
| status | varchar(32) | `draft` / `pending_approval` / `approved` / `received` / `cancelled` |
| source | varchar(32) | `manual` / `agent` / `recommendation` |
| total_amount | float | Tổng giá trị |
| notes | text | |
| created_by / approved_by | int FK users | |
| approved_at / received_at | datetime nullable | |
| items.product_id | int FK | |
| items.quantity | float > 0 | |
| items.unit_cost | float | |

## alerts

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| product_id / warehouse_id | int FK nullable | |
| type | varchar(48) | `stockout_risk` / `overstock` / `anomaly` / `data_quality` |
| severity | varchar(16) | `info` / `warning` / `critical` |
| message | text | Tiếng Việt, có SKU/ngày/lý do |
| status | varchar(16) | `open` / `acked` / `resolved` |
| created_at / updated_at | datetime | |

## agent_runs

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| user_id | int FK nullable | |
| question | text | Câu hỏi người dùng |
| answer | text | Câu trả lời cuối |
| tool_calls | json | `[{tool, arguments, result_summary, ok}]` |
| status | varchar(32) | `completed` / `pending_approval` / `error` |
| model | varchar(64) | `rule_router` hoặc tên model LLM |
| latency_ms | int | |
| created_at | datetime | |

## audit_logs

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| user_id | int FK nullable | |
| action | varchar(80) | Ví dụ `purchase_order.approve` |
| entity | varchar(80) | Loại đối tượng |
| entity_id | int nullable | |
| details | json | Ngữ cảnh bổ sung |
| created_at | datetime | |

## import_jobs

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| kind | varchar(32) | `products` / `sales` / `inventory` / `suppliers` |
| filename | varchar(255) | |
| status | varchar(16) | `completed` / `failed` / `partial` / `reverted` |
| rows_total / rows_ok / rows_failed | int | |
| errors | json | Tối đa 50 lỗi: `{row, field, message}` |
| created_by | int FK nullable | |
| created_at | datetime | |

## import_sources

Liên kết từng dòng do một lần import tạo/cập nhật, phục vụ hoàn tác.

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| id | int PK | |
| tenant_id | int FK | |
| job_id | int FK → import_jobs | |
| entity_type | varchar(32) | `product` / `supplier` / `sales_transaction` / `inventory_snapshot` |
| entity_id | int | ID của bản ghi tương ứng |
| action | varchar(16) | `created` / `updated` |
| created_at | datetime | |

Khi xóa một job: chỉ bản ghi `created` được xóa; bản ghi `updated` được giữ
nguyên (không có giá trị cũ để khôi phục). Nếu còn bản ghi bị tham chiếu,
job chuyển `partial` và giữ `import_sources` để có thể thử lại sau.

## Định dạng import

| Loại | Cột bắt buộc | Cột tuỳ chọn |
| --- | --- | --- |
| `products` | `sku`, `name` | `category`, `unit`, `unit_cost`, `price`, `supplier_name`, `lead_time_days`, `moq`, `order_multiple` |
| `sales` | `sku`, `date`, `quantity` | `unit_price`, `warehouse_code`, `external_id` |
| `inventory` | `sku`, `on_hand` | `warehouse_code`, `on_order`, `committed`, `date` |
| `suppliers` | `name` | `email`, `lead_time_days`, `moq`, `order_multiple` |

Tên cột được chuẩn hoá (chữ thường, khoảng trắng → `_`), nên `Unit Cost` và `unit_cost`
đều hợp lệ. File CSV đọc UTF-8 (có BOM) hoặc CP1258; Excel đọc `.xlsx`/`.xls`.
