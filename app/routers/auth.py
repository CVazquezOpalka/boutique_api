from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime

from ..db import get_db
from ..models import User, RefreshToken
from ..schemas import TokenOut, MeOut
from ..security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


# -------------------------
# FORM LOGIN (swagger)
# -------------------------
@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username
    password = form.password

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.active:
        raise HTTPException(401, "Credenciales inválidas")
    if not verify_password(password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")

    extra = {"role": user.role.value, "tenant_id": user.tenant_id}

    access = create_access_token(subject=str(user.id), extra=extra)
    refresh, jti, exp_dt = create_refresh_token(subject=str(user.id), extra=extra)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            jti=jti,
            expires_at=exp_dt,
            revoked=False,
        )
    )
    db.commit()

    return TokenOut(access_token=access, refresh_token=refresh, token_type="bearer")


@router.get("/me", response_model=MeOut)
def me(u=Depends(get_current_user)):
    # ✅ si tu MeOut espera role string, usar u.role.value
    return MeOut(
        id=u.id, tenant_id=u.tenant_id, role=u.role, name=u.name, email=u.email
    )


# -------------------------
# JSON LOGIN (front)
# -------------------------
class LoginJSON(BaseModel):
    # si después vas a forzar tenant_slug acá, lo agregamos
    email: EmailStr
    password: str


@router.post("/login-json", response_model=TokenOut)
def login_json(payload: LoginJSON, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.active:
        raise HTTPException(401, "Credenciales inválidas")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")

    extra = {"role": user.role.value, "tenant_id": user.tenant_id}

    access = create_access_token(subject=str(user.id), extra=extra)
    refresh, jti, exp_dt = create_refresh_token(subject=str(user.id), extra=extra)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            jti=jti,
            expires_at=exp_dt,
            revoked=False,
        )
    )
    db.commit()

    return TokenOut(access_token=access, refresh_token=refresh, token_type="bearer")


# -------------------------
# REFRESH
# -------------------------
class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    token = payload.refresh_token

    # 1) decode + validar tipo
    try:
        claims = decode_token(token)
    except Exception:
        raise HTTPException(401, "Refresh token inválido")

    if claims.get("type") != "refresh":
        raise HTTPException(401, "Refresh token inválido")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(401, "Refresh token inválido")

    token_h = hash_token(token)

    # 2) validar en DB
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_h).first()
    if not rt or rt.revoked:
        raise HTTPException(401, "Refresh token inválido")

    if rt.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Refresh token expirado")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.active:
        raise HTTPException(401, "Usuario inválido")

    # 3) rotación: revocar el actual
    rt.revoked = True
    rt.revoked_at = datetime.utcnow()

    extra = {"role": user.role.value, "tenant_id": user.tenant_id}
    new_access = create_access_token(subject=str(user.id), extra=extra)
    new_refresh, new_jti, new_exp_dt = create_refresh_token(subject=str(user.id), extra=extra)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(new_refresh),
            jti=new_jti,
            expires_at=new_exp_dt,
            revoked=False,
        )
    )
    db.commit()

    return TokenOut(access_token=new_access, refresh_token=new_refresh, token_type="bearer")


# -------------------------
# LOGOUT (revoca refresh)
# -------------------------
class LogoutIn(BaseModel):
    refresh_token: str


@router.post("/logout")
def logout(payload: LogoutIn, db: Session = Depends(get_db)):
    token_h = hash_token(payload.refresh_token)
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_h).first()
    if rt and not rt.revoked:
        rt.revoked = True
        rt.revoked_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


# -------------------------
# BACKWARD COMPAT (FRONT LOABLE)
# /api/auth/* -> alias de /auth/*
# -------------------------

@router.post("/../api/auth/refresh", include_in_schema=False)
def refresh_compat(payload: RefreshIn, db: Session = Depends(get_db)):
    # Reusa la misma lógica del refresh real
    return refresh(payload, db)

@router.post("/../api/auth/logout", include_in_schema=False)
def logout_compat(payload: LogoutIn, db: Session = Depends(get_db)):
    return logout(payload, db)