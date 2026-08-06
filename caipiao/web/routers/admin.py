"""管理后台路由（P5.E）：用户管理、角色分级、概览统计。

所有接口要求管理员权限（``require_admin`` 依赖）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import require_admin
from ..models import ApiKey, UsageRecord, User
from ..ratelimit import default_limit, limiter
from ..schemas import AdminStats, RoleUpdate, UserAdminOut

router = APIRouter(prefix="/admin", tags=["admin"])

_FORBIDDEN_SELF = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="不能对自身执行该操作"
)


@router.get("/stats", response_model=AdminStats)
@limiter.limit(default_limit)
def stats(request: Request, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminStats:
    """管理后台概览：用户数、管理员数、API Key 数、累计调用量。"""
    user_count = db.query(func.count(User.id)).scalar() or 0
    admin_count = db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0
    api_key_count = db.query(func.count(ApiKey.id)).scalar() or 0
    total_usage = db.query(func.coalesce(func.sum(UsageRecord.count), 0)).scalar() or 0
    return AdminStats(
        user_count=user_count,
        admin_count=admin_count,
        api_key_count=api_key_count,
        total_usage=int(total_usage),
    )


@router.get("/users", response_model=list[UserAdminOut])
@limiter.limit(default_limit)
def list_users(
    request: Request, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[User]:
    """列出全部用户（按创建时间升序）。"""
    return db.query(User).order_by(User.created_at.asc()).all()


@router.patch("/users/{user_id}/role", response_model=UserAdminOut)
@limiter.limit(default_limit)
def set_role(
    request: Request,
    user_id: str,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """修改指定用户的角色（admin / user）。"""
    if user_id == admin.id:
        raise _FORBIDDEN_SELF
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(default_limit)
def delete_user(
    request: Request,
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """删除用户（级联删除其 API Key）。不能删除自身。"""
    if user_id == admin.id:
        raise _FORBIDDEN_SELF
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    db.delete(user)
    db.commit()
