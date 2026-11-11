import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, formatNumber, formatVnd, type DashboardSummary } from "../api";

const RISK_LABEL: Record<string, string> = {
  critical: "Nghiêm trọng",
  high: "Cao",
  medium: "Trung bình",
  low: "Thấp",
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      setSummary(await api.dashboard());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dashboard.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runForecast() {
    setBusy("forecast");
    setNotice("");
    try {
      const result = await api.runForecasts(30);
      setNotice(
        `Đã dự báo ${result.products_processed} SKU trong ${(result.duration_ms / 1000).toFixed(1)}s` +
          (result.avg_wape != null ? ` · WAPE trung bình ${(result.avg_wape * 100).toFixed(1)}%` : "") +
          (result.improvement_pct != null ? ` · cải thiện ${result.improvement_pct}% so với baseline` : ""),
      );
      await api.runRecommendations();
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Chạy dự báo thất bại.");
    } finally {
      setBusy("");
    }
  }

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!summary) return <div className="card skeleton">Đang tải dashboard…</div>;

  const trend = summary.sales_trend.map((point) => ({
    ...point,
    label: new Date(point.date).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }),
  }));
  const isEmpty = summary.total_products === 0;

  return (
    <div className="stack">
      {isEmpty && (
        <div className="card onboarding">
          <h3>Chưa có dữ liệu — bắt đầu từ file của bạn</h3>
          <p className="muted">
            Hệ thống không tạo dữ liệu mẫu. Các chỉ số và dự báo sẽ xuất hiện sau khi bạn import
            dữ liệu thật của cửa hàng.
          </p>
          <ol className="steps">
            <li>
              Import <strong>Sản phẩm</strong> — mã SKU, tên, giá vốn/giá bán, nhà cung cấp,
              lead time, MOQ.
            </li>
            <li>
              Import <strong>Tồn kho</strong> — số lượng hiện có theo SKU và kho.
            </li>
            <li>
              Import <strong>Lịch sử bán hàng</strong> — càng nhiều ngày càng tốt (tối thiểu 7–30
              ngày gần nhất).
            </li>
            <li>
              Bấm <strong>Chạy dự báo &amp; đề xuất</strong> để tính ROP, tồn kho an toàn và số
              lượng cần nhập.
            </li>
          </ol>
          <div className="quick-links">
            <Link to="/imports" className="quick-link">
              ⇪ Import dữ liệu
            </Link>
            <Link to="/products" className="quick-link">
              ▦ Quản lý sản phẩm
            </Link>
          </div>
        </div>
      )}

      <div className="grid kpi-grid">
        {summary.kpis.map((kpi) => (
          <div className="card kpi" key={kpi.label}>
            <div className="kpi-label">{kpi.label}</div>
            <div className="kpi-value">
              {kpi.unit === "đ" ? formatVnd(kpi.value) : formatNumber(kpi.value, 1)}
              {kpi.unit !== "đ" && <span className="kpi-unit"> {kpi.unit}</span>}
            </div>
            <div className="kpi-foot">
              {kpi.delta_pct != null && (
                <span className={kpi.delta_pct >= 0 ? "delta up" : "delta down"}>
                  {kpi.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(kpi.delta_pct)}%
                </span>
              )}
              <span className="muted">{kpi.hint}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid two-col">
        <div className="card">
          <div className="card-head">
            <div>
              <h3>Doanh thu 30 ngày</h3>
              <p className="muted">Tổng hợp từ giao dịch bán hàng đã import</p>
            </div>
            <div className="row gap-sm">
              <button className="btn btn-soft" onClick={load} disabled={!!busy}>
                Làm mới
              </button>
              <button className="btn btn-primary" onClick={runForecast} disabled={!!busy}>
                {busy === "forecast" ? "Đang chạy mô hình…" : "Chạy dự báo & đề xuất"}
              </button>
            </div>
          </div>
          <div className="chart">
            {isEmpty ? (
              <div className="chart-empty">
                Chưa có giao dịch bán hàng.
                <div className="muted small">
                  Import lịch sử bán hàng để xem xu hướng doanh thu 30 ngày.
                </div>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={trend} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="revenue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#4f46e5" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7f0" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={3} tickLine={false} axisLine={false} />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    tickFormatter={(value) => `${Math.round(value / 1000)}k`}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                  />
                  <Tooltip
                    formatter={(value: number) => formatVnd(value)}
                    labelStyle={{ fontWeight: 600 }}
                    contentStyle={{ borderRadius: 10, border: "1px solid #e5e7f0" }}
                  />
                  <Area type="monotone" dataKey="revenue" stroke="#4f46e5" strokeWidth={2} fill="url(#revenue)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          {notice && <div className="alert alert-info">{notice}</div>}
        </div>

        <div className="stack">
          <div className="card">
            <h3>Tình trạng vận hành</h3>
            <div className="mini-stats">
              <div>
                <span className="mini-value">{summary.open_alerts}</span>
                <span className="muted">Cảnh báo mở</span>
              </div>
              <div>
                <span className="mini-value">{summary.pending_orders}</span>
                <span className="muted">Đơn chờ duyệt</span>
              </div>
              <div>
                <span className="mini-value">
                  {summary.last_forecast_at ? new Date(summary.last_forecast_at).toLocaleDateString("vi-VN") : "—"}
                </span>
                <span className="muted">Lần dự báo gần nhất</span>
              </div>
            </div>
            <div className="quick-links">
              <Link to="/forecasts" className="quick-link">
                ◔ Xem dự báo theo SKU
              </Link>
              <Link to="/recommendations" className="quick-link">
                ◈ Lập kế hoạch nhập hàng
              </Link>
              <Link to="/imports" className="quick-link">
                ⇪ Import dữ liệu Excel/CSV
              </Link>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h3>SKU cần chú ý</h3>
              <Link to="/recommendations" className="link">
                Xem tất cả
              </Link>
            </div>
            <table className="table compact">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Tồn</th>
                  <th>Còn bán</th>
                  <th>Đề xuất</th>
                  <th>Rủi ro</th>
                </tr>
              </thead>
              <tbody>
                {summary.top_risks.map((risk) => (
                  <tr key={risk.product_id}>
                    <td>
                      <strong>{risk.sku}</strong>
                      <div className="muted small">{risk.product_name}</div>
                    </td>
                    <td>{formatNumber(risk.on_hand)}</td>
                    <td>{risk.days_of_inventory != null ? `${risk.days_of_inventory} ngày` : "—"}</td>
                    <td>{formatNumber(risk.suggested_qty)}</td>
                    <td>
                      <span className={`badge risk-${risk.stockout_risk}`}>
                        {RISK_LABEL[risk.stockout_risk] ?? risk.stockout_risk}
                      </span>
                    </td>
                  </tr>
                ))}
                {summary.top_risks.length === 0 && (
                  <tr>
                    <td colSpan={5} className="empty">
                      Chưa có đề xuất. Import dữ liệu rồi chạy dự báo để tính điểm đặt hàng lại.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
