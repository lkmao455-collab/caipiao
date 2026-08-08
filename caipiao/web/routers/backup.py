"""数据备份路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..backup_manager import BackupConfig, get_backup_manager
from ..deps import get_current_principal

router = APIRouter(prefix="/backup", tags=["backup"])


class BackupConfigCreate(BaseModel):
    name: str
    backup_type: str = "full"
    source_paths: list[str] = []
    destination: str = ""
    retention_days: int = 30
    compression: bool = True


class RestoreRequest(BaseModel):
    restore_point_id: str
    target_dir: str


@router.post("/configs")
def create_config(
    req: BackupConfigCreate,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    config = BackupConfig(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        backup_type=req.backup_type,
        source_paths=req.source_paths,
        destination=req.destination,
        retention_days=req.retention_days,
        compression=req.compression,
    )
    mgr.create_config(config)
    return {"id": config.id, "name": config.name}


@router.get("/configs")
def list_configs(
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    return [
        {"id": c.id, "name": c.name, "backup_type": c.backup_type, "enabled": c.enabled}
        for c in mgr.list_configs()
    ]


@router.delete("/configs/{config_id}")
def delete_config(
    config_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    if mgr.delete_config(config_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/configs/{config_id}/run")
def run_backup(
    config_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    record = mgr.execute_backup(config_id)
    if not record:
        return {"error": "Config not found"}
    return {"id": record.id, "status": record.status}


@router.get("/records")
def list_records(
    config_id: str | None = None,
    limit: int = 50,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    records = mgr.get_records(config_id, limit)
    return [
        {"id": r.id, "config_id": r.config_id, "status": r.status, "file_size": r.file_size, "duration": r.duration}
        for r in records
    ]


@router.post("/restore")
def restore(
    req: RestoreRequest,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    if mgr.restore(req.restore_point_id, req.target_dir):
        return {"status": "ok"}
    return {"error": "Restore failed"}


@router.post("/cleanup")
def cleanup(
    retention_days: int = 30,
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    count = mgr.cleanup_old_backups(retention_days)
    return {"cleaned": count}


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    mgr = get_backup_manager()
    return mgr.get_stats()
