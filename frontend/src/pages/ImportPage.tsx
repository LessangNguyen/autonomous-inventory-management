import { useEffect, useState } from "react";
import {
  api,
  formatDate,
  type ImportDeleteCounts,
  type ImportDeletePreview,
  type ImportDeleteResult,
  type ImportJob,
} from "../api";

const KINDS = [
  {
    key: "products",
    title: "Sản phẩm",
    description: "Danh mục SKU, giá, nhà cung cấp, lead time, MOQ, bội số đóng gói.",
    columns: "sku, name, category, unit, unit_cost, price, supplier_name, lead_time_days, moq, order_multiple",
  },
  {
    key: "sales",
    title: "Lịch sử bán hàng",
    description: "Từng dòng là một SKU trong một đơn bán. Cần import sản phẩm trước.",
    columns: "sku, date, quantity, unit_price, warehouse_code, external_id",
  },
  {
    key: "inventory",
    title: "Tồn kho đầu kỳ",
    description:
      "Chỉ cần nhập MỘT LẦN làm mốc. Sau đó hệ thống tự cộng hàng nhập đã nhận và trừ hàng bán.",
    columns: "sku, warehouse_code, on_hand, on_order, committed, date",
  },
  {
    key: "suppliers",
    title: "Nhà cung cấp",
    description: "Lead time, MOQ và bội số đóng gói dùng cho tính toán nhập hàng.",
    columns: "name, email, lead_time_days, moq, order_multiple",
  },
];

const JOB_STATUS: Record<string, { label: string; className: string }> = {
  completed: { label: "Hoàn tất", className: "badge success" },
  failed: { label: "Có lỗi", className: "badge warning" },
  partial: { label: "Đã xóa một phần", className: "badge warning" },
  reverted: { label: "Đã xóa", className: "badge neutral" },
};

const DELETE_FIELDS: { key: keyof ImportDeleteCounts; label: string }[] = [
  { key: "products", label: "sản phẩm" },
  { key: "suppliers", label: "nhà cung cấp" },
  { key: "sales_transactions", label: "đơn bán" },
  { key: "inventory_snapshots", label: "dòng tồn kho" },
  { key: "forecasts", label: "dự báo" },
  { key: "recommendations", label: "đề xuất nhập hàng" },
  { key: "alerts", label: "cảnh báo đang mở" },
];

