"""测试 AI 预测路由：验证历史开奖数据已接入预测引擎。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


def _make_env():
    """在导入 web 应用前设置隔离环境，返回临时数据根目录。"""
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_ai_predict_test_"))
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
    username = f"ai_predict_tester_{_COUNTER['n']}"
    password = "pw123456"
    r = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth_header(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_models_listed(client, token):
    r = client.get("/ai/models", headers=_auth_header(token))
    assert r.status_code == 200
    models = r.json()["models"]
    assert {"frequency", "markov", "ensemble"}.issubset(set(models))


def test_predict_returns_numbers_from_history(client, token):
    """/ai/predict 应基于真实开奖历史返回非空预测（此前恒为空）。"""
    r = client.post(
        "/ai/predict",
        json={"profile_key": "ssq"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["model"] == "ensemble"
    numbers = data["numbers"]
    assert isinstance(numbers, list)
    assert len(numbers) == 6  # 双色球主号组个数
    assert all(1 <= n <= 33 for n in numbers)


def test_predict_with_explicit_model(client, token):
    r = client.post(
        "/ai/predict",
        json={"profile_key": "ssq", "model_name": "frequency"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["model"] == "frequency"
    assert len(data["numbers"]) == 6


def test_batch_predict(client, token):
    r = client.post(
        "/ai/batch-predict",
        json={"profile_key": "ssq"},
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    preds = r.json()["predictions"]
    assert len(preds) == 3
    for p in preds:
        assert len(p["numbers"]) == 6
