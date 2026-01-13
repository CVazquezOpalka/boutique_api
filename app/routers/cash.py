from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..db import get_db
from ..deps import require_tenant_user
from ..models import CashSession, CashStatus, Sale
from ..schemas import CashOpenIn, CashCloseIn, CashOut, CashOpenOut

router = APIRouter(prefix="/cash", tags=["cash"])


def _sales_breakdown_for_cash(db: Session, cash_id: int):
    rows = (
        db.query(Sale.payment_method, func.coalesce(func.sum(Sale.total), 0))
        .filter(Sale.cash_session_id == cash_id)
        .group_by(Sale.payment_method)
        .all()
    )
    by_pm = {(pm.value if pm else "EFECTIVO"): float(total or 0) for pm, total in rows}

    # ✅ agrupación simple para UI: efectivo / tarjeta / otros
    cash_amount = by_pm.get("EFECTIVO", 0.0)

    card_amount = by_pm.get("DEBITO", 0.0) + by_pm.get("CREDITO", 0.0)

    other_amount = by_pm.get("TRANSFERENCIA", 0.0) + by_pm.get("OTRO", 0.0)

    total_sales_amount = cash_amount + card_amount + other_amount

    return {
        "by_payment_method": by_pm,
        "cash_amount": cash_amount,
        "card_amount": card_amount,
        "other_amount": other_amount,
        "total_sales_amount": total_sales_amount,
    }


@router.get("/open", response_model=CashOpenOut | None)
def get_open_cash(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    c = (
        db.query(CashSession)
        .filter(
            CashSession.tenant_id == u.tenant_id, CashSession.status == CashStatus.OPEN
        )
        .order_by(CashSession.opened_at.desc())
        .first()
    )
    if not c:
        return None

    breakdown = _sales_breakdown_for_cash(db, c.id)
    withdrawal = float(getattr(c, "withdrawal_amount", 0) or 0)
    expected = (
        float(c.opening_amount or 0)
        + float(breakdown["total_sales_amount"] or 0)
        - withdrawal
    )

    return CashOpenOut(
        id=c.id,
        tenant_id=c.tenant_id,
        opened_by_user_id=c.opened_by_user_id,
        opened_at=c.opened_at,
        opening_amount=float(c.opening_amount or 0),
        status=c.status,
        cash_amount=breakdown["cash_amount"],
        card_amount=breakdown["card_amount"],
        other_amount=breakdown["other_amount"],
        total_sales_amount=breakdown["total_sales_amount"],
        withdrawal_amount=withdrawal,
        expected_amount=expected,
        by_payment_method=breakdown["by_payment_method"],
    )


@router.post("/open", response_model=CashOut)
def open_cash(
    payload: CashOpenIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)
):
    existing = (
        db.query(CashSession)
        .filter(
            CashSession.tenant_id == u.tenant_id, CashSession.status == CashStatus.OPEN
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "Ya hay una caja abierta")

    c = CashSession(
        tenant_id=u.tenant_id,
        opened_by_user_id=u.id,
        opening_amount=payload.opening_amount,
        status=CashStatus.OPEN,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.post("/{cash_id}/close", response_model=CashOut)
def close_cash(
    cash_id: int,
    payload: CashCloseIn,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    c = db.get(CashSession, cash_id)
    if not c or c.tenant_id != u.tenant_id:
        raise HTTPException(404, "Caja no encontrada")
    if c.status != CashStatus.OPEN:
        raise HTTPException(409, "Caja ya cerrada")

    # ✅ guardar retiro/egreso
    c.withdrawal_amount = float(payload.withdrawal_amount or 0)
    c.withdrawal_notes = payload.withdrawal_notes

    # ✅ calcular totales de ventas reales de esta caja
    breakdown = _sales_breakdown_for_cash(db, c.id)
    expected = (
        float(c.opening_amount or 0)
        + float(breakdown["total_sales_amount"] or 0)
        - float(c.withdrawal_amount or 0)
    )

    # ✅ cierre contado (si no viene, usamos expected)
    counted = (
        float(payload.counted_amount)
        if payload.counted_amount is not None
        else expected
    )

    c.status = CashStatus.CLOSED
    c.closed_at = datetime.utcnow()
    c.closed_by_user_id = u.id

    c.expected_amount = expected
    c.closing_amount = counted
    c.difference_amount = counted - expected

    db.commit()
    db.refresh(c)
    return c
