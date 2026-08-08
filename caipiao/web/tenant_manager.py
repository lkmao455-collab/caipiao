"""多租户系统：租户管理、资源隔离、配额控制。

持久化：租户定义、成员关系、资源用量快照均写入 web 数据库（核心层零侵入）。
运行时状态（如 plan 默认配额表）仍为内存配置；实例会在每次调用时按需从数据库
水合（URL 感知，支持测试隔离与进程重启持久化）。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


@dataclass
class TenantQuota:
    max_users: int = 100
    max_storage_mb: int = 1024
    max_api_calls: int = 10000
    max_projects: int = 10
    max_storage_used_mb: float = 0
    api_calls_used: int = 0


@dataclass
class Tenant:
    id: str
    name: str
    plan: str = "free"  # free, basic, pro, enterprise
    status: str = "active"  # active, suspended, deleted
    quota: TenantQuota = field(default_factory=TenantQuota)
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class TenantUser:
    user_id: str
    tenant_id: str
    role: str = "member"  # owner, admin, member, viewer
    joined_at: float = field(default_factory=time.time)


@dataclass
class ResourceUsage:
    tenant_id: str
    storage_mb: float = 0
    api_calls: int = 0
    users: int = 0
    projects: int = 0
    period_start: float = field(default_factory=time.time)


def _quota_to_dict(q: TenantQuota) -> dict[str, Any]:
    return {
        "max_users": q.max_users,
        "max_storage_mb": q.max_storage_mb,
        "max_api_calls": q.max_api_calls,
        "max_projects": q.max_projects,
        "max_storage_used_mb": q.max_storage_used_mb,
        "api_calls_used": q.api_calls_used,
    }


def _dict_to_quota(d: dict[str, Any]) -> TenantQuota:
    return TenantQuota(
        max_users=d.get("max_users", 100),
        max_storage_mb=d.get("max_storage_mb", 1024),
        max_api_calls=d.get("max_api_calls", 10000),
        max_projects=d.get("max_projects", 10),
        max_storage_used_mb=d.get("max_storage_used_mb", 0),
        api_calls_used=d.get("api_calls_used", 0),
    )


def _tenant_to_dict(t: Tenant) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "plan": t.plan,
        "status": t.status,
        "quota": _quota_to_dict(t.quota),
        "settings": t.settings,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def _dict_to_tenant(d: dict[str, Any]) -> Tenant:
    return Tenant(
        id=d["id"],
        name=d["name"],
        plan=d.get("plan", "free"),
        status=d.get("status", "active"),
        quota=_dict_to_quota(d.get("quota", {})),
        settings=d.get("settings", {}),
        created_at=d.get("created_at", time.time),
        updated_at=d.get("updated_at", time.time),
    )


def _tenant_user_to_dict(u: TenantUser) -> dict[str, Any]:
    return {
        "user_id": u.user_id,
        "tenant_id": u.tenant_id,
        "role": u.role,
        "joined_at": u.joined_at,
    }


def _dict_to_tenant_user(d: dict[str, Any]) -> TenantUser:
    return TenantUser(
        user_id=d["user_id"],
        tenant_id=d["tenant_id"],
        role=d.get("role", "member"),
        joined_at=d.get("joined_at", time.time),
    )


def _usage_to_dict(u: ResourceUsage) -> dict[str, Any]:
    return {
        "tenant_id": u.tenant_id,
        "storage_mb": u.storage_mb,
        "api_calls": u.api_calls,
        "users": u.users,
        "projects": u.projects,
        "period_start": u.period_start,
    }


def _dict_to_usage(d: dict[str, Any]) -> ResourceUsage:
    return ResourceUsage(
        tenant_id=d["tenant_id"],
        storage_mb=d.get("storage_mb", 0),
        api_calls=d.get("api_calls", 0),
        users=d.get("users", 0),
        projects=d.get("projects", 0),
        period_start=d.get("period_start", time.time),
    )


class TenantManager:
    """租户管理器：租户管理、配额控制、资源隔离。"""

    def __init__(self):
        self._tenants: dict[str, Tenant] = {}
        self._users: dict[str, TenantUser] = {}
        self._usage: dict[str, ResourceUsage] = {}
        self._plan_limits = {
            "free": TenantQuota(max_users=5, max_storage_mb=100, max_api_calls=1000, max_projects=2),
            "basic": TenantQuota(max_users=20, max_storage_mb=512, max_api_calls=5000, max_projects=5),
            "pro": TenantQuota(max_users=100, max_storage_mb=2048, max_api_calls=50000, max_projects=20),
            "enterprise": TenantQuota(max_users=1000, max_storage_mb=10240, max_api_calls=500000, max_projects=100),
        }
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._tenants = {}
        self._users = {}
        self._usage = {}
        from .models import (
            ResourceUsageRow,
            TenantRow,
            TenantUserRow,
        )

        with _webdb._SessionLocal() as session:
            for row in session.query(TenantRow).all():
                try:
                    self._tenants[row.id] = _dict_to_tenant(json.loads(row.data_json))
                except Exception as exc:
                    logger.error("加载租户 %s 失败: %s", row.id, exc)
            for row in session.query(TenantUserRow).all():
                try:
                    u = _dict_to_tenant_user(json.loads(row.data_json))
                    self._users[f"{u.user_id}:{u.tenant_id}"] = u
                except Exception as exc:
                    logger.error("加载租户成员 %s 失败: %s", row.id, exc)
            for row in session.query(ResourceUsageRow).all():
                try:
                    u = _dict_to_usage(json.loads(row.data_json))
                    self._usage[u.tenant_id] = u
                except Exception as exc:
                    logger.error("加载资源用量 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_tenant(self, tenant_id: str) -> None:
        from .models import TenantRow

        t = self._tenants.get(tenant_id)
        with _webdb._SessionLocal() as session:
            row = session.get(TenantRow, tenant_id)
            if t is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_tenant_to_dict(t), ensure_ascii=False)
            if row is None:
                session.add(
                    TenantRow(
                        id=tenant_id,
                        name=t.name,
                        plan=t.plan,
                        status=t.status,
                        data_json=data,
                        updated_at=time.time(),
                    )
                )
            else:
                row.name = t.name
                row.plan = t.plan
                row.status = t.status
                row.data_json = data
                row.updated_at = time.time()
            session.commit()

    def _persist_user(self, user_id: str, tenant_id: str) -> None:
        from .models import TenantUserRow

        key = f"{user_id}:{tenant_id}"
        u = self._users.get(key)
        with _webdb._SessionLocal() as session:
            row = session.get(TenantUserRow, key)
            if u is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_tenant_user_to_dict(u), ensure_ascii=False)
            if row is None:
                session.add(
                    TenantUserRow(
                        id=key,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        role=u.role,
                        data_json=data,
                        updated_at=time.time(),
                    )
                )
            else:
                row.tenant_id = tenant_id
                row.user_id = user_id
                row.role = u.role
                row.data_json = data
                row.updated_at = time.time()
            session.commit()

    def _persist_usage(self, tenant_id: str) -> None:
        from .models import ResourceUsageRow

        u = self._usage.get(tenant_id)
        with _webdb._SessionLocal() as session:
            row = session.get(ResourceUsageRow, tenant_id)
            data = json.dumps(_usage_to_dict(u), ensure_ascii=False) if u is not None else "{}"
            if u is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                session.add(
                    ResourceUsageRow(
                        id=tenant_id,
                        tenant_id=tenant_id,
                        data_json=data,
                        updated_at=time.time(),
                    )
                )
            else:
                row.data_json = data
                row.updated_at = time.time()
            session.commit()

    def create_tenant(self, name: str, plan: str = "free") -> Tenant:
        self._ensure_loaded()
        tenant = Tenant(
            id=str(uuid.uuid4())[:8],
            name=name,
            plan=plan,
            quota=self._plan_limits.get(plan, self._plan_limits["free"]),
        )
        self._tenants[tenant.id] = tenant
        self._usage[tenant.id] = ResourceUsage(tenant_id=tenant.id)
        self._persist_tenant(tenant.id)
        self._persist_usage(tenant.id)
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        self._ensure_loaded()
        return self._tenants.get(tenant_id)

    def list_tenants(self, status: str | None = None) -> list[Tenant]:
        self._ensure_loaded()
        tenants = list(self._tenants.values())
        if status:
            tenants = [t for t in tenants if t.status == status]
        return tenants

    def update_tenant(self, tenant_id: str, **kwargs) -> bool:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        tenant.updated_at = time.time()
        self._persist_tenant(tenant_id)
        return True

    def delete_tenant(self, tenant_id: str) -> bool:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        tenant.status = "deleted"
        self._persist_tenant(tenant_id)
        return True

    def suspend_tenant(self, tenant_id: str) -> bool:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = "suspended"
            self._persist_tenant(tenant_id)
            return True
        return False

    def activate_tenant(self, tenant_id: str) -> bool:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = "active"
            self._persist_tenant(tenant_id)
            return True
        return False

    # 用户管理
    def add_user(self, user_id: str, tenant_id: str, role: str = "member") -> TenantUser | None:
        self._ensure_loaded()
        if tenant_id not in self._tenants:
            return None
        tenant_user = TenantUser(user_id=user_id, tenant_id=tenant_id, role=role)
        self._users[f"{user_id}:{tenant_id}"] = tenant_user
        usage = self._usage.get(tenant_id)
        if usage:
            usage.users += 1
            self._persist_usage(tenant_id)
        self._persist_user(user_id, tenant_id)
        return tenant_user

    def remove_user(self, user_id: str, tenant_id: str) -> bool:
        self._ensure_loaded()
        key = f"{user_id}:{tenant_id}"
        if key in self._users:
            del self._users[key]
            usage = self._usage.get(tenant_id)
            if usage and usage.users > 0:
                usage.users -= 1
                self._persist_usage(tenant_id)
            self._persist_user(user_id, tenant_id)
            return True
        return False

    def get_tenant_users(self, tenant_id: str) -> list[TenantUser]:
        self._ensure_loaded()
        return [u for u in self._users.values() if u.tenant_id == tenant_id]

    def get_user_tenants(self, user_id: str) -> list[TenantUser]:
        self._ensure_loaded()
        return [u for u in self._users.values() if u.user_id == user_id]

    # 配额检查
    def check_quota(self, tenant_id: str, resource: str, amount: int = 1) -> bool:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        usage = self._usage.get(tenant_id)
        if not tenant or not usage:
            return False

        quota = tenant.quota
        if resource == "users":
            return usage.users + amount <= quota.max_users
        elif resource == "storage":
            return usage.storage_mb + amount <= quota.max_storage_mb
        elif resource == "api_calls":
            return usage.api_calls + amount <= quota.max_api_calls
        elif resource == "projects":
            return usage.projects + amount <= quota.max_projects
        return False

    def record_usage(self, tenant_id: str, resource: str, amount: float = 1):
        self._ensure_loaded()
        usage = self._usage.get(tenant_id)
        if not usage:
            return
        if resource == "storage":
            usage.storage_mb += amount
        elif resource == "api_calls":
            usage.api_calls += int(amount)
        elif resource == "projects":
            usage.projects += int(amount)
        self._persist_usage(tenant_id)

    def get_usage(self, tenant_id: str) -> ResourceUsage | None:
        self._ensure_loaded()
        return self._usage.get(tenant_id)

    def get_tenant_stats(self, tenant_id: str) -> dict:
        self._ensure_loaded()
        tenant = self._tenants.get(tenant_id)
        usage = self._usage.get(tenant_id)
        if not tenant or not usage:
            return {}

        quota = tenant.quota
        return {
            "tenant_id": tenant_id,
            "plan": tenant.plan,
            "status": tenant.status,
            "users": {"used": usage.users, "limit": quota.max_users},
            "storage": {"used_mb": round(usage.storage_mb, 2), "limit_mb": quota.max_storage_mb},
            "api_calls": {"used": usage.api_calls, "limit": quota.max_api_calls},
            "projects": {"used": usage.projects, "limit": quota.max_projects},
        }


# 全局租户管理器
_manager: TenantManager | None = None


def get_tenant_manager() -> TenantManager:
    global _manager
    if _manager is None:
        _manager = TenantManager()
    _manager._ensure_loaded()
    return _manager
