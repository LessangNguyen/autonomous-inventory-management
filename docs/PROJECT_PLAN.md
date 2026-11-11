# Kế hoạch dự án — Autonomous Inventory Management System

> Bản tóm tắt kế hoạch 12 tuần đã được hiện thực hoá trong repository này.
> Nguồn gốc: `Autonomous_Inventory_Management_Project_Plan.docx`.
> Mặc định hệ thống không có dữ liệu mẫu. Dữ liệu synthetic chỉ dùng cho test/notebook và
> không có tuyên bố độ chính xác thương mại.

## 1. Mục tiêu

Giúp cửa hàng nhỏ / chuỗi bán lẻ trả lời ba câu hỏi mỗi ngày:

1. **Sắp tới sẽ bán bao nhiêu?** — dự báo nhu cầu 7/14/30 ngày theo SKU.
2. **Cần nhập gì, bao nhiêu, khi nào?** — đề xuất dựa trên ROP, safety stock, lead time.
3. **Có gì bất thường?** — cảnh báo hết hàng, tồn dư, doanh số bất thường.

Điểm khác biệt: **AI agent có con người phê duyệt** — mọi thay đổi ghi dữ liệu
(đơn nhập hàng) đều dừng ở trạng thái chờ duyệt.

## 2. Phạm vi MVP

| Trong phạm vi | Ngoài phạm vi |
| --- | --- |
| Quản lý SKU, nhà cung cấp, kho, tồn kho | Tích hợp POS/kế toán trực tiếp |
| Import CSV/Excel + báo cáo lỗi từng dòng | EDI / API nhà cung cấp |
| Dự báo 7/14/30 ngày, so sánh baseline | Tối ưu giá, khuyến mãi, dự báo đa kho nâng cao |
| Đề xuất nhập theo chính sách (Q,R) | Tối ưu danh mục / ngân sách |
| Cảnh báo + phát hiện bất thường | Chat đa kênh (Zalo, WhatsApp) |
| Agent hỏi đáp + tạo đơn nháp | Tự động gửi đơn không cần duyệt |
| Docker, tài liệu, test | HA/DR đa vùng, SSO doanh nghiệp |

## 3. Lộ trình 12 tuần (đã hoàn thành trong bản này)

| Tuần | Hạng mục | Kết quả bàn giao |
| --- | --- | --- |
| 1 | Khảo sát, phỏng vấn, xác định KPI | BRD/SRS, phạm vi MVP |
| 2 | Thiết kế kiến trúc, ERD, API contract | `docs/ARCHITECTURE.md`, `docs/API.md` |
| 3 | Khung backend, auth, multi-tenant | FastAPI + JWT + RBAC |
| 4 | Danh mục, tồn kho, import dữ liệu | API catalogue/inventory/imports, UI nhập liệu |
| 5 | Pipeline dự báo, baseline | `ai/forecasting` |
| 6 | Mô hình ML, backtest, chọn mô hình | HGB + moving average/seasonal naive |
| 7 | Decision engine (ROP, safety stock, MOQ) | `inventory_engine.py`, đề xuất |
| 8 | Cảnh báo, bất thường, dashboard | Alerts + dashboard |
| 9 | Agent + tool allowlist + phê duyệt | `ai/agents`, đơn nháp |
| 10 | UI hoàn chỉnh, luồng duyệt đơn | React app 8 màn hình |
| 11 | Kiểm thử, hiệu năng, tài liệu | pytest, README, docs |
| 12 | Đóng gói Docker, demo, bàn giao | compose stack, seed demo |

## 4. KPI thành công (đo trên dữ liệu thật của khách hàng)

| KPI | Mục tiêu |
| --- | --- |
| WAPE dự báo SKU bán chạy | ≤ 30% sau 3 tháng vận hành |
| Tỉ lệ SKU có đề xuất đúng hạn | ≥ 90% |
| Giảm hết hàng | ≥ 25% so với baseline thủ công |
| Thời gian tạo đơn nhập | < 5 phút/ngày |
| Tỉ lệ đơn AI tạo bị sửa trước duyệt | theo dõi, mục tiêu giảm dần |

> Các số liệu trên là **mục tiêu**, không phải kết quả đã đạt. Kết quả đo trên dữ liệu
> synthetic chỉ dùng để kiểm chứng kỹ thuật — xem `MODEL_EVALUATION.md`.

## 5. Rủi ro chính

| Rủi ro | Giảm thiểu |
| --- | --- |
| Dữ liệu bán hàng bẩn/thiếu | Import validate từng dòng, báo cáo lỗi, cảnh báo `data_quality` |
| Dự báo kém ở SKU bán chậm | Fallback baseline, hiển thị confidence, không tự đặt hàng |
| Agent “ảo giác” | Tool allowlist, dữ liệu trả về có cấu trúc, chỉ tạo nháp |
| Duyệt nhầm đơn | Trạng thái rõ ràng, audit log, chỉ owner/manager duyệt |
| Lệch múi giờ/ngày | Chuẩn hoá ngày về `date`, lưu UTC cho timestamp |

## 6. Bàn giao

- Mã nguồn đầy đủ trong repository này.
- `docker-compose.yml` chạy toàn stack (Postgres + API + UI).
- Bộ test backend và dữ liệu mẫu CSV.
- Tài liệu kiến trúc, API, dữ liệu, mô hình và runbook.
