"""数据备份系统：备份、恢复、归档策略。

持久化：备份配置、备份执行记录、恢复点定义写入 web 数据库（核心层零侵入）。
实际备份文件保留在磁盘（_backup_dir），记录仅持久化其元数据引用。实例会在每次调用时
按需从数据库水合（URL 感知，支持测试隔离与进程重启持久化）。
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


@dataclass
class BackupConfig:
    id: str
    name: str
    backup_type: str  # full, incremental, differential
    source_paths: list[str] = field(default_factory=list)
    destination: str = ""
    schedule: str = ""
    retention_days: int = 30
    compression: bool = True
    encryption: bool = False
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class BackupRecord:
    id: str
    config_id: str
    status: str = "pending"  # pending, running, completed, failed
    backup_type: str = "full"
    file_path: str = ""
    file_size: int = 0
    compressed_size: int = 0
    duration: float = 0
    error: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


@dataclass
class RestorePoint:
    id: str
    backup_id: str
    name: str
    description: str = ""
    created_at: float = field(default_factory=time.time)


class BackupManager:
    """备份管理器：备份、恢复、归档。"""

    def __init__(self, backup_dir: str = ".caipiao/backups"):
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._configs: dict[str, BackupConfig] = {}
        self._records: dict[str, BackupRecord] = {}
        self._restore_points: dict[str, RestorePoint] = {}
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._configs = {}
        self._records = {}
        self._restore_points = {}
        from .models import (
            BackupConfigRow,
            BackupRecordRow,
            RestorePointRow,
        )

        with _webdb._SessionLocal() as session:
            for row in session.query(BackupConfigRow).all():
                try:
                    self._configs[row.id] = BackupConfig(
                        id=row.id,
                        name=row.name,
                        backup_type=row.backup_type,
                        source_paths=json.loads(row.source_paths_json),
                        destination=row.destination,
                        schedule=row.schedule,
                        retention_days=row.retention_days,
                        compression=row.compression,
                        encryption=row.encryption,
                        enabled=row.enabled,
                        created_at=row.created_at,
                    )
                except Exception as exc:
                    logger.error("加载备份配置 %s 失败: %s", row.id, exc)
            for row in session.query(BackupRecordRow).all():
                try:
                    self._records[row.id] = BackupRecord(
                        id=row.id,
                        config_id=row.config_id,
                        status=row.status,
                        backup_type=row.backup_type,
                        file_path=row.file_path,
                        file_size=row.file_size,
                        compressed_size=row.compressed_size,
                        duration=row.duration,
                        error=row.error,
                        started_at=row.started_at,
                        completed_at=row.completed_at,
                    )
                except Exception as exc:
                    logger.error("加载备份记录 %s 失败: %s", row.id, exc)
            for row in session.query(RestorePointRow).all():
                try:
                    self._restore_points[row.id] = RestorePoint(
                        id=row.id,
                        backup_id=row.backup_id,
                        name=row.name,
                        description=row.description,
                        created_at=row.created_at,
                    )
                except Exception as exc:
                    logger.error("加载恢复点 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_config(self, config_id: str) -> None:
        from .models import BackupConfigRow

        c = self._configs.get(config_id)
        with _webdb._SessionLocal() as session:
            row = session.get(BackupConfigRow, config_id)
            if c is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                session.add(
                    BackupConfigRow(
                        id=c.id,
                        name=c.name,
                        backup_type=c.backup_type,
                        source_paths_json=json.dumps(c.source_paths, ensure_ascii=False),
                        destination=c.destination,
                        schedule=c.schedule,
                        retention_days=c.retention_days,
                        compression=c.compression,
                        encryption=c.encryption,
                        enabled=c.enabled,
                        created_at=c.created_at,
                    )
                )
            else:
                row.name = c.name
                row.backup_type = c.backup_type
                row.source_paths_json = json.dumps(c.source_paths, ensure_ascii=False)
                row.destination = c.destination
                row.schedule = c.schedule
                row.retention_days = c.retention_days
                row.compression = c.compression
                row.encryption = c.encryption
                row.enabled = c.enabled
                row.created_at = c.created_at
            session.commit()

    def _persist_record(self, record_id: str) -> None:
        from .models import BackupRecordRow

        r = self._records.get(record_id)
        if r is None:
            return
        with _webdb._SessionLocal() as session:
            row = session.get(BackupRecordRow, record_id)
            if row is None:
                session.add(
                    BackupRecordRow(
                        id=r.id,
                        config_id=r.config_id,
                        status=r.status,
                        backup_type=r.backup_type,
                        file_path=r.file_path,
                        file_size=r.file_size,
                        compressed_size=r.compressed_size,
                        duration=r.duration,
                        error=r.error,
                        started_at=r.started_at,
                        completed_at=r.completed_at,
                    )
                )
            else:
                row.status = r.status
                row.file_path = r.file_path
                row.file_size = r.file_size
                row.compressed_size = r.compressed_size
                row.duration = r.duration
                row.error = r.error
                row.completed_at = r.completed_at
            session.commit()

    def _persist_restore_point(self, point_id: str) -> None:
        from .models import RestorePointRow

        p = self._restore_points.get(point_id)
        if p is None:
            return
        with _webdb._SessionLocal() as session:
            row = session.get(RestorePointRow, point_id)
            if row is None:
                session.add(
                    RestorePointRow(
                        id=p.id,
                        backup_id=p.backup_id,
                        name=p.name,
                        description=p.description,
                        created_at=p.created_at,
                    )
                )
            else:
                row.backup_id = p.backup_id
                row.name = p.name
                row.description = p.description
                row.created_at = p.created_at
            session.commit()

    def create_config(self, config: BackupConfig) -> BackupConfig:
        self._ensure_loaded()
        self._configs[config.id] = config
        self._persist_config(config.id)
        return config

    def get_config(self, config_id: str) -> BackupConfig | None:
        self._ensure_loaded()
        return self._configs.get(config_id)

    def list_configs(self) -> list[BackupConfig]:
        self._ensure_loaded()
        return list(self._configs.values())

    def delete_config(self, config_id: str) -> bool:
        self._ensure_loaded()
        if config_id in self._configs:
            del self._configs[config_id]
            self._persist_config(config_id)
            return True
        return False

    def execute_backup(self, config_id: str) -> BackupRecord | None:
        self._ensure_loaded()
        config = self._configs.get(config_id)
        if not config:
            return None

        record = BackupRecord(
            id=str(uuid.uuid4())[:8],
            config_id=config_id,
            backup_type=config.backup_type,
            status="running",
        )
        self._records[record.id] = record

        try:
            backup_path = self._backup_dir / f"{record.id}_{int(time.time())}"
            backup_path.mkdir(parents=True, exist_ok=True)

            total_size = 0
            for source in config.source_paths:
                source_path = Path(source)
                if source_path.exists():
                    if source_path.is_file():
                        dest = backup_path / source_path.name
                        shutil.copy2(source_path, dest)
                        total_size += source_path.stat().st_size
                    elif source_path.is_dir():
                        dest = backup_path / source_path.name
                        shutil.copytree(source_path, dest, dirs_exist_ok=True)
                        total_size += sum(f.stat().st_size for f in source_path.rglob("*") if f.is_file())

            record.file_path = str(backup_path)
            record.file_size = total_size
            record.compressed_size = total_size
            record.status = "completed"
            record.completed_at = time.time()
            record.duration = record.completed_at - record.started_at

        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            logger.error(f"Backup failed: {e}")

        self._persist_record(record.id)
        return record

    def get_records(self, config_id: str | None = None, limit: int = 50) -> list[BackupRecord]:
        self._ensure_loaded()
        records = list(self._records.values())
        if config_id:
            records = [r for r in records if r.config_id == config_id]
        return records[-limit:]

    def create_restore_point(self, backup_id: str, name: str, description: str = "") -> RestorePoint:
        self._ensure_loaded()
        point = RestorePoint(
            id=str(uuid.uuid4())[:8],
            backup_id=backup_id,
            name=name,
            description=description,
        )
        self._restore_points[point.id] = point
        self._persist_restore_point(point.id)
        return point

    def restore(self, restore_point_id: str, target_dir: str) -> bool:
        self._ensure_loaded()
        point = self._restore_points.get(restore_point_id)
        if not point:
            return False

        record = self._records.get(point.backup_id)
        if not record or record.status != "completed":
            return False

        backup_path = Path(record.file_path)
        target_path = Path(target_dir)

        if not backup_path.exists():
            return False

        try:
            if backup_path.is_dir():
                shutil.copytree(backup_path, target_path, dirs_exist_ok=True)
            else:
                shutil.copy2(backup_path, target_path)
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def get_old_backups(self, retention_days: int = 30) -> list[BackupRecord]:
        cutoff = time.time() - retention_days * 86400
        return [r for r in self._records.values() if r.started_at < cutoff and r.status == "completed"]

    def cleanup_old_backups(self, retention_days: int = 30) -> int:
        old = self.get_old_backups(retention_days)
        for record in old:
            path = Path(record.file_path)
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        return len(old)

    def get_stats(self) -> dict:
        self._ensure_loaded()
        total_backups = len(self._records)
        successful = sum(1 for r in self._records.values() if r.status == "completed")
        failed = sum(1 for r in self._records.values() if r.status == "failed")
        total_size = sum(r.file_size for r in self._records.values() if r.status == "completed")

        return {
            "total_configs": len(self._configs),
            "total_backups": total_backups,
            "successful_backups": successful,
            "failed_backups": failed,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "restore_points": len(self._restore_points),
        }


# 全局备份管理器
_manager: BackupManager | None = None


def get_backup_manager() -> BackupManager:
    global _manager
    if _manager is None:
        _manager = BackupManager()
    _manager._ensure_loaded()
    return _manager
