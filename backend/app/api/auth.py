from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AuditLog, Tenant, User, Warehouse
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User, tenant: Tenant) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.tenant_id, user.role),
        user=UserOut.model_validate(user),
        tenant_name=tenant.name,
    )


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict:
    """Public bootstrap flags used by the login screen.

    ``initialized`` is false on a brand-new database, so the UI can start on
    the "create store" tab instead of showing a login form nobody can use.
    """

    return {
        "initialized": db.query(User.id).first() is not None,
        "registration_open": settings.allow_registration,
        "demo_enabled": settings.seed_demo_data,
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not settings.allow_registration:
        raise HTTPException(
            status_code=403,
            detail="Tự đăng ký đã bị tắt. Liên hệ quản trị viên để tạo tài khoản.",
        )
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email đã được sử dụng.")

    tenant = Tenant(name=payload.store_name.strip(), plan="trial")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    db.add(
        Warehouse(tenant_id=tenant.id, code="MAIN", name="Kho chính", is_default=True)
    )
    db.flush()
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            user_id=user.id,
            action="auth.register",
            entity="tenant",
            entity_id=tenant.id,
            details={"store_name": tenant.name},
        )
    )
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    return _token_response(user, tenant)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa.")
    tenant = db.get(Tenant, user.tenant_id)
    return _token_response(user, tenant)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
