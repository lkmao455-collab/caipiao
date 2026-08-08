"""服务治理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..service_registry import ServiceInstance, ServiceRoute, get_service_registry

router = APIRouter(prefix="/services", tags=["services"])


class ServiceRegister(BaseModel):
    name: str
    host: str
    port: int
    protocol: str = "http"
    health_check_url: str = "/health"
    metadata: dict = {}


class RouteCreate(BaseModel):
    path: str
    service: str
    method: str = "*"
    strip_prefix: bool = False
    timeout: float = 30
    retries: int = 3


@router.post("/register")
def register_service(
    req: ServiceRegister,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    instance = ServiceInstance(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        host=req.host,
        port=req.port,
        protocol=req.protocol,
        health_check_url=req.health_check_url,
        metadata=req.metadata,
    )
    registry.register(instance)
    return {"id": instance.id, "name": instance.name}


@router.post("/deregister")
def deregister_service(
    service_name: str,
    instance_id: str,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    if registry.deregister(service_name, instance_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/list")
def list_services(
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    services = registry.list_services()
    return {
        name: [
            {"id": i.id, "host": i.host, "port": i.port, "status": i.status}
            for i in instances
        ]
        for name, instances in services.items()
    }


@router.get("/discover/{service_name}")
def discover_service(
    service_name: str,
    strategy: str = "round_robin",
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    instance = registry.discover(service_name, strategy)
    if not instance:
        return {"error": "No healthy instances"}
    return {"id": instance.id, "host": instance.host, "port": instance.port, "protocol": instance.protocol}


@router.post("/heartbeat")
def heartbeat(
    service_name: str,
    instance_id: str,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    if registry.heartbeat(service_name, instance_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/health/{instance_id}")
def get_health(
    instance_id: str,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    history = registry.get_health_history(instance_id)
    return [
        {"status": h.status, "response_time": h.response_time, "checked_at": h.checked_at}
        for h in history
    ]


@router.post("/routes")
def add_route(
    req: RouteCreate,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    route = ServiceRoute(
        path=req.path,
        service=req.service,
        method=req.method,
        strip_prefix=req.strip_prefix,
        timeout=req.timeout,
        retries=req.retries,
    )
    registry.add_route(route)
    return {"path": route.path, "service": route.service}


@router.get("/routes")
def list_routes(
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    return [
        {"path": r.path, "service": r.service, "method": r.method}
        for r in registry.list_routes()
    ]


@router.delete("/routes/{path}")
def delete_route(
    path: str,
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    if registry.remove_route(path):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    registry = get_service_registry()
    return registry.get_stats()
