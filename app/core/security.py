from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.utils import now
from app.db.models import User
from app.db.session import get_db

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: str) -> str:
    settings = get_settings()
    issued = now()
    claims = {
        "sub": user_id,
        "iat": issued,
        "exp": issued + timedelta(days=settings.jwt_expires_days),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def _unauthorized() -> ApiError:
    return ApiError("unauthorized", "Please log in again.")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        raise _unauthorized()
    user = db.get(User, claims.get("sub"))
    if user is None:
        raise _unauthorized()
    return user
