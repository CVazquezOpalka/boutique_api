from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_tenant_user
from ..models import Sale, Variant
from ..schemas import DashboardOut

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    sales = db.query(Sale).filter(Sale.tenant_id == u.tenant_id).all()
    sales_total = sum(s.total for s in sales)
    margin_total = sum(s.margin for s in sales)
    sales_count = len(sales)

    variants = db.query(Variant).filter(Variant.tenant_id == u.tenant_id).all()
    low_stock_count = sum(1 for v in variants if v.stock <= v.min_stock)

    return DashboardOut(
        sales_total=sales_total,
        sales_count=sales_count,
        margin_total=margin_total,
        low_stock_count=low_stock_count
    )
