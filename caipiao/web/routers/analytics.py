"""数据分析路由：事件追踪、漏斗分析、A/B 测试。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..analytics import (
    ABTest,
    ABTestVariant,
    FunnelDefinition,
    FunnelStep,
    UserEvent,
    get_analytics,
)
from ..deps import get_current_principal

router = APIRouter(prefix="/analytics", tags=["analytics"])


class EventTrack(BaseModel):
    event_type: str
    event_name: str
    properties: dict = {}
    session_id: str = ""


class FunnelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    steps: list[dict]
    time_window_minutes: int = 60


class ABTestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    variants: list[dict]
    target_metric: str = ""


@router.post("/events")
def track_event(
    req: EventTrack,
    principal=Depends(get_current_principal),
):
    """追踪用户事件。"""
    analytics = get_analytics()
    event = UserEvent(
        event_id=str(uuid.uuid4())[:8],
        user_id=principal.id,
        event_type=req.event_type,
        event_name=req.event_name,
        properties=req.properties,
        session_id=req.session_id or str(uuid.uuid4())[:8],
    )
    analytics.track_event(event)
    return {"status": "ok", "event_id": event.event_id}


@router.get("/overview")
def get_overview(
    minutes: int = 60,
    principal=Depends(get_current_principal),
):
    """获取分析概览。"""
    analytics = get_analytics()
    return analytics.get_overview(minutes)


@router.get("/events/counts")
def get_event_counts(
    event_type: str = "action",
    minutes: int = 60,
    principal=Depends(get_current_principal),
):
    """获取事件计数。"""
    analytics = get_analytics()
    return analytics.get_event_counts(event_type, minutes)


@router.get("/user/{user_id}/events")
def get_user_events(
    user_id: str,
    limit: int = 100,
    principal=Depends(get_current_principal),
):
    """获取用户事件。"""
    analytics = get_analytics()
    events = analytics.get_user_events(user_id, limit)
    return {
        "user_id": user_id,
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "event_name": e.event_name,
                "properties": e.properties,
                "timestamp": e.timestamp,
            }
            for e in events
        ],
    }


# 漏斗分析
@router.post("/funnels")
def create_funnel(
    req: FunnelCreate,
    principal=Depends(get_current_principal),
):
    """创建漏斗。"""
    analytics = get_analytics()
    steps = [FunnelStep(**s) for s in req.steps]
    funnel = FunnelDefinition(
        id=str(uuid.uuid4())[:8],
        name=req.name,
        steps=steps,
        time_window_minutes=req.time_window_minutes,
    )
    analytics.create_funnel(funnel)
    return {"id": funnel.id, "name": funnel.name}


@router.get("/funnels/{funnel_id}/analyze")
def analyze_funnel(
    funnel_id: str,
    minutes: int = 60,
    principal=Depends(get_current_principal),
):
    """分析漏斗转化。"""
    analytics = get_analytics()
    result = analytics.analyze_funnel(funnel_id, minutes)
    if not result:
        return {"error": "漏斗不存在"}
    return {
        "funnel_id": funnel_id,
        "total_users": result.total_users,
        "conversion_rate": result.conversion_rate,
        "steps": result.step_results,
    }


# A/B 测试
@router.post("/ab-tests")
def create_ab_test(
    req: ABTestCreate,
    principal=Depends(get_current_principal),
):
    """创建 A/B 测试。"""
    analytics = get_analytics()
    variants = [ABTestVariant(name=v["name"], weight=v.get("weight", 0.5)) for v in req.variants]
    test = ABTest(
        id=str(uuid.uuid4())[:8],
        name=req.name,
        variants=variants,
        target_metric=req.target_metric,
    )
    analytics.create_ab_test(test)
    return {"id": test.id, "name": test.name}


@router.get("/ab-tests/{test_id}")
def get_ab_test(
    test_id: str,
    principal=Depends(get_current_principal),
):
    """获取 A/B 测试结果。"""
    analytics = get_analytics()
    result = analytics.get_ab_test_results(test_id)
    if not result:
        return {"error": "测试不存在"}
    return result


@router.post("/ab-tests/{test_id}/assign")
def assign_variant(
    test_id: str,
    principal=Depends(get_current_principal),
):
    """为用户分配变体。"""
    analytics = get_analytics()
    variant = analytics.assign_variant(test_id, principal.id)
    if not variant:
        return {"error": "无法分配变体"}
    return {"variant": variant}


@router.post("/ab-tests/{test_id}/convert")
def record_conversion(
    test_id: str,
    variant: str,
    principal=Depends(get_current_principal),
):
    """记录转化。"""
    analytics = get_analytics()
    analytics.record_conversion(test_id, variant)
    return {"status": "ok"}
