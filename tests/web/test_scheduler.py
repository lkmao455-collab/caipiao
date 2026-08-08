"""调度器持久化集成测试：/scheduler（通用任务）与 /tasks（自动化任务）。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_sched_test_"))
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
    username = "sched_tester"
    password = "pw123456"
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- /scheduler: 通用任务定义持久化 ---
def test_generic_task_persist(client, token):
    r = client.post(
        "/scheduler/tasks",
        headers=_auth(token),
        json={"name": "g1", "task_type": "email", "payload": {"to": "a@b.c"}},
    )
    assert r.status_code == 200, r.text
    tid = r.json()["id"]

    lst = client.get("/scheduler/tasks", headers=_auth(token))
    assert any(t["id"] == tid for t in lst.json())

    from caipiao.web.task_scheduler import TaskScheduler

    assert TaskScheduler().get_task(tid) is not None


def test_generic_task_delete_persist(client, token):
    r = client.post(
        "/scheduler/tasks",
        headers=_auth(token),
        json={"name": "g2", "task_type": "email"},
    )
    tid = r.json()["id"]
    d = client.delete(f"/scheduler/tasks/{tid}", headers=_auth(token))
    assert d.status_code == 200, d.text

    from caipiao.web.task_scheduler import TaskScheduler

    assert TaskScheduler().get_task(tid) is None


# --- /tasks: 自动化任务持久化 ---
def test_automation_task_persist_and_run(client, token):
    r = client.post(
        "/tasks",
        headers=_auth(token),
        json={
            "name": "每日分析",
            "task_type": "analysis",
            "profile_key": "ssq",
            "interval_minutes": 120,
            "params": {"periods": 3},
        },
    )
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    # 任务 id 形如 task_N，计数器应在重载后延续，避免重复
    assert tid.startswith("task_")

    lst = client.get("/tasks", headers=_auth(token))
    assert any(t["id"] == tid for t in lst.json())

    # 立即执行（analysis 为模拟，不触发网络）
    run = client.post(f"/tasks/{tid}/run", headers=_auth(token))
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "completed"

    from caipiao.web.scheduler import TaskScheduler

    fresh = TaskScheduler()
    assert fresh.get_task(tid) is not None
    # 新建实例计数器应接续，id 不与已存在冲突
    created = fresh.add_task(
        name="后续任务", task_type=__import__("caipiao.web.scheduler", fromlist=["TaskType"]).TaskType.BACKTEST,
        profile_key="dlt",
    )
    assert created.id != tid


def test_automation_task_delete_persist(client, token):
    r = client.post(
        "/tasks",
        headers=_auth(token),
        json={"name": "临时任务", "task_type": "backtest", "profile_key": "dlt"},
    )
    tid = r.json()["id"]
    d = client.delete(f"/tasks/{tid}", headers=_auth(token))
    assert d.status_code == 200, d.text

    from caipiao.web.scheduler import TaskScheduler

    assert TaskScheduler().get_task(tid) is None
