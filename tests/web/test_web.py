"""Web 后端集成测试：用 FastAPI TestClient 覆盖主要端点。

隔离策略：使用临时 DATA_ROOT（复制真实开奖数据用于生成/回测），
临时 SQLite 作为用户库；不依赖 PySide/桌面 UI。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    """在导入 web 应用前设置隔离环境，返回临时数据根目录。"""
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_test_"))
    src = Path(".caipiao")
    if src.exists():
        for f in src.glob("draws*.json"):
            shutil.copy(f, tmp / f.name)
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret"
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


_COUNTER = {"n": 0}


@pytest.fixture
def token(client):
    _COUNTER["n"] += 1
    username = f"tester_{_COUNTER['n']}"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_login_me(client):
    r = client.post(
        "/auth/register", json={"username": "alice", "password": "secret123"}
    )
    assert r.status_code == 201
    r = client.post("/auth/login", data={"username": "alice", "password": "secret123"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    r = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_register_duplicate(client):
    client.post("/auth/register", json={"username": "bob", "password": "secret123"})
    r = client.post("/auth/register", json={"username": "bob", "password": "secret123"})
    assert r.status_code == 409


def test_me_requires_auth(client):
    r = client.get("/me")
    assert r.status_code == 401


def test_profiles_and_strategies(client):
    r = client.get("/profiles")
    assert r.status_code == 200
    keys = [p["key"] for p in r.json()]
    assert "ssq" in keys

    r = client.get("/profiles/ssq/strategies")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert "smart_hot_cold" in ids

    # 未知彩种由核心层回退到默认（双色球），接口仍返回 200
    r = client.get("/profiles/nope/strategies")
    assert r.status_code == 200


def test_generate_requires_auth(client):
    r = client.post(
        "/generate",
        json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 1},
    )
    assert r.status_code == 401


def test_generate_with_jwt(client, token):
    r = client.post(
        "/generate",
        json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 2
    assert len(data["tickets"]) == 2


def test_generate_unknown_strategy(client, token):
    r = client.post(
        "/generate",
        json={"profile_key": "ssq", "strategy_id": "does_not_exist", "count": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_backtest(client, token):
    r = client.post(
        "/backtest",
        json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["latest_draw"]
    assert len(data["results"]) == 1


def test_api_keys_crud(client, token):
    r = client.post("/me/apikeys", json={"name": "k1"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    raw = r.json()["key"]
    assert raw and raw.startswith("cpk_")

    r = client.get("/me/apikeys", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    kids = [k["id"] for k in r.json()]
    assert r.json()[0]["id"] in kids

    # API Key 可用于 /generate
    r = client.post(
        "/generate",
        json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 1},
        headers={"X-API-Key": raw},
    )
    assert r.status_code == 200, r.text

    # delete by id
    created_id = [k["id"] for k in client.get("/me/apikeys", headers={"Authorization": f"Bearer {token}"}).json()][0]
    r = client.delete(f"/me/apikeys/{created_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204
    r = client.get("/me/apikeys", headers={"Authorization": f"Bearer {token}"})
    assert all(k["id"] != created_id for k in r.json())


def test_param_groups(client, token):
    payload = {
        "id": "",
        "name": "g1",
        "profile_key": "ssq",
        "created_at": "2024-01-01",
        "items": [],
        "scan_context": {},
    }
    r = client.post(
        "/me/param-groups/ssq", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"]

    r = client.get("/me/param-groups/ssq", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_ws_draws_push(client, token):
    with client.websocket_connect("/ws/draws") as ws:
        r = client.post(
            "/generate",
            json={"profile_key": "ssq", "strategy_id": "smart_hot_cold", "count": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "generate"
        assert msg["profile"] == "ssq"
