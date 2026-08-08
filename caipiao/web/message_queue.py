"""消息队列系统：异步消息处理和事件驱动。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from ..log import get_logger

logger = get_logger(__name__)


class MessageStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class MessagePriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class Message:
    id: str
    topic: str
    payload: dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING
    attempts: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    processed_at: float | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Topic:
    name: str
    description: str = ""
    subscribers: list[str] = field(default_factory=list)
    message_count: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class Subscription:
    id: str
    topic: str
    subscriber: str
    callback_name: str = ""
    filter_expr: str = ""
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


MessageHandler = Callable[[Message], Awaitable[bool]]


class MessageQueue:
    """消息队列：发布/订阅模式的消息系统。"""

    def __init__(self, max_queue_size: int = 100000):
        self._topics: dict[str, Topic] = {}
        self._queues: dict[str, list[Message]] = defaultdict(list)
        self._subscriptions: dict[str, Subscription] = {}
        self._handlers: dict[str, dict[str, MessageHandler]] = defaultdict(dict)
        self._dead_letter: list[Message] = []
        self._max_queue_size = max_queue_size
        self._running = False
        self._task: asyncio.Task | None = None

    def create_topic(self, name: str, description: str = "") -> Topic:
        topic = Topic(name=name, description=description)
        self._topics[name] = topic
        return topic

    def get_topic(self, name: str) -> Topic | None:
        return self._topics.get(name)

    def list_topics(self) -> list[Topic]:
        return list(self._topics.values())

    def delete_topic(self, name: str) -> bool:
        if name in self._topics:
            del self._topics[name]
            self._queues.pop(name, None)
            return True
        return False

    def publish(self, topic: str, payload: dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> Message | None:
        if topic not in self._topics:
            return None

        if len(self._queues[topic]) >= self._max_queue_size:
            logger.warning(f"Queue full for topic: {topic}")
            return None

        message = Message(
            id=str(uuid.uuid4())[:12],
            topic=topic,
            payload=payload,
            priority=priority,
        )
        self._queues[topic].append(message)
        self._topics[topic].message_count += 1

        self._queues[topic].sort(key=lambda m: -m.priority.value)
        return message

    def subscribe(self, topic: str, subscriber: str, callback_name: str = "", filter_expr: str = "") -> Subscription:
        sub_id = str(uuid.uuid4())[:8]
        sub = Subscription(
            id=sub_id,
            topic=topic,
            subscriber=subscriber,
            callback_name=callback_name,
            filter_expr=filter_expr,
        )
        self._subscriptions[sub_id] = sub
        if topic in self._topics:
            self._topics[topic].subscribers.append(subscriber)
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        sub = self._subscriptions.pop(subscription_id, None)
        if sub and sub.topic in self._topics:
            topic = self._topics[sub.topic]
            if sub.subscriber in topic.subscribers:
                topic.subscribers.remove(sub.subscriber)
            return True
        return False

    def register_handler(self, subscriber: str, handler: MessageHandler):
        for sub in self._subscriptions.values():
            if sub.subscriber == subscriber:
                self._handlers[sub.topic][subscriber] = handler

    def consume(self, topic: str, subscriber: str) -> Message | None:
        queue = self._queues.get(topic, [])
        for i, msg in enumerate(queue):
            if msg.status == MessageStatus.PENDING:
                msg.status = MessageStatus.PROCESSING
                msg.attempts += 1
                return queue.pop(i)
        return None

    def ack(self, topic: str, message_id: str):
        queue = self._queues.get(topic, [])
        for msg in queue:
            if msg.id == message_id:
                msg.status = MessageStatus.COMPLETED
                msg.processed_at = time.time()
                break

    def nack(self, topic: str, message_id: str, error: str = ""):
        queue = self._queues.get(topic, [])
        for msg in queue:
            if msg.id == message_id:
                msg.error = error
                if msg.attempts < msg.max_retries:
                    msg.status = MessageStatus.RETRYING
                    queue.append(msg)
                else:
                    msg.status = MessageStatus.FAILED
                    self._dead_letter.append(msg)
                break

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Message queue started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Message queue stopped")

    async def _process_loop(self):
        while self._running:
            try:
                for topic_name, queue in self._queues.items():
                    for sub in self._subscriptions.values():
                        if sub.topic == topic_name and sub.enabled:
                            handler = self._handlers.get(topic_name, {}).get(sub.subscriber)
                            if handler:
                                msg = self.consume(topic_name, sub.subscriber)
                                if msg:
                                    try:
                                        success = await handler(msg)
                                        if success:
                                            msg.status = MessageStatus.COMPLETED
                                            msg.processed_at = time.time()
                                        else:
                                            self.nack(topic_name, msg.id, "Handler returned False")
                                    except Exception as e:
                                        self.nack(topic_name, msg.id, str(e))
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Process loop error: {e}")

    def get_queue_size(self, topic: str) -> int:
        return len(self._queues.get(topic, []))

    def get_dead_letters(self, limit: int = 100) -> list[Message]:
        return self._dead_letter[-limit:]

    def get_stats(self) -> dict:
        return {
            "topics": len(self._topics),
            "subscriptions": len(self._subscriptions),
            "queue_sizes": {t: len(q) for t, q in self._queues.items()},
            "dead_letters": len(self._dead_letter),
        }


# 全局消息队列
_queue: MessageQueue | None = None


def get_message_queue() -> MessageQueue:
    global _queue
    if _queue is None:
        _queue = MessageQueue()
    return _queue
