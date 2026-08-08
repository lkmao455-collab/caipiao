"""测试智能客服路由。"""

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
    username = f"root_chatbot_tester_{_COUNTER['n']}"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth_header(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_chatbot_basic(client, token):
    """测试基本对话。"""
    r = client.post(
        "/chatbot",
        json={"message": "你好"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


def test_chatbot_generate(client, token):
    """测试生成相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "如何生成号码？"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "生成" in data["reply"] or "号码" in data["reply"]
    assert len(data["suggestions"]) > 0


def test_chatbot_backtest(client, token):
    """测试回测相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "怎么进行回测？"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "回测" in data["reply"]


def test_chatbot_stats(client, token):
    """测试统计相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "统计分析在哪里？"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "统计" in data["reply"]


def test_chatbot_help(client, token):
    """测试帮助相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "帮助"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["reply"]) > 0


def test_chatbot_strategy(client, token):
    """测试策略相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "有哪些策略？"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "策略" in data["reply"]


def test_chatbot_community(client, token):
    """测试社区相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "社区功能怎么用？"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "社区" in data["reply"]


def test_chatbot_default_reply(client, token):
    """测试无法识别的问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "随机乱码xyz123"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["suggestions"]) > 0
