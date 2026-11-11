import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, formatNumber, type Forecast, type ForecastRunResult } from "../api";

const CONFIDENCE: Record<string, { label: string; className: string }> = {
  high: { label: "Cao", className: "badge success" },
  medium: { label: "Trung bình", className: "badge warning" },
  low: { label: "Thấp", className: "badge neutral" },
};

export default function ForecastsPage() {
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [selected, setSelected] = useState<Forecast | null>(null);
  const [search, setSearch] = useState("");
  const [horizon, setHorizon] = useState(30);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ForecastRunResult | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const rows = await api.forecasts();
      setForecasts(rows);
      setSelected((current) => rows.find((row) => row.id === current?.id) ?? rows[0] ?? null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dự báo.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const response = await api.runForecasts(horizon);
      setResult(response);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chạy dự báo thất bại.");
    } finally {
      setBusy(false);
    }
  }

  const filtered = useMemo(
    () =>
      forecasts.filter(
        (row) =>
          !search ||
          row.sku?.toLowerCase().includes(search.toLowerCase()) ||
          row.product_name?.toLowerCase().includes(search.toLowerCase()),
      ),
    [forecasts, search],
  );

  const chartData = useMemo(() => {
    if (!selected) return [];
    const start = new Date();
    return selected.daily_series.map((value, index) => {
      const day = new Date(start);
      day.setDate(day.getDate() + index + 1);
      return {
        label: day.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }),
        demand: Math.round(value * 10) / 10,
      };
    });
  }, [selected]);

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head wrap">
          <div>
            <h3>Dự báo nhu cầu theo SKU</h3>
            <p className="muted">
              Mô hình được chọn bằng backtesting theo thời gian; baseline luôn được so sánh và lưu lại.
            </p>
          </div>
          <div className="row gap-sm">
            <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
              <option value={7}>7 ngày</option>
              <option value={14}>14 ngày</option>
              <option value={30}>30 ngày</option>
            </select>
            <button className="btn btn-primary" onClick={run} disabled={busy}>
              {busy ? "Đang huấn luyện…" : "Chạy dự báo"}
            </button>
          </div>
        </div>

        {result && (
          <div className="alert alert-info">
            Đã xử lý <strong>{result.products_processed}</strong> SKU trong{" "}
            {(result.duration_ms / 1000).toFixed(1)}s · Bỏ qua {result.products_skipped} SKU thiếu dữ liệu
            {result.avg_wape != null && <> · WAPE TB {(result.avg_wape * 100).toFixed(1)}%</>}
            {result.improvement_pct != null && <> · Cải thiện {result.improvement_pct}% so với baseline</>}
          </div>
        )}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      <div className="grid forecast-grid">
        <div className="card">
          <div className="card-head">
            <h3>Danh sách SKU</h3>
            <input
              placeholder="Tìm SKU hoặc tên…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="table-scroll">
            <table className="table selectable">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Dự báo</th>
                  <th>Mô hình</th>
                  <th>WAPE</th>
                  <th>Tin cậy</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr
                    key={row.id}
                    className={selected?.id === row.id ? "selected" : ""}
                    onClick={() => setSelected(row)}
                  >
                    <td>
                      <strong>{row.sku}</strong>
                      <div className="muted small">{row.product_name}</div>
                    </td>
                    <td>
                      {formatNumber(row.predicted_qty)}
                      <span className="muted small"> / {row.horizon_days} ngày</span>
                    </td>
                    <td className="small">{row.model_name}</td>
                    <td>{row.wape != null ? `${(row.wape * 100).toFixed(1)}%` : "—"}</td>
                    <td>
                      <span className={CONFIDENCE[row.confidence]?.className ?? "badge neutral"}>
                        {CONFIDENCE[row.confidence]?.label ?? row.confidence}
                      </span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="empty">
                      Chưa có dự báo. Bấm “Chạy dự báo” để huấn luyện mô hình cho các SKU đủ dữ liệu.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="card-head">
                <div>
                  <h3>
                    {selected.sku} · {selected.product_name}
                  </h3>
                  <p className="muted">
                    {selected.model_name} · {selected.model_version} · trained đến{" "}
                    {selected.trained_until ?? "—"}
                  </p>
                </div>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7f0" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
                    <Tooltip
                      formatter={(value: number) => [`${value} đơn vị`, "Nhu cầu dự báo"]}
                      contentStyle={{ borderRadius: 10, border: "1px solid #e5e7f0" }}
                    />
                    <Bar dataKey="demand" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="metric-row">
                <div>
                  <span className="metric-label">Tổng nhu cầu</span>
                  <span className="metric-value">{formatNumber(selected.predicted_qty)}</span>
                </div>
                <div>
                  <span className="metric-label">MAE</span>
                  <span className="metric-value">{selected.mae ?? "—"}</span>
                </div>
                <div>
                  <span className="metric-label">RMSE</span>
                  <span className="metric-value">{selected.rmse ?? "—"}</span>
                </div>
                <div>
                  <span className="metric-label">Baseline MAE</span>
                  <span className="metric-value">{selected.baseline_mae ?? "—"}</span>
                </div>
              </div>
              <p className="muted small">
                Dự báo được tạo {new Date(selected.created_at).toLocaleString("vi-VN")}. WAPE thấp hơn
                baseline nghĩa là mô hình tốt hơn naive/moving-average trên giai đoạn kiểm định.
              </p>
            </>
          ) : (
            <div className="empty">Chọn một SKU để xem chi tiết dự báo.</div>
          )}
        </div>
      </div>
    </div>
  );
}
