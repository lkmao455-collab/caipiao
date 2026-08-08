"""可视化平台持久化集成测试（仪表盘持久化，模板为静态默认）。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_viz_test_"))
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
    username = "viz_tester"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_and_chart_persist(client, token):
    d = client.post(
        "/viz/dashboards",
        headers=_auth(token),
        json={"name": "运营看板", "description": "x"},
    )
    assert d.status_code == 200, d.text
    did = d.json()["id"]

    c = client.post(
        f"/viz/dashboards/{did}/charts",
        headers=_auth(token),
        json={"name": "频率", "chart_type": "bar"},
    )
    assert c.status_code == 200, c.text

    got = client.get(f"/viz/dashboards/{did}", headers=_auth(token))
    assert len(got.json()["charts"]) == 1

    # 新实例（模拟重启）应从数据库加载仪表盘与图表
    from caipiao.web.visualization import VisualizationPlatform

    fresh = VisualizationPlatform()
    dash = fresh.get_dashboard(did)
    assert dash is not None
    assert len(dash.charts) == 1
    assert dash.charts[0].chart_type == "bar"


def test_dashboard_delete_persist(client, token):
    d = client.post(
        "/viz/dashboards",
        headers=_auth(token),
        json={"name": "临时看板"},
    )
    did = d.json()["id"]
    r = client.delete(f"/viz/dashboards/{did}", headers=_auth(token))
    assert r.status_code == 200, r.text

    from caipiao.web.visualization import VisualizationPlatform

    assert VisualizationPlatform().get_dashboard(did) is None


def test_default_templates_available(client, token):
    r = client.get("/viz/templates", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 7
