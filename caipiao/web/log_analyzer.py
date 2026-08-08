"""日志分析系统：日志收集、分析、告警。"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class LogEntry:
    timestamp: float
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: str
    source: str = ""
    service: str = ""
    trace_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    id: str
    name: str
    condition: str  # error_count > 10, response_time > 1000, etc.
    threshold: float = 0
    time_window: int = 300  # seconds
    severity: str = "warning"  # info, warning, critical
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class Alert:
    id: str
    rule_id: str
    message: str
    severity: str
    triggered_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    status: str = "active"  # active, resolved


@dataclass
class LogPattern:
    pattern: str
    count: int = 0
    last_seen: float = 0
    sample: str = ""


class LogAnalyzer:
    """日志分析器：日志收集、模式分析、告警。"""

    def __init__(self, max_entries: int = 100000):
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries
        self._rules: dict[str, AlertRule] = {}
        self._alerts: list[Alert] = []
        self._patterns: dict[str, LogPattern] = {}
        self._service_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "errors": 0})

    def add_entry(self, entry: LogEntry):
        if len(self._entries) >= self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]
        self._entries.append(entry)

        stats = self._service_stats[entry.service or "unknown"]
        stats["count"] += 1
        if entry.level in ("ERROR", "CRITICAL"):
            stats["errors"] += 1

        self._analyze_pattern(entry)
        self._check_alerts(entry)

    def _analyze_pattern(self, entry: LogEntry):
        normalized = re.sub(r'\d+', 'N', entry.message)
        normalized = re.sub(r'[a-f0-9]{8,}', 'ID', normalized)

        if normalized not in self._patterns:
            self._patterns[normalized] = LogPattern(
                pattern=normalized,
                sample=entry.message,
            )
        self._patterns[normalized].count += 1
        self._patterns[normalized].last_seen = entry.timestamp

    def _check_alerts(self, entry: LogEntry):
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if entry.level in ("ERROR", "CRITICAL"):
                recent_errors = [
                    e for e in self._entries
                    if e.level in ("ERROR", "CRITICAL")
                    and e.timestamp > time.time() - rule.time_window
                ]
                if len(recent_errors) >= rule.threshold:
                    self._trigger_alert(rule, f"Error count exceeded threshold: {len(recent_errors)}")

    def _trigger_alert(self, rule: AlertRule, message: str):
        existing = next(
            (a for a in self._alerts if a.rule_id == rule.id and a.status == "active"),
            None,
        )
        if existing:
            return

        alert = Alert(
            id=str(__import__("uuid").uuid4())[:8],
            rule_id=rule.id,
            message=message,
            severity=rule.severity,
        )
        self._alerts.append(alert)
        logger.warning(f"Alert triggered: {rule.name} - {message}")

    # 规则管理
    def create_rule(self, rule: AlertRule) -> AlertRule:
        self._rules[rule.id] = rule
        return rule

    def get_rule(self, rule_id: str) -> AlertRule | None:
        return self._rules.get(rule_id)

    def list_rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    # 告警管理
    def get_alerts(self, status: str | None = None, limit: int = 100) -> list[Alert]:
        alerts = self._alerts
        if status:
            alerts = [a for a in alerts if a.status == status]
        return alerts[-limit:]

    def resolve_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.id == alert_id and alert.status == "active":
                alert.status = "resolved"
                alert.resolved_at = time.time()
                return True
        return False

    # 查询
    def search(self, query: str, level: str | None = None, service: str | None = None, limit: int = 100) -> list[LogEntry]:
        results = self._entries
        if level:
            results = [e for e in results if e.level == level]
        if service:
            results = [e for e in results if e.service == service]
        if query:
            results = [e for e in results if query.lower() in e.message.lower()]
        return results[-limit:]

    def get_level_stats(self, minutes: int = 60) -> dict[str, int]:
        cutoff = time.time() - minutes * 60
        stats = defaultdict(int)
        for entry in self._entries:
            if entry.timestamp >= cutoff:
                stats[entry.level] += 1
        return dict(stats)

    def get_service_stats(self) -> dict[str, dict]:
        return dict(self._service_stats)

    def get_top_patterns(self, limit: int = 20) -> list[dict]:
        sorted_patterns = sorted(self._patterns.values(), key=lambda p: p.count, reverse=True)
        return [
            {"pattern": p.pattern, "count": p.count, "sample": p.sample}
            for p in sorted_patterns[:limit]
        ]

    def get_timeline(self, minutes: int = 60, interval: int = 60) -> list[dict]:
        cutoff = time.time() - minutes * 60
        buckets: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for entry in self._entries:
            if entry.timestamp >= cutoff:
                bucket = int(entry.timestamp / interval) * interval
                buckets[bucket][entry.level] += 1

        return [
            {"timestamp": ts, "counts": dict(counts)}
            for ts, counts in sorted(buckets.items())
        ]


# 全局日志分析器
_analyzer: LogAnalyzer | None = None


def get_log_analyzer() -> LogAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = LogAnalyzer()
    return _analyzer
