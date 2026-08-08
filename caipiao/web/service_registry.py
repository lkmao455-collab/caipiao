"""服务治理：服务注册、发现、健康检查。"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class ServiceInstance:
    id: str
    name: str
    host: str
    port: int
    protocol: str = "http"
    status: str = "healthy"  # healthy, unhealthy, maintenance
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    health_check_url: str = "/health"


@dataclass
class HealthCheck:
    instance_id: str
    status: str
    response_time: float = 0
    error: str = ""
    checked_at: float = field(default_factory=time.time)


@dataclass
class ServiceRoute:
    path: str
    service: str
    method: str = "*"
    strip_prefix: bool = False
    timeout: float = 30
    retries: int = 3


class ServiceRegistry:
    """服务注册中心：服务注册、发现、健康检查。"""

    def __init__(self):
        self._services: dict[str, dict[str, ServiceInstance]] = {}
        self._health_history: dict[str, list[HealthCheck]] = {}
        self._routes: list[ServiceRoute] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def register(self, instance: ServiceInstance) -> ServiceInstance:
        if instance.name not in self._services:
            self._services[instance.name] = {}
        self._services[instance.name][instance.id] = instance
        logger.info(f"Service registered: {instance.name} ({instance.host}:{instance.port})")
        return instance

    def deregister(self, service_name: str, instance_id: str) -> bool:
        if service_name in self._services and instance_id in self._services[service_name]:
            del self._services[service_name][instance_id]
            if not self._services[service_name]:
                del self._services[service_name]
            return True
        return False

    def get_service(self, service_name: str) -> list[ServiceInstance]:
        return list(self._services.get(service_name, {}).values())

    def get_instance(self, service_name: str, instance_id: str) -> ServiceInstance | None:
        return self._services.get(service_name, {}).get(instance_id)

    def list_services(self) -> dict[str, list[ServiceInstance]]:
        return {name: list(instances.values()) for name, instances in self._services.items()}

    def discover(self, service_name: str, strategy: str = "round_robin") -> ServiceInstance | None:
        instances = [
            i for i in self._services.get(service_name, {}).values()
            if i.status == "healthy"
        ]
        if not instances:
            return None
        if strategy == "round_robin":
            return instances[int(time.time()) % len(instances)]
        elif strategy == "random":
            import random
            return random.choice(instances)
        elif strategy == "least_connections":
            return min(instances, key=lambda i: i.metadata.get("connections", 0))
        return instances[0]

    # 健康检查
    async def check_health(self, instance: ServiceInstance) -> HealthCheck:
        start = time.time()
        check = HealthCheck(instance_id=instance.id, status="unknown")

        try:
            import aiohttp
            url = f"{instance.protocol}://{instance.host}:{instance.port}{instance.health_check_url}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    check.status = "healthy" if resp.status == 200 else "unhealthy"
                    check.response_time = (time.time() - start) * 1000
        except Exception as e:
            check.status = "unhealthy"
            check.error = str(e)

        if instance.id not in self._health_history:
            self._health_history[instance.id] = []
        self._health_history[instance.id].append(check)
        if len(self._health_history[instance.id]) > 100:
            self._health_history[instance.id] = self._health_history[instance.id][-100:]

        instance.status = check.status
        instance.last_heartbeat = time.time()
        return check

    def get_health_history(self, instance_id: str, limit: int = 50) -> list[HealthCheck]:
        return self._health_history.get(instance_id, [])[-limit:]

    # 路由管理
    def add_route(self, route: ServiceRoute):
        self._routes.append(route)

    def get_route(self, path: str) -> ServiceRoute | None:
        for route in self._routes:
            if path.startswith(route.path):
                return route
        return None

    def list_routes(self) -> list[ServiceRoute]:
        return self._routes

    def remove_route(self, path: str) -> bool:
        for i, route in enumerate(self._routes):
            if route.path == path:
                self._routes.pop(i)
                return True
        return False

    # 心跳更新
    def heartbeat(self, service_name: str, instance_id: str) -> bool:
        instance = self.get_instance(service_name, instance_id)
        if instance:
            instance.last_heartbeat = time.time()
            return True
        return False

    async def start_health_checks(self, interval: int = 30):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._health_check_loop(interval))
        logger.info("Health check loop started")

    async def stop_health_checks(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _health_check_loop(self, interval: int):
        while self._running:
            try:
                for service_name, instances in self._services.items():
                    for instance in instances.values():
                        await self.check_health(instance)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Health check error: {e}")

    def get_stats(self) -> dict:
        total_services = len(self._services)
        total_instances = sum(len(instances) for instances in self._services.values())
        healthy = sum(
            1 for instances in self._services.values()
            for i in instances.values() if i.status == "healthy"
        )

        return {
            "total_services": total_services,
            "total_instances": total_instances,
            "healthy_instances": healthy,
            "unhealthy_instances": total_instances - healthy,
            "routes": len(self._routes),
        }


# 全局服务注册中心
_registry: ServiceRegistry | None = None


def get_service_registry() -> ServiceRegistry:
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry
