"""SQLAlchemy 引擎 / 会话 / 基类（仅用于用户与 API Key 存储）。"""

from __future__ import annotations

from collections.abc import Iterator
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL as _DEFAULT_DB_URL


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


_engine = None
_SessionLocal = None
_engine_url = None


def _db_url() -> str:
    return os.getenv("CAIPIAO_WEB_DB", _DEFAULT_DB_URL)


def _connect_args_for(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def _ensure_engine() -> None:
    """按当前 CAIPIAO_WEB_DB 惰性创建/重建引擎。

    测试环境中不同测试模块通过 _make_env() 设置各自的临时库，引擎需随
    环境变量变化而重建以实现数据库隔离；生产环境该变量稳定，引擎仅创建一次。
    """
    global _engine, _SessionLocal, _engine_url
    url = _db_url()
    if _engine is not None and _engine_url == url:
        return
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = create_engine(
        url,
        connect_args=_connect_args_for(url),
        future=True,
        pool_pre_ping=True,  # 连接前检查有效性，避免使用断开的连接
        pool_size=5,  # 连接池大小（SQLite 会忽略）
        max_overflow=10,  # 最大溢出连接数（SQLite 会忽略）
    )
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,  # 避免访问已提交对象时触发额外查询
    )
    _engine_url = url


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：提供一个数据库会话并在结束时关闭。"""
    _ensure_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表（幂等），并对已存在表做轻量迁移。"""
    _ensure_engine()
    # 导入模型以确保它们注册到 Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=_engine)
    # P5.E：为已存在的 users 表补充 role 列（create_all 不会为旧表新增列）
    _migrate_add_role_column()


def _migrate_add_role_column() -> None:
    inspector = inspect(_engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "role" not in cols:
        with _engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'")
            )
