"""用量计量：记录并查询用户对各端点的调用次数（开放平台配额基础）。"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import UsageRecord, User


def record_usage(db: Session, owner: User, endpoint: str, amount: int = 1) -> None:
    """累加某用户对某端点的调用次数（upsert）。"""
    if owner is None:
        return
    row = (
        db.query(UsageRecord)
        .filter_by(owner_id=owner.id, endpoint=endpoint)
        .first()
    )
    if row is None:
        row = UsageRecord(owner_id=owner.id, endpoint=endpoint, count=amount)
        db.add(row)
    else:
        row.count += amount
    db.commit()


def get_usage(db: Session, owner: User) -> list[dict]:
    """返回某用户的用量明细（按端点聚合）。"""
    rows = db.query(UsageRecord).filter_by(owner_id=owner.id).all()
    return [
        {"endpoint": r.endpoint, "count": r.count, "updated_at": str(r.updated_at)}
        for r in rows
    ]


def total_usage(db: Session) -> list[dict]:
    """返回全局用量（按端点聚合，供管理员查看）。"""
    rows = (
        db.query(UsageRecord.endpoint, func.sum(UsageRecord.count).label("total"))
        .group_by(UsageRecord.endpoint)
        .all()
    )
    return [{"endpoint": ep, "count": int(total or 0)} for ep, total in rows]
