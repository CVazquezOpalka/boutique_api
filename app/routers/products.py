from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from ..db import get_db
from ..deps import require_roles, require_tenant_user
from ..models import Product, Variant, Role
from ..schemas import ProductCreate, ProductOut, ProductUpdate, VariantUpdate

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    return (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.tenant_id == u.tenant_id)
        .order_by(Product.created_at.desc())
        .all()
    )


@router.get("/search")
def search_products(
    q: str,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    qn = q.strip()
    if not qn:
        return []

    products = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .outerjoin(Variant, Variant.product_id == Product.id)
        .filter(Product.tenant_id == u.tenant_id)
        .filter(
            or_(
                # Producto
                Product.name.ilike(f"%{qn}%"),
                Product.sku.ilike(f"%{qn}%"),
                Product.barcode.ilike(f"%{qn}%"),
                # Variante
                Variant.sku.ilike(f"%{qn}%"),
                # Variant.barcode.ilike(f"%{qn}%"),  # si existe en el modelo
            )
        )
        .distinct(Product.id)  # ✅ evita duplicados por JOIN
        .order_by(Product.created_at.desc())
        .limit(50)
        .all()
    )

    return products


@router.post("", response_model=ProductOut)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_roles(Role.ADMIN)),
):
    p = Product(
        tenant_id=admin.tenant_id,
        name=payload.name.strip(),
        category=payload.category,
        brand=(payload.brand.strip() if payload.brand else None),
        description=(payload.description.strip() if payload.description else None),
        size=(payload.size.strip() if payload.size else None),
        sku=(payload.sku.strip() if payload.sku else None),
        barcode=(payload.barcode.strip() if payload.barcode else None),
        stock=int(payload.stock or 0),
        min_stock=int(payload.min_stock or 0),
        cost=float(payload.cost or 0),
        price=float(payload.price or 0),
        active=bool(payload.active),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_roles(Role.ADMIN)),
):
    p = db.get(Product, product_id)
    if not p or p.tenant_id != admin.tenant_id:
        raise HTTPException(404, "Producto no encontrado")

    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.category is not None:
        p.category = payload.category

    if payload.brand is not None:
        p.brand = payload.brand.strip() if payload.brand else None
    if payload.description is not None:
        p.description = payload.description.strip() if payload.description else None
    if payload.size is not None:
        p.size = payload.size.strip() if payload.size else None

    if payload.sku is not None:
        p.sku = payload.sku.strip() if payload.sku else None
    if payload.barcode is not None:
        p.barcode = payload.barcode.strip() if payload.barcode else None

    if payload.stock is not None:
        p.stock = int(payload.stock)
    if payload.min_stock is not None:
        p.min_stock = int(payload.min_stock)

    if payload.cost is not None:
        p.cost = float(payload.cost)
    if payload.price is not None:
        p.price = float(payload.price)
    if payload.active is not None:
        p.active = bool(payload.active)

    db.commit()
    db.refresh(p)
    return p


@router.patch("/variants/{variant_id}")
def update_variant(
    variant_id: int,
    payload: VariantUpdate,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    # admin y employee pueden: stock/min_stock
    # solo admin puede: sku/size/color (para evitar quilombo)
    v = db.get(Variant, variant_id)
    if not v or v.tenant_id != u.tenant_id:
        raise HTTPException(404, "Variante no encontrada")

    if payload.stock is not None:
        if payload.stock < 0:
            raise HTTPException(409, "Stock no puede ser negativo")
        v.stock = int(payload.stock)

    if payload.min_stock is not None:
        if payload.min_stock < 0:
            raise HTTPException(409, "min_stock no puede ser negativo")
        v.min_stock = int(payload.min_stock)

    if u.role == Role.ADMIN:
        if payload.size is not None:
            v.size = payload.size.strip()
        if payload.color is not None:
            v.color = payload.color.strip()
        if payload.sku is not None:
            sku = payload.sku.strip()
            exists = (
                db.query(Variant)
                .filter(
                    Variant.tenant_id == u.tenant_id,
                    Variant.sku == sku,
                    Variant.id != v.id,
                )
                .first()
            )
            if exists:
                raise HTTPException(409, "SKU duplicado")
            v.sku = sku
    else:
        # employee no puede tocar identidad SKU/talle/color
        if (
            payload.size is not None
            or payload.color is not None
            or payload.sku is not None
        ):
            raise HTTPException(403, "Solo admin puede editar SKU/talle/color")

    db.commit()
    return {
        "id": v.id,
        "product_id": v.product_id,
        "sku": v.sku,
        "size": v.size,
        "color": v.color,
        "stock": v.stock,
        "min_stock": v.min_stock,
    }
