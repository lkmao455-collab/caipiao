"""数据分析平台：用户行为分析、漏斗分析、A/B 测试。"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


def _funnel_to_dict(f: FunnelDefinition) -> dict[str, Any]:
    return {
        "id": f.id,
        "name": f.name,
        "steps": [
            {"name": s.name, "event_type": s.event_type, "event_name": s.event_name}
            for s in f.steps
        ],
        "time_window_minutes": f.time_window_minutes,
        "created_at": f.created_at,
    }


def _dict_to_funnel(d: dict[str, Any]) -> FunnelDefinition:
    return FunnelDefinition(
        id=d["id"],
        name=d["name"],
        steps=[
            FunnelStep(name=s["name"], event_type=s["event_type"], event_name=s["event_name"])
            for s in d.get("steps", [])
        ],
        time_window_minutes=d.get("time_window_minutes", 60),
        created_at=d.get("created_at", time.time),
    )


def _ab_test_to_dict(t: ABTest) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "variants": [
            {
                "name": v.name,
                "weight": v.weight,
                "assigned_users": v.assigned_users,
                "conversions": v.conversions,
            }
            for v in t.variants
        ],
        "start_time": t.start_time,
        "end_time": t.end_time,
        "status": t.status,
        "target_metric": t.target_metric,
    }


def _dict_to_ab_test(d: dict[str, Any]) -> ABTest:
    return ABTest(
        id=d["id"],
        name=d["name"],
        variants=[
            ABTestVariant(
                name=v["name"],
                weight=v.get("weight", 1),
                assigned_users=v.get("assigned_users", 0),
                conversions=v.get("conversions", 0),
            )
            for v in d.get("variants", [])
        ],
        start_time=d.get("start_time", time.time),
        end_time=d.get("end_time"),
        status=d.get("status", "running"),
        target_metric=d.get("target_metric", ""),
    )


@dataclass
class UserEvent:
    event_id: str
    user_id: str
    event_type: str
    event_name: str
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    platform: str = "web"


@dataclass
class FunnelStep:
    name: str
    event_type: str
    event_name: str


@dataclass
class FunnelDefinition:
    id: str
    name: str
    steps: list[FunnelStep]
    time_window_minutes: int = 60
    created_at: float = field(default_factory=time.time)


@dataclass
class FunnelResult:
    definition: FunnelDefinition
    total_users: int
    step_results: list[dict[str, Any]]
    conversion_rate: float
    drop_off_rates: list[float]


@dataclass
class ABTestVariant:
    name: str
    weight: float
    assigned_users: int = 0
    conversions: int = 0


@dataclass
class ABTest:
    id: str
    name: str
    variants: list[ABTestVariant]
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: str = "running"
    target_metric: str = ""


class AnalyticsPlatform:
    """数据分析平台：收集事件、分析行为。"""

    def __init__(self, max_events: int = 1000000):
        self._events: list[UserEvent] = []
        self._max_events = max_events
        self._funnels: dict[str, FunnelDefinition] = {}
        self._ab_tests: dict[str, ABTest] = {}
        self._user_sessions: dict[str, list[UserEvent]] = defaultdict(list)
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._funnels = {}
        self._ab_tests = {}
        from .models import ABTestRow, FunnelRow

        with _webdb._SessionLocal() as session:
            for row in session.query(FunnelRow).all():
                try:
                    self._funnels[row.id] = _dict_to_funnel(json.loads(row.data_json))
                except Exception as exc:
                    logger.error("加载漏斗 %s 失败: %s", row.id, exc)
            for row in session.query(ABTestRow).all():
                try:
                    self._ab_tests[row.id] = _dict_to_ab_test(json.loads(row.data_json))
                except Exception as exc:
                    logger.error("加载 A/B 测试 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_funnel(self, funnel_id: str) -> None:
        from .models import FunnelRow

        f = self._funnels.get(funnel_id)
        with _webdb._SessionLocal() as session:
            row = session.get(FunnelRow, funnel_id)
            if f is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_funnel_to_dict(f), ensure_ascii=False)
            if row is None:
                session.add(
                    FunnelRow(
                        id=funnel_id,
                        name=f.name,
                        data_json=data,
                        updated_at=time.time(),
                    )
                )
            else:
                row.data_json = data
                row.name = f.name
            session.commit()

    def _persist_ab_test(self, test_id: str) -> None:
        from .models import ABTestRow

        t = self._ab_tests.get(test_id)
        with _webdb._SessionLocal() as session:
            row = session.get(ABTestRow, test_id)
            if t is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_ab_test_to_dict(t), ensure_ascii=False)
            if row is None:
                session.add(
                    ABTestRow(
                        id=test_id,
                        name=t.name,
                        data_json=data,
                        updated_at=time.time(),
                    )
                )
            else:
                row.data_json = data
                row.name = t.name
            session.commit()

    def track_event(self, event: UserEvent):
        """追踪用户事件。"""
        if len(self._events) >= self._max_events:
            # 保留最近的事件
            self._events = self._events[-self._max_events // 2:]

        self._events.append(event)
        self._user_sessions[event.session_id].append(event)

    def get_user_events(self, user_id: str, limit: int = 100) -> list[UserEvent]:
        """获取用户事件。"""
        return [e for e in self._events if e.user_id == user_id][-limit:]

    def get_event_counts(self, event_type: str, minutes: int = 60) -> dict[str, int]:
        """获取事件计数。"""
        cutoff = time.time() - minutes * 60
        counts: dict[str, int] = defaultdict(int)
        for e in self._events:
            if e.event_type == event_type and e.timestamp >= cutoff:
                counts[e.event_name] += 1
        return dict(counts)

    def get_user_activity(self, minutes: int = 60) -> dict:
        """获取用户活跃度。"""
        cutoff = time.time() - minutes * 60
        active_users = set()
        events_by_hour: dict[int, int] = defaultdict(int)

        for e in self._events:
            if e.timestamp >= cutoff:
                active_users.add(e.user_id)
                hour = int((e.timestamp % 86400) / 3600)
                events_by_hour[hour] += 1

        return {
            "active_users": len(active_users),
            "total_events": sum(events_by_hour.values()),
            "hourly_distribution": [
                {"hour": h, "count": c} for h, c in sorted(events_by_hour.items())
            ],
        }

    # 漏斗分析
    def create_funnel(self, definition: FunnelDefinition) -> FunnelDefinition:
        """创建漏斗定义。"""
        self._ensure_loaded()
        self._funnels[definition.id] = definition
        self._persist_funnel(definition.id)
        return definition

    def analyze_funnel(self, funnel_id: str, minutes: int = 60) -> FunnelResult | None:
        """分析漏斗转化。"""
        self._ensure_loaded()
        definition = self._funnels.get(funnel_id)
        if not definition:
            return None

        cutoff = time.time() - minutes * 60
        relevant_events = [e for e in self._events if e.timestamp >= cutoff]

        # 按用户分组
        user_events: dict[str, list[UserEvent]] = defaultdict(list)
        for e in relevant_events:
            user_events[e.user_id].append(e)

        total_users = len(user_events)
        step_results = []
        prev_count = total_users

        for i, step in enumerate(definition.steps):
            # 找到完成此步骤的用户
            completed = 0
            for user_id, events in user_events.items():
                # 按时间排序
                sorted_events = sorted(events, key=lambda x: x.timestamp)
                # 查找匹配事件
                for e in sorted_events:
                    if e.event_type == step.event_type and e.event_name == step.event_name:
                        completed += 1
                        break

            conversion_rate = (completed / total_users * 100) if total_users > 0 else 0
            drop_off = ((prev_count - completed) / prev_count * 100) if prev_count > 0 else 0

            step_results.append({
                "step": i + 1,
                "name": step.name,
                "users": completed,
                "conversion_rate": round(conversion_rate, 2),
                "drop_off_rate": round(drop_off, 2),
            })
            prev_count = completed

        final_conversion = (step_results[-1]["users"] / total_users * 100) if total_users > 0 and step_results else 0

        return FunnelResult(
            definition=definition,
            total_users=total_users,
            step_results=step_results,
            conversion_rate=round(final_conversion, 2),
            drop_off_rates=[s["drop_off_rate"] for s in step_results[1:]],
        )

    # A/B 测试
    def create_ab_test(self, test: ABTest) -> ABTest:
        """创建 A/B 测试。"""
        self._ensure_loaded()
        self._ab_tests[test.id] = test
        self._persist_ab_test(test.id)
        return test

    def assign_variant(self, test_id: str, user_id: str) -> str | None:
        """为用户分配变体。"""
        self._ensure_loaded()
        test = self._ab_tests.get(test_id)
        if not test or test.status != "running":
            return None

        # 简单的哈希分配
        hash_val = hash(user_id + test_id) % 100
        cumulative = 0
        for variant in test.variants:
            cumulative += variant.weight * 100
            if hash_val < cumulative:
                variant.assigned_users += 1
                self._persist_ab_test(test_id)
                return variant.name

        result = test.variants[0].name if test.variants else None
        if result is not None:
            self._persist_ab_test(test_id)
        return result

    def record_conversion(self, test_id: str, variant_name: str):
        """记录转化。"""
        self._ensure_loaded()
        test = self._ab_tests.get(test_id)
        if test:
            for v in test.variants:
                if v.name == variant_name:
                    v.conversions += 1
                    break
            self._persist_ab_test(test_id)

    def get_ab_test_results(self, test_id: str) -> dict | None:
        """获取 A/B 测试结果。"""
        self._ensure_loaded()
        test = self._ab_tests.get(test_id)
        if not test:
            return None

        variants = []
        for v in test.variants:
            conversion_rate = (v.conversions / v.assigned_users * 100) if v.assigned_users > 0 else 0
            variants.append({
                "name": v.name,
                "assigned_users": v.assigned_users,
                "conversions": v.conversions,
                "conversion_rate": round(conversion_rate, 2),
            })

        return {
            "id": test.id,
            "name": test.name,
            "status": test.status,
            "target_metric": test.target_metric,
            "variants": variants,
        }

    def get_overview(self, minutes: int = 60) -> dict:
        """获取分析概览。"""
        self._ensure_loaded()
        activity = self.get_user_activity(minutes)
        event_counts = self.get_event_counts("action", minutes)

        return {
            "active_users": activity["active_users"],
            "total_events": activity["total_events"],
            "top_events": sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "hourly_distribution": activity["hourly_distribution"],
            "active_funnels": len(self._funnels),
            "active_ab_tests": sum(1 for t in self._ab_tests.values() if t.status == "running"),
        }


# 全局分析平台实例
_analytics: AnalyticsPlatform | None = None


def get_analytics() -> AnalyticsPlatform:
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsPlatform()
    return _analytics
