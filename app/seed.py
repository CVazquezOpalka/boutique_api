from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Tenant, User, Role, Product, PlanType
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


def _sqlite_add_missing_tenant_columns(db: Session) -> None:
    if not _is_sqlite(db):
        return

    existing = _sqlite_table_columns(db, "tenants")

    if "plan" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN plan VARCHAR(20)"))
    if "trial_end" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN trial_end DATETIME"))
    if "is_active" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN is_active BOOLEAN"))
    if "updated_at" not in existing:
        db.execute(text("ALTER TABLE tenants ADD COLUMN updated_at DATETIME"))

    db.commit()

    # Backfill tenants
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


def _sqlite_add_missing_product_columns(db: Session) -> None:
    """
    Products MVP: sku/barcode/stock/min_stock.
    """
    if not _is_sqlite(db):
        return

    existing = _sqlite_table_columns(db, "products")

    if "sku" not in existing:
        db.execute(text("ALTER TABLE products ADD COLUMN sku VARCHAR(100)"))
    if "barcode" not in existing:
        db.execute(text("ALTER TABLE products ADD COLUMN barcode VARCHAR(100)"))
    if "stock" not in existing:
        db.execute(text("ALTER TABLE products ADD COLUMN stock INTEGER"))
    if "min_stock" not in existing:
        db.execute(text("ALTER TABLE products ADD COLUMN min_stock INTEGER"))

    db.commit()

    # Backfill products
    db.execute(text("UPDATE products SET stock = COALESCE(stock, 0)"))
    db.execute(text("UPDATE products SET min_stock = COALESCE(min_stock, 0)"))
    db.commit()


def _sqlite_add_missing_user_columns(db: Session) -> None:
    if not _is_sqlite(db):
        return

    existing = _sqlite_table_columns(db, "users")

    if "must_change_password" not in existing:
        db.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN"))
    if "updated_at" not in existing:
        db.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME"))

    db.commit()

    # Backfill users
    now = datetime.utcnow().isoformat(sep=" ")
    db.execute(text("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL"))
    db.execute(text("UPDATE users SET updated_at = COALESCE(updated_at, created_at, :now)"), {"now": now})
    db.commit()


def _sqlite_add_missing_cash_columns(db: Session) -> None:
    """
    Solo si tu CashSession fue creciendo (withdrawal/expected/difference/closed_by).
    Si tu tabla cash_sessions todavía no existe o no tiene estos campos, esto evita el crash.
    """
    if not _is_sqlite(db):
        return

    # si la tabla no existe, no hacemos nada (tu create_all la crea al inicio)
    try:
        existing = _sqlite_table_columns(db, "cash_sessions")
    except Exception:
        return

    # Campos "nuevos" típicos del cierre automático
    if "withdrawal_amount" not in existing:
        db.execute(text("ALTER TABLE cash_sessions ADD COLUMN withdrawal_amount FLOAT"))
    if "withdrawal_notes" not in existing:
        db.execute(text("ALTER TABLE cash_sessions ADD COLUMN withdrawal_notes TEXT"))
    if "expected_amount" not in existing:
        db.execute(text("ALTER TABLE cash_sessions ADD COLUMN expected_amount FLOAT"))
    if "difference_amount" not in existing:
        db.execute(text("ALTER TABLE cash_sessions ADD COLUMN difference_amount FLOAT"))
    if "closed_by_user_id" not in existing:
        db.execute(text("ALTER TABLE cash_sessions ADD COLUMN closed_by_user_id INTEGER"))

    db.commit()

    # Backfill defaults
    db.execute(text("UPDATE cash_sessions SET withdrawal_amount = COALESCE(withdrawal_amount, 0)"))
    db.execute(text("UPDATE cash_sessions SET expected_amount = COALESCE(expected_amount, 0)"))
    db.execute(text("UPDATE cash_sessions SET difference_amount = COALESCE(difference_amount, 0)"))
    db.commit()


# -----------
# Seed
# -----------

def ensure_seed(db: Session) -> None:
    # ✅ 0) Auto-migrate SQLite (MVP)
    _sqlite_add_missing_tenant_columns(db)
    _sqlite_add_missing_product_columns(db)
    _sqlite_add_missing_user_columns(db)
    _sqlite_add_missing_cash_columns(db)

    # --- Superadmin
    super_email = "super@boutiqueos.com"
    super_user = db.query(User).filter(User.email == super_email).first()
    if not super_user:
        db.add(
            User(
                tenant_id=None,
                role=Role.SUPER_ADMIN,
                name="Super Admin",
                email=super_email,
                password_hash=hash_password("123456"),
                active=True,
                must_change_password=False,
            )
        )
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
        db.add(
            User(
                tenant_id=tenant.id,
                role=Role.ADMIN,
                name="Admin Luna",
                email=admin_email,
                password_hash=hash_password("123456"),
                active=True,
                must_change_password=False,
            )
        )
        db.commit()

    # --- Employee tenant (Luna)
    emp_email = "emp@luna.com"
    emp_user = db.query(User).filter(User.email == emp_email).first()
    if not emp_user:
        db.add(
            User(
                tenant_id=tenant.id,
                role=Role.EMPLOYEE,
                name="Empleado 1",
                email=emp_email,
                password_hash=hash_password("123456"),
                active=True,
                must_change_password=False,
            )
        )
        db.commit()

    # --- Producto demo (SIN variantes)
    demo = (
        db.query(Product)
        .filter(Product.tenant_id == tenant.id, Product.name == "Remera básica")
        .first()
    )

    if not demo:
        p = Product(
            tenant_id=tenant.id,
            name="Remera básica",
            category="Remeras",
            sku="REM-BASICA",
            barcode="7501234567890",
            stock=15,
            min_stock=3,
            cost=4500,
            price=12000,
            active=True,
        )
        db.add(p)
        db.commit()
