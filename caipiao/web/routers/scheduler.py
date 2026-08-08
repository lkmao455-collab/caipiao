"""任务调度路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import get_current_principal
from ..task_scheduler import TaskDefinition, TaskPriority, WorkerNode, get_scheduler

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    task_type: str
    payload: dict = {}
    priority: int = 1
    max_retries: int = 3
    timeout: float = 300
    schedule: str = ""


class TaskSubmit(BaseModel):
    payload: dict = {}


class WorkerRegister(BaseModel):
    name: str
    capabilities: list[str] = []
    max_concurrent: int = 1


@router.post("/tasks")
def create_task(
    req: TaskCreate,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    task = TaskDefinition(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        task_type=req.task_type,
        payload=req.payload,
        priority=TaskPriority(req.priority),
        max_retries=req.max_retries,
        timeout=req.timeout,
        schedule=req.schedule,
    )
    scheduler.create_task(task)
    return {"id": task.id, "name": task.name}


@router.get("/tasks")
def list_tasks(
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    return [
        {"id": t.id, "name": t.name, "task_type": t.task_type, "enabled": t.enabled}
        for t in scheduler.list_tasks()
    ]


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    if not scheduler.delete_task(task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"status": "ok"}


@router.post("/tasks/{task_id}/submit")
def submit_task(
    task_id: str,
    req: TaskSubmit,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    run = scheduler.submit_task(task_id, req.payload)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或已禁用")
    return {"run_id": run.id, "status": run.status}


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    if not scheduler.cancel_task(run_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法取消")
    return {"status": "ok"}


@router.get("/runs")
def list_runs(
    task_id: str | None = None,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    runs = scheduler.list_runs(task_id)
    return [
        {"id": r.id, "task_id": r.task_id, "status": r.status, "started_at": r.started_at, "completed_at": r.completed_at}
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    run = scheduler.get_run(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "运行不存在")
    return {
        "id": run.id,
        "task_id": run.task_id,
        "status": run.status,
        "result": run.result,
        "error": run.error,
        "attempts": run.attempts,
    }


@router.post("/workers")
def register_worker(
    req: WorkerRegister,
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    worker = WorkerNode(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        capabilities=req.capabilities,
        max_concurrent=req.max_concurrent,
    )
    scheduler.register_worker(worker)
    return {"id": worker.id, "name": worker.name}


@router.get("/workers")
def list_workers(
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    return [
        {"id": w.id, "name": w.name, "status": w.status, "active_tasks": w.active_tasks, "completed_tasks": w.completed_tasks}
        for w in scheduler.list_workers()
    ]


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    scheduler = get_scheduler()
    return scheduler.get_stats()
