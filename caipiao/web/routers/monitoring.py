"""性能监控路由：API 调用统计、错误追踪、系统性能。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal
from ..monitoring import monitor
from ..ratelimit import limiter

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class APICallStats(BaseModel):
    total_calls: int
    avg_duration: float
    error_rate: float
    status_counts: dict[str, int]
    top_paths: list[dict]
    slowest_calls: list[dict]


class ErrorStats(BaseModel):
    total_errors: int
    error_types: dict[str, int]
    recent_errors: list[dict]


class SystemStats(BaseModel):
    memory_mb: float
    cpu_percent: float
    threads: int
    uptime_seconds: float


@router.get("/api-stats", response_model=APICallStats)
@limiter.limit("30/minute")
def get_api_stats(
    request: Request,
    minutes: int = Query(default=60, ge=1, le=1440),
    principal=Depends(get_current_principal),
) -> APICallStats:
    """获取 API 调用统计（管理员）。"""
    if principal.role != "admin":
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")

    stats = monitor.get_api_stats(minutes)
    return APICallStats(**stats)


@router.get("/error-stats", response_model=ErrorStats)
@limiter.limit("30/minute")
def get_error_stats(
    request: Request,
    minutes: int = Query(default=60, ge=1, le=1440),
    principal=Depends(get_current_principal),
) -> ErrorStats:
    """获取错误统计（管理员）。"""
    if principal.role != "admin":
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")

    stats = monitor.get_error_stats(minutes)
    return ErrorStats(**stats)


@router.get("/system-stats", response_model=SystemStats)
@limiter.limit("10/minute")
def get_system_stats(
    request: Request,
    principal=Depends(get_current_principal),
) -> SystemStats:
    """获取系统性能统计（管理员）。"""
    if principal.role != "admin":
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")

    try:
        stats = monitor.get_system_stats()
        return SystemStats(**stats)
    except ImportError:
        return SystemStats(
            memory_mb=0,
            cpu_percent=0,
            threads=0,
            uptime_seconds=0,
        )
