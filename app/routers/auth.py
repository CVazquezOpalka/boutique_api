from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from ..db import get_db
from ..models import User
from ..schemas import TokenOut, MeOut
from ..security import verify_password, create_access_token
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Swagger manda username/password -> lo usamos como email
    email = form.username
    password = form.password

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.active:
        raise HTTPException(401, "Credenciales inválidas")
    if not verify_password(password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")

    token = create_access_token(
        subject=str(user.id),
        extra={"role": user.role.value, "tenant_id": user.tenant_id},
    )
    return TokenOut(access_token=token)


@router.get("/me", response_model=MeOut)
def me(u=Depends(get_current_user)):
    return MeOut(
        id=u.id, tenant_id=u.tenant_id, role=u.role, name=u.name, email=u.email
    )


class LoginJSON(BaseModel):
    email: EmailStr
    password: str


@router.post("/login-json", response_model=TokenOut)
def login_json(payload: LoginJSON, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.active:
        raise HTTPException(401, "Credenciales inválidas")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")

    token = create_access_token(
        subject=str(user.id),
        extra={"role": user.role.value, "tenant_id": user.tenant_id},
    )
    return TokenOut(access_token=token)
