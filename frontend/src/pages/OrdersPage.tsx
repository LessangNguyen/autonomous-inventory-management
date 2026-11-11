import { useEffect, useState } from "react";
import { api, formatDate, formatNumber, formatVnd, type PurchaseOrder } from "../api";

const STATUS: Record<string, { label: string; className: string }> = {
  draft: { label: "Nháp", className: "badge neutral" },
  pending_approval: { label: "Chờ phê duyệt", className: "badge warning" },
  approved: { label: "Đã phê duyệt", className: "badge info" },
  received: { label: "Đã nhận hàng", className: "badge success" },
  cancelled: { label: "Đã hủy", className: "badge danger" },
};

export default function OrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setOrders(await api.orders());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được đơn nhập.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function act(order: PurchaseOrder, action: "submit" | "approve" | "receive" | "cancel") {
    setBusy(order.id);
    setNotice("");
    try {
      const labels = {
        submit: "gửi duyệt",
        approve: "phê duyệt",
        receive: "nhận hàng",
        cancel: "hủy",
      };
      if (action === "submit") await api.submitOrder(order.id);
      if (action === "approve") await api.approveOrder(order.id);
      if (action === "receive") await api.receiveOrder(order.id);
      if (action === "cancel") await api.cancelOrder(order.id);
      setNotice(`Đã ${labels[action]} đơn #${order.id}.`);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Thao tác thất bại.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <div>
            <h3>Đơn nhập hàng</h3>
            <p className="muted">
              Mọi thay đổi tồn kho chỉ xảy ra khi đơn được phê duyệt và ghi nhận nhận hàng — luôn có
              người chịu trách nhiệm.
            </p>
          </div>
          <button className="btn btn-soft" onClick={load}>
            Làm mới
          </button>
        </div>
        {notice && <div className="alert alert-info">{notice}</div>}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      <div className="stack">
        {orders.map((order) => (
          <div className="card order" key={order.id}>
            <div className="order-head" onClick={() => setExpanded(expanded === order.id ? null : order.id)}>
              <div>
                <div className="row gap-sm">
                  <strong>Đơn #{order.id}</strong>
                  <span className={STATUS[order.status]?.className ?? "badge"}>
                    {STATUS[order.status]?.label ?? order.status}
                  </span>
                  <span className="badge neutral">{order.source === "agent" ? "AI tạo" : "Thủ công"}</span>
                </div>
                <div className="muted small">
                  {order.supplier_name ?? "Chưa chọn nhà cung cấp"} · {order.warehouse_name} ·{" "}
                  {formatDate(order.created_at)} · {order.items.length} SKU
                </div>
              </div>
              <div className="order-right">
                <strong>{formatVnd(order.total_amount)}</strong>
                <span className="muted small">
                  {expanded === order.id ? "Thu gọn" : "Chi tiết"}
                </span>
              </div>
            </div>

            {expanded === order.id && (
              <div className="order-body">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Sản phẩm</th>
                      <th className="num">Số lượng</th>
                      <th className="num">Đơn giá</th>
                      <th className="num">Thành tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {order.items.map((item) => (
                      <tr key={item.id}>
                        <td>{item.sku}</td>
                        <td>{item.product_name}</td>
                        <td className="num">{formatNumber(item.quantity)}</td>
                        <td className="num">{formatVnd(item.unit_cost)}</td>
                        <td className="num">{formatVnd(item.unit_cost * item.quantity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {order.notes && <p className="muted small">Ghi chú: {order.notes}</p>}
                <div className="row gap-sm">
                  {order.status === "draft" && (
                    <button className="btn btn-soft btn-sm" disabled={busy === order.id} onClick={() => act(order, "submit")}>
                      Gửi duyệt
                    </button>
                  )}
                  {(order.status === "draft" || order.status === "pending_approval") && (
                    <button className="btn btn-primary btn-sm" disabled={busy === order.id} onClick={() => act(order, "approve")}>
                      Phê duyệt
                    </button>
                  )}
                  {order.status === "approved" && (
                    <button className="btn btn-primary btn-sm" disabled={busy === order.id} onClick={() => act(order, "receive")}>
                      Ghi nhận nhận hàng
                    </button>
                  )}
                  {order.status !== "received" && order.status !== "cancelled" && (
                    <button className="btn btn-ghost btn-sm" disabled={busy === order.id} onClick={() => act(order, "cancel")}>
                      Hủy đơn
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {orders.length === 0 && (
          <div className="card empty">
            Chưa có đơn nhập nào. Tạo đơn từ mục Đề xuất nhập hàng hoặc nhờ trợ lý AI soạn đơn nháp.
          </div>
        )}
      </div>
    </div>
  );
}
