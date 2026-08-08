"""工作流引擎集成测试：持久化 + 表达式沙箱。"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_wf_test_"))
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
    username = "wf_tester"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# 表达式沙箱（纯单元测试，无需服务）
# --------------------------------------------------------------------------- #
def test_safe_eval_allows_ctx_and_blocks_builtins():
    from caipiao.web.workflow_engine import _safe_eval

    assert _safe_eval("ctx.a + ctx.b", {"a": 1, "b": 2}) == 3
    assert _safe_eval("len([ctx.a, ctx.b])", {"a": 1, "b": 2}) == 2
    # 受限命名空间：危险内建（__import__/open/exec）不可达
    with pytest.raises(Exception):
        _safe_eval("__import__('os').system('echo pwned')", {})
    with pytest.raises(Exception):
        _safe_eval("open('/etc/passwd')", {})


# --------------------------------------------------------------------------- #
# 持久化（跨引擎实例 = 模拟重启）
# --------------------------------------------------------------------------- #
def _simple_workflow_payload() -> dict:
    return {
        "name": "sandbox-wf",
        "nodes": [
            {"id": "start", "type": "start", "name": "开始", "next_nodes": ["t1"]},
            {
                "id": "t1",
                "type": "transform",
                "name": "变换",
                "config": {"expression": "ctx.x * 2"},
                "next_nodes": ["end"],
            },
            {"id": "end", "type": "end", "name": "结束", "next_nodes": []},
        ],
        "edges": [
            {"source": "start", "target": "t1"},
            {"source": "t1", "target": "end"},
        ],
    }


def test_workflow_persisted_across_engine_instances(client, token):
    r = client.post("/workflows", headers=_auth(token), json=_simple_workflow_payload())
    assert r.status_code in (200, 201), r.text
    wid = r.json()["id"]

    # 新引擎实例（模拟服务重启）应从数据库重新加载定义
    from caipiao.web.workflow_engine import WorkflowEngine

    fresh = WorkflowEngine()
    assert any(d.id == wid for d in fresh.list_definitions())


def test_workflow_delete_persisted(client, token):
    r = client.post("/workflows", headers=_auth(token), json=_simple_workflow_payload())
    wid = r.json()["id"]
    d = client.delete(f"/workflows/{wid}", headers=_auth(token))
    assert d.status_code == 200, d.text
    assert d.status_code == 200, d.text

    from caipiao.web.workflow_engine import WorkflowEngine

    assert not any(x.id == wid for x in WorkflowEngine().list_definitions())


# --------------------------------------------------------------------------- #
# 运行时：表达式求值（含沙箱拦截）
# --------------------------------------------------------------------------- #
def _poll_run(client, token, run_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rr = client.get(f"/workflows/runs/{run_id}", headers=_auth(token))
        body = rr.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.1)
    return client.get(f"/workflows/runs/{run_id}", headers=_auth(token)).json()


def test_workflow_run_uses_context(client, token):
    r = client.post("/workflows", headers=_auth(token), json=_simple_workflow_payload())
    wid = r.json()["id"]
    run = client.post(
        f"/workflows/{wid}/run",
        headers=_auth(token),
        json={"context": {"x": 21}},
    )
    assert run.status_code == 200, run.text
    run_id = run.json()["run_id"]

    body = _poll_run(client, token, run_id)
    assert body["status"] == "completed", body
    assert body["node_outputs"]["t1"]["result"] == 42


def test_workflow_run_blocks_dangerous_expression(client, token):
    payload = _simple_workflow_payload()
    payload["nodes"][1]["config"] = {"expression": "__import__('os').system('echo pwned')"}
    r = client.post("/workflows", headers=_auth(token), json=payload)
    wid = r.json()["id"]
    run = client.post(f"/workflows/{wid}/run", headers=_auth(token), json={"context": {}})
    run_id = run.json()["run_id"]

    body = _poll_run(client, token, run_id)
    assert body["status"] == "completed", body
    # 危险表达式在沙箱中被拦截，返回 error 而非执行成功
    assert "error" in body["node_outputs"]["t1"]
