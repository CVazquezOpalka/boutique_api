from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_tenant_user
from ..models import CashSession, CashStatus
from ..schemas import CashOpenIn, CashCloseIn, CashOut

router = APIRouter(prefix="/cash", tags=["cash"])

@router.get("/open", response_model=CashOut | None)
def get_open_cash(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    return db.query(CashSession).filter(
        CashSession.tenant_id == u.tenant_id,
        CashSession.status == CashStatus.OPEN
    ).first()

@router.post("/open", response_model=CashOut)
def open_cash(payload: CashOpenIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    existing = db.query(CashSession).filter(
        CashSession.tenant_id == u.tenant_id,
        CashSession.status == CashStatus.OPEN
    ).first()
    if existing:
        raise HTTPException(409, "Ya hay una caja abierta")

    c = CashSession(
        tenant_id=u.tenant_id,
        opened_by_user_id=u.id,
        opening_amount=payload.opening_amount,
        status=CashStatus.OPEN,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c

@router.post("/{cash_id}/close", response_model=CashOut)
def close_cash(cash_id: int, payload: CashCloseIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    c = db.get(CashSession, cash_id)
    if not c or c.tenant_id != u.tenant_id:
        raise HTTPException(404, "Caja no encontrada")
    if c.status != CashStatus.OPEN:
        raise HTTPException(409, "Caja ya cerrada")

    c.status = CashStatus.CLOSED
    c.closed_at = datetime.utcnow()
    c.closing_amount = payload.closing_amount
    db.commit(); db.refresh(c)
    return c
