# app/routers/customers.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from ..db import get_db
from ..deps import require_tenant_user
from ..models import Customer
from ..schemas import CustomerCreateIn, CustomerUpdateIn, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


def _norm(s: str) -> str:
    return (s or "").strip()

def _norm_doc(s: str) -> str:
    # normaliza documento para comparar (quita espacios y guiones)
    return _norm(s).replace("-", "").replace(" ", "")

def _looks_like_doc(s: str) -> bool:
    t = _norm_doc(s)
    return t.isdigit() and len(t) >= 6  # DNI típico, ajustable


@router.get("", response_model=List[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(Customer).filter(Customer.tenant_id == u.tenant_id)

    if search:
        s = f"%{_norm(search)}%"
        q = q.filter(
            or_(
                Customer.name.ilike(s),
                Customer.email.ilike(s),
                Customer.phone.ilike(s),
                Customer.document.ilike(s),
            )
        )

    return q.order_by(Customer.created_at.desc()).limit(limit).all()


@router.get("/search", response_model=List[CustomerOut])
def search_customers(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
    limit: int = Query(20, ge=1, le=50),
):
    term_raw = _norm(q)
    term_doc = _norm_doc(q)
    like = f"%{term_raw}%"

    base = (
        db.query(Customer)
        .filter(Customer.tenant_id == u.tenant_id, Customer.active == True)
    )

    # 1) si parece documento: exact match primero (top 1)
    if _looks_like_doc(q):
        exact = (
            base.filter(func.replace(func.replace(Customer.document, "-", ""), " ", "") == term_doc)
            .order_by(Customer.created_at.desc())
            .limit(1)
            .all()
        )
        if exact:
            return exact

    # 2) fallback general (incluye document parcial)
    starts = f"{term_raw}%"
    rows = (
        base.filter(
            or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.phone.ilike(like),
                Customer.document.ilike(like),
            )
        )
        .order_by(
            func.case((Customer.document.ilike(starts), 0), else_=1),
            func.case((Customer.name.ilike(starts), 0), else_=1),
            Customer.created_at.desc(),
        )
        .limit(limit)
        .all()
    )
    return rows


@router.post("", response_model=CustomerOut)
def create_customer(
    payload: CustomerCreateIn,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    name = _norm(payload.name)
    if not name:
        raise HTTPException(400, "name es requerido")

    doc = _norm(payload.document) if payload.document else None

    # ✅ si viene documento, opcionalmente validamos "no duplicado" por tenant
    if doc:
        exists = (
            db.query(Customer.id)
            .filter(Customer.tenant_id == u.tenant_id, Customer.document == doc)
            .first()
        )
        if exists:
            raise HTTPException(409, "Ya existe un cliente con ese documento")

    now = datetime.utcnow()
    c = Customer(
        tenant_id=u.tenant_id,
        name=name,
        document=doc,
        email=(payload.email or None),
        phone=(payload.phone or None),
        address=(payload.address or None),
        notes=(payload.notes or None),
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), u=Depends(require_tenant_user)):
    c = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.tenant_id == u.tenant_id)
        .first()
    )
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdateIn,
    db: Session = Depends(get_db),
    u=Depends(require_tenant_user),
):
    c = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.tenant_id == u.tenant_id)
        .first()
    )
    if not c:
        raise HTTPException(404, "Cliente no encontrado")

    if payload.name is not None:
        name = _norm(payload.name)
        if not name:
            raise HTTPException(400, "name no puede ser vacío")
        c.name = name

    if payload.document is not None:
        doc = _norm(payload.document) if payload.document else None
        if doc:
            # evitar duplicado si cambia documento
            exists = (
                db.query(Customer.id)
                .filter(Customer.tenant_id == u.tenant_id, Customer.document == doc, Customer.id != c.id)
                .first()
            )
            if exists:
                raise HTTPException(409, "Ya existe un cliente con ese documento")
        c.document = doc

    if payload.email is not None:
        c.email = payload.email or None
    if payload.phone is not None:
        c.phone = payload.phone or None
    if payload.address is not None:
        c.address = payload.address or None
    if payload.notes is not None:
        c.notes = payload.notes or None
    if payload.active is not None:
        c.active = bool(payload.active)

    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return c
