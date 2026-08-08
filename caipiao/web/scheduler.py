"""自动化任务调度器：定时拉取数据、自动回测、推送结果。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(str, Enum):
    FETCH_DATA = "fetch_data"
    BACKTEST = "backtest"
    ANALYSIS = "analysis"


@dataclass
class ScheduledTask:
    """定时任务配置。"""

    id: str
    name: str
    task_type: TaskType
    profile_key: str
    strategy_id: str | None = None
    interval_minutes: int = 60  # 执行间隔（分钟）
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None


@dataclass
class TaskResult:
    """任务执行结果。"""

    task_id: str
    status: TaskStatus
    started_at: str
    finished_at: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None


class TaskScheduler:
    """任务调度器。"""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._results: list[TaskResult] = []
        self._running = False
        self._task_counter = 0

    def add_task(
        self,
        name: str,
        task_type: TaskType,
        profile_key: str,
        strategy_id: str | None = None,
        interval_minutes: int = 60,
        params: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        """添加定时任务。"""
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        now = datetime.now()
        next_run = now + timedelta(minutes=interval_minutes)

        task = ScheduledTask(
            id=task_id,
            name=name,
            task_type=task_type,
            profile_key=profile_key,
            strategy_id=strategy_id,
            interval_minutes=interval_minutes,
            params=params or {},
            next_run=next_run.isoformat(),
        )
        self._tasks[task_id] = task
        return task

    def remove_task(self, task_id: str) -> bool:
        """移除任务。"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """列出所有任务。"""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """获取任务详情。"""
        return self._tasks.get(task_id)

    def toggle_task(self, task_id: str, enabled: bool) -> bool:
        """启用/禁用任务。"""
        task = self._tasks.get(task_id)
        if task:
            task.enabled = enabled
            return True
        return False

    def get_results(self, task_id: str | None = None, limit: int = 20) -> list[TaskResult]:
        """获取任务执行结果。"""
        if task_id:
            return [r for r in self._results if r.task_id == task_id][-limit:]
        return self._results[-limit:]

    async def run_task(self, task_id: str) -> TaskResult:
        """立即执行任务。"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"任务 {task_id} 不存在")

        task.status = TaskStatus.RUNNING
        started_at = datetime.now().isoformat()

        result = TaskResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            started_at=started_at,
        )

        try:
            if task.task_type == TaskType.FETCH_DATA:
                data = await self._execute_fetch(task)
            elif task.task_type == TaskType.BACKTEST:
                data = await self._execute_backtest(task)
            elif task.task_type == TaskType.ANALYSIS:
                data = await self._execute_analysis(task)
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            result.status = TaskStatus.COMPLETED
            result.data = data
            task.status = TaskStatus.COMPLETED
            task.result = data
            task.last_run = started_at

            # 更新下次执行时间
            next_run = datetime.now() + timedelta(minutes=task.interval_minutes)
            task.next_run = next_run.isoformat()

        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
            task.status = TaskStatus.FAILED
            logger.error(f"任务 {task_id} 执行失败: {e}")

        result.finished_at = datetime.now().isoformat()
        self._results.append(result)
        return result

    async def _execute_fetch(self, task: ScheduledTask) -> dict[str, Any]:
        """执行数据拉取任务。"""
        from ..core.profile import get_profile
        from ..data.fetcher import DrawFetcher

        profile = get_profile(task.profile_key)
        fetcher = DrawFetcher(profile)
        result = fetcher.fetch_latest()
        return {
            "fetched": result.get("fetched", 0),
            "added": result.get("added", 0),
            "total": result.get("total", 0),
        }

    async def _execute_backtest(self, task: ScheduledTask) -> dict[str, Any]:
        """执行回测任务。"""
        # 模拟回测执行
        await asyncio.sleep(0.1)
        return {
            "rounds": task.params.get("rounds", 30),
            "hit_count": 0,
            "profit": 0,
        }

    async def _execute_analysis(self, task: ScheduledTask) -> dict[str, Any]:
        """执行分析任务。"""
        # 模拟分析执行
        await asyncio.sleep(0.1)
        return {
            "analysis_type": "multi_period",
            "periods": task.params.get("periods", 5),
        }


# 全局调度器实例
scheduler = TaskScheduler()
