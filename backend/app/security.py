import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
import bcrypt
from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(sub: str, extra: dict | None = None, minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": sub, "exp": expire, **(extra or {})}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(email: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Transcribe Hub")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def random_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_payload(payload: str) -> str:
    return hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