export default function ImportPage() {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [active, setActive] = useState<string>("products");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportJob | null>(null);
  const [error, setError] = useState("");
  const [deleteJob, setDeleteJob] = useState<ImportJob | null>(null);
  const [preview, setPreview] = useState<ImportDeletePreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [lastDeleted, setLastDeleted] = useState<ImportDeleteResult | null>(null);

  async function load() {
    try {
      setJobs(await api.imports());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được lịch sử import.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function upload(kind: string, file: File | null) {
    if (!file) return;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      const job = await api.uploadImport(kind, file);
      setResult(job);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function openDelete(job: ImportJob) {
    setDeleteJob(job);
    setPreview(null);
    setPreviewBusy(true);
    setDeleteError("");
    setLastDeleted(null);
    try {
      setPreview(await api.previewImportDeletion(job.id));
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Không xem được dữ liệu sẽ xóa.");
    } finally {
      setPreviewBusy(false);
    }
  }

  function closeDelete() {
    if (deleting) return;
    setDeleteJob(null);
    setPreview(null);
    setDeleteError("");
  }

  async function confirmDelete() {
    if (!deleteJob) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const deleted = await api.deleteImport(deleteJob.id);
      setLastDeleted(deleted);
      setDeleteJob(null);
      setPreview(null);
      await load();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Xóa import thất bại.");
    } finally {
      setDeleting(false);
    }
  }

  const coreRows = preview
    ? preview.will_delete.products +
      preview.will_delete.suppliers +
      preview.will_delete.sales_transactions +
      preview.will_delete.inventory_snapshots
    : 0;

  return (
    <div className="stack">
      <div className="card">
        <h3>Import dữ liệu</h3>
        <p className="muted">
          Hỗ trợ CSV, XLSX (tối đa 25MB). Dòng lỗi được giữ lại kèm số dòng và lý do; dữ liệu hợp lệ
          vẫn được nhập.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        {lastDeleted && (
          <div className="alert alert-info">
            <strong>
              Đã xóa import #{lastDeleted.job_id} · {lastDeleted.filename}
            </strong>
            <ul className="error-list">
              {DELETE_FIELDS.filter((field) => lastDeleted.will_delete[field.key] > 0).map((field) => (
                <li key={field.key}>
                  {lastDeleted.will_delete[field.key]} {field.label}
                </li>
              ))}
            </ul>
            {lastDeleted.notes.length > 0 && (
              <p className="small" style={{ marginTop: 6 }}>
                {lastDeleted.notes.join(" ")}
              </p>
            )}
          </div>
        )}
        {result && (
          <div className={result.rows_failed ? "alert alert-warning" : "alert alert-info"}>
            <strong>
              {result.filename}: {result.rows_ok}/{result.rows_total} dòng hợp lệ
            </strong>
            {result.rows_failed > 0 && <> · {result.rows_failed} dòng lỗi</>}
            {result.errors.length > 0 && (
              <ul className="error-list">
                {result.errors.slice(0, 8).map((item, index) => (
                  <li key={index}>
                    Dòng {item.row}
                    {item.field ? ` · ${item.field}` : ""}: {item.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Thứ tự nhập dữ liệu lần đầu</h3>
        <ol className="steps">
          <li>
            <strong>Sản phẩm</strong> — bắt buộc trước. Tên nhà cung cấp trong file sẽ được tạo tự
            động nếu chưa tồn tại.
          </li>
          <li>
            <strong>Tồn kho đầu kỳ</strong> — số lượng thực tế tại một thời điểm, chỉ cần nhập
            một lần (mặc định kho <code>MAIN</code>). Hệ thống tự cộng hàng nhập đã nhận và trừ
            hàng bán sau mốc này.
          </li>
          <li>
            <strong>Lịch sử bán hàng</strong> — nên có tối thiểu 30 ngày gần nhất để dự báo 7/14/30
            ngày.
          </li>
          <li>
            <strong>Nhà cung cấp</strong> — tùy chọn, dùng để cập nhật lead time, MOQ và bội số
            đóng gói.
          </li>
        </ol>
        <p className="muted small">
          Sau khi import, vào <strong>Tổng quan</strong> bấm <strong>Chạy dự báo &amp; đề xuất</strong>.
        </p>
      </div>

      <div className="grid import-grid">
        {KINDS.map((kind) => (
          <div
            className={`card import-card${active === kind.key ? " active" : ""}`}
            key={kind.key}
            onClick={() => setActive(kind.key)}
          >
            <div className="row between">
              <h4>{kind.title}</h4>
              <a className="link small" href={api.templateUrl(kind.key)} onClick={(event) => event.stopPropagation()}>
                Tải template
              </a>
            </div>
            <p className="muted small">{kind.description}</p>
            <code className="columns">{kind.columns}</code>
            <label className="upload">
              <input
                type="file"
                accept=".csv,.xlsx,.xlsm"
                disabled={busy}
                onChange={(event) => upload(kind.key, event.target.files?.[0] ?? null)}
              />
              <span className="btn btn-soft btn-sm">{busy && active === kind.key ? "Đang import…" : "Chọn file"}</span>
            </label>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <h3>Lịch sử import</h3>
          <button className="btn btn-ghost btn-sm" onClick={load}>
            Làm mới
          </button>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Loại</th>
              <th>File</th>
              <th className="num">Tổng</th>
              <th className="num">Thành công</th>
              <th className="num">Lỗi</th>
              <th>Trạng thái</th>
              <th>Thời điểm</th>
              <th className="actions">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => {
              const status = JOB_STATUS[job.status] ?? {
                label: job.status,
                className: "badge neutral",
              };
              return (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{KINDS.find((kind) => kind.key === job.kind)?.title ?? job.kind}</td>
                  <td className="muted">{job.filename}</td>
                  <td className="num">{job.rows_total}</td>
                  <td className="num">{job.rows_ok}</td>
                  <td className="num">{job.rows_failed}</td>
                  <td>
                    <span className={status.className}>{status.label}</span>
                  </td>
                  <td className="muted">{formatDate(job.created_at)}</td>
                  <td className="actions">
                    {job.status !== "reverted" && job.rows_ok > 0 ? (
                      <button className="btn btn-danger-ghost btn-sm" onClick={() => openDelete(job)}>
                        Xóa
                      </button>
                    ) : (
                      <span className="muted small">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {jobs.length === 0 && (
              <tr>
                <td colSpan={9} className="empty">
                  Chưa có lần import nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {deleteJob && (
        <div className="modal-backdrop" onClick={closeDelete}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-import-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="card-head">
              <div>
                <h3 id="delete-import-title">Xóa lần import #{deleteJob.id}</h3>
                <p className="muted small">
                  {KINDS.find((kind) => kind.key === deleteJob.kind)?.title ?? deleteJob.kind} ·{" "}
                  {deleteJob.filename}
                </p>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={closeDelete} disabled={deleting}>
                Đóng
              </button>
            </div>

            <div className="alert alert-warning">
              Chỉ dữ liệu do lần import này tạo ra mới bị xóa. Thao tác không thể hoàn tác.
            </div>

            {previewBusy && <div className="skeleton">Đang kiểm tra dữ liệu…</div>}
            {deleteError && <div className="alert alert-error">{deleteError}</div>}

            {preview && (
              <>
                {preview.legacy && (
                  <div className="alert alert-warning">
                    <strong>Lần import cũ chưa có thông tin nguồn.</strong> Không xác định được
                    từng dòng, nên phạm vi xóa là <strong>toàn bộ dữ liệu cùng loại</strong> hiện
                    có. Nên xóa lần lượt: bán hàng → tồn kho → sản phẩm → nhà cung cấp.
                  </div>
                )}
                <h4 style={{ marginBottom: 8 }}>Sẽ xóa</h4>
                {coreRows + preview.will_delete.forecasts + preview.will_delete.recommendations + preview.will_delete.alerts > 0 ? (
                  <ul className="delete-list">
                    {DELETE_FIELDS.filter((field) => preview.will_delete[field.key] > 0).map((field) => (
                      <li key={field.key}>
                        <strong>{preview.will_delete[field.key]}</strong> {field.label}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small">Không có dữ liệu nào có thể xóa.</p>
                )}

                {preview.skipped.length > 0 && (
                  <div className="alert alert-warning">
                    <strong>Giữ lại {preview.skipped.length} mục đang được tham chiếu:</strong>
                    <ul className="error-list">
                      {preview.skipped.map((item) => (
                        <li key={`${item.entity_type}-${item.entity_id}`}>
                          {item.label}: {item.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {preview.notes.map((note) => (
                  <p className="muted small" key={note} style={{ marginTop: 6 }}>
                    • {note}
                  </p>
                ))}
              </>
            )}

            <div className="row between" style={{ marginTop: 18 }}>
              <button className="btn btn-ghost" onClick={closeDelete} disabled={deleting}>
                Hủy
              </button>
              <button
                className="btn btn-danger"
                onClick={confirmDelete}
                disabled={deleting || previewBusy || coreRows === 0}
              >
                {deleting ? "Đang xóa…" : "Xóa dữ liệu import"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
