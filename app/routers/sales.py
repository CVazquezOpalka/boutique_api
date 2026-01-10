from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from ..db import get_db
from ..deps import require_tenant_user
from ..models import (
    Sale, SaleItem, Product, Variant,
    StockMovement, StockReason,
    PaymentMethod,
    CashSession, CashStatus
)
from ..schemas import SaleCreate, SaleOut

router = APIRouter(prefix="/sales", tags=["sales"])

@router.get("", response_model=list[SaleOut])
def list_sales(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    return (
        db.query(Sale)
        .options(joinedload(Sale.items))
        .filter(Sale.tenant_id == u.tenant_id)
        .order_by(Sale.created_at.desc())
        .all()
    )

@router.post("", response_model=SaleOut)
def create_sale(payload: SaleCreate, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    if not payload.items:
        raise HTTPException(400, "Items vacíos")

    open_cash = db.query(CashSession).filter(
        CashSession.tenant_id == u.tenant_id,
        CashSession.status == CashStatus.OPEN
    ).first()

    if payload.payment_method == PaymentMethod.EFECTIVO and not open_cash:
        raise HTTPException(409, "Debe abrir caja para cobrar en efectivo")

    # Validación + cálculos
    subtotal = 0.0
    margin = 0.0
    resolved = []  # (prod, var, qty)

    for it in payload.items:
        prod = db.get(Product, it.product_id)
        if not prod or prod.tenant_id != u.tenant_id:
            raise HTTPException(404, f"Producto {it.product_id} no encontrado")

        var = db.get(Variant, it.variant_id)
        if not var or var.tenant_id != u.tenant_id or var.product_id != prod.id:
            raise HTTPException(404, f"Variante {it.variant_id} no encontrada")

        if var.stock < it.qty:
            raise HTTPException(409, f"Stock insuficiente para SKU {var.sku}")

        subtotal += it.qty * prod.price
        margin += it.qty * (prod.price - prod.cost)
        resolved.append((prod, var, it.qty))

    discount = max(0.0, payload.discount)
    total = max(0.0, subtotal - discount)
    margin = margin - discount

    sale = Sale(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        payment_method=payload.payment_method,
        discount=discount,
        subtotal=subtotal,
        total=total,
        margin=margin,
        cash_session_id=open_cash.id if payload.payment_method == PaymentMethod.EFECTIVO else None
    )
    db.add(sale)
    db.flush()

    for prod, var, qty in resolved:
        # descontar stock
        var.stock -= qty

        db.add(SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            variant_id=var.id,
            name=prod.name,
            sku=var.sku,
            qty=qty,
            unit_price=prod.price,
            unit_cost=prod.cost,
        ))

        db.add(StockMovement(
            tenant_id=u.tenant_id,
            created_by_user_id=u.id,
            product_id=prod.id,
            variant_id=var.id,
            delta=-qty,
            reason=StockReason.VENTA,
        ))

    db.commit()
    return (
        db.query(Sale)
        .options(joinedload(Sale.items))
        .get(sale.id)
    )
