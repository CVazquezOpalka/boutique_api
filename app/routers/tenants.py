from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta

from ..db import get_db
from ..deps import require_roles
from ..models import Tenant, Role, User, PlanType
from ..schemas import TenantCreate, TenantOut, TenantUpdateIn
from ..security import hash_password

router = APIRouter(prefix="/super/tenants", tags=["super-tenants"])


def tenant_out_with_admin(db: Session, t: Tenant) -> TenantOut:
    admin = (
        db.query(User)
        .filter(User.tenant_id == t.id, User.role == Role.ADMIN, User.active == True)
        .order_by(User.id.asc())
        .first()
    )

    return TenantOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        plan=t.plan,
        trial_end=t.trial_end,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
        admin_email=admin.email if admin else None,
        admin_name=admin.name if admin else None,
    )


@router.get("", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db),
    _=Depends(require_roles(Role.SUPER_ADMIN)),
):
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [tenant_out_with_admin(db, t) for t in tenants]


@router.post("", response_model=TenantOut)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    _=Depends(require_roles(Role.SUPER_ADMIN)),
):
    slug = payload.slug.strip().lower()

    if db.query(Tenant).filter(Tenant.slug == slug).first():
        raise HTTPException(409, "Ese slug ya existe")

    now = datetime.utcnow()

    tenant = Tenant(
        name=payload.name.strip(),
        slug=slug,
        plan=PlanType.FREE_TRIAL,
        trial_end=now + timedelta(days=15),
        is_active=True,
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # ✅ crear admin user
    admin = payload.admin_user
    user = User(
        tenant_id=tenant.id,
        name=admin.name.strip(),
        email=admin.email.strip().lower(),
        role=Role.ADMIN,
        active=True,
        password_hash=hash_password(admin.password),
        must_change_password=True,  # si existe en tu modelo
    )

    db.add(user)
    db.commit()

    # ✅ devolver response_model completo
    return tenant_out_with_admin(db, tenant)


class ChangePlanIn(BaseModel):
    plan: PlanType


@router.post("/{tenant_id}/change-plan", response_model=TenantOut)
def change_plan(
    tenant_id: int,
    payload: ChangePlanIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(Role.SUPER_ADMIN)),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant no encontrado")

    tenant.plan = payload.plan

    now = datetime.utcnow()

    if payload.plan == PlanType.FREE_TRIAL:
        tenant.trial_end = now + timedelta(days=15)
        tenant.is_active = True
    else:
        tenant.trial_end = None

    # opcional si tenés updated_at
    if hasattr(tenant, "updated_at"):
        tenant.updated_at = now

    db.commit()
    db.refresh(tenant)
    return tenant_out_with_admin(db, tenant)


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdateIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(Role.SUPER_ADMIN)),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant no encontrado")

    if payload.is_active is not None:
        tenant.is_active = payload.is_active

    if payload.plan is not None:
        tenant.plan = payload.plan
        tenant.trial_end = (
            None
            if payload.plan != PlanType.FREE_TRIAL
            else datetime.utcnow() + timedelta(days=15)
        )

    if hasattr(tenant, "updated_at"):
        tenant.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(tenant)

    admin = next((u for u in tenant.users if u.role == Role.ADMIN and u.active), None)

    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan,
        trial_end=tenant.trial_end,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        admin_email=admin.email if admin else None,
        admin_name=admin.name if admin else None,
    )
