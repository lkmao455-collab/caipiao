"""审计日志路由：查询操作日志和统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal
from ..ratelimit import limiter
from ..security_audit import audit_logger

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogOut(BaseModel):
    timestamp: str
    user_id: str
    action: str
    resource: str
    details: dict = {}
    ip_address: str
    success: bool
    error_message: str = ""


class AuditStats(BaseModel):
    total_logs: int
    action_counts: dict[str, int]
    user_counts: dict[str, int]
    recent_errors: int


@router.get("/logs", response_model=list[AuditLogOut])
@limiter.limit("60/minute")
def get_audit_logs(
    request: Request,
    user_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    """查询审计日志（管理员可查全部，普通用户只能查自己）。"""
    # 非管理员只能查自己的日志
    if principal.role != "admin":
        user_id = principal.id

    logs = audit_logger.get_logs(user_id=user_id, action=action, limit=limit)
    return [
        AuditLogOut(
            timestamp=l.timestamp,
            user_id=l.user_id,
            action=l.action,
            resource=l.resource,
            details=l.details,
            ip_address=l.ip_address,
            success=l.success,
            error_message=l.error_message,
        )
        for l in logs
    ]


@router.get("/stats", response_model=AuditStats)
@limiter.limit("30/minute")
def get_audit_stats(
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AuditStats:
    """获取审计统计（仅管理员）。"""
    if principal.role != "admin":
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")

    stats = audit_logger.get_stats()
    return AuditStats(**stats)
