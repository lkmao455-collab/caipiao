"""日志分析路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..log_analyzer import AlertRule, get_log_analyzer

router = APIRouter(prefix="/logs", tags=["logs"])


class AlertRuleCreate(BaseModel):
    name: str
    condition: str
    threshold: float = 0
    time_window: int = 300
    severity: str = "warning"


class LogSearch(BaseModel):
    query: str = ""
    level: str | None = None
    service: str | None = None
    limit: int = 100


@router.post("/search")
def search_logs(
    req: LogSearch,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    entries = analyzer.search(req.query, req.level, req.service, req.limit)
    return [
        {
            "timestamp": e.timestamp,
            "level": e.level,
            "message": e.message,
            "service": e.service,
        }
        for e in entries
    ]


@router.get("/stats")
def get_stats(
    minutes: int = 60,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    return {
        "levels": analyzer.get_level_stats(minutes),
        "services": analyzer.get_service_stats(),
    }


@router.get("/patterns")
def get_patterns(
    limit: int = 20,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    return {"patterns": analyzer.get_top_patterns(limit)}


@router.get("/timeline")
def get_timeline(
    minutes: int = 60,
    interval: int = 60,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    return {"timeline": analyzer.get_timeline(minutes, interval)}


@router.post("/alerts/rules")
def create_alert_rule(
    req: AlertRuleCreate,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    rule = AlertRule(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        condition=req.condition,
        threshold=req.threshold,
        time_window=req.time_window,
        severity=req.severity,
    )
    analyzer.create_rule(rule)
    return {"id": rule.id, "name": rule.name}


@router.get("/alerts/rules")
def list_alert_rules(
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    return [
        {"id": r.id, "name": r.name, "condition": r.condition, "severity": r.severity, "enabled": r.enabled}
        for r in analyzer.list_rules()
    ]


@router.delete("/alerts/rules/{rule_id}")
def delete_alert_rule(
    rule_id: str,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    if analyzer.delete_rule(rule_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/alerts")
def list_alerts(
    status: str | None = None,
    limit: int = 100,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    alerts = analyzer.get_alerts(status, limit)
    return [
        {"id": a.id, "rule_id": a.rule_id, "message": a.message, "severity": a.severity, "status": a.status}
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    principal=Depends(get_current_principal),
):
    analyzer = get_log_analyzer()
    if analyzer.resolve_alert(alert_id):
        return {"status": "ok"}
    return {"error": "Not found"}
