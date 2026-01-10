from sqlalchemy.orm import Session
from .models import Tenant, User, Role, Product, Variant
from .security import hash_password


def ensure_seed(db: Session):
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
        tenant = Tenant(name="Boutique Luna", slug="luna")
        db.add(tenant)
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
