"""发布管理系统：灰度发布、功能开关、版本管理。"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

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
        self._deployments: list[Deployment] = []

    # 功能开关
    def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        self._flags[flag.key] = flag
        return flag

    def get_flag(self, key: str) -> FeatureFlag | None:
        return self._flags.get(key)

    def list_flags(self) -> list[FeatureFlag]:
        return list(self._flags.values())

    def update_flag(self, key: str, **kwargs) -> bool:
        flag = self._flags.get(key)
        if not flag:
            return False
        for k, v in kwargs.items():
            if hasattr(flag, k):
                setattr(flag, k, v)
        flag.updated_at = time.time()
        return True

    def delete_flag(self, key: str) -> bool:
        if key in self._flags:
            del self._flags[key]
            return True
        return False

    def is_enabled(self, key: str, user_id: str = "", context: dict | None = None) -> bool:
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
        self._versions[version.id] = version
        return version

    def get_version(self, version_id: str) -> ReleaseVersion | None:
        return self._versions.get(version_id)

    def list_versions(self, status: str | None = None) -> list[ReleaseVersion]:
        versions = list(self._versions.values())
        if status:
            versions = [v for v in versions if v.status == status]
        return versions

    def release_version(self, version_id: str, environment: str = "production") -> Deployment | None:
        version = self._versions.get(version_id)
        if not version:
            return None

        deployment = Deployment(
            id=str(uuid.uuid4())[:8],
            version_id=version_id,
            environment=environment,
            status="running",
        )
        self._deployments.append(deployment)

        version.status = environment
        version.released_at = time.time()
        deployment.status = "completed"
        deployment.completed_at = time.time()

        return deployment

    def rollback_version(self, version_id: str) -> bool:
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
        self._deployments.append(deployment)
        version.status = "archived"
        return True

    def get_deployments(self, version_id: str | None = None, limit: int = 50) -> list[Deployment]:
        deployments = self._deployments
        if version_id:
            deployments = [d for d in deployments if d.version_id == version_id]
        return deployments[-limit:]


# 全局发布管理器
_manager: ReleaseManager | None = None


def get_release_manager() -> ReleaseManager:
    global _manager
    if _manager is None:
        _manager = ReleaseManager()
    return _manager
