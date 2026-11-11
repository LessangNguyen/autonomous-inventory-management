# Runbook vận hành

## 1. Khởi động / dừng

### Docker Compose

```bash
cp .env.example .env          # đổi SECRET_KEY trước khi dùng chung
docker compose up -d --build
docker compose ps
docker compose logs -f backend
docker compose down            # thêm -v để xoá cả volume dữ liệu
```

Kiểm tra sức khoẻ:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","app":"Autonomous Inventory Management","environment":"production"}
```

### Local

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend dev: `cd frontend; npm run dev`. Production build: `npm run build`, phục vụ
`frontend/dist` bằng nginx (xem `frontend/nginx.conf`).

## 2. Tài khoản & dữ liệu

- Database mặc định **trống**. Lần đầu mở UI, chọn **Tạo cửa hàng** để tạo owner.
- Sau khi tạo tài khoản, có thể đặt `ALLOW_REGISTRATION=false` để đóng đăng ký.
- Tenant demo synthetic chỉ xuất hiện khi đặt `SEED_DEMO_DATA=true` **trước** lần khởi động
  đầu tiên (owner `demo@inventory.ai` / `demo1234`, tenant “Cửa hàng Demo”).
- Muốn database sạch: dừng backend, xoá `backend/inventory.db` (SQLite) hoặc
  `docker compose down -v` (Postgres), rồi khởi động lại. Với bản không demo, database mới
  sẽ trống và UI tự chuyển sang tab **Tạo cửa hàng**.

> Không có dữ liệu mẫu trong bản phát hành mặc định. Không dùng dữ liệu synthetic để tuyên bố
> độ chính xác thương mại.

## 3. Sao lưu & phục hồi

### SQLite

```powershell
# Sao lưu (backend đang chạy vẫn an toàn với .backup)
sqlite3 backend\inventory.db ".backup 'backup\inventory-2026-11-10.db'"

# Phục hồi
Copy-Item backup\inventory-2026-11-10.db backend\inventory.db
```

### PostgreSQL

```bash
docker compose exec db pg_dump -U inventory inventory > backup/inventory-$(date +%F).sql
cat backup/inventory-2026-11-10.sql | docker compose exec -T db psql -U inventory inventory
```

Khuyến nghị: sao lưu hằng ngày, giữ 14 bản; kiểm tra phục hồi mỗi quý.

## 4. Quy trình vận hành hằng ngày

1. **Sáng:** mở Tổng quan, xem SKU rủi ro + cảnh báo mở.
2. Nhập dữ liệu bán hàng mới (CSV/Excel) — tồn kho tự trừ theo các dòng bán.
3. Chạy dự báo 30 ngày (hoặc 7 ngày cho đặt hàng gấp).
4. Chạy đề xuất → kiểm tra số lượng, MOQ, nhà cung cấp.
5. Tạo đơn nháp (thủ công hoặc qua trợ lý AI) → **duyệt** → gửi NCC ngoài hệ thống.
6. Khi hàng về: mở đơn đã duyệt → **Nhận hàng**; tồn kho tự cộng theo phát sinh.
7. Đóng cảnh báo đã xử lý.

> Chỉ import **tồn kho đầu kỳ** một lần (hoặc khi kiểm kê lại). Không cần import tồn kho
> hằng ngày: `on_hand = tồn đầu kỳ + đã nhận − đã bán`.

## 5. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
| --- | --- | --- |
| `401 Chưa đăng nhập` | Token hết hạn/bị xoá localStorage | Đăng nhập lại |
| `404` ở `/health` | Đang chạy bản cũ trước khi thêm alias | Khởi động lại backend; `/health` và `/api/health` đều hợp lệ |
| API khởi động chậm > 30 s | Seed demo synthetic đang chạy (`SEED_DEMO_DATA=true`) | Đặt `SEED_DEMO_DATA=false` (mặc định) |
| Dự báo 0 SKU | Chưa có kho/dữ liệu bán | Import sản phẩm → bán hàng → tồn kho đầu kỳ |
| Tồn kho âm | Bán nhiều hơn tồn đầu kỳ + hàng đã nhận | Kiểm kê lại và import tồn kho mới làm mốc |
| WAPE cao bất thường | Dữ liệu ngày bị dồn/thiếu, import lặp | Kiểm tra `sales_transactions`, tránh import trùng |
| Frontend trắng trang | Thiếu `npm install` / build lỗi | `npm install && npm run build`, xem console |
| CORS error | Origin không nằm trong `CORS_ORIGINS` | Thêm origin, restart backend |
| Import báo thiếu cột | Tên cột không khớp template | Tải template tại `/api/imports/templates/{kind}` |
| Import sai file / trùng dữ liệu | Chọn nhầm file hoặc import lặp | **Nhập dữ liệu → Lịch sử import → Xóa**; xem trước số dòng, chạy lại dự báo |
| Job cũ hiện cảnh báo "chưa có thông tin nguồn" | Job tạo trước khi bật theo dõi nguồn | Preview sẽ xóa toàn bộ dữ liệu cùng loại; thứ tự an toàn: bán hàng → tồn kho → sản phẩm → nhà cung cấp |
| Job import ở trạng thái "Đã xóa một phần" | Sản phẩm/NCC còn được bán hàng, tồn kho hoặc đơn nhập tham chiếu | Xóa lần import liên quan trước rồi bấm Xóa lại |
| `docker compose` không kết nối DB | Postgres chưa healthy | `docker compose logs db`, chờ healthcheck |

## 6. Nhật ký & kiểm toán

- Log ứng dụng: stdout (docker logs / terminal uvicorn).
- Audit log nghiệp vụ: `GET /api/audit-logs?limit=100` (theo tenant).
- Lịch sử agent: `GET /api/agent/runs?limit=50`.
- Lịch sử import: `GET /api/imports`.

Các hành động được ghi audit: tạo/sửa sản phẩm, tạo/gửi/duyệt/nhận/huỷ đơn,
chạy dự báo/đề xuất (tuỳ luồng), tạo đơn từ agent, xóa/hoàn tác import
(`import.revert`).

## 7. Bảo mật vận hành

- Đổi `SECRET_KEY` (≥ 32 ký tự ngẫu nhiên) trước khi dùng thật.
- Đặt API sau reverse proxy có HTTPS; không mở trực tiếp cổng 8000 ra Internet.
- Giới hạn `CORS_ORIGINS` đúng domain.
- Không commit `.env`, database, file import chứa dữ liệu khách hàng.
- Xoay khoá LLM định kỳ; nếu không dùng, để trống để chạy RuleRouter offline.
- Cân nhắc bật PostgreSQL RLS và mã hoá ổ đĩa khi lên production.

## 8. Nâng cấp & rollback

```bash
git pull
docker compose build
docker compose up -d
```

- Schema hiện tạo bằng `Base.metadata.create_all` (không có migration).
  Khi thay đổi schema production, thêm Alembic trước khi triển khai.
- Rollback: checkout tag trước đó, build lại; phục hồi backup DB nếu có thay đổi schema.

## 9. Giới hạn đã biết

- Không có background worker: request dự báo giữ kết nối ~10–20 s với 24 SKU.
- SQLite chỉ phù hợp 1–2 người dùng đồng thời; production dùng PostgreSQL.
- Chưa có refresh token/SSO; token sống 12 giờ.
- Chưa có rate limiting; nên đặt sau API gateway khi public.
