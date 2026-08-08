"""发布管理系统：灰度发布、功能开关、版本管理。

持久化：功能开关、发布版本、部署记录均写入 web 数据库。部署记录为 append-only，
实例会在每次调用时按需从数据库水合（URL 感知，支持测试隔离与进程重启持久化）。
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


@dataclass
class FeatureFlag:
    key: str
    name: str
    description: str = ""
    enabled: bool = False
    rollout_percentage: float = 0
    target_rules: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ReleaseVersion:
    id: str
    version: str
    name: str
    description: str = ""
    status: str = "draft"  # draft, staging, production, archived
    rollout_percentage: float = 0
    target_audience: str = "all"  # all, beta, internal, custom
    features: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    released_at: float | None = None


@dataclass
class Deployment:
    id: str
    version_id: str
    environment: str  # dev, staging, production
    status: str = "pending"  # pending, running, completed, failed, rolled_back
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    rollback_version: str = ""


class ReleaseManager:
    """发布管理器：功能开关、灰度发布、版本管理。"""

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}
        self._versions: dict[str, ReleaseVersion] = {}
        self._deployments: list[Deployment] = {}
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._flags = {}
        self._versions = {}
        self._deployments = {}
        from .models import (
            DeploymentRow,
            FeatureFlagRow,
            ReleaseVersionRow,
        )

        with _webdb._SessionLocal() as session:
            for row in session.query(FeatureFlagRow).all():
                try:
                    self._flags[row.id] = FeatureFlag(
                        key=row.id,
                        name=row.name,
                        description=row.description,
                        enabled=row.enabled,
                        rollout_percentage=row.rollout_percentage,
                        target_rules=json.loads(row.target_rules_json),
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                except Exception as exc:
                    logger.error("加载功能开关 %s 失败: %s", row.id, exc)
            for row in session.query(ReleaseVersionRow).all():
                try:
                    self._versions[row.id] = ReleaseVersion(
                        id=row.id,
                        version=row.version,
                        name=row.name,
                        description=row.description,
                        status=row.status,
                        rollout_percentage=row.rollout_percentage,
                        target_audience=row.target_audience,
                        features=json.loads(row.features_json),
                        created_at=row.created_at,
                        released_at=row.released_at,
                    )
                except Exception as exc:
                    logger.error("加载发布版本 %s 失败: %s", row.id, exc)
            for row in session.query(DeploymentRow).all():
                try:
                    self._deployments[row.id] = Deployment(
                        id=row.id,
                        version_id=row.version_id,
                        environment=row.environment,
                        status=row.status,
                        started_at=row.started_at,
                        completed_at=row.completed_at,
                        rollback_version=row.rollback_version,
                    )
                except Exception as exc:
                    logger.error("加载部署记录 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_flag(self, key: str) -> None:
        from .models import FeatureFlagRow

        f = self._flags.get(key)
        with _webdb._SessionLocal() as session:
            row = session.get(FeatureFlagRow, key)
            if f is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = {
                "name": f.name,
                "description": f.description,
                "enabled": f.enabled,
                "rollout_percentage": f.rollout_percentage,
                "updated_at": f.updated_at,
                "created_at": f.created_at,
            }
            if row is None:
                session.add(
                    FeatureFlagRow(
                        id=key,
                        target_rules_json=json.dumps(f.target_rules, ensure_ascii=False),
                        **data,
                    )
                )
            else:
                row.name = f.name
                row.description = f.description
                row.enabled = f.enabled
                row.rollout_percentage = f.rollout_percentage
                row.target_rules_json = json.dumps(f.target_rules, ensure_ascii=False)
                row.updated_at = f.updated_at
                row.created_at = f.created_at
            session.commit()

    def _persist_version(self, version_id: str) -> None:
        from .models import ReleaseVersionRow

        v = self._versions.get(version_id)
        with _webdb._SessionLocal() as session:
            row = session.get(ReleaseVersionRow, version_id)
            if v is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                session.add(
                    ReleaseVersionRow(
                        id=v.id,
                        version=v.version,
                        name=v.name,
                        description=v.description,
                        status=v.status,
                        rollout_percentage=v.rollout_percentage,
                        target_audience=v.target_audience,
                        features_json=json.dumps(v.features, ensure_ascii=False),
                        created_at=v.created_at,
                        released_at=v.released_at,
                    )
                )
            else:
                row.version = v.version
                row.name = v.name
                row.description = v.description
                row.status = v.status
                row.rollout_percentage = v.rollout_percentage
                row.target_audience = v.target_audience
                row.features_json = json.dumps(v.features, ensure_ascii=False)
                row.created_at = v.created_at
                row.released_at = v.released_at
            session.commit()

    def _persist_deployment(self, deployment_id: str) -> None:
        from .models import DeploymentRow

        d = self._deployments.get(deployment_id)
        if d is None:
            return
        with _webdb._SessionLocal() as session:
            session.add(
                DeploymentRow(
                    id=d.id,
                    version_id=d.version_id,
                    environment=d.environment,
                    status=d.status,
                    started_at=d.started_at,
                    completed_at=d.completed_at,
                    rollback_version=d.rollback_version,
                )
            )
            session.commit()

    # 功能开关
    def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        self._ensure_loaded()
        self._flags[flag.key] = flag
        self._persist_flag(flag.key)
        return flag

    def get_flag(self, key: str) -> FeatureFlag | None:
        self._ensure_loaded()
        return self._flags.get(key)

    def list_flags(self) -> list[FeatureFlag]:
        self._ensure_loaded()
        return list(self._flags.values())

    def update_flag(self, key: str, **kwargs) -> bool:
        self._ensure_loaded()
        flag = self._flags.get(key)
        if not flag:
            return False
        for k, v in kwargs.items():
            if hasattr(flag, k):
                setattr(flag, k, v)
        flag.updated_at = time.time()
        self._persist_flag(key)
        return True

    def delete_flag(self, key: str) -> bool:
        self._ensure_loaded()
        if key in self._flags:
            del self._flags[key]
            self._persist_flag(key)
            return True
        return False

    def is_enabled(self, key: str, user_id: str = "", context: dict | None = None) -> bool:
        self._ensure_loaded()
        flag = self._flags.get(key)
        if not flag or not flag.enabled:
            return False

        if flag.rollout_percentage >= 100:
            return True
        if flag.rollout_percentage <= 0:
            return False

        if user_id:
            hash_val = int(hashlib.md5(f"{key}:{user_id}".encode()).hexdigest(), 16) % 100
            return hash_val < flag.rollout_percentage

        return flag.rollout_percentage > 50

    def get_variant(self, key: str, user_id: str, variants: list[str]) -> str:
        if not self.is_enabled(key, user_id):
            return variants[0] if variants else ""
        hash_val = int(hashlib.md5(f"{key}:{user_id}".encode()).hexdigest(), 16) % len(variants)
        return variants[hash_val]

    # 版本管理
    def create_version(self, version: ReleaseVersion) -> ReleaseVersion:
        self._ensure_loaded()
        self._versions[version.id] = version
        self._persist_version(version.id)
        return version

    def get_version(self, version_id: str) -> ReleaseVersion | None:
        self._ensure_loaded()
        return self._versions.get(version_id)

    def list_versions(self, status: str | None = None) -> list[ReleaseVersion]:
        self._ensure_loaded()
        versions = list(self._versions.values())
        if status:
            versions = [v for v in versions if v.status == status]
        return versions

    def release_version(self, version_id: str, environment: str = "production") -> Deployment | None:
        self._ensure_loaded()
        version = self._versions.get(version_id)
        if not version:
            return None

        deployment = Deployment(
            id=str(uuid.uuid4())[:8],
            version_id=version_id,
            environment=environment,
            status="running",
        )
        self._deployments[deployment.id] = deployment

        version.status = environment
        version.released_at = time.time()
        deployment.status = "completed"
        deployment.completed_at = time.time()

        self._persist_version(version_id)
        self._persist_deployment(deployment.id)
        return deployment

    def rollback_version(self, version_id: str) -> bool:
        self._ensure_loaded()
        version = self._versions.get(version_id)
        if not version:
            return False

        deployment = Deployment(
            id=str(uuid.uuid4())[:8],
            version_id=version_id,
            environment=version.status,
            status="rolled_back",
            rollback_version=version.version,
        )
        self._deployments[deployment.id] = deployment
        version.status = "archived"
        self._persist_version(version_id)
        self._persist_deployment(deployment.id)
        return True

    def get_deployments(self, version_id: str | None = None, limit: int = 50) -> list[Deployment]:
        self._ensure_loaded()
        deployments = list(self._deployments.values())
        if version_id:
            deployments = [d for d in deployments if d.version_id == version_id]
        return deployments[-limit:]


# 全局发布管理器
_manager: ReleaseManager | None = None


def get_release_manager() -> ReleaseManager:
    global _manager
    if _manager is None:
        _manager = ReleaseManager()
    _manager._ensure_loaded()
    return _manager
