"""多租户路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..tenant_manager import get_tenant_manager

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    name: str
    plan: str = "free"


class TenantUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    settings: dict | None = None


class UserAdd(BaseModel):
    user_id: str
    role: str = "member"


@router.post("")
def create_tenant(
    req: TenantCreate,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    tenant = mgr.create_tenant(req.name, req.plan)
    return {"id": tenant.id, "name": tenant.name, "plan": tenant.plan}


@router.get("")
def list_tenants(
    status: str | None = None,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    tenants = mgr.list_tenants(status)
    return [
        {"id": t.id, "name": t.name, "plan": t.plan, "status": t.status}
        for t in tenants
    ]


@router.get("/{tenant_id}")
def get_tenant(
    tenant_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    tenant = mgr.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Not found"}
    return {"id": tenant.id, "name": tenant.name, "plan": tenant.plan, "status": tenant.status}


@router.put("/{tenant_id}")
def update_tenant(
    tenant_id: str,
    req: TenantUpdate,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if mgr.update_tenant(tenant_id, **kwargs):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.delete("/{tenant_id}")
def delete_tenant(
    tenant_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    if mgr.delete_tenant(tenant_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/{tenant_id}/users")
def add_user(
    tenant_id: str,
    req: UserAdd,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    tenant_user = mgr.add_user(req.user_id, tenant_id, req.role)
    if not tenant_user:
        return {"error": "Tenant not found"}
    return {"status": "ok", "role": tenant_user.role}


@router.get("/{tenant_id}/users")
def list_users(
    tenant_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    users = mgr.get_tenant_users(tenant_id)
    return [{"user_id": u.user_id, "role": u.role} for u in users]


@router.delete("/{tenant_id}/users/{user_id}")
def remove_user(
    tenant_id: str,
    user_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    if mgr.remove_user(user_id, tenant_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/{tenant_id}/stats")
def get_stats(
    tenant_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    return mgr.get_tenant_stats(tenant_id)


@router.get("/{tenant_id}/usage")
def get_usage(
    tenant_id: str,
    principal=Depends(get_current_principal),
):
    mgr = get_tenant_manager()
    usage = mgr.get_usage(tenant_id)
    if not usage:
        return {"error": "Not found"}
    return {
        "storage_mb": usage.storage_mb,
        "api_calls": usage.api_calls,
        "users": usage.users,
        "projects": usage.projects,
    }
