from sqlalchemy.orm import Session
from .models import Tenant, User, Role, Product, Variant, PlanType
from .security import hash_password

from sqlalchemy import text
from datetime import datetime, timedelta

def _sqlite_add_missing_tenant_columns(db: Session):
    # Solo aplica si estás en SQLite
    dialect = db.bind.dialect.name if db.bind else ""
    if dialect != "sqlite":
        return

    # Obtener columnas actuales de la tabla tenants
    cols = db.execute(text("PRAGMA table_info(tenants)")).fetchall()
    existing = {c[1] for c in cols}  # c[1] = name

    # Agregar columnas faltantes (SQLite permite ADD COLUMN)
    # Nota: defaults en SQLite no siempre se aplican retroactivamente, por eso luego hacemos UPDATE.
    if "plan" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN plan VARCHAR(20)"))
    if "trial_end" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN trial_end DATETIME"))
    if "is_active" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN is_active BOOLEAN"))
    if "updated_at" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN updated_at DATETIME"))

    db.commit()

    # Backfill de valores para filas ya existentes
    now = datetime.utcnow().isoformat(sep=" ")
    # FREE_TRIAL por defecto
    db.execute(text("UPDATE tenants SET plan = 'FREE_TRIAL' WHERE plan IS NULL"))
    # activar por defecto
    db.execute(text("UPDATE tenants SET is_active = 1 WHERE is_active IS NULL"))
    # updated_at fallback
    db.execute(text("UPDATE tenants SET updated_at = COALESCE(updated_at, created_at, :now)"), {"now": now})

    # Si es FREE_TRIAL y trial_end es NULL, setear trial_end = created_at + 15 días (o now + 15 si no hay created_at)
    # SQLite date() soporta '+15 day'
    db.execute(text("""
        UPDATE tenants
        SET trial_end = COALESCE(trial_end, datetime(COALESCE(created_at, :now), '+15 day'))
        WHERE plan = 'FREE_TRIAL' AND trial_end IS NULL
    """), {"now": now})

    db.commit()


def ensure_seed(db: Session):
    # ✅ 0) Auto-migrate tenants columns en SQLite (MVP)
    _sqlite_add_missing_tenant_columns(db)

    # --- Superadmin
    if not db.query(User).filter(User.email == "super@boutiqueos.com").first():
        db.add(User(
            tenant_id=None,
            role=Role.SUPER_ADMIN,
            name="Super Admin",
            email="super@boutiqueos.com",
            password_hash=hash_password("123456"),
            active=True
        ))
        db.commit()

    # --- Tenant base
    tenant = db.query(Tenant).filter(Tenant.slug == "luna").first()
    if not tenant:
        now = datetime.utcnow()
        tenant = Tenant(
            name="Boutique Luna",
            slug="luna",
            plan=PlanType.FREE_TRIAL,
            trial_end=now + timedelta(days=15),
            is_active=True,
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    else:
        # Por si existía de antes sin datos nuevos (en DB vieja)
        now = datetime.utcnow()
        if getattr(tenant, "plan", None) is None:
            tenant.plan = PlanType.FREE_TRIAL
        if getattr(tenant, "is_active", None) is None:
            tenant.is_active = True
        if tenant.plan == PlanType.FREE_TRIAL and getattr(tenant, "trial_end", None) is None:
            tenant.trial_end = (tenant.created_at or now) + timedelta(days=15)
        db.commit()
        db.refresh(tenant)

    # --- Admin tenant
    if not db.query(User).filter(User.email == "admin@luna.com").first():
        db.add(User(
            tenant_id=tenant.id,
            role=Role.ADMIN,
            name="Admin Luna",
            email="admin@luna.com",
            password_hash=hash_password("123456"),
            active=True
        ))
        db.commit()

    # --- Employee tenant
    if not db.query(User).filter(User.email == "emp@luna.com").first():
        db.add(User(
            tenant_id=tenant.id,
            role=Role.EMPLOYEE,
            name="Empleado 1",
            email="emp@luna.com",
            password_hash=hash_password("123456"),
            active=True
        ))
        db.commit()

    # --- Producto demo + variantes
    demo = db.query(Product).filter(
        Product.tenant_id == tenant.id,
        Product.name == "Remera básica"
    ).first()

    if not demo:
        p = Product(
            tenant_id=tenant.id,
            name="Remera básica",
            category="Remeras",
            cost=4500,
            price=12000,
            active=True
        )
        db.add(p)
        db.commit()
        db.refresh(p)

        db.add_all([
            Variant(tenant_id=tenant.id, product_id=p.id, size="S", color="Negro",  sku="REM-S-NEG", stock=8, min_stock=3),
            Variant(tenant_id=tenant.id, product_id=p.id, size="M", color="Negro",  sku="REM-M-NEG", stock=5, min_stock=3),
            Variant(tenant_id=tenant.id, product_id=p.id, size="L", color="Blanco", sku="REM-L-BLA", stock=2, min_stock=3),
        ])
        db.commit()