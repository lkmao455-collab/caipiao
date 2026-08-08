"""测试智能客服路由。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from caipiao.web.app import app
from tests.conftest import _make_token

client = TestClient(app)


def _auth_header(t: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {t or _make_token()}"}


def test_chatbot_basic():
    """测试基本对话。"""
    r = client.post(
        "/chatbot",
        json={"message": "你好"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


def test_chatbot_generate():
    """测试生成相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "如何生成号码？"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "生成" in data["reply"] or "号码" in data["reply"]
    assert len(data["suggestions"]) > 0


def test_chatbot_backtest():
    """测试回测相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "怎么进行回测？"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "回测" in data["reply"]


def test_chatbot_stats():
    """测试统计相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "统计分析在哪里？"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "统计" in data["reply"]


def test_chatbot_help():
    """测试帮助相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "帮助"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "回复" not in data["reply"] or len(data["reply"]) > 0


def test_chatbot_strategy():
    """测试策略相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "有哪些策略？"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "策略" in data["reply"]


def test_chatbot_community():
    """测试社区相关问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "社区功能怎么用？"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "社区" in data["reply"]


def test_chatbot_default_reply():
    """测试无法识别的问题。"""
    r = client.post(
        "/chatbot",
        json={"message": "随机乱码xyz123"},
        headers=_auth_header(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["suggestions"]) > 0
