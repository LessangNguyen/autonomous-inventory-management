# BRD / SRS — Autonomous Inventory Management System

Phiên bản 1.0 · MVP · Ngôn ngữ sản phẩm: tiếng Việt

## 1. Bối cảnh kinh doanh

Cửa hàng bán lẻ nhỏ (mỹ phẩm, tạp hoá, mini-mart) thường quản lý tồn kho bằng Excel
hoặc sổ tay. Hệ quả: hết hàng ở SKU bán chạy, tồn dư ở SKU chậm, đặt hàng theo cảm tính,
không có bằng chứng để cải thiện. Hệ thống này cung cấp dự báo nhu cầu, đề xuất nhập hàng
và trợ lý AI — nhưng **luôn để con người quyết định** các thay đổi quan trọng.

## 2. Stakeholder

| Vai trò | Nhu cầu chính |
| --- | --- |
| Chủ cửa hàng (`owner`) | Nhìn nhanh SKU rủi ro, duyệt đơn, kiểm soát chi phí |
| Quản lý (`manager`) | Tạo/duyệt đơn, xử lý cảnh báo, nhập dữ liệu |
| Nhân viên (`staff`) | Tra cứu tồn kho, xem đề xuất (chỉ đọc) |
| Nhà cung cấp | Nhận đơn đúng SKU/số lượng/giá (ngoài hệ thống) |
| Đội vận hành | Chạy, giám sát, sao lưu hệ thống |

## 3. Yêu cầu chức năng

| ID | Yêu cầu | Ưu tiên | Tiêu chí chấp nhận |
| --- | --- | --- | --- |
| FR-01 | Đăng ký cửa hàng mới | Must | Tạo tenant + owner; email duy nhất; mật khẩu ≥ 8 ký tự |
| FR-02 | Đăng nhập / đăng xuất | Must | JWT trả về; sai mật khẩu → 401; token hết hạn → 401 |
| FR-03 | Quản lý sản phẩm | Must | CRUD SKU, giá, nhà cung cấp, lead time, MOQ, bội số |
| FR-04 | Quản lý nhà cung cấp & kho | Should | Tạo, sửa, chọn kho mặc định |
| FR-05 | Import sản phẩm/bán hàng/tồn kho đầu kỳ/NCC | Must | Nhận CSV/XLS/XLSX; lỗi từng dòng; tải file mẫu |
| FR-06 | Dự báo 7/14/30 ngày | Must | Mỗi SKU có predicted_qty, model, MAE/RMSE/WAPE, confidence |
| FR-07 | Đề xuất nhập hàng | Must | Safety stock, ROP, target, suggested_qty, risk; tôn trọng MOQ/multiple |
| FR-08 | Đơn nhập hàng | Must | draft → pending_approval → approved → received; huỷ được trước khi nhận |
| FR-09 | Phê duyệt bắt buộc | Must | Chỉ owner/manager duyệt; agent không thể duyệt |
| FR-10 | Nhận hàng cộng tồn kho | Must | Tồn hiện tại tăng đúng số lượng nhờ phát sinh đã nhận; audit log ghi nhận |
| FR-11 | Cảnh báo | Must | stockout_risk, overstock, anomaly, data_quality; trạng thái open/acked/resolved |
| FR-12 | Phát hiện bất thường | Should | Z-score theo thứ + Isolation Forest; thông điệp tiếng Việt |
| FR-13 | Trợ lý AI | Should | Trả lời tồn kho/đề xuất/dự báo; tạo đơn nháp; lưu lịch sử |
| FR-14 | Dashboard | Must | KPI, xu hướng 30 ngày, top rủi ro, số cảnh báo, đơn chờ duyệt |
| FR-15 | Audit log | Should | Ghi hành động ghi quan trọng kèm user, entity, chi tiết |

## 4. Yêu cầu phi chức năng

