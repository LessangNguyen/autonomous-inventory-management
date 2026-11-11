# Đánh giá mô hình dự báo

> **Cảnh báo:** mọi số liệu trong tài liệu này được đo trên **dữ liệu synthetic**
> (24 SKU mỹ phẩm/tạp hoá, 200 ngày, seed cố định). Chúng dùng để kiểm chứng pipeline
> và so sánh tương đối giữa mô hình, **không** phải cam kết độ chính xác thương mại.
> Khi triển khai thật, phải chạy lại backtest trên dữ liệu của khách hàng.

## 1. Bài toán

Cho chuỗi nhu cầu bán hàng theo ngày của một SKU, dự báo tổng nhu cầu trong
7 / 14 / 30 ngày tiếp theo. Dự báo được dùng để tính ROP, safety stock và số lượng
đặt hàng — vì vậy sai số ở cấp tổng (WAPE) quan trọng hơn sai số từng ngày.

## 2. Dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Nguồn | `backend/app/services/seed.py` hoặc `data/generate_synthetic.py` |
| Số SKU | 24 |
| Lịch sử | 200 ngày (dự báo dùng 180 ngày gần nhất) |
| Mùa vụ | Chu kỳ tuần (cuối tuần cao hơn), trend nhẹ, promo mỗi 45 ngày |
| Nhiễu | Gamma(shape=4, scale=0.25), tỉ lệ ngày không bán 1–35% |
| Kho | 1 kho mặc định (`MAIN`) |

Dữ liệu tổng hợp có chủ đích tạo các tình huống khó: SKU bán chậm (0,7–1,4/ngày),
SKU gần như ngẫu nhiên (tỉ lệ zero cao), SKU bán chạy (8–12/ngày).

## 3. Quy trình

1. **Làm sạch chuỗi:** group bán hàng theo `date` (chuẩn hoá bỏ giờ), điền ngày thiếu = 0.
2. **Baseline:** moving average 7/14/28 ngày và seasonal naive theo thứ trong tuần.
3. **Features:** lag 1/7/14/28, rolling mean/std (7/14/28), thứ, tháng, cuối tuần,
   cờ ngày lễ Việt Nam gần đúng, trend, promo flag.
4. **Backtest giữ trật tự thời gian:** 28 ngày cuối làm holdout; mô hình chỉ thấy dữ liệu trước đó.
5. **Dự báo đệ quy:** mỗi ngày dự báo được nối vào lịch sử để tạo lag cho ngày kế tiếp.
6. **Chọn mô hình:** ML chỉ được chọn nếu MAE holdout cải thiện **> 2%** so với baseline tốt nhất.
7. **Lưu vết:** mỗi lần chạy ghi `Forecast` gồm model, MAE/RMSE/WAPE, baseline MAE,
   `daily_series`, `trained_until`.

## 4. Kết quả lần chạy tham chiếu (dữ liệu synthetic)

Lần chạy 2026-11-10, horizon 30 ngày, 24 SKU:

| Chỉ số | Giá trị |
| --- | --- |
| SKU xử lý | 24 (0 bỏ qua) |
| Thời gian chạy | ~13 s (CPU, 24 SKU) |
| MAE trung bình | 1,942 |
| RMSE trung bình | 2,571 |
| WAPE trung bình | 0,546 |
| MAE baseline trung bình | 2,074 |
| Cải thiện MAE so với baseline | **+6,36%** |
| Số SKU chọn GBM | 9 |
| Số SKU chọn moving average | 15 |
| Độ tin cậy | 18 medium, 6 low |

Theo mô hình (lần chạy mới nhất mỗi SKU):

| Mô hình | Số SKU | MAE TB | WAPE TB | Baseline MAE TB |
| --- | --- | --- | --- | --- |
| `gbm_hist_gradient_boosting` | 9 | 2,473 | 0,498 | 2,825 |
| `moving_average` | 15 | 1,623 | 0,575 | 1,623 |

**Diễn giải:** GBM thắng ở các SKU có mùa vụ/promo rõ; baseline thắng ở SKU bán chậm
hoặc quá nhiễu. WAPE ~0,55 là cao — bình thường với dữ liệu bán lẻ tổng hợp nhiều ngày
không bán và nhiễu lớn; đây là lý do hệ thống luôn hiển thị confidence và không tự đặt hàng.

## 5. Vì sao dùng WAPE

WAPE = `Σ|actual − forecast| / Σ actual`. Khác MAPE, WAPE không bùng nổ khi có ngày
bán = 0 (rất phổ biến ở SKU bán chậm) và phản ánh đúng sai số trên tổng nhu cầu —
đúng với quyết định nhập hàng.

## 6. Cấu hình mô hình

| Tham số | Giá trị | Ghi chú |
| --- | --- | --- |
| `max_iter` | 160 | Cân bằng tốc độ/chất lượng |
| `learning_rate` | 0,08 | |
| `max_leaf_nodes` | 15 | |
| `min_samples_leaf` | 4 | |
| `l2_regularization` | 1,0 | |
| `early_stopping` | True | `validation_fraction=0,15`, `n_iter_no_change=8` |
| Holdout | 28 ngày | Giữ trật tự thời gian |
| Ngưỡng chọn ML | > 2% MAE | Tránh overfit |

LightGBM là tuỳ chọn (`backend/requirements-ai.txt`); nếu cài, engine có thể dùng làm
backend boosting thay thế. Mặc định dùng `HistGradientBoostingRegressor` của scikit-learn
để giảm phụ thuộc.

## 7. Cách tái lập

```powershell
# Sinh lại CSV synthetic
.\.venv\Scripts\python.exe data\generate_synthetic.py --days 200

# Hoặc dùng seed có sẵn, chạy API rồi gọi:
curl -X POST http://127.0.0.1:8000/api/forecasts/run `
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" `
  -d '{\"horizon_days\": 30}'

# Xem phân bố mô hình
curl http://127.0.0.1:8000/api/forecasts/models -H "Authorization: Bearer <token>"
```

Notebook EDA: `notebooks/01_eda_demand.ipynb`.

## 8. Hạn chế & hướng cải thiện

- Chưa có exogenous variables thật (giá, khuyến mãi, thời tiết, ngày lễ chính xác).
- Chưa dự báo khoảng tin cậy; mới có confidence heuristic theo WAPE/số điểm dữ liệu.
- Chưa xử lý SKU mới ra mắt (cold start) ngoài fallback baseline.
- Chưa tối ưu đa SKU/đa kho hoặc ràng buộc ngân sách.
- Nên thêm: cross-validation theo rolling window, quantile regression cho safety stock,
  hierarchical reconciliation khi có nhiều kho, và theo dõi drift theo tháng.
