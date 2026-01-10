from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose.exceptions import JWTError

from .db import get_db
from .models import User, Role
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(401, "Token inválido")
        user = db.get(User, int(sub))
        if not user or not user.active:
            raise HTTPException(401, "Usuario inválido")
        return user
    except JWTError:
        raise HTTPException(401, "Token inválido")

def require_roles(*roles: Role):
    def _inner(u: User = Depends(get_current_user)) -> User:
        if u.role not in roles:
            raise HTTPException(403, "No autorizado")
        return u
    return _inner

def require_tenant_user(u: User = Depends(get_current_user)) -> User:
    if u.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "No autorizado para tenant")
    if not u.tenant_id:
        raise HTTPException(400, "Usuario sin tenant")
    return u
