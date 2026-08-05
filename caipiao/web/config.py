"""Web 后端配置（来自环境变量，提供安全默认值）。"""

from __future__ import annotations

import os
from pathlib import Path


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value is not None else default


# JWT
SECRET_KEY = _env("CAIPIAO_WEB_SECRET", "dev-only-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(_env("CAIPIAO_WEB_TOKEN_TTL", "1440"))

# 数据库（用户 / API Key）
DATABASE_URL = _env("CAIPIAO_WEB_DB", "sqlite:///./web_app.db")

# 业务数据根目录（复用桌面端 .caipiao 下的开奖数据，按用户命名空间隔离私有数据）
DATA_ROOT = Path(_env("CAIPIAO_WEB_DATA", ".caipiao")).resolve()

# CORS：逗号分隔的来源列表；"*" 表示全部
_CORS_RAW = _env("CAIPIAO_WEB_CORS", "*")
CORS_ORIGINS = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]


def user_data_dir(user_id: str) -> Path:
    """返回某用户的私有数据目录（参数组等），不改动全局存储。"""
    path = DATA_ROOT / "users" / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path
