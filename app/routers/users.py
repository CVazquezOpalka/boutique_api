from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_roles
from ..models import User, Role
from ..schemas import EmployeeCreate, UserOut
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/employees", response_model=list[UserOut])
def list_employees(db: Session = Depends(get_db), admin=Depends(require_roles(Role.ADMIN))):
    return (
        db.query(User)
        .filter(User.tenant_id == admin.tenant_id)
        .order_by(User.created_at.desc())
        .all()
    )

@router.post("/employees", response_model=UserOut)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db), admin=Depends(require_roles(Role.ADMIN))):
    if payload.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise HTTPException(400, "Rol inválido para tenant")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email ya existe")

    u = User(
        tenant_id=admin.tenant_id,
        role=payload.role,
        name=payload.name.strip(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u
