from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import Tenant, User, Role, Product, Variant, PlanType
from .security import hash_password


# -------------------------
# SQLite MVP auto-migrations
# -------------------------

def _is_sqlite(db: Session) -> bool:
    dialect = db.bind.dialect.name if db.bind else ""
    return dialect == "sqlite"


def _sqlite_table_columns(db: Session, table_name: str) -> set[str]:
    cols = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {c[1] for c in cols}  # c[1] = column name


def _sqlite_add_missing_tenant_columns(db: Session):
    if not _is_sqlite(db):
        return

    existing = _sqlite_table_columns(db, "tenants")

    # Tenants columns
    if "plan" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN plan VARCHAR(20)"))
    if "trial_end" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN trial_end DATETIME"))
    if "is_active" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN is_active BOOLEAN"))
    if "updated_at" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN updated_at DATETIME"))

    db.commit()

    # Backfill
    now = datetime.utcnow().isoformat(sep=" ")

    db.execute(text("UPDATE tenants SET plan = 'FREE_TRIAL' WHERE plan IS NULL"))
    db.execute(text("UPDATE tenants SET is_active = 1 WHERE is_active IS NULL"))
    db.execute(
        text("UPDATE tenants SET updated_at = COALESCE(updated_at, created_at, :now)"),
        {"now": now},
    )
    db.execute(
        text("""
            UPDATE tenants
            SET trial_end = COALESCE(trial_end, datetime(COALESCE(created_at, :now), '+15 day'))
            WHERE plan = 'FREE_TRIAL' AND trial_end IS NULL
        """),
        {"now": now},
    )

    db.commit()


def _sqlite_add_missing_user_columns(db: Session):
    if not _is_sqlite(db):
        return

    existing = _sqlite_table_columns(db, "users")

    # Users columns (solo las necesarias para tu flujo MVP)
    if "must_change_password" not in existing:
        db.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN"))
    if "updated_at" not in existing:
        # opcional: si tu modelo User ya tiene updated_at, esto lo crea
        db.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME"))

    db.commit()

    # Backfill: must_change_password default false, updated_at fallback
    now = datetime.utcnow().isoformat(sep=" ")
    db.execute(text("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL"))
    db.execute(text("UPDATE users SET updated_at = COALESCE(updated_at, created_at, :now)"), {"now": now})
    db.commit()


# -----------
# Seed
# -----------

def ensure_seed(db: Session):
    # ✅ 0) Auto-migrate SQLite (MVP)
    _sqlite_add_missing_tenant_columns(db)
    _sqlite_add_missing_user_columns(db)

    # --- Superadmin
    super_email = "super@boutiqueos.com"
    super_user = db.query(User).filter(User.email == super_email).first()
    if not super_user:
        db.add(User(
            tenant_id=None,
            role=Role.SUPER_ADMIN,
            name="Super Admin",
            email=super_email,
            password_hash=hash_password("123456"),
            active=True,
            must_change_password=False,  # super no necesita cambiar
        ))
        db.commit()

    # --- Tenant base (Boutique Luna)
    tenant = db.query(Tenant).filter(Tenant.slug == "luna").first()
    now = datetime.utcnow()

    if not tenant:
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
        # Backfill por si existe viejo
        changed = False
        if getattr(tenant, "plan", None) is None:
            tenant.plan = PlanType.FREE_TRIAL
            changed = True
        if getattr(tenant, "is_active", None) is None:
            tenant.is_active = True
            changed = True
        if tenant.plan == PlanType.FREE_TRIAL and getattr(tenant, "trial_end", None) is None:
            tenant.trial_end = (tenant.created_at or now) + timedelta(days=15)
            changed = True
        if changed:
            db.commit()
            db.refresh(tenant)

    # --- Admin tenant (Luna)
    admin_email = "admin@luna.com"
    admin_user = db.query(User).filter(User.email == admin_email).first()
    if not admin_user:
        db.add(User(
            tenant_id=tenant.id,
            role=Role.ADMIN,
            name="Admin Luna",
            email=admin_email,
            password_hash=hash_password("123456"),
            active=True,
            must_change_password=False,  # en seed no forzamos cambio
        ))
        db.commit()

    # --- Employee tenant (Luna)
    emp_email = "emp@luna.com"
    emp_user = db.query(User).filter(User.email == emp_email).first()
    if not emp_user:
        db.add(User(
            tenant_id=tenant.id,
            role=Role.EMPLOYEE,
            name="Empleado 1",
            email=emp_email,
            password_hash=hash_password("123456"),
            active=True,
            must_change_password=False,
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
