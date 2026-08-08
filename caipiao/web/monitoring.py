"""性能监控模块：API 调用统计、错误追踪、系统性能。"""

from __future__ import annotations

import time
import traceback
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
import threading


@dataclass
class APICallRecord:
    """API 调用记录。"""

    timestamp: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    user_id: str = ""
    error: str = ""


@dataclass
class ErrorRecord:
    """错误记录。"""

    timestamp: str
    path: str
    error_type: str
    message: str
    traceback: str = ""
    user_id: str = ""


class PerformanceMonitor:
    """性能监控器。"""

    def __init__(self):
        self._api_calls: list[APICallRecord] = []
        self._errors: list[ErrorRecord] = []
        self._max_records = 10000
        self._lock = threading.Lock()

    def record_api_call(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: str = "",
        error: str = "",
    ) -> None:
        """记录 API 调用。"""
        with self._lock:
            record = APICallRecord(
                timestamp=datetime.now().isoformat(),
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                error=error,
            )
            self._api_calls.append(record)
            if len(self._api_calls) > self._max_records:
                self._api_calls = self._api_calls[-self._max_records:]

    def record_error(
        self,
        path: str,
        error_type: str,
        message: str,
        tb: str = "",
        user_id: str = "",
    ) -> None:
        """记录错误。"""
        with self._lock:
            record = ErrorRecord(
                timestamp=datetime.now().isoformat(),
                path=path,
                error_type=error_type,
                message=message,
                traceback=tb,
                user_id=user_id,
            )
            self._errors.append(record)
            if len(self._errors) > self._max_records:
                self._errors = self._errors[-self._max_records:]

    def get_api_stats(self, minutes: int = 60) -> dict[str, Any]:
        """获取 API 调用统计。"""
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        recent = [r for r in self._api_calls if r.timestamp >= cutoff]

        if not recent:
            return {
                "total_calls": 0,
                "avg_duration": 0,
                "error_rate": 0,
                "status_counts": {},
                "top_paths": [],
                "slowest_calls": [],
            }

        # 状态码统计
        status_counts = Counter(r.status_code for r in recent)

        # 路径统计
        path_calls: dict[str, list[float]] = defaultdict(list)
        for r in recent:
            path_calls[r.path].append(r.duration_ms)

        top_paths = [
            {"path": p, "count": len(durations), "avg_ms": sum(durations) / len(durations)}
            for p, durations in sorted(path_calls.items(), key=lambda x: -len(x[1]))[:10]
        ]

        # 最慢调用
        slowest = sorted(recent, key=lambda r: -r.duration_ms)[:5]

        # 错误率
        error_count = sum(1 for r in recent if r.status_code >= 400)
        error_rate = error_count / len(recent) if recent else 0

        return {
            "total_calls": len(recent),
            "avg_duration": sum(r.duration_ms for r in recent) / len(recent),
            "error_rate": error_rate,
            "status_counts": dict(status_counts),
            "top_paths": top_paths,
            "slowest_calls": [
                {
                    "path": r.path,
                    "duration_ms": r.duration_ms,
                    "timestamp": r.timestamp,
                }
                for r in slowest
            ],
        }

    def get_error_stats(self, minutes: int = 60) -> dict[str, Any]:
        """获取错误统计。"""
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        recent = [r for r in self._errors if r.timestamp >= cutoff]

        if not recent:
            return {
                "total_errors": 0,
                "error_types": {},
                "recent_errors": [],
            }

        type_counts = Counter(r.error_type for r in recent)

        return {
            "total_errors": len(recent),
            "error_types": dict(type_counts.most_common(10)),
            "recent_errors": [
                {
                    "timestamp": r.timestamp,
                    "path": r.path,
                    "error_type": r.error_type,
                    "message": r.message[:200],
                }
                for r in recent[-10:]
            ],
        }

    def get_system_stats(self) -> dict[str, Any]:
        """获取系统统计。"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        memory = process.memory_info()

        return {
            "memory_mb": memory.rss / 1024 / 1024,
            "cpu_percent": process.cpu_percent(),
            "threads": process.num_threads(),
            "uptime_seconds": time.time() - process.create_time(),
        }


# 全局监控实例
monitor = PerformanceMonitor()
