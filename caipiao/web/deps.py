"""FastAPI 依赖：当前用户（JWT 或 API Key）。"""

from __future__ import annotations

import datetime

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiKey, User
from .security import decode_access_token, hash_api_key

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未认证",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """仅支持 JWT 的当前用户依赖。"""
    if not token:
        raise _CREDENTIALS_EXC
    subject = decode_access_token(token)
    if subject is None:
        raise _CREDENTIALS_EXC
    user = db.get(User, subject)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


def get_current_principal(
    token: str | None = Depends(_oauth2_scheme),
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> User:
    """支持 JWT 或 API Key 的当前用户依赖（用于开放接口，如 /generate）。"""
    if token:
        subject = decode_access_token(token)
        if subject is not None:
            user = db.get(User, subject)
            if user is not None:
                return user
    if api_key:
        key = db.query(ApiKey).filter_by(key_hash=hash_api_key(api_key)).first()
        if key is not None:
            key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return key.owner
    raise _CREDENTIALS_EXC


_FORBIDDEN_EXC = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="需要管理员权限",
)


def require_admin(current: User = Depends(get_current_user)) -> User:
    """仅管理员可访问的依赖（P5.E 权限分级）。"""
    if not current.is_admin:
        raise _FORBIDDEN_EXC
    return current
