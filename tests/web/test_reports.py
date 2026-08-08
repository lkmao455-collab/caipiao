"""报表引擎集成测试：验证数据源已接入真实开奖历史。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_reports_test_"))
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
    username = "reports_tester"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_data_sources_registered(client, token):
    r = client.get("/reports/data-sources", headers=_auth(token))
    assert r.status_code == 200, r.text
    names = {s["name"] for s in r.json()["data_sources"]}
    assert "ssq" in names
    assert "default" in names
    assert all(s["row_count"] > 0 for s in r.json()["data_sources"])


def test_generate_report_returns_real_data(client, token):
    # 创建一个基于 ssq 数据源的报表配置
    create = client.post(
        "/reports",
        headers=_auth(token),
        json={
            "name": "ssq 期号报表",
            "columns": [{"key": "issue", "label": "期号", "type": "text"}],
            "sort_by": "issue",
            "sort_order": "asc",
        },
    )
    assert create.status_code == 201, create.text
    report_id = create.json()["id"]

    gen = client.get(
        f"/reports/{report_id}/generate",
        params={"data_source": "ssq"},
        headers=_auth(token),
    )
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body["summary"]["total_rows"] > 0
    assert len(body["data"]) > 0
    assert "issue" in body["data"][0]


def test_export_csv_returns_content(client, token):
    create = client.post(
        "/reports",
        headers=_auth(token),
        json={
            "name": "ssq 导出",
            "columns": [
                {"key": "issue", "label": "期号", "type": "text"},
                {"key": "number_sum", "label": "和值", "type": "number"},
            ],
        },
    )
    report_id = create.json()["id"]
    r = client.get(
        f"/reports/{report_id}/export/csv",
        params={"data_source": "ssq"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    assert "期号" in r.text
