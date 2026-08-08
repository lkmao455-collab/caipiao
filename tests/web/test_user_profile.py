"""用户画像持久化集成测试。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_up_test_"))
    src = Path(".caipiao")
    if src.exists():
        for f in src.glob("draws*.json"):
            shutil.copy(f, tmp / f.name)
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret"
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
    os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
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
    username = "up_tester"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_tag_and_summary_persist_across_instances(client, token):
    uid = "user-001"
    r = client.post(
        "/profile/tags",
        headers=_auth(token),
        json={"user_id": uid, "name": "vip", "value": "gold"},
    )
    assert r.status_code == 200, r.text

    summary = client.get(f"/profile/summary/{uid}", headers=_auth(token))
    assert summary.json()["tags"]["vip"] == "gold"

    # 新实例（模拟重启）应从数据库加载
    from caipiao.web.user_profile import UserProfileSystem

    fresh = UserProfileSystem()
    assert fresh.get_tags(uid)["vip"].value == "gold"


def test_segment_persist_and_match(client, token):
    uid = "user-002"
    client.post(
        "/profile/tags",
        headers=_auth(token),
        json={"user_id": uid, "name": "plan", "value": "pro"},
    )
    seg = client.post(
        "/profile/segments",
        headers=_auth(token),
        json={"name": "pro-users", "rules": {"plan": "pro"}},
    )
    assert seg.status_code == 200, seg.text
    seg_id = seg.json()["id"]

    users = client.get(f"/profile/segments/{seg_id}/users", headers=_auth(token))
    assert uid in users.json()["users"]

    from caipiao.web.user_profile import UserProfileSystem

    assert any(s.id == seg_id for s in UserProfileSystem().list_segments())


def test_remove_tag_persist(client, token):
    uid = "user-003"
    client.post(
        "/profile/tags",
        headers=_auth(token),
        json={"user_id": uid, "name": "temp", "value": "x"},
    )
    d = client.delete(f"/profile/tags/{uid}/temp", headers=_auth(token))
    assert d.status_code == 200, d.text

    from caipiao.web.user_profile import UserProfileSystem

    assert "temp" not in UserProfileSystem().get_tags(uid)
