"""事件总线：进程内（开发）与 Redis pub/sub（生产）两种实现，统一接口。

- 未设置 ``REDIS_URL`` 时使用内存总线（单进程开发足够）。
- 设置 ``REDIS_URL`` 时使用 Redis pub/sub，跨进程/多副本推送开奖与生成事件。
WebSocket 路由只依赖统一接口 ``subscribe/unsubscribe/publish``，无需感知后端。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Set
from typing import Any, Protocol


class EventBus(Protocol):
    """事件总线接口：订阅/取消订阅/发布。"""

    def subscribe(self) -> asyncio.Queue: ...
    def unsubscribe(self, queue: asyncio.Queue) -> None: ...
    def publish(self, message: dict[str, Any]) -> None: ...


class InMemoryEventBus:
    """进程内事件总线：订阅者各自持有一个 asyncio.Queue。"""

    def __init__(self) -> None:
        self._queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def publish(self, message: dict[str, Any]) -> None:
        for queue in list(self._queues):
            queue.put_nowait(message)


class RedisEventBus:
    """基于 Redis pub/sub 的事件总线（可选依赖 redis>=5）。

    订阅者通过 Redis 订阅频道拿到消息，转发到本地 asyncio.Queue，供 WebSocket 推送。
    """

    def __init__(self, redis_url: str, channel: str = "caipiao:events") -> None:
        import redis
        import redis.asyncio as aioredis  # 延迟导入，未装 redis 时不影响内存总线

        self._redis = aioredis.from_url(redis_url)  # 异步：后台监听
        self._channel = channel
        self._pub = redis.Redis.from_url(redis_url)  # 同步：发布（调用方可能在同步上下文）
        self._queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def _listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            import json

            try:
                payload = json.loads(message["data"])
            except (ValueError, TypeError):
                continue
            for queue in list(self._queues):
                queue.put_nowait(payload)

    def publish(self, message: dict[str, Any]) -> None:
        import json

        self._pub.publish(self._channel, json.dumps(message, default=str))

    def start(self) -> asyncio.Task:
        """启动后台监听任务（在应用 lifespan 中调用）。"""
        return asyncio.create_task(self._listen())


def create_event_bus() -> EventBus:
    """根据环境变量选择总线实现（不在导入时启动后台任务，由 lifespan 启动）。"""
    redis_url = os.getenv("CAIPIAO_WEB_REDIS_URL")
    if redis_url:
        try:
            return RedisEventBus(redis_url)
        except Exception:
            # Redis 不可用（如未安装客户端/无法连接）时回退内存总线，保证可用性
            pass
    return InMemoryEventBus()


# 默认全局总线（开发/无 REDIS_URL 时为内存实现）
bus = create_event_bus()

