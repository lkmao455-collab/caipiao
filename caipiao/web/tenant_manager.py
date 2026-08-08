"""多租户系统：租户管理、资源隔离、配额控制。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

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

    def create_tenant(self, name: str, plan: str = "free") -> Tenant:
        tenant = Tenant(
            id=str(uuid.uuid4())[:8],
            name=name,
            plan=plan,
            quota=self._plan_limits.get(plan, self._plan_limits["free"]),
        )
        self._tenants[tenant.id] = tenant
        self._usage[tenant.id] = ResourceUsage(tenant_id=tenant.id)
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self, status: str | None = None) -> list[Tenant]:
        tenants = list(self._tenants.values())
        if status:
            tenants = [t for t in tenants if t.status == status]
        return tenants

    def update_tenant(self, tenant_id: str, **kwargs) -> bool:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        tenant.updated_at = time.time()
        return True

    def delete_tenant(self, tenant_id: str) -> bool:
        if tenant_id in self._tenants:
            self._tenants[tenant_id].status = "deleted"
            return True
        return False

    def suspend_tenant(self, tenant_id: str) -> bool:
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = "suspended"
            return True
        return False

    def activate_tenant(self, tenant_id: str) -> bool:
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = "active"
            return True
        return False

    # 用户管理
    def add_user(self, user_id: str, tenant_id: str, role: str = "member") -> TenantUser | None:
        if tenant_id not in self._tenants:
            return None
        tenant_user = TenantUser(user_id=user_id, tenant_id=tenant_id, role=role)
        self._users[f"{user_id}:{tenant_id}"] = tenant_user
        usage = self._usage.get(tenant_id)
        if usage:
            usage.users += 1
        return tenant_user

    def remove_user(self, user_id: str, tenant_id: str) -> bool:
        key = f"{user_id}:{tenant_id}"
        if key in self._users:
            del self._users[key]
            usage = self._usage.get(tenant_id)
            if usage and usage.users > 0:
                usage.users -= 1
            return True
        return False

    def get_tenant_users(self, tenant_id: str) -> list[TenantUser]:
        return [u for u in self._users.values() if u.tenant_id == tenant_id]

    def get_user_tenants(self, user_id: str) -> list[TenantUser]:
        return [u for u in self._users.values() if u.user_id == user_id]

    # 配额检查
    def check_quota(self, tenant_id: str, resource: str, amount: int = 1) -> bool:
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
        usage = self._usage.get(tenant_id)
        if not usage:
            return
        if resource == "storage":
            usage.storage_mb += amount
        elif resource == "api_calls":
            usage.api_calls += int(amount)
        elif resource == "projects":
            usage.projects += int(amount)

    def get_usage(self, tenant_id: str) -> ResourceUsage | None:
        return self._usage.get(tenant_id)

    def get_tenant_stats(self, tenant_id: str) -> dict:
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
    return _manager
