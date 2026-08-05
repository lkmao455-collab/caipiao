"""进程内事件总线：用于 WebSocket 实时推送（生产化可换 Redis）。"""

from __future__ import annotations

import asyncio
from collections.abc import Set
from typing import Any


class EventBus:
    """简单的发布/订阅：订阅者各自拿到一个 asyncio.Queue。"""

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


bus = EventBus()
