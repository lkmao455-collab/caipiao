"""用户行为分析路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..behavior_analyzer import UserAction, get_behavior_analyzer
from ..deps import get_current_principal

router = APIRouter(prefix="/behavior", tags=["behavior"])


class SessionStart(BaseModel):
    device: str = ""
    browser: str = ""
    os: str = ""
    ip: str = ""


class PageViewTrack(BaseModel):
    session_id: str
    page: str
    title: str = ""
    referrer: str = ""


class ActionTrack(BaseModel):
    session_id: str
    action_type: str
    target: str
    value: str = ""
    x: float = 0
    y: float = 0


@router.post("/sessions")
def start_session(
    req: SessionStart,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    session_id = analyzer.start_session(
        user_id=principal.id,
        device=req.device,
        browser=req.browser,
        os=req.os,
        ip=req.ip,
    )
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/end")
def end_session(
    session_id: str,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    analyzer.end_session(session_id)
    return {"status": "ok"}


@router.post("/pageview")
def track_pageview(
    req: PageViewTrack,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    analyzer.track_pageview(req.session_id, req.page, req.title, req.referrer)
    return {"status": "ok"}


@router.post("/action")
def track_action(
    req: ActionTrack,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    action = UserAction(
        action_type=req.action_type,
        target=req.target,
        value=req.value,
        x=req.x,
        y=req.y,
    )
    analyzer.track_action(req.session_id, action)
    return {"status": "ok"}


@router.get("/overview")
def get_overview(
    minutes: int = 60,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    return analyzer.get_overview(minutes)


@router.get("/retention")
def get_retention(
    days: int = 30,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    return analyzer.analyze_retention(days)


@router.get("/paths")
def get_paths(
    limit: int = 20,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    return {"paths": analyzer.analyze_paths(limit)}


@router.get("/heatmap")
def get_heatmap(
    page: str,
    principal=Depends(get_current_principal),
):
    analyzer = get_behavior_analyzer()
    return {"heatmap": analyzer.get_click_heatmap(page)}
