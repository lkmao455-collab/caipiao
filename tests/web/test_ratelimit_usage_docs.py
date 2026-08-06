"""P5.B 测试：限流（429）、用量计量、Swagger 公开/私有分层。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_b_"))
    src = Path(".caipiao")
    if src.exists():
        for f in src.glob("draws*.json"):
            shutil.copy(f, tmp / f.name)
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test_b.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret-b"
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "600/minute"
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


@pytest.fixture
def token(client):
    username = "meter_user"
    client.post("/auth/register", json={"username": username, "password": "pw123456"})
    r = client.post("/auth/login", data={"username": username, "password": "pw123456"})
    return r.json()["access_token"]


def test_ratelimit_429(client, monkeypatch):
    # 临时把默认限制调低（默认路由使用动态 callable 读取环境变量）
    monkeypatch.setenv("CAIPIAO_WEB_RATE_LIMIT", "3/minute")
    codes = []
    for _ in range(5):
        r = client.get("/profiles")
        codes.append(r.status_code)
    # 前 3 次 200，之后 429
    assert codes[0] == 200
    assert 429 in codes


def test_usage_metering(client, token):
    # 调用两次 /generate，用量应累加
    for _ in range(2):
        r = client.post(
            "/generate",
            json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
    r = client.get("/me/usage", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    usage = {u["endpoint"]: u["count"] for u in r.json()}
    assert usage.get("generate", 0) >= 2


def test_docs_layering(client):
    # 默认 /docs 关闭
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # 公开子集存在且只含公开端点
    r = client.get("/openapi-public.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/health" in paths
    assert "/auth/login" in paths
    assert "/generate" not in paths  # 需鉴权，不在公开子集
    # 私有完整文档存在
    r = client.get("/openapi-private.json")
    assert r.status_code == 200
    assert "/generate" in r.json()["paths"]
