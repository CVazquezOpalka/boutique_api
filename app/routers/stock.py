from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_tenant_user
from ..models import Variant, StockMovement, StockReason
from ..schemas import StockAdjustIn, StockMovementOut

router = APIRouter(prefix="/stock", tags=["stock"])

@router.get("/movements", response_model=list[StockMovementOut])
def list_movements(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    return (
        db.query(StockMovement)
        .filter(StockMovement.tenant_id == u.tenant_id)
        .order_by(StockMovement.created_at.desc())
        .limit(200)
        .all()
    )

@router.post("/adjust", response_model=StockMovementOut)
def adjust_stock(payload: StockAdjustIn, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    var = db.get(Variant, payload.variant_id)
    if not var or var.tenant_id != u.tenant_id:
        raise HTTPException(404, "Variante no encontrada")

    if var.stock + payload.delta < 0:
        raise HTTPException(409, "No se puede dejar stock negativo")

    var.stock += payload.delta

    mov = StockMovement(
        tenant_id=u.tenant_id,
        created_by_user_id=u.id,
        product_id=payload.product_id,
        variant_id=payload.variant_id,
        delta=payload.delta,
        reason=StockReason.AJUSTE,
        note=payload.note,
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov

@router.get("/low")
def low_stock(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    # Variantes con stock <= min_stock
    variants = (
        db.query(Variant)
        .filter(Variant.tenant_id == u.tenant_id)
        .all()
    )
    low = [v for v in variants if v.stock <= v.min_stock]
    return [
        {
            "variant_id": v.id,
            "product_id": v.product_id,
            "sku": v.sku,
            "size": v.size,
            "color": v.color,
            "stock": v.stock,
            "min_stock": v.min_stock,
        }
        for v in low
    ]
