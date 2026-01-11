import bcrypt
import hashlib
import uuid
from datetime import datetime, timedelta
from jose import jwt
from .settings import settings

def hash_password(p: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(p.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(p: str, hashed: str) -> bool:
    return bcrypt.checkpw(p.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(subject: str, extra: dict | None = None, minutes: int | None = None) -> str:
    exp = datetime.utcnow() + timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": exp, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

# ✅ NUEVO: hashear refresh tokens antes de guardarlos
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

# ✅ NUEVO: crear refresh token JWT (con jti y exp)
def create_refresh_token(
    subject: str,
    extra: dict | None = None,
    days: int | None = None,
) -> tuple[str, str, datetime]:
    # Si no tenés REFRESH_TOKEN_EXPIRE_DAYS en settings, usamos 30 por defecto
    expire_days = days or getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 30)

    exp_dt = datetime.utcnow() + timedelta(days=expire_days)
    jti = str(uuid.uuid4())

    payload = {
        "sub": subject,
        "exp": exp_dt,
        "jti": jti,
        "type": "refresh",
    }
    if extra:
        payload.update(extra)

    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token, jti, exp_dt

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
