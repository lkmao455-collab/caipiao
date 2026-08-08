"""API 网关管理：限流、统计、开发者门户。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitRule:
    path: str
    method: str = "*"
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst: int = 10


@dataclass
class APIUsageRecord:
    timestamp: float
    path: str
    method: str
    status_code: int
    duration_ms: float
    user_id: str = ""
    api_key: str = ""


@dataclass
class DeveloperApp:
    id: str
    name: str
    owner_id: str
    api_key: str
    rate_limit: RateLimitRule | None = None
    allowed_paths: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    enabled: bool = True
    total_calls: int = 0
    last_used_at: float = 0


class APIGateway:
    """API 网关：限流、统计、开发者管理。"""

    def __init__(self, default_rate_limit: int = 60):
        self._default_rate_limit = default_rate_limit
        self._rate_limits: dict[str, RateLimitRule] = {}
        self._usage_history: deque[APIUsageRecord] = deque(maxlen=100000)
        self._developer_apps: dict[str, DeveloperApp] = {}
        self._request_counts: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=10000))

    def add_rate_limit(self, rule: RateLimitRule):
        """添加限流规则。"""
        key = f"{rule.method}:{rule.path}"
        self._rate_limits[key] = rule

    def check_rate_limit(self, path: str, method: str, identifier: str) -> tuple[bool, dict]:
        """检查是否超过限流。"""
        # 查找匹配的规则
        rule = self._rate_limits.get(f"{method}:{path}")
        if not rule:
            rule = self._rate_limits.get(f"*:{path}")
        if not rule:
            rule = RateLimitRule(path=path, requests_per_minute=self._default_rate_limit)

        now = time.time()
        key = f"{identifier}:{path}"

        # 清理过期记录
        counts = self._request_counts[key]
        while counts and counts[0] < now - 86400:
            counts.popleft()

        # 计算各时间段请求数
        minute_count = sum(1 for t in counts if t > now - 60)
        hour_count = sum(1 for t in counts if t > now - 3600)
        day_count = len(counts)

        limits = {
            "requests_per_minute": rule.requests_per_minute,
            "requests_per_hour": rule.requests_per_hour,
            "requests_per_day": rule.requests_per_day,
            "remaining_minute": max(0, rule.requests_per_minute - minute_count),
            "remaining_hour": max(0, rule.requests_per_hour - hour_count),
            "remaining_day": max(0, rule.requests_per_day - day_count),
        }

        # 检查是否超限
        exceeded = (
            minute_count >= rule.requests_per_minute
            or hour_count >= rule.requests_per_hour
            or day_count >= rule.requests_per_day
        )

        if not exceeded:
            counts.append(now)

        return not exceeded, limits

    def record_usage(self, record: APIUsageRecord):
        """记录 API 使用。"""
        self._usage_history.append(record)

    def get_usage_stats(self, minutes: int = 60) -> dict:
        """获取使用统计。"""
        cutoff = time.time() - minutes * 60
        recent = [r for r in self._usage_history if r.timestamp >= cutoff]

        if not recent:
            return {
                "total_calls": 0,
                "avg_duration_ms": 0,
                "error_rate": 0,
                "status_counts": {},
                "top_paths": [],
                "hourly_distribution": [],
            }

        # 状态码统计
        status_counts: dict[int, int] = defaultdict(int)
        for r in recent:
            status_counts[r.status_code] += 1

        # 路径统计
        path_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_ms": 0})
        for r in recent:
            path_stats[r.path]["count"] += 1
            path_stats[r.path]["total_ms"] += r.duration_ms

        top_paths = sorted(
            [
                {
                    "path": p,
                    "count": s["count"],
                    "avg_ms": round(s["total_ms"] / s["count"], 2) if s["count"] > 0 else 0,
                }
                for p, s in path_stats.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # 小时分布
        hourly: dict[int, int] = defaultdict(int)
        for r in recent:
            hour = int((r.timestamp % 86400) / 3600)
            hourly[hour] += 1

        total = len(recent)
        errors = sum(1 for r in recent if r.status_code >= 400)

        return {
            "total_calls": total,
            "avg_duration_ms": round(sum(r.duration_ms for r in recent) / total, 2),
            "error_rate": round(errors / total * 100, 2) if total > 0 else 0,
            "status_counts": dict(status_counts),
            "top_paths": top_paths,
            "hourly_distribution": [{"hour": h, "count": c} for h, c in sorted(hourly.items())],
        }

    def create_developer_app(self, name: str, owner_id: str, api_key: str) -> DeveloperApp:
        """创建开发者应用。"""
        app = DeveloperApp(
            id=str(__import__("uuid").uuid4())[:8],
            name=name,
            owner_id=owner_id,
            api_key=api_key,
        )
        self._developer_apps[app.id] = app
        return app

    def get_developer_app(self, app_id: str) -> DeveloperApp | None:
        return self._developer_apps.get(app_id)

    def list_developer_apps(self, owner_id: str | None = None) -> list[DeveloperApp]:
        apps = list(self._developer_apps.values())
        if owner_id:
            apps = [a for a in apps if a.owner_id == owner_id]
        return apps

    def disable_developer_app(self, app_id: str) -> bool:
        app = self._developer_apps.get(app_id)
        if app:
            app.enabled = False
            return True
        return False

    def enable_developer_app(self, app_id: str) -> bool:
        app = self._developer_apps.get(app_id)
        if app:
            app.enabled = True
            return True
        return False

    def get_developer_stats(self, app_id: str, minutes: int = 60) -> dict:
        """获取开发者应用统计。"""
        app = self._developer_apps.get(app_id)
        if not app:
            return {}

        cutoff = time.time() - minutes * 60
        app_usage = [r for r in self._usage_history if r.api_key == app.api_key and r.timestamp >= cutoff]

        return {
            "app_id": app.id,
            "app_name": app.name,
            "total_calls": len(app_usage),
            "avg_duration_ms": round(
                sum(r.duration_ms for r in app_usage) / len(app_usage), 2
            ) if app_usage else 0,
            "error_rate": round(
                sum(1 for r in app_usage if r.status_code >= 400) / len(app_usage) * 100, 2
            ) if app_usage else 0,
        }


# 全局网关实例
_gateway: APIGateway | None = None


def get_gateway() -> APIGateway:
    global _gateway
    if _gateway is None:
        _gateway = APIGateway()
    return _gateway
