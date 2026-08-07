"""安全工具：密码哈希、JWT 签发/校验、API Key 生成。"""

from __future__ import annotations

import datetime
import hashlib
import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_password(password: str) -> bytes:
    """bcrypt 限制密码长度 <= 72 字节，超长（如中文口令）先做一次 SHA-256。"""
    data = password.encode("utf-8")
    if len(data) > 72:
        data = hashlib.sha256(data).digest()
    return data


def hash_password(password: str) -> str:
    """对明文密码做 bcrypt 哈希（自动处理超长/多字节口令）。"""
    return _pwd_context.hash(_normalize_password(password))


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与哈希（与 hash_password 同样的归一化）。"""
    try:
        return _pwd_context.verify(_normalize_password(password), hashed)
    except ValueError:
        return False


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与哈希。"""
    return _pwd_context.verify(password, hashed)


def create_access_token(subject: str, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    """为某个用户签发 JWT。"""
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=expires_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """解码 JWT，成功返回 subject（用户 id），失败返回 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")


def generate_api_key() -> tuple[str, str]:
    """生成 API Key，返回 (原始 key, 哈希)。原始 key 仅创建时展示一次。"""
    raw = "cpk_" + secrets.token_urlsafe(32)
    return raw, _hash_key(raw)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_api_key(raw: str) -> str:
    """对传入的 API Key 原始值求哈希，用于查找。"""
    return _hash_key(raw)
