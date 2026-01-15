from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_tenant_user
from ..models import Sale, Variant, PaymentMethod, Product, CashSession, CashStatus

router = APIRouter(prefix="/sales", tags=["sales"])


# -------- Schemas (MVP) --------
class SaleItemIn(BaseModel):
    product_id: int
    quantity: int
    unit_price: Optional[float] = None


class SaleCreateIn(BaseModel):
    total: float
    payment_method: Optional[str] = "EFECTIVO"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    product_id: Optional[int] = None
    code: Optional[str] = None
    quantity: int


class SaleOut(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total: float
    items_count: Optional[int] = None
    payment_method: Optional[str] = None
    created_at: datetime

    # ✅ snapshot
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    product_barcode: Optional[str] = None
    product_sku: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None

    class Config:
        from_attributes = True


# -------- helpers --------
def _find_product_by_code(db: Session, tenant_id: int, code: str) -> Product | None:
    c = (code or "").strip()
    if not c:
        return None
    return (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id)
        .filter((Product.barcode == c) | (Product.sku == c))
        .first()
    )


def _parse_payment_method(value: Optional[str]) -> PaymentMethod:
    if not value:
        return PaymentMethod.EFECTIVO
    v = value.strip().upper()
    try:
        return PaymentMethod(v)
    except Exception:
        allowed = [pm.value for pm in PaymentMethod]
        raise HTTPException(400, f"payment_method inválido. Permitidos: {allowed}")


@router.get("", response_model=List[SaleOut])
def list_sales(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    return (
        db.query(Sale)
        .filter(Sale.tenant_id == u.tenant_id)
        .order_by(Sale.created_at.desc())
        .all()
    )


@router.post("", response_model=SaleOut)
def create_sale(
    payload: SaleCreateIn,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    if payload.total <= 0:
        raise HTTPException(400, "El total debe ser mayor a 0.")

    if payload.quantity is None or payload.quantity <= 0:
        raise HTTPException(400, "quantity es requerido y debe ser > 0")

    pm = _parse_payment_method(payload.payment_method)

    # 🔍 Resolver producto
    product: Product | None = None

    if payload.product_id:
        product = (
            db.query(Product)
            .filter(
                Product.id == payload.product_id,
                Product.tenant_id == u.tenant_id,
                Product.active == True,
            )
            .first()
        )
    elif payload.code:
        product = _find_product_by_code(db, u.tenant_id, payload.code)

    if not product:
        raise HTTPException(404, "Producto no encontrado")

    # 📦 Stock
    if (product.stock or 0) < payload.quantity:
        raise HTTPException(409, f"Stock insuficiente. Disponible: {product.stock}")

    product.stock = (product.stock or 0) - payload.quantity

    # 💰 Caja abierta
    open_cash = (
        db.query(CashSession)
        .filter(
            CashSession.tenant_id == u.tenant_id,
            CashSession.status == CashStatus.OPEN,
        )
        .order_by(CashSession.opened_at.desc())
        .first()
    )

    if not open_cash:
        raise HTTPException(
            409,
            "No hay una caja abierta. Debes abrir la caja para registrar ventas.",
        )

    # 💵 Precio unitario (snapshot)
    unit_price = float(product.price or 0)

    # Si el front manda total, ok. Pero si querés protegerte:
    expected_total = unit_price * payload.quantity
    # (opcional) si querés forzar consistencia:
    # if abs(payload.total - expected_total) > 0.01:
    #     raise HTTPException(400, "Total inválido para el producto/cantidad.")

    # 🧾 Crear venta (GUARDANDO SNAPSHOT)
    sale = Sale(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        payment_method=pm,
        subtotal=float(payload.total),
        total=float(payload.total),
        discount=0.0,
        margin=0.0,
        items_count=int(payload.quantity),  # si lo usás como "unidades"
        cash_session_id=open_cash.id,
        created_at=datetime.utcnow(),
        # ✅ snapshot producto
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        product_barcode=product.barcode,
        quantity=int(payload.quantity),
        unit_price=unit_price,
    )

    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
