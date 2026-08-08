"""自动化任务路由：管理定时任务和执行结果。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal
from ..ratelimit import limiter
from ..scheduler import scheduler, TaskType

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    task_type: str = Field(description="任务类型: fetch_data, backtest, analysis")
    profile_key: str
    strategy_id: str | None = None
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    params: dict = {}


class TaskOut(BaseModel):
    id: str
    name: str
    task_type: str
    profile_key: str
    strategy_id: str | None = None
    interval_minutes: int
    enabled: bool
    last_run: str | None = None
    next_run: str | None = None
    status: str
    result: dict | None = None


class TaskResultOut(BaseModel):
    task_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    data: dict | None = None
    error: str | None = None


@router.get("", response_model=list[TaskOut])
def list_tasks(
    principal=Depends(get_current_principal),
) -> list[TaskOut]:
    """列出所有定时任务。"""
    tasks = scheduler.list_tasks()
    return [
        TaskOut(
            id=t.id,
            name=t.name,
            task_type=t.task_type.value,
            profile_key=t.profile_key,
            strategy_id=t.strategy_id,
            interval_minutes=t.interval_minutes,
            enabled=t.enabled,
            last_run=t.last_run,
            next_run=t.next_run,
            status=t.status.value,
            result=t.result,
        )
        for t in tasks
    ]


@router.post("", response_model=TaskOut)
def create_task(
    req: TaskCreate,
    principal=Depends(get_current_principal),
) -> TaskOut:
    """创建定时任务。"""
    try:
        task_type = TaskType(req.task_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知任务类型: {req.task_type}")

    task = scheduler.add_task(
        name=req.name,
        task_type=task_type,
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        interval_minutes=req.interval_minutes,
        params=req.params,
    )
    return TaskOut(
        id=task.id,
        name=task.name,
        task_type=task.task_type.value,
        profile_key=task.profile_key,
        strategy_id=task.strategy_id,
        interval_minutes=task.interval_minutes,
        enabled=task.enabled,
        last_run=task.last_run,
        next_run=task.next_run,
        status=task.status.value,
        result=task.result,
    )


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    principal=Depends(get_current_principal),
) -> dict:
    """删除定时任务。"""
    if not scheduler.remove_task(task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"deleted": task_id}


@router.patch("/{task_id}/toggle")
def toggle_task(
    task_id: str,
    enabled: bool = True,
    principal=Depends(get_current_principal),
) -> dict:
    """启用/禁用定时任务。"""
    if not scheduler.toggle_task(task_id, enabled):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"task_id": task_id, "enabled": enabled}


@router.post("/{task_id}/run")
async def run_task(
    task_id: str,
    principal=Depends(get_current_principal),
) -> TaskResultOut:
    """立即执行任务。"""
    try:
        result = await scheduler.run_task(task_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return TaskResultOut(
        task_id=result.task_id,
        status=result.status.value,
        started_at=result.started_at,
        finished_at=result.finished_at,
        data=result.data,
        error=result.error,
    )


@router.get("/{task_id}/results", response_model=list[TaskResultOut])
def get_task_results(
    task_id: str,
    limit: int = 10,
    principal=Depends(get_current_principal),
) -> list[TaskResultOut]:
    """获取任务执行结果。"""
    results = scheduler.get_results(task_id, limit)
    return [
        TaskResultOut(
            task_id=r.task_id,
            status=r.status.value,
            started_at=r.started_at,
            finished_at=r.finished_at,
            data=r.data,
            error=r.error,
        )
        for r in results
    ]
