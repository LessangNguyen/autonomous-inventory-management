"""Safe reversal of an import job.

Every successful import row records the entity it created or updated in
``import_sources``. Reverting a job deletes the rows that job *created* and
clears derived forecasts/recommendations for the affected products. Rows that
only updated existing data are kept because replacing them would overwrite
newer values; the API reports that limitation to the user.

Referenced entities are never deleted silently: a product that already has
sales, an inventory count or a purchase order is skipped and reported, so the
owner can delete the dependent import first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AuditLog,
    Forecast,
    ImportJob,
    ImportSource,
    InventorySnapshot,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    ReplenishmentRecommendation,
    SalesItem,
    SalesTransaction,
    Supplier,
)

KIND_LABELS = {
    "products": "sản phẩm",
    "suppliers": "nhà cung cấp",
    "sales": "lịch sử bán hàng",
    "inventory": "tồn kho đầu kỳ",
}


@dataclass
class DeletionPlan:
    job: ImportJob
    sales_transaction_ids: list[int] = field(default_factory=list)
    inventory_snapshot_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    supplier_ids: list[int] = field(default_factory=list)
    affected_product_ids: set[int] = field(default_factory=set)
    forecasts: int = 0
    recommendations: int = 0
    alerts: int = 0
    skipped: list[dict] = field(default_factory=list)
    updated_entities: int = 0
    legacy: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "products": len(self.product_ids),
            "suppliers": len(self.supplier_ids),
            "sales_transactions": len(self.sales_transaction_ids),
            "inventory_snapshots": len(self.inventory_snapshot_ids),
            "forecasts": self.forecasts,
            "recommendations": self.recommendations,
            "alerts": self.alerts,
        }

    @property
    def deletable_rows(self) -> int:
        return (
            len(self.sales_transaction_ids)
            + len(self.inventory_snapshot_ids)
            + len(self.product_ids)
            + len(self.supplier_ids)
        )

    def as_preview(self) -> dict:
        return {
            "job_id": self.job.id,
            "kind": self.job.kind,
            "filename": self.job.filename,
            "status": self.job.status,
            "rows_ok": self.job.rows_ok,
            "will_delete": self.counts,
            "skipped": self.skipped,
            "updated_entities": self.updated_entities,
            "legacy": self.legacy,
            "notes": self.notes,
        }


def _created_ids(db: Session, job: ImportJob, entity_type: str) -> list[int]:
    return [
        row[0]
        for row in db.query(ImportSource.entity_id)
        .filter(
            ImportSource.tenant_id == job.tenant_id,
            ImportSource.job_id == job.id,
            ImportSource.entity_type == entity_type,
            ImportSource.action == "created",
        )
        .all()
    ]


def _existing_ids(db: Session, model, tenant_id: int, ids: list[int]) -> list[int]:
    if not ids:
        return []
    return [
        row[0]
        for row in db.query(model.id)
        .filter(model.tenant_id == tenant_id, model.id.in_(ids))
        .all()
    ]


def _all_ids(db: Session, model, tenant_id: int) -> list[int]:
    return [
        row[0]
        for row in db.query(model.id).filter(model.tenant_id == tenant_id).all()
    ]


def _has_source_rows(db: Session, job: ImportJob) -> bool:
    return bool(
        db.query(func.count(ImportSource.id))
        .filter(ImportSource.tenant_id == job.tenant_id, ImportSource.job_id == job.id)
        .scalar()
    )


def _reference_counts(db: Session, model, column, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    return {
        key: int(count or 0)
        for key, count in db.query(column, func.count(model.id))
        .filter(column.in_(ids))
        .group_by(column)
        .all()
    }


def _open_alert_count(db: Session, tenant_id: int, product_ids: set[int]) -> int:
    if not product_ids:
        return 0
    return int(
        db.query(func.count(Alert.id))
        .filter(
            Alert.tenant_id == tenant_id,
            Alert.product_id.in_(product_ids),
            Alert.status == "open",
        )
        .scalar()
        or 0
    )


def build_deletion_plan(db: Session, job: ImportJob) -> DeletionPlan:
    plan = DeletionPlan(job=job)
    tenant_id = job.tenant_id

    plan.updated_entities = int(
        db.query(func.count(ImportSource.id))
        .filter(
            ImportSource.tenant_id == tenant_id,
            ImportSource.job_id == job.id,
            ImportSource.action == "updated",
        )
        .scalar()
        or 0
    )

    # Jobs created before source tracking existed have no rows in
    # ``import_sources``. For those only, fall back to "all data of this kind"
    # and say so clearly in the preview; tracked jobs keep exact scope.
    plan.legacy = not _has_source_rows(db, job) and job.rows_ok > 0
    if plan.legacy:
        plan.notes.append(
            "Lần import này được tạo trước khi bật theo dõi nguồn. "
            "Không xác định được từng dòng, nên phạm vi xóa là toàn bộ "
            f"{KIND_LABELS.get(job.kind, job.kind)} hiện có."
        )
        plan.sales_transaction_ids = (
            _all_ids(db, SalesTransaction, tenant_id) if job.kind == "sales" else []
        )
        plan.inventory_snapshot_ids = (
            _all_ids(db, InventorySnapshot, tenant_id) if job.kind == "inventory" else []
        )
        candidate_products = _all_ids(db, Product, tenant_id) if job.kind == "products" else []
        candidate_suppliers = _all_ids(db, Supplier, tenant_id) if job.kind == "suppliers" else []
    else:
        plan.sales_transaction_ids = _existing_ids(
            db,
            SalesTransaction,
            tenant_id,
            _created_ids(db, job, "sales_transaction"),
        )
        plan.inventory_snapshot_ids = _existing_ids(
            db,
            InventorySnapshot,
            tenant_id,
            _created_ids(db, job, "inventory_snapshot"),
        )
        candidate_products = _existing_ids(
            db, Product, tenant_id, _created_ids(db, job, "product")
        )
        candidate_suppliers = _existing_ids(
            db, Supplier, tenant_id, _created_ids(db, job, "supplier")
        )

    product_labels = {
        product.id: product.sku
        for product in db.query(Product)
        .filter(Product.tenant_id == tenant_id, Product.id.in_(candidate_products or [0]))
        .all()
    } if candidate_products else {}

    sales_refs = _reference_counts(db, SalesItem, SalesItem.product_id, candidate_products)
    inventory_refs = _reference_counts(
        db, InventorySnapshot, InventorySnapshot.product_id, candidate_products
    )
    po_refs = _reference_counts(
        db, PurchaseOrderItem, PurchaseOrderItem.product_id, candidate_products
    )

    for product_id in candidate_products:
        reasons = []
        if sales_refs.get(product_id):
            reasons.append(f"{sales_refs[product_id]} dòng bán hàng")
        if inventory_refs.get(product_id):
            reasons.append(f"{inventory_refs[product_id]} dòng tồn kho")
        if po_refs.get(product_id):
            reasons.append(f"{po_refs[product_id]} dòng đơn nhập")
        if reasons:
            plan.skipped.append(
                {
                    "entity_type": "product",
                    "entity_id": product_id,
                    "label": product_labels.get(product_id, f"#{product_id}"),
                    "reason": "đang được dùng trong " + ", ".join(reasons),
                }
            )
        else:
            plan.product_ids.append(product_id)

    supplier_labels = {
        supplier.id: supplier.name
        for supplier in db.query(Supplier)
        .filter(Supplier.tenant_id == tenant_id, Supplier.id.in_(candidate_suppliers or [0]))
        .all()
    } if candidate_suppliers else {}

    if candidate_suppliers:
        product_query = db.query(Product.supplier_id, func.count(Product.id)).filter(
            Product.supplier_id.in_(candidate_suppliers)
        )
        if plan.product_ids:
            product_query = product_query.filter(~Product.id.in_(plan.product_ids))
        supplier_product_refs = {
            key: int(count or 0)
            for key, count in product_query.group_by(Product.supplier_id).all()
        }
    else:
        supplier_product_refs = {}
    supplier_po_refs = _reference_counts(
        db, PurchaseOrder, PurchaseOrder.supplier_id, candidate_suppliers
    )

    for supplier_id in candidate_suppliers:
        reasons = []
        if supplier_product_refs.get(supplier_id):
            reasons.append(f"{supplier_product_refs[supplier_id]} sản phẩm")
        if supplier_po_refs.get(supplier_id):
            reasons.append(f"{supplier_po_refs[supplier_id]} đơn nhập")
        if reasons:
            plan.skipped.append(
                {
                    "entity_type": "supplier",
                    "entity_id": supplier_id,
                    "label": supplier_labels.get(supplier_id, f"#{supplier_id}"),
                    "reason": "đang được dùng bởi " + ", ".join(reasons),
                }
            )
        else:
            plan.supplier_ids.append(supplier_id)

    if plan.sales_transaction_ids:
        plan.affected_product_ids.update(
            row[0]
            for row in db.query(SalesItem.product_id)
            .filter(SalesItem.transaction_id.in_(plan.sales_transaction_ids))
            .distinct()
            .all()
        )
    if plan.inventory_snapshot_ids:
        plan.affected_product_ids.update(
            row[0]
            for row in db.query(InventorySnapshot.product_id)
            .filter(InventorySnapshot.id.in_(plan.inventory_snapshot_ids))
            .distinct()
            .all()
        )
    plan.affected_product_ids.update(plan.product_ids)

    if plan.affected_product_ids:
        plan.forecasts = int(
            db.query(func.count(Forecast.id))
            .filter(
                Forecast.tenant_id == tenant_id,
                Forecast.product_id.in_(plan.affected_product_ids),
            )
            .scalar()
            or 0
        )
        plan.recommendations = int(
            db.query(func.count(ReplenishmentRecommendation.id))
            .filter(
                ReplenishmentRecommendation.tenant_id == tenant_id,
                ReplenishmentRecommendation.product_id.in_(plan.affected_product_ids),
            )
            .scalar()
            or 0
        )
        plan.alerts = _open_alert_count(db, tenant_id, plan.affected_product_ids)

    if plan.updated_entities:
        plan.notes.append(
            f"{plan.updated_entities} dòng chỉ cập nhật dữ liệu đã tồn tại. "
            "Hệ thống không lưu giá trị cũ nên các cập nhật này được giữ nguyên."
        )
    if plan.skipped:
        plan.notes.append(
            "Dữ liệu đang được tham chiếu sẽ được giữ lại. "
            "Hãy xóa lần import liên quan trước nếu muốn xóa tiếp."
        )
    if plan.forecasts or plan.recommendations or plan.alerts:
        plan.notes.append(
            "Dự báo, đề xuất và cảnh báo liên quan sẽ bị xóa để tránh số liệu cũ. "
            "Hãy chạy lại dự báo sau khi hoàn tất."
        )
    return plan


def revert_import_job(db: Session, job: ImportJob, user_id: int | None) -> DeletionPlan:
    if job.status == "reverted":
        raise ValueError("Lần import này đã được xóa trước đó.")

    plan = build_deletion_plan(db, job)
    if plan.deletable_rows == 0:
        if plan.updated_entities:
            raise ValueError(
                "Lần import này chỉ cập nhật dữ liệu đã có. "
                "Hệ thống không thể khôi phục giá trị cũ."
            )
        raise ValueError(
            "Không còn dữ liệu nào có thể xóa. "
            "Dữ liệu đã bị xóa hoặc đang được dữ liệu khác tham chiếu."
        )

    if plan.sales_transaction_ids:
        db.query(SalesItem).filter(
            SalesItem.transaction_id.in_(plan.sales_transaction_ids)
        ).delete(synchronize_session=False)
        db.query(SalesTransaction).filter(
            SalesTransaction.tenant_id == job.tenant_id,
            SalesTransaction.id.in_(plan.sales_transaction_ids),
        ).delete(synchronize_session=False)

    if plan.inventory_snapshot_ids:
        db.query(InventorySnapshot).filter(
            InventorySnapshot.tenant_id == job.tenant_id,
            InventorySnapshot.id.in_(plan.inventory_snapshot_ids),
        ).delete(synchronize_session=False)

    if plan.affected_product_ids:
        db.query(Forecast).filter(
            Forecast.tenant_id == job.tenant_id,
            Forecast.product_id.in_(plan.affected_product_ids),
        ).delete(synchronize_session=False)
        db.query(ReplenishmentRecommendation).filter(
            ReplenishmentRecommendation.tenant_id == job.tenant_id,
            ReplenishmentRecommendation.product_id.in_(plan.affected_product_ids),
        ).delete(synchronize_session=False)
        db.query(Alert).filter(
            Alert.tenant_id == job.tenant_id,
            Alert.product_id.in_(plan.affected_product_ids),
            Alert.status == "open",
        ).delete(synchronize_session=False)

    if plan.product_ids:
        db.query(Product).filter(
            Product.tenant_id == job.tenant_id,
            Product.id.in_(plan.product_ids),
        ).delete(synchronize_session=False)

    if plan.supplier_ids:
        db.query(Supplier).filter(
            Supplier.tenant_id == job.tenant_id,
            Supplier.id.in_(plan.supplier_ids),
        ).delete(synchronize_session=False)

    # Keep the source rows when some entities were blocked so the owner can
    # remove the dependent import and retry this job later.
    if not plan.skipped:
        db.query(ImportSource).filter(
            ImportSource.tenant_id == job.tenant_id,
            ImportSource.job_id == job.id,
        ).delete(synchronize_session=False)

    if plan.legacy and not plan.skipped:
        # The fallback removed every row of this kind, so older jobs of the
        # same kind no longer have data either.
        db.query(ImportJob).filter(
            ImportJob.tenant_id == job.tenant_id,
            ImportJob.kind == job.kind,
            ImportJob.status != "reverted",
        ).update({ImportJob.status: "reverted"}, synchronize_session=False)
    else:
        job.status = "partial" if plan.skipped else "reverted"
    db.add(
        AuditLog(
            tenant_id=job.tenant_id,
            user_id=user_id,
            action="import.revert",
            entity="import_job",
            entity_id=job.id,
            details={
                "kind": job.kind,
                "filename": job.filename,
                "deleted": plan.counts,
                "skipped": plan.skipped,
                "legacy_scope": plan.legacy,
            },
        )
    )
    db.commit()
    db.refresh(job)
    return plan
