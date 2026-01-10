import bcrypt
from datetime import datetime, timedelta
from jose import jwt
from .settings import settings

def hash_password(p: str) -> str:
    # bcrypt truncates internally at 72 bytes; for MVP passwords like "123456" ok.
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(p.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(p: str, hashed: str) -> bool:
    return bcrypt.checkpw(p.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(subject: str, extra: dict | None = None, minutes: int | None = None) -> str:
    exp = datetime.utcnow() + timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": exp}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
