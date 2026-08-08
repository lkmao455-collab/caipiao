"""任务调度系统：分布式任务调度和队列管理。"""

from __future__ import annotations

import asyncio
import heapq
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from ..log import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class TaskDefinition:
    id: str
    name: str
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 3
    retry_delay: float = 60
    timeout: float = 300
    schedule: str = ""  # cron expression or interval
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class TaskRun:
    id: str
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str = ""
    attempts: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    worker_id: str = ""


@dataclass
class WorkerNode:
    id: str
    name: str
    status: str = "idle"
    current_task: str | None = None
    capabilities: list[str] = field(default_factory=list)
    max_concurrent: int = 1
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    last_heartbeat: float = field(default_factory=time.time)


TaskHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class TaskScheduler:
    """任务调度器：管理和调度任务执行。"""

    def __init__(self, max_queue_size: int = 10000):
        self._definitions: dict[str, TaskDefinition] = {}
        self._runs: dict[str, TaskRun] = {}
        self._queue: list[tuple[int, float, str]] = []  # (priority, time, run_id)
        self._handlers: dict[str, TaskHandler] = {}
        self._workers: dict[str, WorkerNode] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._max_queue_size = max_queue_size

    def register_handler(self, task_type: str, handler: TaskHandler):
        self._handlers[task_type] = handler

    def create_task(self, definition: TaskDefinition) -> TaskDefinition:
        self._definitions[definition.id] = definition
        return definition

    def get_task(self, task_id: str) -> TaskDefinition | None:
        return self._definitions.get(task_id)

    def list_tasks(self) -> list[TaskDefinition]:
        return list(self._definitions.values())

    def delete_task(self, task_id: str) -> bool:
        if task_id in self._definitions:
            del self._definitions[task_id]
            return True
        return False

    def submit_task(self, task_id: str, payload: dict | None = None) -> TaskRun | None:
        definition = self._definitions.get(task_id)
        if not definition or not definition.enabled:
            return None

        run = TaskRun(
            id=str(uuid.uuid4())[:8],
            task_id=task_id,
        )
        if payload:
            definition.payload.update(payload)

        self._runs[run.id] = run
        heapq.heappush(self._queue, (-definition.priority.value, time.time(), run.id))
        run.status = TaskStatus.QUEUED
        return run

    def cancel_task(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run and run.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
            run.status = TaskStatus.CANCELLED
            return True
        return False

    def get_run(self, run_id: str) -> TaskRun | None:
        return self._runs.get(run_id)

    def list_runs(self, task_id: str | None = None) -> list[TaskRun]:
        runs = list(self._runs.values())
        if task_id:
            runs = [r for r in runs if r.task_id == task_id]
        return runs[-100:]

    def register_worker(self, worker: WorkerNode):
        self._workers[worker.id] = worker

    def get_worker(self, worker_id: str) -> WorkerNode | None:
        return self._workers.get(worker_id)

    def list_workers(self) -> list[WorkerNode]:
        return list(self._workers.values())

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("Task scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task scheduler stopped")

    async def _dispatch_loop(self):
        while self._running:
            try:
                if self._queue:
                    _, _, run_id = heapq.heappop(self._queue)
                    run = self._runs.get(run_id)
                    if run and run.status == TaskStatus.QUEUED:
                        await self._execute_run(run)
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Dispatch error: {e}")

    async def _execute_run(self, run: TaskRun):
        definition = self._definitions.get(run.task_id)
        if not definition:
            run.status = TaskStatus.FAILED
            run.error = "Task definition not found"
            return

        handler = self._handlers.get(definition.task_type)
        if not handler:
            run.status = TaskStatus.FAILED
            run.error = f"No handler for task type: {definition.task_type}"
            return

        run.status = TaskStatus.RUNNING
        run.started_at = time.time()
        run.attempts += 1

        try:
            result = await asyncio.wait_for(
                handler(definition.payload),
                timeout=definition.timeout,
            )
            run.result = result
            run.status = TaskStatus.COMPLETED
        except asyncio.TimeoutError:
            run.error = "Task timed out"
            run.status = TaskStatus.FAILED
        except Exception as e:
            run.error = str(e)
            if run.attempts < definition.max_retries:
                run.status = TaskStatus.RETRYING
                heapq.heappush(
                    self._queue,
                    (-definition.priority.value, time.time() + definition.retry_delay, run.id),
                )
            else:
                run.status = TaskStatus.FAILED

        run.completed_at = time.time()

    def get_queue_size(self) -> int:
        return len(self._queue)

    def get_stats(self) -> dict:
        status_counts = defaultdict(int)
        for run in self._runs.values():
            status_counts[run.status] += 1

        return {
            "total_tasks": len(self._definitions),
            "total_runs": len(self._runs),
            "queue_size": len(self._queue),
            "status_counts": dict(status_counts),
            "workers": len(self._workers),
        }


# 全局调度器
_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
