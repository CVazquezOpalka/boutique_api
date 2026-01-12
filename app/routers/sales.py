from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_tenant_user
from ..models import Sale, Variant  # ajustá imports si tus modelos cambian
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/sales", tags=["sales"])


# -------- Schemas (MVP) --------
class SaleCreateIn(BaseModel):
    # MVP: venta simple (sin items detallados aún)
    total: float
    payment_method: Optional[str] = "EFECTIVO"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    # ✅ opcional para descontar stock en una sola línea
    # si la UI todavía no manda items, lo dejamos opcional
    variant_id: Optional[int] = None
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
def create_sale(payload: SaleCreateIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    if payload.total <= 0:
        raise HTTPException(status_code=400, detail="El total debe ser mayor a 0.")

    # ✅ 1) (Opcional) descontar stock si viene variant_id + quantity
    if payload.variant_id is not None or payload.quantity is not None:
        if not payload.variant_id or not payload.quantity:
            raise HTTPException(status_code=400, detail="variant_id y quantity deben venir juntos.")
        if payload.quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity debe ser > 0.")

        v = (
            db.query(Variant)
            .filter(Variant.tenant_id == u.tenant_id, Variant.id == payload.variant_id)
            .first()
        )
        if not v:
            raise HTTPException(status_code=404, detail="Variante no encontrada.")
        if (v.stock or 0) < payload.quantity:
            raise HTTPException(status_code=400, detail="Stock insuficiente para esa variante.")

        v.stock = (v.stock or 0) - payload.quantity

    # ✅ 2) crear venta
    sale = Sale(
        tenant_id=u.tenant_id,
        total=payload.total,
        payment_method=payload.payment_method,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        created_at=datetime.utcnow(),
    )

    # si tu modelo tiene items_count y querés setearlo:
    # sale.items_count = 1 if payload.variant_id else 0

    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