| ID | Yêu cầu | Mục tiêu |
| --- | --- | --- |
| NFR-01 | Hiệu năng API đọc | p95 < 500 ms (dữ liệu ≤ 50k dòng) |
| NFR-02 | Dự báo toàn bộ SKU | < 60 s với ≤ 50 SKU trên 4 vCPU |
| NFR-03 | Khởi động API | < 5 s khi đã có dữ liệu (không train lúc khởi động) |
| NFR-04 | Cô lập dữ liệu | Mọi endpoint lọc theo tenant; test cross-tenant |
| NFR-05 | Bảo mật | Mật khẩu hash PBKDF2; JWT hết hạn; CORS giới hạn |
| NFR-06 | Khả dụng | Docker Compose một lệnh; healthcheck `/api/health` |
| NFR-07 | Khả năng kiểm toán | Mọi đơn nhập có trạng thái, người tạo/duyệt, thời điểm |
| NFR-08 | Ngôn ngữ | UI và thông điệp lỗi tiếng Việt, định dạng số/ngày vi-VN |
| NFR-09 | Dữ liệu | Mặc định không có dữ liệu mẫu; dữ liệu synthetic chỉ dùng cho test/notebook, không tuyên bố độ chính xác thương mại |
| NFR-10 | Khả năng test | Logic nghiệp vụ tách khỏi router; pytest chạy offline |

## 5. User stories tiêu biểu

1. **Là chủ cửa hàng**, tôi muốn thấy ngay 5 SKU nguy cơ hết hàng để quyết định nhập trước cuối tuần.
2. **Là quản lý**, tôi muốn chạy dự báo 30 ngày và xem mô hình nào được chọn, kèm sai số, để tin tưởng con số.
3. **Là quản lý**, tôi muốn trợ lý AI soạn đơn nháp từ đề xuất, nhưng tôi là người duyệt và nhận hàng.
4. **Là nhân viên**, tôi muốn tra cứu nhanh “SKU nào sắp hết?” mà không cần mở Excel.
5. **Là đội vận hành**, tôi muốn một lệnh `docker compose up` để dựng toàn bộ hệ thống và biết cách sao lưu.

## 6. Quy tắc nghiệp vụ

- BR-01: Số lượng đề xuất = 0 nếu tồn kho vị thế đã ≥ tồn kho mục tiêu.
- BR-02: Số lượng đề xuất làm tròn lên theo bội số đặt hàng, tối thiểu bằng MOQ khi > 0.
- BR-03: `inventory_position = on_hand + on_order − committed`.
- BR-04: Không thể nhận hàng cho đơn chưa `approved`; không thể duyệt đơn đã huỷ.
- BR-05: Agent chỉ tạo được đơn `pending_approval` (nháp chờ duyệt).
- BR-06: Chỉ `owner`/`manager` được tạo, duyệt, nhận, huỷ đơn và chạy dự báo/đề xuất.
- BR-07: Dữ liệu bán hàng phải tham chiếu SKU đã tồn tại; ngày không hợp lệ bị từ chối.
- BR-08: Một tenant chỉ thấy dữ liệu của chính mình.

## 7. Màn hình

| Màn hình | Nội dung chính |
| --- | --- |
| Đăng nhập/Đăng ký | Chuyển chế độ, thông báo lỗi tiếng Việt |
| Tổng quan | 4 KPI, chart doanh thu/số lượng, top rủi ro, nút chạy dự báo |
| Dự báo | Bảng dự báo theo SKU, horizon 7/14/30, metrics, độ tin cậy |
| Đề xuất | Bảng đề xuất, lọc rủi ro/trạng thái, nút tạo đơn |
| Đơn nhập | Danh sách đơn, chi tiết item, nút duyệt/nhận/huỷ |
| Sản phẩm & kho | Danh mục + tồn kho, form thêm sản phẩm |
| Nhập dữ liệu | Chọn loại, tải file, kết quả import + lỗi |
| Cảnh báo | Danh sách cảnh báo, xác nhận/đóng |
| Trợ lý AI | Chat, gợi ý câu hỏi, hiển thị tool calls, đơn nháp được tạo |

## 8. Giả định & phụ thuộc

- Dữ liệu bán hàng có ít nhất 28 ngày lịch sử để backtest; < 7 ngày sẽ bị bỏ qua.
- Một kho mặc định cho mỗi tenant trong MVP.
- Không có ràng buộc hạn dùng/hạn sử dụng sản phẩm.
- LLM là tuỳ chọn; hệ thống đầy đủ chức năng khi không cấu hình LLM.
