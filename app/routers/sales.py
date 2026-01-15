from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_tenant_user
from ..models import (
    Sale,
    SaleItem,          # ✅ IMPORTANTE
    PaymentMethod,
    Product,
    CashSession,
    CashStatus,
)

router = APIRouter(prefix="/sales", tags=["sales"])


# ---------------- Schemas ----------------
class SaleItemIn(BaseModel):
    product_id: int
    quantity: int
    unit_price: Optional[float] = None


class SaleCreateIn(BaseModel):
    payment_method: Optional[str] = "EFECTIVO"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    # ✅ NUEVO: carrito
    items: Optional[List[SaleItemIn]] = None

    # ✅ LEGACY (fallback)
    product_id: Optional[int] = None
    code: Optional[str] = None
    quantity: Optional[int] = None

    # ✅ opcional: si el front lo manda, lo validamos vs lo calculado (soft)
    total: Optional[float] = None


class SaleOut(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total: float
    items_count: Optional[int] = None
    payment_method: Optional[str] = None
    created_at: datetime

    # snapshot rápido (para tabla)
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    product_barcode: Optional[str] = None
    product_sku: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None

    class Config:
        from_attributes = True


# ---------------- helpers ----------------
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
    pm = _parse_payment_method(payload.payment_method)

    # 💰 Caja abierta (obligatorio)
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

    # ✅ Resolver items: carrito o legacy
    items_in: List[SaleItemIn] = []
    if payload.items and len(payload.items) > 0:
        items_in = payload.items
    else:
        # legacy: product_id o code + quantity
        if (payload.product_id is None) and (not payload.code):
            raise HTTPException(400, "Debe enviar items[] o product_id/code (legacy).")
        if payload.quantity is None or payload.quantity <= 0:
            raise HTTPException(400, "quantity es requerido y debe ser > 0 (legacy).")

        # si viene por code, lo resolvemos a product_id
        if payload.product_id is None and payload.code:
            p = _find_product_by_code(db, u.tenant_id, payload.code)
            if not p:
                raise HTTPException(404, "Producto no encontrado")
            items_in = [SaleItemIn(product_id=p.id, quantity=int(payload.quantity))]
        else:
            items_in = [SaleItemIn(product_id=int(payload.product_id), quantity=int(payload.quantity))]

    # Validaciones básicas
    if not items_in:
        raise HTTPException(400, "items vacío.")
    for it in items_in:
        if it.quantity is None or it.quantity <= 0:
            raise HTTPException(400, "Cada item.quantity debe ser > 0")

    # 🔍 Precargar productos y validar
    product_ids = list({it.product_id for it in items_in})
    products = (
        db.query(Product)
        .filter(
            Product.tenant_id == u.tenant_id,
            Product.id.in_(product_ids),
            Product.active == True,
        )
        .all()
    )
    prod_by_id = {p.id: p for p in products}

    # chequeo: todos existen
    missing = [pid for pid in product_ids if pid not in prod_by_id]
    if missing:
        raise HTTPException(404, f"Productos no encontrados o inactivos: {missing}")

    # 📦 Stock + cálculo total
    subtotal = 0.0
    items_count = 0

    # Creamos la venta primero (sin totals) para asociar items
    sale = Sale(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        payment_method=pm,
        discount=0.0,
        margin=0.0,
        cash_session_id=open_cash.id,
        created_at=datetime.utcnow(),
        subtotal=0.0,
        total=0.0,
        items_count=0,
    )

    # Snapshot rápido: primer item
    first_product: Optional[Product] = None
    first_unit_price: Optional[float] = None

    for idx, it in enumerate(items_in):
        p = prod_by_id[it.product_id]

        unit_price = float(it.unit_price) if it.unit_price is not None else float(p.price or 0)
        line_total = unit_price * int(it.quantity)

        # stock
        current_stock = int(p.stock or 0)
        if current_stock < int(it.quantity):
            raise HTTPException(
                409,
                f"Stock insuficiente para '{p.name}'. Disponible: {current_stock}",
            )

        # descuenta stock
        p.stock = current_stock - int(it.quantity)

        # acumula totales
        subtotal += line_total
        items_count += int(it.quantity)

        # snapshot del primer item
        if idx == 0:
            first_product = p
            first_unit_price = unit_price

        # crea item
        sale_item = SaleItem(
            tenant_id=u.tenant_id,
            sale=sale,
            product_id=p.id,
            quantity=int(it.quantity),
            unit_price=unit_price,
            # si tu SaleItem tiene snapshot extra, podés guardarlo acá:
            # product_name=p.name,
            # product_sku=p.sku,
            # product_barcode=p.barcode,
            # line_total=line_total,
        )
        sale.items.append(sale_item)

    # totals en Sale
    sale.subtotal = float(subtotal)
    sale.total = float(subtotal)  # si más adelante metés descuento/impuestos, ajustás acá
    sale.items_count = int(items_count)

    # snapshot rápido para la tabla (1er producto + cantidad total)
    if first_product:
        sale.product_id = first_product.id
        sale.product_name = first_product.name
        sale.product_sku = first_product.sku
        sale.product_barcode = first_product.barcode
        sale.quantity = int(items_count)          # ✅ total unidades vendidas en la operación
        sale.unit_price = float(first_unit_price or 0)

    # (opcional) validar total del front si lo mandan
    if payload.total is not None:
        if abs(float(payload.total) - float(sale.total)) > 0.01:
            raise HTTPException(
                400,
                f"Total inválido. Calculado={sale.total} recibido={payload.total}",
            )

    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
