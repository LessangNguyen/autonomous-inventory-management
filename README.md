# Autonomous Inventory Management System — Inventory AI

Hệ thống quản lý tồn kho tự động cho cửa hàng nhỏ và chuỗi bán lẻ: dự báo nhu cầu theo SKU,
Đề xuất nhập hàng dựa trên tồn kho và lead time, cảnh báo bất thường, và trợ lý AI có bước
**con người phê duyệt** trước mọi thay đổi ghi dữ liệu.

Giao diện và nội dung sản phẩm bằng tiếng Việt. Hệ thống **không tạo dữ liệu mẫu**:
bạn tạo cửa hàng, import dữ liệu thật và mọi con số đều tính từ dữ liệu đó.

![stack](https://img.shields.io/badge/FastAPI-0.115-009688) ![stack](https://img.shields.io/badge/React-18-61dafb) ![stack](https://img.shields.io/badge/PostgreSQL-16-336791) ![stack](https://img.shields.io/badge/scikit--learn-1.5-f7931e)

---

## 1. Tính năng chính

| Khu vực | Chức năng |
| --- | --- |
| **Tổng quan** | KPI tồn kho, giá trị hàng, số SKU rủi ro, biểu đồ nhu cầu 30 ngày, danh sách SKU cần nhập, nút chạy dự báo |
| **Dự báo nhu cầu** | Dự báo 7 / 14 / 30 ngày cho từng SKU, hiển thị MAE/RMSE/WAPE, mô hình được chọn và so sánh với baseline |
| **Đề xuất nhập hàng** | Safety stock, reorder point (ROP), tồn kho mục tiêu, số lượng đề xuất (tôn trọng MOQ & bội số đặt hàng), mức rủi ro |
| **Đơn nhập hàng** | Tạo nháp → gửi duyệt → **phê duyệt** → nhận hàng (tồn kho tự cập nhật) / huỷ; ghi audit log |
| **Sản phẩm & kho** | Danh mục SKU, nhà cung cấp, tồn kho hiện tại (tính từ mốc + nhập − bán), thêm sản phẩm nhanh |
| **Nhập dữ liệu** | CSV/Excel cho sản phẩm, bán hàng, **tồn kho đầu kỳ**, nhà cung cấp; báo cáo lỗi theo từng dòng; tải file mẫu |
| **Cảnh báo** | Rủi ro hết hàng, tồn kho quá mức, bất thường doanh số (z-score theo thứ trong tuần + Isolation Forest), xác nhận/đóng cảnh báo |
| **Trợ lý AI** | Hỏi đáp tiếng Việt về tồn kho/đề xuất/dự báo; tạo **đơn nháp** chờ duyệt; lịch sử chạy và tool calls |

**Nguyên tắc an toàn:** agent chỉ được đọc dữ liệu và tạo *đơn nháp*. Không có tool nào
được phép phê duyệt, nhận hàng, xoá dữ liệu hay gửi đơn cho nhà cung cấp.

### Cách tính tồn kho

Tồn kho **không phải nhập lại mỗi lần**. Bạn chỉ cần một **tồn kho đầu kỳ** làm mốc
(import một lần), sau đó hệ thống tính:

```
tồn hiện tại = tồn đầu kỳ + hàng đã nhận từ đơn nhập − hàng đã bán
```

- Mốc là bản ghi tồn kho mới nhất theo SKU–kho (ngày chụp được hiểu là đầu ngày).
- Đơn nhập ở trạng thái `approved` hiển thị là **đang về**; khi bấm **Nhận hàng** thì
  chuyển sang **đã nhập** và tự cộng vào tồn.
- Mọi dòng bán hàng import/ghi nhận sau ngày chụp đều tự trừ tồn.
- Nếu bạn nhập lại một tồn kho mới, mốc mới thay thế mốc cũ (dùng khi kiểm kê thực tế).

---

## 🌟 Tài khoản Demo trải nghiệm nhanh (Dành cho khách hàng test giao diện)

Hệ thống được cấu hình sẵn **tài khoản Demo** kèm dữ liệu mẫu sinh động (mô phỏng cửa hàng bán lẻ/mỹ phẩm với 24 SKU, 200 ngày lịch sử bán hàng, các mức tồn kho thực tế, cảnh báo rủi ro và trợ lý AI):

| Thông tin | Giá trị |
| --- | --- |
| **URL giao diện** | http://localhost:3000 *(Docker)* hoặc http://localhost:5173 *(Local)* |
| **Email đăng nhập** | `demo@inventory.ai` |
| **Mật khẩu** | `demo1234` |
| **Vai trò** | Chủ cửa hàng (`owner`) |
| **Cửa hàng demo** | Cửa hàng Demo (kèm đầy đủ báo cáo, dự báo, đơn hàng mẫu) |

> 💡 **Đăng nhập 1-click:** Tại màn hình Đăng nhập, khách hàng chỉ cần bấm nút **`⚡ Đăng nhập nhanh tài khoản Demo`** để vào thẳng Dashboard trải nghiệm toàn bộ giao diện và chức năng mà không cần nhập tay!

---

## 2. Khởi chạy nhanh

### 2.1. Docker Compose (khuyến nghị)

```bash
cp .env.example .env
docker compose up --build
```

| Thành phần | URL |
| --- | --- |
| Giao diện | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/health |

- **Khách hàng test giao diện:** Đăng nhập ngay bằng **`demo@inventory.ai`** / **`demo1234`** (hoặc click nút đăng nhập nhanh trên màn hình).
- **Triển khai dữ liệu thật:** Bạn có thể chọn tab **Tạo cửa hàng** để tạo tài khoản mới và import dữ liệu thực tế của doanh nghiệp.

### 2.2. Chạy local (không cần Docker)

Yêu cầu: Python 3.11+ và Node.js 18+.

```powershell
# 1) Backend
cd K:\autonomous-inventory-management
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
# 2) Frontend (terminal khác)
cd K:\autonomous-inventory-management\frontend
npm install
npm run dev
```

Mở http://localhost:5173 (Vite proxy `/api` → `http://127.0.0.1:8000`).

Mặc định backend dùng **SQLite** (`backend/inventory.db`), nên không cần cài PostgreSQL.
Muốn dùng PostgreSQL, đặt `DATABASE_URL` theo mẫu trong `.env.example`.

> Trên Linux/macOS dùng `.venv/bin/python`. Có thể dùng `make install|backend|frontend|test`.

### 2.3. Lần chạy đầu tiên (dữ liệu thật)

1. Mở giao diện → **Tạo cửa hàng** (tên cửa hàng, họ tên, email, mật khẩu).
2. Vào **Nhập dữ liệu** → tải **template** cho từng loại.
3. Import theo thứ tự: **Sản phẩm** → **Tồn kho đầu kỳ** → **Lịch sử bán hàng** (Nhà cung cấp là tùy chọn).
4. Vào **Tổng quan** → bấm **Chạy dự báo & đề xuất** (train mô hình cho toàn bộ SKU).
5. Vào **Đề xuất nhập hàng** → xem SKU cần nhập, số lượng và lý do.
6. Vào **Trợ lý AI** → hỏi *“Tạo đơn nhập hàng cho các SKU sắp hết”*.
7. Vào **Đơn nhập hàng** → kiểm tra đơn nháp → **Phê duyệt** → **Nhận hàng**.

> Cần ít nhất 7 ngày bán hàng cho một SKU để dự báo; nên có 30–180 ngày để kết quả ổn định.
> Tồn kho đầu kỳ chỉ cần import **một lần**; sau đó hàng bán và đơn nhập tự cập nhật tồn.

**Import sai?** Vào **Nhập dữ liệu → Lịch sử import**, bấm **Xóa** ở lần import
sai. Hệ thống xem trước số dòng sẽ xóa, giữ lại dữ liệu đang được tham chiếu và
ghi audit log. Dự báo/đề xuất liên quan được xóa để tránh số liệu cũ — chạy lại
dự báo sau khi xóa. Với lần import cũ tạo trước khi bật tính năng này, phạm vi
xóa là toàn bộ dữ liệu cùng loại; nên xóa theo thứ tự bán hàng → tồn kho →
sản phẩm → nhà cung cấp.

---

## 3. Kiến trúc

```
┌────────────────────────────┐        ┌──────────────────────────────────────────┐
│ React 18 + Vite + TS       │  /api  │ FastAPI (JWT, RBAC theo tenant)          │
│ Dashboard / Forecasts /    │ ─────► │  ├─ catalogue, inventory, imports        │
│ Recommendations / Orders / │        │  ├─ forecasts, recommendations, alerts   │
│ Alerts / Agent / Imports   │        │  ├─ purchase-orders (draft→approve→receive)│
└────────────────────────────┘        │  └─ agent (tool allowlist, audit)        │
                                      └───────────────┬──────────────────────────┘
                                                      │
                          ┌───────────────────────────┼──────────────────────────┐
                          ▼                           ▼                          ▼
                 ┌─────────────────┐        ┌──────────────────┐       ┌─────────────────┐
                 │ SQLAlchemy ORM  │        │ Forecasting      │       │ Agent layer     │
                 │ SQLite / Postgres│       │ engine (ai/)     │       │ RuleRouter or   │
                 │ tenant-scoped   │        │ HGB vs baselines │       │ LLM / LangGraph │
                 └─────────────────┘        └──────────────────┘       └─────────────────┘
```

### Cấu trúc thư mục (theo kế hoạch dự án, mục 14)

```
autonomous-inventory-management/
├── backend/
│   ├── app/
│   │   ├── api/            # auth, catalogue, inventory, imports, forecasts,
│   │   │                   # recommendations, alerts, purchase_orders, agent, dashboard
│   │   ├── core/           # config, database, security, deps
│   │   ├── models/         # SQLAlchemy ORM (tenant-scoped)
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # importer, forecasting, inventory_engine, agent_service, seed
│   │   └── main.py
│   ├── tests/              # pytest suite
│   ├── requirements.txt
│   └── Dockerfile
├── ai/
│   ├── forecasting/        # features, baselines, metrics, engine
│   ├── anomaly_detection/  # z-score + Isolation Forest
│   └── agents/             # tools, router, graph (LLM/LangGraph)
├── frontend/
│   ├── src/{pages,api.ts,App.tsx,styles.css}
│   ├── Dockerfile
│   └── nginx.conf
├── data/
│   ├── generate_synthetic.py
│   └── synthetic/          # CSV mẫu để import
├── docs/                   # kế hoạch, kiến trúc, BRD/SRS, API, dữ liệu, mô hình, runbook
├── notebooks/              # EDA nhu cầu
├── infrastructure/         # ghi chú triển khai
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

---

## 4. Phương pháp dự báo

- **Dữ liệu:** chuỗi bán hàng theo ngày của từng SKU (180 ngày gần nhất theo mặc định).
- **Baseline:** moving average (7/14/28 ngày) và seasonal naive theo thứ trong tuần.
- **Mô hình ML:** `HistGradientBoostingRegressor` với đặc trưng lịch (thứ, tháng, cuối tuần,
  ngày lễ Việt Nam gần đúng), lag (1, 7, 14, 28), rolling mean/std, trend và promo flag.
- **Chọn mô hình:** backtest giữ trật tự thời gian (28 ngày cuối), dự báo đệ quy;
  chỉ chọn ML nếu cải thiện MAE > **2%** so với baseline. Ngược lại dùng baseline.
- **Chỉ số:** MAE, RMSE, WAPE; độ tin cậy `high/medium/low` theo WAPE và lượng dữ liệu.
- **Không huấn luyện lúc khởi động** để API khởi động nhanh; dự báo chạy theo yêu cầu
  (`POST /api/forecasts/run`) và lưu từng kết quả vào bảng `forecasts` để truy vết.

Chi tiết và số liệu đánh giá: [`docs/MODEL_EVALUATION.md`](docs/MODEL_EVALUATION.md).

## 5. Chính sách tồn kho

Với mỗi cặp SKU–kho, tồn kho hiện tại được suy ra từ mốc kiểm kê gần nhất:

```
on_hand        = tồn đầu kỳ + hàng nhận sau mốc − hàng bán sau mốc
```

Từ đó `inventory_engine.py` tính:

```
σ_d            = độ lệch chuẩn nhu cầu ngày
safety_stock   = z(service_level) × σ_d × √(lead_time)
ROP            = nhu cầu bình quân ngày × lead_time + safety_stock
target_stock   = nhu cầu bình quân ngày × (lead_time + review_period) + safety_stock
inventory_pos  = on_hand + on_order − committed
suggested_qty  = làm tròn lên theo MOQ và bội số đặt hàng của nhà cung cấp
```

Rủi ro: `critical` (dưới ROP hoặc dưới 3 ngày), `high`, `medium`, `low`.
Mọi tính toán được lưu vào `replenishment_recommendations` kèm `as_of` và lý do hiển thị trên UI.

## 6. Trợ lý AI và kiểm soát

- Không có `LLM_API_KEY`: dùng **RuleRouter** xác định (offline) nhận diện ý định tiếng Việt
  và gọi đúng tool; kết quả trả về có cấu trúc, không “ảo giác”.
- Có `LLM_API_KEY`: vòng lặp tool-calling OpenAI-compatible; nếu cài `langgraph` thì dùng
  graph trong `ai/agents/graph.py`. Mọi tool đều nằm trong allowlist:
  `get_inventory_status`, `get_sales_history`, `get_forecast`, `recommend_replenishment`,
  `get_product_info`, `list_alerts`, `create_draft_purchase_order`.
- Tool ghi duy nhất là `create_draft_purchase_order`, luôn tạo trạng thái
  `pending_approval`, không bao giờ tự phê duyệt/gửi/nhận hàng.
- Mỗi lượt chạy lưu `AgentRun` (câu hỏi, câu trả lời, tool calls, latency, model) để audit.

## 7. Kiểm thử

```powershell
cd backend
..\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # pytest
..\.venv\Scripts\python.exe -m pytest -q
```

Bộ test dùng SQLite tách biệt và tắt seed demo; bao phủ: import validation, công thức
quyết định tồn kho, dự báo trên chuỗi synthetic, luồng API (đăng ký → sản phẩm → tồn kho →
dự báo → đề xuất → đơn nháp → phê duyệt → nhận hàng).

## 8. Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `SECRET_KEY` | `dev-secret-change-me...` | Khoá ký JWT — **đổi khi triển khai** |
| `DATABASE_URL` | `sqlite:///./inventory.db` | Chuỗi kết nối SQLAlchemy |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Thời hạn access token |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Origin được phép |
| `SERVICE_LEVEL` | `0.95` | Mức phục vụ dùng tính safety stock |
| `REVIEW_PERIOD_DAYS` | `7` | Chu kỳ kiểm tra đặt hàng |
| `FORECAST_HISTORY_DAYS` | `180` | Số ngày lịch sử dùng để train |
| `SEED_DEMO_DATA` | `true` | Bật mặc định tạo sẵn tài khoản và dữ liệu demo; đặt `false` nếu muốn db sạch hoàn toàn |
| `ALLOW_REGISTRATION` | `true` | Cho phép tự tạo cửa hàng từ màn hình đăng nhập |
| `LLM_API_KEY` | *(rỗng)* | Bật agent LLM; rỗng = RuleRouter |
| `LLM_BASE_URL`, `LLM_MODEL` | OpenAI + `gpt-4o-mini` | Endpoint/model tương thích OpenAI |

## 9. Tài liệu

- [Kế hoạch dự án & phạm vi](docs/PROJECT_PLAN.md)
- [Kiến trúc hệ thống](docs/ARCHITECTURE.md)
- [BRD / SRS](docs/BRD_SRS.md)
- [Từ điển dữ liệu](docs/DATA_DICTIONARY.md)
- [Tài liệu API](docs/API.md)
- [Đánh giá mô hình](docs/MODEL_EVALUATION.md)
- [Runbook vận hành](docs/RUNBOOK.md)

## 10. Giới hạn đã biết

- Hệ thống không tạo dữ liệu mẫu; số liệu chỉ có sau khi bạn import dữ liệu thật.
- Bộ dữ liệu synthetic trong `data/synthetic/` chỉ dùng để kiểm thử kỹ thuật, không đại diện cho độ chính xác thương mại.
- Chưa tích hợp POS/kế toán thật; nhập liệu qua CSV/Excel hoặc API.
- Chưa có refresh token, SSO, phân quyền chi tiết theo từng kho (RBAC hiện có 3 vai trò).
- Row-level security của PostgreSQL chưa bật mặc định; cô lập dữ liệu hiện được thực thi ở query layer.
- LLM/LangGraph là tuỳ chọn; mặc định hệ thống chạy offline với RuleRouter.
