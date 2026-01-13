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
class SaleCreateIn(BaseModel):
    total: float
    payment_method: Optional[str] = "EFECTIVO"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    # ✅ MVP: vincular producto vendido
    product_id: Optional[int] = None

    # ✅ nuevo: código escaneado (barcode o sku)
    code: Optional[str] = None

    quantity: Optional[int] = None


class SaleOut(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total: float
    items_count: Optional[int] = None
    payment_method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True  # pydantic v2


# -------- helpers --------


def _find_product_by_code(db: Session, tenant_id: int, code: str) -> Product | None:
    c = code.strip()
    if not c:
        return None

    return (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id)
        .filter((Product.barcode == c) | (Product.sku == c))
        .first()
    )


def _parse_payment_method(value: Optional[str]) -> PaymentMethod:
    """
    Convierte string -> Enum PaymentMethod.
    Acepta:
      - "EFECTIVO"
      - "efectivo"
      - si llega None => EFECTIVO
    """
    if not value:
        return PaymentMethod.EFECTIVO

    v = value.strip().upper()
    try:
        return PaymentMethod(v)
    except Exception:
        allowed = [pm.value for pm in PaymentMethod]
        raise HTTPException(
            status_code=400,
            detail=f"payment_method inválido. Permitidos: {allowed}",
        )


# -------- Endpoints --------


@router.get("", response_model=List[SaleOut])
def list_sales(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    rows = (
        db.query(Sale)
        .filter(Sale.tenant_id == u.tenant_id)
        .order_by(Sale.created_at.desc())
        .all()
    )
    return rows


@router.post("", response_model=SaleOut)
def create_sale(
    payload: SaleCreateIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)
):
    if payload.total <= 0:
        raise HTTPException(status_code=400, detail="El total debe ser mayor a 0.")

    pm = _parse_payment_method(payload.payment_method)

    if payload.quantity is None or payload.quantity <= 0:
        raise HTTPException(
            status_code=400, detail="quantity es requerido y debe ser > 0."
        )

    # ✅ Resolver producto: por id o por code (barcode/sku)
    p = None
    if payload.product_id is not None:
        p = (
            db.query(Product)
            .filter(Product.tenant_id == u.tenant_id, Product.id == payload.product_id)
            .first()
        )
    elif payload.code:
        p = _find_product_by_code(db, u.tenant_id, payload.code)

    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    # ✅ Stock
    current_stock = p.stock or 0
    if current_stock < payload.quantity:
        raise HTTPException(
            status_code=400, detail="Stock insuficiente para ese producto."
        )
    p.stock = current_stock - payload.quantity

    # ✅ Caja abierta (última OPEN)
    open_cash = (
        db.query(CashSession)
        .filter(
            CashSession.tenant_id == u.tenant_id, CashSession.status == CashStatus.OPEN
        )
        .order_by(CashSession.opened_at.desc())
        .first()
    )

    # (opcional recomendado) exigir caja abierta
    # if not open_cash:
    #     raise HTTPException(409, "No hay una caja abierta. Abrí caja para registrar ventas.")

    sale = Sale(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        payment_method=pm,
        total=float(payload.total),
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        created_at=datetime.utcnow(),
        discount=0.0,
        subtotal=float(payload.total),
        margin=0.0,
        items_count=1,  # MVP: 1 línea
        cash_session_id=open_cash.id if open_cash else None,
    )

    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
