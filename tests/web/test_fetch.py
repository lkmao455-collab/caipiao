"""/fetch 数据拉取端点测试。

复用仓库既有约定：模块级 env 隔离（临时 DATA_ROOT + 临时 SQLite），monkeypatch
核心层 ``LotteryDataFetcher`` 避免真实网络请求。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest

from caipiao.data.fetcher import LotteryDataFetcher as RealFetcher
from caipiao.data.models import DrawRecord
from caipiao.web.eventbus import bus


def _make_env():
    tmp = tempfile.mkdtemp(prefix="caipiao_web_fetch_")
    src = os.path.join(os.getcwd(), ".caipiao")
    if os.path.isdir(src):
        for f in os.listdir(src):
            if f.startswith("draws") and f.endswith(".json"):
                shutil.copy(os.path.join(src, f), os.path.join(tmp, f))
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp}/fetch.db"
    os.environ["CAIPIAO_WEB_DATA"] = tmp
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret-fetch"
    return tmp


@pytest.fixture(scope="module")
def app():
    _make_env()
    from web_main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="module")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def _register(client, username, password="pw123456"):
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def tok(client) -> str:
    return _register(client, f"u_{uuid.uuid4().hex[:10]}")


class _FakeFetcher:
    _counter = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    def fetch_latest(self) -> DrawRecord:
        from datetime import datetime, timezone

        _FakeFetcher._counter += 1
        n = _FakeFetcher._counter
        return DrawRecord(
            issue=f"2099{n:04d}",
            draw_date=datetime(2099, 12, 28, tzinfo=timezone.utc),
            profile="ssq",
            groups={"red": [1, 2, 3, 4, 5, 6], "blue": [7]},
        )

    def fetch_all(self) -> list[DrawRecord]:
        from datetime import datetime, timezone

        return [
            DrawRecord(
                issue=f"20991{10 + i}",
                draw_date=datetime(2099, 1, i + 1, tzinfo=timezone.utc),
                profile="ssq",
                groups={"red": [i + 1, i + 2, i + 3, i + 4, i + 5, i + 6], "blue": [7]},
            )
            for i in range(5)
        ]


@pytest.fixture
def fake_fetcher(monkeypatch):
    # 路由器在模块顶层绑定了 LotteryDataFetcher，需 patch 该命名空间内的引用
    import caipiao.web.routers.fetch as fetch_mod

    monkeypatch.setattr(fetch_mod, "LotteryDataFetcher", _FakeFetcher)
    yield


def test_fetch_requires_auth(client):
    r = client.post("/profiles/ssq/fetch", json={"mode": "latest"})
    assert r.status_code == 401


def test_fetch_unknown_key_falls_back_to_default(client, tok, fake_fetcher):
    # get_profile 对未知 key 回退到默认（双色球），不返回 404
    r = client.post(
        "/profiles/nope/fetch",
        headers={"Authorization": f"Bearer {tok}"},
        json={"mode": "latest"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["fetched"] == 1


def test_fetch_latest_adds_record(client, tok, fake_fetcher):
    # 先拿基线总数
    base = client.get("/profiles/ssq/stats", headers={"Authorization": f"Bearer {tok}"})
    assert base.status_code == 200
    before_total = base.json()["total_records"]

    queue = bus.subscribe()
    r = client.post(
        "/profiles/ssq/fetch",
        headers={"Authorization": f"Bearer {tok}"},
        json={"mode": "latest"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile_key"] == "ssq"
    assert body["mode"] == "latest"
    assert body["fetched"] == 1
    assert body["added"] == 1
    assert body["total"] == before_total + 1
    latest_issue = body["latest"]["issue"]

    # 事件总线应收到本次拉取产生的 draw_update（忽略后台 poller 可能插入的消息）
    import asyncio

    found = False
    while True:
        try:
            msg = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if msg.get("type") == "draw_update" and msg.get("issue") == latest_issue:
            found = True
            break
    assert found, "未收到本次拉取产生的 draw_update 事件"
    bus.unsubscribe(queue)


def test_fetch_all_adds_multiple(client, tok, fake_fetcher):
    r = client.post(
        "/profiles/ssq/fetch",
        headers={"Authorization": f"Bearer {tok}"},
        json={"mode": "all"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fetched"] == 5
    # 第一次 all 拉取的 5 期均为新增（与 latest 的 issue 不冲突）
    assert body["added"] == 5


def test_fetch_global(client, tok, fake_fetcher):
    r = client.post(
        "/fetch",
        headers={"Authorization": f"Bearer {tok}"},
        json={"mode": "latest"},
    )
    assert r.status_code == 200, r.text
    results = r.json()
    assert isinstance(results, list) and len(results) > 0
    ssq = next(x for x in results if x["profile_key"] == "ssq")
    assert ssq["fetched"] == 1
