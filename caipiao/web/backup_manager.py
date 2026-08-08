"""数据备份系统：备份、恢复、归档策略。"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..log import get_logger

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
        self._records: list[BackupRecord] = []
        self._restore_points: list[RestorePoint] = []

    def create_config(self, config: BackupConfig) -> BackupConfig:
        self._configs[config.id] = config
        return config

    def get_config(self, config_id: str) -> BackupConfig | None:
        return self._configs.get(config_id)

    def list_configs(self) -> list[BackupConfig]:
        return list(self._configs.values())

    def delete_config(self, config_id: str) -> bool:
        if config_id in self._configs:
            del self._configs[config_id]
            return True
        return False

    def execute_backup(self, config_id: str) -> BackupRecord | None:
        config = self._configs.get(config_id)
        if not config:
            return None

        record = BackupRecord(
            id=str(uuid.uuid4())[:8],
            config_id=config_id,
            backup_type=config.backup_type,
            status="running",
        )
        self._records.append(record)

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

        return record

    def get_records(self, config_id: str | None = None, limit: int = 50) -> list[BackupRecord]:
        records = self._records
        if config_id:
            records = [r for r in records if r.config_id == config_id]
        return records[-limit:]

    def create_restore_point(self, backup_id: str, name: str, description: str = "") -> RestorePoint:
        point = RestorePoint(
            id=str(uuid.uuid4())[:8],
            backup_id=backup_id,
            name=name,
            description=description,
        )
        self._restore_points.append(point)
        return point

    def restore(self, restore_point_id: str, target_dir: str) -> bool:
        point = next((p for p in self._restore_points if p.id == restore_point_id), None)
        if not point:
            return False

        record = next((r for r in self._records if r.id == point.backup_id), None)
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
        return [r for r in self._records if r.started_at < cutoff and r.status == "completed"]

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
        total_backups = len(self._records)
        successful = sum(1 for r in self._records if r.status == "completed")
        failed = sum(1 for r in self._records if r.status == "failed")
        total_size = sum(r.file_size for r in self._records if r.status == "completed")

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
    return _manager
