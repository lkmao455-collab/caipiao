"""消息队列路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import get_current_principal
from ..message_queue import MessagePriority, get_message_queue

router = APIRouter(prefix="/mq", tags=["message-queue"])


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""


class MessagePublish(BaseModel):
    payload: dict
    priority: int = 1


class SubscriptionCreate(BaseModel):
    topic: str
    subscriber: str
    filter_expr: str = ""


@router.post("/topics")
def create_topic(
    req: TopicCreate,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    topic = mq.create_topic(req.name, req.description)
    return {"name": topic.name, "description": topic.description}


@router.get("/topics")
def list_topics(
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    return [
        {"name": t.name, "description": t.description, "subscribers": len(t.subscribers), "message_count": t.message_count}
        for t in mq.list_topics()
    ]


@router.delete("/topics/{name}")
def delete_topic(
    name: str,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    if not mq.delete_topic(name):
        return {"error": "Topic not found"}
    return {"status": "ok"}


@router.post("/topics/{topic}/publish")
def publish_message(
    topic: str,
    req: MessagePublish,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    msg = mq.publish(topic, req.payload, MessagePriority(req.priority))
    if not msg:
        return {"error": "Failed to publish"}
    return {"message_id": msg.id, "topic": topic}


@router.post("/subscriptions")
def create_subscription(
    req: SubscriptionCreate,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    sub = mq.subscribe(req.topic, req.subscriber, filter_expr=req.filter_expr)
    return {"id": sub.id, "topic": sub.topic, "subscriber": sub.subscriber}


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(
    sub_id: str,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    if not mq.unsubscribe(sub_id):
        return {"error": "Subscription not found"}
    return {"status": "ok"}


@router.get("/dead-letters")
def get_dead_letters(
    limit: int = 100,
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    letters = mq.get_dead_letters(limit)
    return [
        {"id": m.id, "topic": m.topic, "payload": m.payload, "error": m.error, "attempts": m.attempts}
        for m in letters
    ]


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    mq = get_message_queue()
    return mq.get_stats()
