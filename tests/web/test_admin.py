"""P5.E 测试：多用户角色权限 + 管理后台。

遵循仓库既有约定：模块级 app fixture 在进入前设置隔离环境（临时 DATA_ROOT +
临时 SQLite），其余 web 测试文件共享同一 web_main 单例。本文件按字母序最先收集，
因此首个注册用户会成为管理员。所有用户由模块级 ``ctx`` 固定创建，避免共享库导致
「首个用户才为管理员」的断言失效。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_admin_"))
    src = Path(".caipiao")
    if src.exists():
        for f in src.glob("draws*.json"):
            shutil.copy(f, tmp / f.name)
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'admin.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret-admin"
    return tmp


@pytest.fixture(scope="module")
def app():
    _make_env()
    from web_main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="module")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def _register(client, username, password="pw123456"):
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _uniq():
    return f"u_{uuid.uuid4().hex[:10]}"


@dataclass
class Ctx:
    admin_tok: str
    admin_id: str
    user_tok: str
    user_id: str


@pytest.fixture(scope="module")
def ctx(client) -> Ctx:
    """模块内仅注册一次：首个用户为管理员，第二个为普通用户。"""
    admin_name = _uniq()
    admin_tok = _register(client, admin_name)
    me = client.get("/me", headers={"Authorization": f"Bearer {admin_tok}"}).json()
    user_name = _uniq()
    user_tok = _register(client, user_name)
    victim = client.get("/me", headers={"Authorization": f"Bearer {user_tok}"}).json()
    return Ctx(
        admin_tok=admin_tok,
        admin_id=me["id"],
        user_tok=user_tok,
        user_id=victim["id"],
    )


def test_first_user_is_admin_and_second_is_user(client, ctx):
    r = client.get("/me", headers={"Authorization": f"Bearer {ctx.admin_tok}"})
    assert r.json()["role"] == "admin"
    r = client.get("/me", headers={"Authorization": f"Bearer {ctx.user_tok}"})
    assert r.json()["role"] == "user"


def test_non_admin_forbidden(client, ctx):
    r = client.get("/admin/stats", headers={"Authorization": f"Bearer {ctx.user_tok}"})
    assert r.status_code == 403
    r = client.get("/admin/users", headers={"Authorization": f"Bearer {ctx.user_tok}"})
    assert r.status_code == 403


def test_admin_manage_users(client, ctx):
    # 管理员可查看统计与用户列表
    r = client.get("/admin/stats", headers={"Authorization": f"Bearer {ctx.admin_tok}"})
    assert r.status_code == 200
    assert r.json()["user_count"] >= 2

    r = client.get("/admin/users", headers={"Authorization": f"Bearer {ctx.admin_tok}"})
    assert r.status_code == 200
    assert any(u["username"] for u in r.json())

    # 新增一个普通用户并提升为管理员
    victim_name = _uniq()
    _register(client, victim_name)
    users = client.get("/admin/users", headers={"Authorization": f"Bearer {ctx.admin_tok}"}).json()
    vid = next(u["id"] for u in users if u["username"] == victim_name)
    r = client.patch(
        f"/admin/users/{vid}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {ctx.admin_tok}"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    # 删除后不可再登录
    r = client.delete(f"/admin/users/{vid}", headers={"Authorization": f"Bearer {ctx.admin_tok}"})
    assert r.status_code == 204
    r = client.post("/auth/login", data={"username": victim_name, "password": "pw123456"})
    assert r.status_code == 401


def test_admin_cannot_act_on_self(client, ctx):
    r = client.patch(
        f"/admin/users/{ctx.admin_id}/role",
        json={"role": "user"},
        headers={"Authorization": f"Bearer {ctx.admin_tok}"},
    )
    assert r.status_code == 400

    r = client.delete(
        f"/admin/users/{ctx.admin_id}", headers={"Authorization": f"Bearer {ctx.admin_tok}"}
    )
    assert r.status_code == 400


def test_invalid_role_rejected(client, ctx):
    victim_name = _uniq()
    _register(client, victim_name)
    users = client.get("/admin/users", headers={"Authorization": f"Bearer {ctx.admin_tok}"}).json()
    vid = next(u["id"] for u in users if u["username"] == victim_name)
    r = client.patch(
        f"/admin/users/{vid}/role",
        json={"role": "superuser"},
        headers={"Authorization": f"Bearer {ctx.admin_tok}"},
    )
    assert r.status_code == 422
