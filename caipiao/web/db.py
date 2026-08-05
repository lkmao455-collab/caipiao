"""SQLAlchemy 引擎 / 会话 / 基类（仅用于用户与 API Key 存储）。"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：提供一个数据库会话并在结束时关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表（幂等）。"""
    # 导入模型以确保它们注册到 Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
