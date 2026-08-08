"""用户画像路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..user_profile import UserTag, Segment, get_user_profile_system

router = APIRouter(prefix="/profile", tags=["user-profile"])


class TagAdd(BaseModel):
    user_id: str
    name: str
    value: str
    confidence: float = 1.0
    source: str = "manual"


class SegmentCreate(BaseModel):
    name: str
    description: str = ""
    rules: dict = {}


@router.post("/tags")
def add_tag(
    req: TagAdd,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    tag = UserTag(name=req.name, value=req.value, confidence=req.confidence, source=req.source)
    system.add_tag(req.user_id, tag)
    return {"status": "ok"}


@router.get("/tags/{user_id}")
def get_tags(
    user_id: str,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    tags = system.get_tags(user_id)
    return {name: tag.value for name, tag in tags.items()}


@router.delete("/tags/{user_id}/{tag_name}")
def remove_tag(
    user_id: str,
    tag_name: str,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    if system.remove_tag(user_id, tag_name):
        return {"status": "ok"}
    return {"error": "Tag not found"}


@router.get("/summary/{user_id}")
def get_summary(
    user_id: str,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    return system.get_profile_summary(user_id)


@router.get("/analytics")
def get_analytics(
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    return system.get_analytics()


@router.post("/segments")
def create_segment(
    req: SegmentCreate,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    segment = Segment(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        rules=req.rules,
    )
    system.create_segment(segment)
    return {"id": segment.id, "name": segment.name}


@router.get("/segments")
def list_segments(
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    return [{"id": s.id, "name": s.name, "description": s.description} for s in system.list_segments()]


@router.get("/segments/{segment_id}/users")
def get_segment_users(
    segment_id: str,
    principal=Depends(get_current_principal),
):
    system = get_user_profile_system()
    users = system.get_segment_users(segment_id)
    return {"users": users, "count": len(users)}
