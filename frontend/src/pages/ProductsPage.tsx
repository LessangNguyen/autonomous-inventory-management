import { useEffect, useState, type FormEvent } from "react";
import { api, formatNumber, formatVnd, type Product, type Supplier } from "../api";

type InventoryRow = {
  product_id: number;
  sku: string;
  product_name: string;
  warehouse_name: string;
  opening_on_hand: number;
  received_since: number;
  sold_since: number;
  on_hand: number;
  on_order: number;
  committed: number;
  snapshot_date: string | null;
  has_opening_count: boolean;
};

const EMPTY = {
  sku: "",
  name: "",
  category: "",
  unit: "cái",
  unit_cost: 0,
  price: 0,
  supplier_id: null as number | null,
  lead_time_days: 7,
  moq: 1,
  order_multiple: 1,
};

export default function ProductsPage() {
  const [tab, setTab] = useState<"catalogue" | "inventory">("catalogue");
  const [products, setProducts] = useState<Product[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [inventory, setInventory] = useState<InventoryRow[]>([]);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    try {
      const [catalogue, supplierList, stock] = await Promise.all([
        api.products(search),
        api.suppliers(),
        api.inventory(search),
      ]);
      setProducts(catalogue);
      setSuppliers(supplierList);
      setInventory(stock as unknown as InventoryRow[]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      await api.createProduct({ ...form, is_active: true });
      setNotice(`Đã thêm ${form.sku}.`);
      setShowForm(false);
      setForm({ ...EMPTY });
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Không thêm được sản phẩm.");
    }
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head wrap">
          <div className="tabs inline">
            <button className={tab === "catalogue" ? "tab active" : "tab"} onClick={() => setTab("catalogue")}>
              Danh mục sản phẩm
            </button>
            <button className={tab === "inventory" ? "tab active" : "tab"} onClick={() => setTab("inventory")}>
              Tồn kho hiện tại
            </button>
          </div>
          <div className="row gap-sm">
            <input placeholder="Tìm SKU / tên…" value={search} onChange={(event) => setSearch(event.target.value)} />
            <button className="btn btn-primary" onClick={() => setShowForm((value) => !value)}>
              {showForm ? "Đóng form" : "+ Sản phẩm"}
            </button>
          </div>
        </div>
        {notice && <div className="alert alert-info">{notice}</div>}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      {showForm && (
        <form className="card" onSubmit={create}>
          <h3>Thêm sản phẩm</h3>
          <div className="form-grid">
            <label>
              SKU
              <input value={form.sku} onChange={(event) => setForm({ ...form, sku: event.target.value })} required />
            </label>
            <label>
              Tên sản phẩm
              <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
            </label>
            <label>
              Danh mục
              <input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} />
            </label>
            <label>
              Đơn vị
              <input value={form.unit} onChange={(event) => setForm({ ...form, unit: event.target.value })} />
            </label>
            <label>
              Giá nhập
              <input
                type="number"
                min={0}
                value={form.unit_cost}
                onChange={(event) => setForm({ ...form, unit_cost: Number(event.target.value) })}
              />
            </label>
            <label>
              Giá bán
              <input
                type="number"
                min={0}
                value={form.price}
                onChange={(event) => setForm({ ...form, price: Number(event.target.value) })}
              />
            </label>
            <label>
              Nhà cung cấp
              <select
                value={form.supplier_id ?? ""}
                onChange={(event) =>
                  setForm({ ...form, supplier_id: event.target.value ? Number(event.target.value) : null })
                }
              >
                <option value="">— Chưa chọn —</option>
                {suppliers.map((supplier) => (
                  <option key={supplier.id} value={supplier.id}>
                    {supplier.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Lead time (ngày)
              <input
                type="number"
                min={1}
                value={form.lead_time_days}
                onChange={(event) => setForm({ ...form, lead_time_days: Number(event.target.value) })}
              />
            </label>
            <label>
              MOQ
              <input
                type="number"
                min={1}
                value={form.moq}
                onChange={(event) => setForm({ ...form, moq: Number(event.target.value) })}
              />
            </label>
            <label>
              Bội số đóng gói
              <input
                type="number"
                min={1}
                value={form.order_multiple}
                onChange={(event) => setForm({ ...form, order_multiple: Number(event.target.value) })}
              />
            </label>
          </div>
          <div className="row">
            <button className="btn btn-primary">Lưu sản phẩm</button>
          </div>
        </form>
      )}

      <div className="card">
        <div className="table-scroll">
          {tab === "catalogue" ? (
            <table className="table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Sản phẩm</th>
                  <th>Danh mục</th>
                  <th className="num">Giá nhập</th>
                  <th className="num">Giá bán</th>
                  <th className="num">Lead time</th>
                  <th className="num">MOQ</th>
                  <th>Nhà cung cấp</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => (
                  <tr key={product.id}>
                    <td>
                      <strong>{product.sku}</strong>
                    </td>
                    <td>{product.name}</td>
                    <td className="muted">{product.category}</td>
                    <td className="num">{formatVnd(product.unit_cost)}</td>
                    <td className="num">{formatVnd(product.price)}</td>
                    <td className="num">{product.lead_time_days ?? "—"} ngày</td>
                    <td className="num">{product.moq ?? 1}</td>
                    <td className="muted">{product.supplier_name ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <>
              <div className="alert alert-info">
                Tồn hiện tại được <strong>tính tự động</strong>: tồn đầu kỳ + hàng đã nhập −
                hàng đã bán. Bạn chỉ cần import tồn kho <strong>một lần</strong> làm mốc ban đầu.
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Sản phẩm</th>
                    <th>Kho</th>
                    <th className="num">Tồn đầu kỳ</th>
                    <th className="num">Đã nhập</th>
                    <th className="num">Đã bán</th>
                    <th className="num">Tồn hiện tại</th>
                    <th className="num">Đang về</th>
                    <th className="num">Khả dụng</th>
                    <th>Mốc</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.map((row) => (
                    <tr key={`${row.product_id}-${row.warehouse_name}`}>
                      <td>
                        <strong>{row.sku}</strong>
                      </td>
                      <td>{row.product_name}</td>
                      <td className="muted">{row.warehouse_name}</td>
                      <td className="num">{formatNumber(row.opening_on_hand)}</td>
                      <td className="num pos">+{formatNumber(row.received_since)}</td>
                      <td className="num neg">−{formatNumber(row.sold_since)}</td>
                      <td className="num">
                        <strong>{formatNumber(row.on_hand)}</strong>
                      </td>
                      <td className="num">{formatNumber(row.on_order)}</td>
                      <td className="num">
                        <strong>{formatNumber(row.on_hand + row.on_order - row.committed)}</strong>
                      </td>
                      <td className="muted">
                        {row.snapshot_date
                          ? new Date(row.snapshot_date).toLocaleDateString("vi-VN")
                          : "Chưa có mốc"}
                      </td>
                    </tr>
                  ))}
                  {inventory.length === 0 && (
                    <tr>
                      <td colSpan={10} className="empty">
                        Chưa có tồn kho. Import tồn kho đầu kỳ để có mốc tính; sau đó hệ thống
                        tự cộng hàng nhập và trừ hàng bán.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
