from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_tenant_user
from ..models import Sale, Variant, Product
from ..schemas import DashboardOut, SaleOut

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    tenant_id = u.tenant_id

    # ---- Ventas hoy / mes (basado en created_at)
    today = date.today()
    start_today = datetime.combine(today, datetime.min.time())
    start_month = datetime.combine(today.replace(day=1), datetime.min.time())

    sales_today = (
        db.query(Sale)
        .filter(Sale.tenant_id == tenant_id)
        .filter(Sale.created_at >= start_today)
        .all()
    )
    total_sales_today = float(sum((s.total or 0) for s in sales_today))

    sales_month = (
        db.query(Sale)
        .filter(Sale.tenant_id == tenant_id)
        .filter(Sale.created_at >= start_month)
        .all()
    )
    total_sales_month = float(sum((s.total or 0) for s in sales_month))

    # ---- Productos (si tu Product tiene active, filtramos por active=True)
    total_products = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id)
        .filter(Product.active == True)  # noqa: E712
        .count()
    )

    # ---- Clientes (todavía no está el modelo/endpoint -> 0 por ahora)
    total_customers = 0

    # ---- Stock bajo: por Variant (como ya lo tenías)
    variants = db.query(Variant).filter(Variant.tenant_id == tenant_id).all()
    low_stock_count = sum(1 for v in variants if (v.stock or 0) <= (v.min_stock or 0))

    # ---- Ventas recientes (últimas 5)
    recent_rows = (
        db.query(Sale)
        .filter(Sale.tenant_id == tenant_id)
        .order_by(Sale.created_at.desc())
        .limit(5)
        .all()
    )

    recent_sales = [
        SaleOut(
            id=s.id,
            customer_id=getattr(s, "customer_id", None),
            customer_name=getattr(s, "customer_name", None),
            total=float(getattr(s, "total", 0) or 0),
            items_count=getattr(s, "items_count", None),
            payment_method=getattr(s, "payment_method", None),
            created_at=s.created_at,
        )
        for s in recent_rows
    ]

    return DashboardOut(
        total_sales_today=total_sales_today,
        total_sales_month=total_sales_month,
        total_products=total_products,
        total_customers=total_customers,
        low_stock_count=low_stock_count,
        recent_sales=recent_sales,
    )


@router.get("/sales")
def sales_report(
    period: str = Query("year", pattern="^(day|month|six_months|year)$"),
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    tenant_id = u.tenant_id
    today = date.today()

    # rangos
    if period == "day":
        start = datetime.combine(today, datetime.min.time())
    elif period == "month":
        start = datetime.combine(today.replace(day=1), datetime.min.time())
    elif period == "six_months":
        start = datetime.utcnow() - timedelta(days=183)
    else:  # year
        start = datetime.combine(today.replace(month=1, day=1), datetime.min.time())

    rows = (
        db.query(Sale)
        .filter(Sale.tenant_id == tenant_id)
        .filter(Sale.created_at >= start)
        .order_by(Sale.created_at.desc())
        .all()
    )

    total_sales = len(rows)
    total_amount = float(sum((s.total or 0) for s in rows))
    avg_ticket = float((total_amount / total_sales) if total_sales else 0)

    by_method: dict[str, float] = {}
    for s in rows:
        pm = s.payment_method.value if s.payment_method else "EFECTIVO"
        by_method[pm] = float(by_method.get(pm, 0) + (s.total or 0))

    return {
        "period": period,
        "from": start.isoformat(),
        "total_sales": total_sales,
        "total_amount": total_amount,
        "avg_ticket": avg_ticket,
        "by_payment_method": by_method,
        "sales": [
            {
                "id": s.id,
                "customer_name": getattr(s, "customer_name", None),
                "total": float(s.total or 0),
                # ✅ FIX: no str(enum), usar enum.value
                "payment_method": s.payment_method.value if s.payment_method else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in rows
        ],
    }
