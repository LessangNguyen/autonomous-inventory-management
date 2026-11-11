from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, writer
from app.models import ImportJob, User
from app.schemas import ImportDeletePreview, ImportDeleteResult, ImportJobOut
from app.services.import_cleanup import build_deletion_plan, revert_import_job
from app.services.importer import TEMPLATE_COLUMNS, import_file

router = APIRouter(prefix="/api/imports", tags=["imports"])

ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")


@router.get("/templates/{kind}")
def download_template(kind: str, user: User = Depends(get_current_user)) -> Response:
    if kind not in TEMPLATE_COLUMNS:
        raise HTTPException(status_code=404, detail="Không có template cho loại dữ liệu này.")
    header = ",".join(TEMPLATE_COLUMNS[kind])
    examples = {
        "products": "SER-001,Serum Vitamin C 30ml,Chăm sóc da,chai,145000,289000,Công ty Mỹ phẩm Ánh Dương,5,12,6",
        "sales": "SER-001,2026-11-01,3,289000,MAIN,HD-0001",
        "inventory": "SER-001,MAIN,120,24,0,2026-11-10",
        "suppliers": "Công ty Mỹ phẩm Ánh Dương,order@anhduong.vn,5,12,6",
    }
    body = f"{header}\n{examples[kind]}\n"
    return Response(
        content=body.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="template_{kind}.csv"'},
    )


@router.post("/{kind}", response_model=ImportJobOut, status_code=201)
async def upload_import(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> ImportJob:
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .csv, .xlsx hoặc .xlsm.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File vượt quá 25MB.")
    try:
        job = import_file(db, user.tenant_id, user.id, kind, filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.get("", response_model=list[ImportJobOut])
def list_imports(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ImportJob]:
    return (
        db.query(ImportJob)
        .filter(ImportJob.tenant_id == user.tenant_id)
        .order_by(ImportJob.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )


@router.get("/{job_id}", response_model=ImportJobOut)
def get_import(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportJob:
    job = _get_job(db, job_id, user)
    return job


def _get_job(db: Session, job_id: int, user: User) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần import này.")
    return job


@router.get("/{job_id}/deletion-preview", response_model=ImportDeletePreview)
def preview_import_deletion(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportDeletePreview:
    job = _get_job(db, job_id, user)
    return ImportDeletePreview(**build_deletion_plan(db, job).as_preview())


@router.delete("/{job_id}", response_model=ImportDeleteResult)
def delete_import(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(writer),
) -> ImportDeleteResult:
    job = _get_job(db, job_id, user)
    try:
        plan = revert_import_job(db, job, user.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportDeleteResult(**plan.as_preview())
