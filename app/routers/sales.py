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

    # ✅ nuevo formato (lovable)
    items: Optional[List[SaleItemIn]] = None

    # ✅ formato legacy (por si algún lado lo usa)
    product_id: Optional[int] = None
    code: Optional[str] = None
    quantity: Optional[int] = None


class SaleCreateIn(BaseModel):
    payment_method: Optional[str] = "EFECTIVO"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    # producto
    product_id: Optional[int] = None
    code: Optional[str] = None  # barcode o sku
    quantity: int  # requerido

    # opcional: si querés permitir override manual (pero mejor no)
    total: Optional[float] = None


class SaleOut(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total: float
    items_count: Optional[int] = None
    payment_method: Optional[str] = None
    created_at: datetime

    # ✅ para la columna "Producto"
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
    payload: SaleCreateIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)
):
    if payload.total is None or float(payload.total) <= 0:
        raise HTTPException(400, "El total debe ser mayor a 0.")

    # ✅ exigir caja abierta
    open_cash = (
        db.query(CashSession)
        .filter(
            CashSession.tenant_id == u.tenant_id, CashSession.status == CashStatus.OPEN
        )
        .order_by(CashSession.opened_at.desc())
        .first()
    )
    if not open_cash:
        raise HTTPException(
            409, "No hay una caja abierta. Abrí caja para registrar ventas."
        )

    pm = _parse_payment_method(payload.payment_method)

    item_product_id = None
    item_qty = None
    item_unit_price = None

    if payload.items and len(payload.items) > 0:
        it = payload.items[0]
        item_product_id = it.product_id
        item_qty = it.quantity
        item_unit_price = it.unit_price
    else:
        item_product_id = payload.product_id
        item_qty = payload.quantity

    if not item_qty or int(item_qty) <= 0:
        raise HTTPException(400, "quantity es requerido y debe ser > 0.")

    # ✅ encontrar producto (por id o code)
    p = None
    if item_product_id is not None:
        p = (
            db.query(Product)
            .filter(Product.tenant_id == u.tenant_id, Product.id == item_product_id)
            .first()
        )
    elif payload.code:
        p = _find_product_by_code(db, u.tenant_id, payload.code)

    if not p:
        raise HTTPException(404, "Producto no encontrado.")

    # ✅ precio unitario: si no lo manda FE, usamos Product.price
    unit_price = (
        float(item_unit_price) if item_unit_price is not None else float(p.price or 0)
    )

    # ✅ stock
    qty = int(item_qty)
    if (p.stock or 0) < qty:
        raise HTTPException(400, "Stock insuficiente para ese producto.")
    p.stock = int(p.stock or 0) - qty

    # ✅ snapshot producto en la venta (para tabla y reportes)
    sale = Sale(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        created_at=datetime.utcnow(),
        payment_method=pm,
        total=float(payload.total),
        subtotal=float(payload.total),
        discount=0.0,
        margin=0.0,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        items_count=1,
        cash_session_id=open_cash.id,
        # ⬇️ estas columnas deben existir (migración)
        product_id=p.id,
        product_name=p.name,
        product_barcode=p.barcode,
        product_sku=p.sku,
        quantity=qty,
        unit_price=unit_price,
    )

    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
