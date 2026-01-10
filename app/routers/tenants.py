from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_roles
from ..models import Tenant, Role, User
from ..schemas import TenantCreate, TenantOut
from ..security import hash_password

router = APIRouter(prefix="/super/tenants", tags=["super-tenants"])

@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db), _=Depends(require_roles(Role.SUPER_ADMIN))):
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()

@router.post("", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db), _=Depends(require_roles(Role.SUPER_ADMIN))):
    slug = payload.slug.strip().lower()

    if db.query(Tenant).filter(Tenant.slug == slug).first():
        raise HTTPException(409, "Ese slug ya existe")

    # ✅ Validación de email admin (evitar duplicados)
    admin_email = payload.admin_user.email.strip().lower()
    if db.query(User).filter(User.email == admin_email).first():
        raise HTTPException(409, "Ese email ya existe")

    # 1) Crear tenant
    t = Tenant(name=payload.name.strip(), slug=slug)
    db.add(t)
    db.commit()
    db.refresh(t)

    # 2) Crear admin del tenant
    admin = User(
        tenant_id=t.id,
        role=Role.ADMIN,
        name=payload.admin_user.name.strip(),
        email=admin_email,
        password_hash=hash_password(payload.admin_user.password),
        active=True,
    )
    db.add(admin)
    db.commit()

    return t
