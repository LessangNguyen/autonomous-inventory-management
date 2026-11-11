import { useEffect, useState } from "react";
import { api, type Alert } from "../api";

const SEVERITY: Record<string, { label: string; className: string }> = {
  info: { label: "Thông tin", className: "badge neutral" },
  warning: { label: "Cảnh báo", className: "badge warning" },
  critical: { label: "Nghiêm trọng", className: "badge danger" },
};

const TYPE_LABEL: Record<string, string> = {
  stockout_risk: "Nguy cơ hết hàng",
  overstock: "Tồn dư",
  anomaly: "Bất thường dữ liệu",
  data_quality: "Chất lượng dữ liệu",
};

export default function AlertsPage() {
  const [status, setStatus] = useState("open");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setAlerts(await api.alerts(status));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được cảnh báo.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function update(id: number, next: string) {
    try {
      await api.updateAlert(id, next);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Không cập nhật được.");
    }
  }

  async function scan() {
    try {
      const result = await api.scanAnomalies();
      setNotice(`Đã quét bất thường: ${result.alerts_created} cảnh báo mới.`);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Quét thất bại.");
    }
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head wrap">
          <div>
            <h3>Cảnh báo vận hành</h3>
            <p className="muted">
              Cảnh báo chỉ là tín hiệu cần kiểm tra. Điểm bất thường không đồng nghĩa gian lận hay lỗi
              dữ liệu.
            </p>
          </div>
          <div className="row gap-sm">
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="open">Đang mở</option>
              <option value="acked">Đã ghi nhận</option>
              <option value="resolved">Đã xử lý</option>
              <option value="all">Tất cả</option>
            </select>
            <button className="btn btn-soft" onClick={scan}>
              Quét bất thường
            </button>
          </div>
        </div>
        {notice && <div className="alert alert-info">{notice}</div>}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      <div className="stack">
        {alerts.map((alert) => (
          <div className={`card alert-row ${alert.severity}`} key={alert.id}>
            <div>
              <div className="row gap-sm">
                <span className={SEVERITY[alert.severity]?.className ?? "badge"}>
                  {SEVERITY[alert.severity]?.label ?? alert.severity}
                </span>
                <span className="badge neutral">{TYPE_LABEL[alert.type] ?? alert.type}</span>
                {alert.sku && <strong>{alert.sku}</strong>}
                <span className="muted small">
                  {new Date(alert.created_at).toLocaleString("vi-VN")}
                </span>
              </div>
              <p>{alert.message}</p>
            </div>
            <div className="row gap-sm">
              {alert.status === "open" && (
                <button className="btn btn-soft btn-sm" onClick={() => update(alert.id, "acked")}>
                  Ghi nhận
                </button>
              )}
              {alert.status !== "resolved" && (
                <button className="btn btn-ghost btn-sm" onClick={() => update(alert.id, "resolved")}>
                  Đã xử lý
                </button>
              )}
            </div>
          </div>
        ))}
        {alerts.length === 0 && <div className="card empty">Không có cảnh báo trong nhóm này.</div>}
      </div>
    </div>
  );
}
