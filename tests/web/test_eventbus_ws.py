"""P5.C 测试：事件总线（内存回退 + Redis pub/sub）与 WebSocket 实时推送。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest

redis = pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_c_"))
    src = Path(".caipiao")
    if src.exists():
        for f in src.glob("draws*.json"):
            shutil.copy(f, tmp / f.name)
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test_c.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret-c"
    os.environ["CAIPIAO_WEB_PULL_INTERVAL"] = "0"  # 测试中禁用后台拉取
    return tmp


@pytest.fixture(scope="module")
def app():
    _make_env()
    from web_main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def test_ws_receives_draw_update(client):
    """总线 publish 的 draw_update 事件应经 WebSocket 推送到客户端（内存总线回退）。"""
    from caipiao.web.eventbus import bus

    with client.websocket_connect("/ws/draws") as ws:
        bus.publish({"type": "draw_update", "profile": "ssq", "issue": "2024001"})
        msg = ws.receive_json()
        assert msg["type"] == "draw_update"
        assert msg["profile"] == "ssq"


def test_redis_eventbus_pubsub(monkeypatch):
    """Redis 事件总线（fakeredis 模拟）能将发布消息经 pub/sub 转发到订阅队列。

    同步发布端（redis.Redis）与异步监听端（redis.asyncio）必须共享同一个
    FakeServer，否则二者各自独立的内存服务无法互通 pub/sub。
    """
    import redis
    import redis.asyncio as rai

    from caipiao.web import eventbus as eb

    fake_server = fakeredis.FakeServer()  # 同步/异步客户端共享同一后端
    monkeypatch.setattr(redis.Redis, "from_url",
                        lambda url, **kw: fakeredis.FakeRedis(server=fake_server))
    monkeypatch.setattr(rai, "from_url",
                        lambda url, **kw: fakeredis.aioredis.FakeRedis(server=fake_server))

    bus = eb.RedisEventBus("redis://fake")

    async def run():
        task = bus.start()
        try:
            queue = bus.subscribe()
            # 等待异步监听器完成 subscribe，否则同步 publish 早于订阅会丢失消息
            await asyncio.sleep(0.2)
            bus.publish({"type": "draw_update", "profile": "dlt"})
            msg = await asyncio.wait_for(queue.get(), timeout=3)
            return msg
        finally:
            task.cancel()

    msg = asyncio.run(run())
    assert msg["type"] == "draw_update"
    assert msg["profile"] == "dlt"
