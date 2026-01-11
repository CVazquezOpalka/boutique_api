from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from .auth import refresh, logout, RefreshIn, LogoutIn  # importando handlers

router = APIRouter(prefix="/api/auth", tags=["auth-compat"])

@router.post("/refresh", include_in_schema=False)
def refresh_compat(payload: RefreshIn, db: Session = Depends(get_db)):
    return refresh(payload, db)

@router.post("/logout", include_in_schema=False)
def logout_compat(payload: LogoutIn, db: Session = Depends(get_db)):
    return logout(payload, db)
