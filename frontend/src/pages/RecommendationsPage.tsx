import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatNumber, type Product, type Recommendation } from "../api";

const RISK: Record<string, { label: string; className: string }> = {
  critical: { label: "Nghiêm trọng", className: "badge risk-critical" },
  high: { label: "Cao", className: "badge risk-high" },
  medium: { label: "Trung bình", className: "badge risk-medium" },
  low: { label: "Thấp", className: "badge risk-low" },
};

export default function RecommendationsPage() {
  const [rows, setRows] = useState<Recommendation[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [search, setSearch] = useState("");
  const [onlyNeed, setOnlyNeed] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [recommendations, catalogue] = await Promise.all([
        api.recommendations(onlyNeed),
        api.products(),
      ]);
      setRows(recommendations);
      setProducts(catalogue);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được đề xuất.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlyNeed]);

  async function recompute() {
    setBusy(true);
    setNotice("");
    try {
      const result = await api.runRecommendations();
      setNotice(
        `Đã tính lại ${result.generated} SKU · ${result.critical} nghiêm trọng · ${result.high} rủi ro cao · ${result.duration_ms}ms`,
      );
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Không tính lại được.");
    } finally {
      setBusy(false);
    }
  }

  async function createDraft(row: Recommendation) {
    setBusy(true);
    try {
      const product = products.find((item) => item.id === row.product_id);
      const order = await api.createOrder({
        warehouse_id: row.warehouse_id,
        supplier_id: product?.supplier_id ?? null,
        notes: `Tạo từ đề xuất tồn kho ngày ${new Date(row.as_of).toLocaleDateString("vi-VN")}`,
        items: [
          {
            product_id: row.product_id,
            quantity: Math.max(1, Math.round(row.suggested_qty)),
            unit_cost: row.unit_cost ?? product?.unit_cost ?? 0,
          },
        ],
      });
      setNotice(`Đã tạo đơn nháp #${order.id} cho ${row.sku}. Vào mục Đơn nhập hàng để phê duyệt.`);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Không tạo được đơn.");
    } finally {
      setBusy(false);
    }
  }

  async function dismiss(row: Recommendation) {
    await api.updateRecommendation(row.id, "dismissed");
    await load();
  }

  const filtered = useMemo(
    () =>
      rows.filter(
        (row) =>
          !search ||
          row.sku.toLowerCase().includes(search.toLowerCase()) ||
          row.product_name.toLowerCase().includes(search.toLowerCase()),
      ),
    [rows, search],
  );

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head wrap">
          <div>
            <h3>Kế hoạch nhập hàng theo chính sách (ROP)</h3>
            <p className="muted">
              Safety stock = z × σ × √lead time · ROP = nhu cầu trong lead time + safety stock · Số lượng
              đề xuất đã áp dụng MOQ và bội số đóng gói.
            </p>
          </div>
          <div className="row gap-sm">
            <label className="check">
              <input
                type="checkbox"
                checked={onlyNeed}
                onChange={(event) => setOnlyNeed(event.target.checked)}
              />
              Chỉ SKU cần nhập
            </label>
            <input
              placeholder="Tìm SKU…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button className="btn btn-primary" onClick={recompute} disabled={busy}>
              {busy ? "Đang tính…" : "Tính lại đề xuất"}
            </button>
          </div>
        </div>
        {notice && <div className="alert alert-info">{notice}</div>}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      <div className="card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>SKU</th>
                <th className="num">Nhu cầu/ngày</th>
                <th className="num">Lead time</th>
                <th className="num">Safety stock</th>
                <th className="num">ROP</th>
                <th className="num">Tồn khả dụng</th>
                <th className="num">Đề xuất nhập</th>
                <th className="num">Còn bán</th>
                <th>Rủi ro</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.sku}</strong>
                    <div className="muted small">{row.product_name}</div>
                  </td>
                  <td className="num">{row.avg_daily_demand.toFixed(1)}</td>
                  <td className="num">{row.lead_time_days} ngày</td>
                  <td className="num">{formatNumber(row.safety_stock, 1)}</td>
                  <td className="num">{formatNumber(row.reorder_point, 1)}</td>
                  <td className="num">{formatNumber(row.inventory_position, 1)}</td>
                  <td className="num">
                    <strong>{formatNumber(row.suggested_qty)}</strong>
                  </td>
                  <td className="num">
                    {row.days_of_inventory != null ? `${row.days_of_inventory} ngày` : "—"}
                  </td>
                  <td>
                    <span className={RISK[row.stockout_risk]?.className ?? "badge"}>
                      {RISK[row.stockout_risk]?.label ?? row.stockout_risk}
                    </span>
                  </td>
                  <td className="actions">
                    {row.suggested_qty > 0 ? (
                      <button className="btn btn-soft btn-sm" disabled={busy} onClick={() => createDraft(row)}>
                        Tạo đơn nháp
                      </button>
                    ) : (
                      <button className="btn btn-ghost btn-sm" onClick={() => dismiss(row)}>
                        Bỏ qua
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} className="empty">
                    Không có SKU nào cần nhập.{" "}
                    <Link to="/imports" className="link">
                      Import dữ liệu mới
                    </Link>{" "}
                    hoặc bấm “Tính lại đề xuất”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
