"""发布管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..release_manager import FeatureFlag, ReleaseVersion, get_release_manager

router = APIRouter(prefix="/release", tags=["release"])


class FlagCreate(BaseModel):
    key: str
    name: str
    description: str = ""
    enabled: bool = False
    rollout_percentage: float = 0


class FlagUpdate(BaseModel):
    enabled: bool | None = None
    rollout_percentage: float | None = None


class VersionCreate(BaseModel):
    version: str
    name: str
    description: str = ""
    features: list[str] = []


class FlagCheck(BaseModel):
    key: str
    user_id: str = ""


@router.post("/flags")
def create_flag(
    req: FlagCreate,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    flag = FeatureFlag(
        key=req.key,
        name=req.name,
        description=req.description,
        enabled=req.enabled,
        rollout_percentage=req.rollout_percentage,
    )
    mgr.create_flag(flag)
    return {"key": flag.key, "name": flag.name}


@router.get("/flags")
def list_flags(
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    return [
        {"key": f.key, "name": f.name, "enabled": f.enabled, "rollout_percentage": f.rollout_percentage}
        for f in mgr.list_flags()
    ]


@router.put("/flags/{key}")
def update_flag(
    key: str,
    req: FlagUpdate,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    kwargs = {k: v for k, v in req.dict().items() if v is not None}
    if mgr.update_flag(key, **kwargs):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.delete("/flags/{key}")
def delete_flag(
    key: str,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    if mgr.delete_flag(key):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/flags/check")
def check_flag(
    req: FlagCheck,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    enabled = mgr.is_enabled(req.key, req.user_id)
    return {"key": req.key, "enabled": enabled}


@router.post("/versions")
def create_version(
    req: VersionCreate,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    version = ReleaseVersion(
        id=str(__import__("uuid").uuid4())[:8],
        version=req.version,
        name=req.name,
        description=req.description,
        features=req.features,
    )
    mgr.create_version(version)
    return {"id": version.id, "version": version.version}


@router.get("/versions")
def list_versions(
    status: str | None = None,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    return [
        {"id": v.id, "version": v.version, "name": v.name, "status": v.status}
        for v in mgr.list_versions(status)
    ]


@router.post("/versions/{version_id}/release")
def release_version(
    version_id: str,
    environment: str = "production",
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    deployment = mgr.release_version(version_id, environment)
    if not deployment:
        return {"error": "Not found"}
    return {"deployment_id": deployment.id, "status": deployment.status}


@router.post("/versions/{version_id}/rollback")
def rollback_version(
    version_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_release_manager()
    if mgr.rollback_version(version_id):
        return {"status": "ok"}
    return {"error": "Not found"}
