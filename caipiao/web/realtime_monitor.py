"""实时监控服务：收集和推送系统指标。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class MetricPoint:
    timestamp: float
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_io_read: float = 0.0
    disk_io_write: float = 0.0
    network_sent: float = 0.0
    network_recv: float = 0.0
    active_connections: int = 0
    requests_per_second: float = 0.0
    avg_response_time: float = 0.0
    error_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)


class RealtimeMonitor:
    """实时监控器：收集指标并通过 WebSocket 推送。"""

    def __init__(self, history_size: int = 300):
        self._history_size = history_size
        self._metrics_history: deque[SystemMetrics] = deque(maxlen=history_size)
        self._custom_metrics: dict[str, deque[MetricPoint]] = {}
        self._subscribers: list[Any] = []
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """启动监控。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info("Realtime monitor started")

    async def stop(self):
        """停止监控。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Realtime monitor stopped")

    async def _collect_loop(self):
        """定期收集指标。"""
        while self._running:
            try:
                metrics = await self._collect_metrics()
                self._metrics_history.append(metrics)
                await self._notify_subscribers(metrics)
            except Exception as e:
                logger.error(f"Failed to collect metrics: {e}")
            await asyncio.sleep(1)

    async def _collect_metrics(self) -> SystemMetrics:
        """收集系统指标。"""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_io_counters()
            net = psutil.net_io_counters()
        except ImportError:
            # Fallback if psutil not available
            cpu = 0.0
            mem = type('Mem', (), {'used': 0, 'total': 1, 'percent': 0})()
            disk = type('Disk', (), {'read_bytes': 0, 'write_bytes': 0})()
            net = type('Net', (), {'bytes_sent': 0, 'bytes_recv': 0})()

        return SystemMetrics(
            cpu_percent=cpu,
            memory_mb=mem.used / (1024 * 1024),
            memory_percent=mem.percent,
            disk_io_read=disk.read_bytes / (1024 * 1024),
            disk_io_write=disk.write_bytes / (1024 * 1024),
            network_sent=net.bytes_sent / (1024 * 1024),
            network_recv=net.bytes_recv / (1024 * 1024),
        )

    def subscribe(self, ws: Any):
        """订阅实时指标推送。"""
        self._subscribers.append(ws)

    def unsubscribe(self, ws: Any):
        """取消订阅。"""
        if ws in self._subscribers:
            self._subscribers.remove(ws)

    async def _notify_subscribers(self, metrics: SystemMetrics):
        """通知所有订阅者。"""
        if not self._subscribers:
            return

        data = {
            "type": "metrics",
            "data": {
                "cpu_percent": metrics.cpu_percent,
                "memory_mb": round(metrics.memory_mb, 2),
                "memory_percent": metrics.memory_percent,
                "network_sent": round(metrics.network_sent, 2),
                "network_recv": round(metrics.network_recv, 2),
                "timestamp": metrics.timestamp,
            },
        }

        import json
        message = json.dumps(data)

        disconnected = []
        for ws in self._subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.unsubscribe(ws)

    def get_history(self, minutes: int = 5) -> list[SystemMetrics]:
        """获取历史指标。"""
        cutoff = time.time() - minutes * 60
        return [m for m in self._metrics_history if m.timestamp >= cutoff]

    def record_custom_metric(self, name: str, value: float, labels: dict[str, str] | None = None):
        """记录自定义指标。"""
        if name not in self._custom_metrics:
            self._custom_metrics[name] = deque(maxlen=self._history_size)
        self._custom_metrics[name].append(
            MetricPoint(timestamp=time.time(), value=value, labels=labels or {})
        )

    def get_custom_metric(self, name: str, minutes: int = 5) -> list[MetricPoint]:
        """获取自定义指标历史。"""
        if name not in self._custom_metrics:
            return []
        cutoff = time.time() - minutes * 60
        return [p for p in self._custom_metrics[name] if p.timestamp >= cutoff]


# 全局监控器实例
_monitor: RealtimeMonitor | None = None


def get_monitor() -> RealtimeMonitor:
    global _monitor
    if _monitor is None:
        _monitor = RealtimeMonitor()
    return _monitor
