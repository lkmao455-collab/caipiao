"""配置管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config_manager import get_config_manager
from ..deps import get_current_principal

router = APIRouter(prefix="/config", tags=["config"])


class ConfigSet(BaseModel):
    key: str
    value: any
    value_type: str = "string"
    description: str = ""
    category: str = "general"
    is_secret: bool = False


class ConfigBulkUpdate(BaseModel):
    configs: dict[str, any]


@router.get("")
def list_configs(
    category: str | None = None,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    if category:
        items = mgr.get_by_category(category)
    else:
        items = mgr.get_all(include_secrets=False)
    return [
        {
            "key": item.key,
            "value": item.value,
            "value_type": item.value_type,
            "description": item.description,
            "category": item.category,
            "is_secret": item.is_secret,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


@router.get("/{key}")
def get_config(
    key: str,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    value = mgr.get(key)
    if value is None:
        return {"error": "Config not found"}
    return {"key": key, "value": value}


@router.post("")
def set_config(
    req: ConfigSet,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    mgr.set(
        key=req.key,
        value=req.value,
        value_type=req.value_type,
        description=req.description,
        category=req.category,
        is_secret=req.is_secret,
        updated_by=principal.id,
    )
    return {"status": "ok", "key": req.key}


@router.post("/bulk")
def bulk_update(
    req: ConfigBulkUpdate,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    mgr.update_many(req.configs, updated_by=principal.id)
    return {"status": "ok", "updated": len(req.configs)}


@router.delete("/{key}")
def delete_config(
    key: str,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    if not mgr.delete(key):
        return {"error": "Cannot delete"}
    return {"status": "ok"}


@router.post("/versions")
def create_version(
    description: str = "",
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    version = mgr.create_version(description=description, created_by=principal.id)
    return {"version": version.version, "created_at": version.created_at}


@router.get("/versions/list")
def list_versions(
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    return [
        {"version": v.version, "description": v.description, "created_at": v.created_at, "items_count": len(v.items)}
        for v in mgr.get_versions()
    ]


@router.post("/rollback/{version}")
def rollback(
    version: int,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    if not mgr.rollback(version):
        return {"error": "Version not found"}
    return {"status": "ok"}


@router.get("/export")
def export_configs(
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    return mgr.export_configs()


@router.post("/import")
def import_configs(
    req: ConfigBulkUpdate,
    principal=Depends(get_current_principal),
):
    mgr = get_config_manager()
    mgr.import_configs(req.configs, updated_by=principal.id)
    return {"status": "ok", "imported": len(req.configs)}
