"""端点级测试：audit / tenants / release / governance / backup 五个企业路由。

与既有 web 测试一致，共享 ``web_main`` 单例（首个导入者决定临时 DATA_ROOT 与 SQLite）。
管理员权限不依赖「首个注册用户为 admin」，而是显式改库提权，因此本文件在任意收集
顺序下都稳定。所有资源名带随机后缀，避免与其它测试文件共享库时相互干扰。
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest


def _make_env() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_endpoints_"))
    os.environ.setdefault("CAIPIAO_WEB_DB", f"sqlite:///{tmp / 'endpoints.db'}")
    os.environ.setdefault("CAIPIAO_WEB_DATA", str(tmp))
    os.environ.setdefault("CAIPIAO_WEB_SECRET", "test-secret-endpoints")
    return tmp


@pytest.fixture(scope="module")
def workdir() -> Path:
    return _make_env()


@pytest.fixture(scope="module")
def client(workdir):
    from fastapi.testclient import TestClient

    from web_main import app as fastapi_app

    # 备份管理器默认写 .caipiao/backups（相对 CWD），测试期改指向临时目录，
    # 避免污染仓库工作区。
    import caipiao.web.backup_manager as _bm

    saved = _bm._manager
    _bm._manager = _bm.BackupManager(backup_dir=str(workdir / "backups"))
    with TestClient(fastapi_app) as c:
        yield c
    _bm._manager = saved


def _uniq(prefix: str = "u") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _register(client, username: str, password: str = "pw123456") -> str:
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _set_role(user_id: str, role: str) -> None:
    """直接改库设定角色，不依赖「首个注册用户为管理员」的注册顺序。"""
    from caipiao.web import db as _webdb
    from caipiao.web.models import User

    _webdb._ensure_engine()
    with _webdb._SessionLocal() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.role = role
        session.commit()


@pytest.fixture(scope="module")
def user(client) -> tuple[str, str]:
    """普通用户 (token, user_id)。"""
    token = _register(client, _uniq("member"))
    uid = client.get("/me", headers=_headers(token)).json()["id"]
    _set_role(uid, "user")
    assert client.get("/me", headers=_headers(token)).json()["role"] == "user"
    return token, uid


@pytest.fixture(scope="module")
def admin(client) -> tuple[str, str]:
    """管理员 (token, user_id)。"""
    token = _register(client, _uniq("root"))
    uid = client.get("/me", headers=_headers(token)).json()["id"]
    _set_role(uid, "admin")
    assert client.get("/me", headers=_headers(token)).json()["role"] == "admin"
    return token, uid


# --------------------------------------------------------------------------- #
# /audit
# --------------------------------------------------------------------------- #
def test_audit_logs_require_auth(client):
    assert client.get("/audit/logs").status_code == 401
    assert client.get("/audit/stats").status_code == 401


def test_audit_logs_scoped_to_self_for_non_admin(client, user, admin):
    from caipiao.web.security_audit import audit_logger

    token, uid = user
    _, other_uid = admin
    action = _uniq("act")
    audit_logger.log(uid, action, "resource/a", details={"k": 1}, ip_address="1.2.3.4")
    audit_logger.log(other_uid, action, "resource/b", success=False, error_message="boom")

    r = client.get("/audit/logs", headers=_headers(token))
    assert r.status_code == 200, r.text
    logs = r.json()
    assert logs, "普通用户应能看到自己的日志"
    # 非管理员的 user_id 过滤被强制覆盖为自身
    assert {l["user_id"] for l in logs} == {uid}
    mine = [l for l in logs if l["action"] == action]
    assert len(mine) == 1
    assert mine[0]["resource"] == "resource/a"
    assert mine[0]["details"] == {"k": 1}
    assert mine[0]["ip_address"] == "1.2.3.4"
    assert mine[0]["success"] is True


def test_audit_logs_admin_sees_all_and_can_filter(client, admin):
    from caipiao.web.security_audit import audit_logger

    token, _ = admin
    action = _uniq("filtered")
    target = _uniq("victim")
    audit_logger.log(target, action, "resource/c")
    audit_logger.log(target, _uniq("other"), "resource/d")

    r = client.get("/audit/logs", params={"action": action}, headers=_headers(token))
    assert r.status_code == 200, r.text
    logs = r.json()
    assert len(logs) == 1
    assert logs[0]["user_id"] == target

    r = client.get(
        "/audit/logs", params={"user_id": target, "limit": 5}, headers=_headers(token)
    )
    assert r.status_code == 200
    assert {l["user_id"] for l in r.json()} == {target}


def test_audit_logs_limit_validated(client, user):
    token, _ = user
    assert client.get("/audit/logs", params={"limit": 0}, headers=_headers(token)).status_code == 422
    assert (
        client.get("/audit/logs", params={"limit": 5000}, headers=_headers(token)).status_code == 422
    )


def test_audit_stats_admin_only(client, user, admin):
    assert client.get("/audit/stats", headers=_headers(user[0])).status_code == 403

    r = client.get("/audit/stats", headers=_headers(admin[0]))
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total_logs"] >= 4
    assert stats["recent_errors"] >= 1
    assert isinstance(stats["action_counts"], dict)
    assert isinstance(stats["user_counts"], dict)


# --------------------------------------------------------------------------- #
# /tenants
# --------------------------------------------------------------------------- #
def test_tenant_crud_endpoints(client, user):
    token, _ = user
    h = _headers(token)
    name = _uniq("tenant")

    r = client.post("/tenants", json={"name": name, "plan": "pro"}, headers=h)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert r.json()["plan"] == "pro"

    r = client.get("/tenants", headers=h)
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    r = client.get("/tenants", params={"status": "active"}, headers=h)
    assert any(t["id"] == tid for t in r.json())

    r = client.get(f"/tenants/{tid}", headers=h)
    assert r.json() == {"id": tid, "name": name, "plan": "pro", "status": "active"}

    r = client.put(f"/tenants/{tid}", json={"name": name + "-x", "plan": "enterprise"}, headers=h)
    assert r.json() == {"status": "ok"}
    assert client.get(f"/tenants/{tid}", headers=h).json()["plan"] == "enterprise"

    # 成员管理
    member = _uniq("m")
    r = client.post(f"/tenants/{tid}/users", json={"user_id": member, "role": "owner"}, headers=h)
    assert r.json() == {"status": "ok", "role": "owner"}
    r = client.get(f"/tenants/{tid}/users", headers=h)
    assert r.json() == [{"user_id": member, "role": "owner"}]

    # 用量与统计
    r = client.get(f"/tenants/{tid}/usage", headers=h)
    assert r.json()["users"] == 1
    r = client.get(f"/tenants/{tid}/stats", headers=h)
    stats = r.json()
    assert stats["tenant_id"] == tid
    assert stats["plan"] == "enterprise"
    assert stats["users"]["used"] == 1

    r = client.delete(f"/tenants/{tid}/users/{member}", headers=h)
    assert r.json() == {"status": "ok"}
    assert client.get(f"/tenants/{tid}/users", headers=h).json() == []

    r = client.delete(f"/tenants/{tid}", headers=h)
    assert r.json() == {"status": "ok"}
    assert client.get(f"/tenants/{tid}", headers=h).json()["status"] == "deleted"


def test_tenant_not_found_branches(client, user):
    h = _headers(user[0])
    missing = "no-such-tenant"

    assert client.get(f"/tenants/{missing}", headers=h).json() == {"error": "Not found"}
    assert client.put(f"/tenants/{missing}", json={"plan": "pro"}, headers=h).json() == {
        "error": "Not found"
    }
    assert client.delete(f"/tenants/{missing}", headers=h).json() == {"error": "Not found"}
    assert client.post(
        f"/tenants/{missing}/users", json={"user_id": "x"}, headers=h
    ).json() == {"error": "Tenant not found"}
    assert client.get(f"/tenants/{missing}/users", headers=h).json() == []
    assert client.delete(f"/tenants/{missing}/users/x", headers=h).json() == {"error": "Not found"}
    assert client.get(f"/tenants/{missing}/usage", headers=h).json() == {"error": "Not found"}
    assert client.get(f"/tenants/{missing}/stats", headers=h).json() == {}


def test_tenant_requires_auth(client):
    assert client.get("/tenants").status_code == 401
    assert client.post("/tenants", json={"name": "x"}).status_code == 401


# --------------------------------------------------------------------------- #
# /release
# --------------------------------------------------------------------------- #
def test_release_flag_lifecycle(client, user):
    h = _headers(user[0])
    key = _uniq("flag")

    r = client.post("/release/flags", json={"key": key, "name": "新首页"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"key": key, "name": "新首页"}

    r = client.get("/release/flags", headers=h)
    entry = next(f for f in r.json() if f["key"] == key)
    assert entry["enabled"] is False
    assert entry["rollout_percentage"] == 0

    # 未开启 -> False
    r = client.post("/release/flags/check", json={"key": key, "user_id": "u1"}, headers=h)
    assert r.json() == {"key": key, "enabled": False}

    # 全量开启 -> True
    r = client.put(f"/release/flags/{key}", json={"enabled": True, "rollout_percentage": 100}, headers=h)
    assert r.json() == {"status": "ok"}
    r = client.post("/release/flags/check", json={"key": key, "user_id": "u1"}, headers=h)
    assert r.json()["enabled"] is True

    # 未知 key 的 check 走「不存在」分支
    r = client.post("/release/flags/check", json={"key": "nope"}, headers=h)
    assert r.json()["enabled"] is False

    assert client.delete(f"/release/flags/{key}", headers=h).json() == {"status": "ok"}
    assert client.delete(f"/release/flags/{key}", headers=h).json() == {"error": "Not found"}
    assert client.put(f"/release/flags/{key}", json={"enabled": True}, headers=h).json() == {
        "error": "Not found"
    }


def test_release_version_lifecycle(client, user):
    h = _headers(user[0])
    version = f"1.0.{uuid.uuid4().hex[:4]}"

    r = client.post(
        "/release/versions",
        json={"version": version, "name": "首个版本", "features": ["a", "b"]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    assert r.json()["version"] == version

    r = client.get("/release/versions", headers=h)
    entry = next(v for v in r.json() if v["id"] == vid)
    assert entry["status"] == "draft"

    r = client.post(f"/release/versions/{vid}/release", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["deployment_id"]

    r = client.get("/release/versions", params={"status": "production"}, headers=h)
    assert any(v["id"] == vid for v in r.json())

    assert client.post(f"/release/versions/{vid}/rollback", headers=h).json() == {"status": "ok"}
    r = client.get("/release/versions", params={"status": "archived"}, headers=h)
    assert any(v["id"] == vid for v in r.json())

    assert client.post("/release/versions/nope/release", headers=h).json() == {"error": "Not found"}
    assert client.post("/release/versions/nope/rollback", headers=h).json() == {"error": "Not found"}


def test_release_release_to_custom_environment(client, user):
    h = _headers(user[0])
    r = client.post(
        "/release/versions", json={"version": f"2.0.{uuid.uuid4().hex[:4]}", "name": "预发"}, headers=h
    )
    vid = r.json()["id"]
    r = client.post(
        f"/release/versions/{vid}/release", params={"environment": "staging"}, headers=h
    )
    assert r.json()["status"] == "completed"
    r = client.get("/release/versions", params={"status": "staging"}, headers=h)
    assert any(v["id"] == vid for v in r.json())


def test_release_requires_auth(client):
    assert client.get("/release/flags").status_code == 401
    assert client.get("/release/versions").status_code == 401


# --------------------------------------------------------------------------- #
# /governance
# --------------------------------------------------------------------------- #
def test_governance_dataset_and_lineage(client, user):
    h = _headers(user[0])
    tag = _uniq("tag")
    src_name = _uniq("raw")
    dst_name = _uniq("mart")

    r = client.post(
        "/governance/datasets",
        json={"name": src_name, "description": "原始层", "source": "etl", "owner": "de", "tags": [tag]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    src_id = r.json()["id"]
    dst_id = client.post(
        "/governance/datasets", json={"name": dst_name, "description": "汇总层"}, headers=h
    ).json()["id"]

    r = client.get("/governance/datasets", headers=h)
    ids = {d["id"] for d in r.json()}
    assert {src_id, dst_id} <= ids

    r = client.get("/governance/datasets", params={"tags": tag}, headers=h)
    assert [d["id"] for d in r.json()] == [src_id]

    r = client.get(f"/governance/datasets/{src_id}", headers=h)
    assert r.json()["name"] == src_name
    assert r.json()["schema"] == []
    assert client.get("/governance/datasets/nope", headers=h).json() == {"error": "Not found"}

    # 静态路由必须优先于 /datasets/{dataset_id}
    r = client.get("/governance/datasets/search", params={"q": src_name}, headers=h)
    assert r.status_code == 200, r.text
    assert [d["id"] for d in r.json()] == [src_id]

    r = client.post(
        "/governance/lineage",
        json={
            "source_dataset": src_id,
            "target_dataset": dst_id,
            "transform_type": "aggregate",
            "transform_logic": "SELECT 1",
        },
        headers=h,
    )
    assert r.json()["id"]

    r = client.get(f"/governance/lineage/{dst_id}", headers=h)
    body = r.json()
    assert body["dataset_id"] == dst_id
    assert body["upstream"] == [{"dataset": src_id, "type": "aggregate"}]
    assert body["downstream"] == []

    r = client.get(f"/governance/lineage/{src_id}", headers=h)
    assert r.json()["downstream"] == [{"dataset": dst_id, "type": "aggregate"}]


def test_governance_quality_endpoints(client, user):
    h = _headers(user[0])
    ds_id = client.post(
        "/governance/datasets", json={"name": _uniq("quality")}, headers=h
    ).json()["id"]

    # 没有规则时校验结果为空、分数为 0
    assert client.get(f"/governance/quality/{ds_id}/check", headers=h).json() == {"results": []}
    assert client.get(f"/governance/quality/{ds_id}/score", headers=h).json() == {
        "dataset_id": ds_id,
        "score": 0,
    }

    r = client.post(
        "/governance/quality/rules",
        json={"dataset_id": ds_id, "rule_type": "not_null", "field_name": "id", "threshold": 99},
        headers=h,
    )
    rule_id = r.json()["id"]
    assert rule_id

    r = client.get(f"/governance/quality/{ds_id}/check", headers=h)
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0] == {"rule_id": rule_id, "passed": True, "score": 100}

    r = client.get(f"/governance/quality/{ds_id}/score", headers=h)
    assert r.json()["score"] == 100

    r = client.get("/governance/stats", headers=h)
    stats = r.json()
    assert stats["total_datasets"] >= 3
    assert stats["total_lineage"] >= 1
    assert stats["total_quality_rules"] >= 1
    assert "avg_quality_score" in stats


def test_governance_requires_auth(client):
    assert client.get("/governance/datasets").status_code == 401
    assert client.get("/governance/stats").status_code == 401


# --------------------------------------------------------------------------- #
# /backup
# --------------------------------------------------------------------------- #
def test_backup_config_run_and_records(client, user, workdir):
    h = _headers(user[0])
    source = workdir / f"src_{uuid.uuid4().hex[:6]}.txt"
    source.write_text("hello backup", encoding="utf-8")

    r = client.post(
        "/backup/configs",
        json={
            "name": _uniq("cfg"),
            "backup_type": "full",
            "source_paths": [str(source)],
            "retention_days": 7,
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    cfg_id = r.json()["id"]

    r = client.get("/backup/configs", headers=h)
    entry = next(c for c in r.json() if c["id"] == cfg_id)
    assert entry["backup_type"] == "full"
    assert entry["enabled"] is True

    r = client.post(f"/backup/configs/{cfg_id}/run", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    record_id = r.json()["id"]

    r = client.get("/backup/records", params={"config_id": cfg_id}, headers=h)
    records = r.json()
    assert [rec["id"] for rec in records] == [record_id]
    assert records[0]["file_size"] == source.stat().st_size

    r = client.get("/backup/records", params={"limit": 1}, headers=h)
    assert len(r.json()) == 1

    r = client.get("/backup/stats", headers=h)
    stats = r.json()
    assert stats["total_configs"] >= 1
    assert stats["successful_backups"] >= 1
    assert stats["failed_backups"] == 0

    assert client.post("/backup/configs/nope/run", headers=h).json() == {"error": "Config not found"}
    assert client.delete(f"/backup/configs/{cfg_id}", headers=h).json() == {"status": "ok"}
    assert client.delete(f"/backup/configs/{cfg_id}", headers=h).json() == {"error": "Not found"}


def test_backup_restore_and_cleanup(client, user, workdir):
    h = _headers(user[0])
    source = workdir / f"restore_src_{uuid.uuid4().hex[:6]}.txt"
    source.write_text("payload", encoding="utf-8")

    cfg_id = client.post(
        "/backup/configs",
        json={"name": _uniq("cfg"), "source_paths": [str(source)]},
        headers=h,
    ).json()["id"]
    record_id = client.post(f"/backup/configs/{cfg_id}/run", headers=h).json()["id"]

    # 路由未暴露恢复点创建，直接用管理器建立恢复点
    from caipiao.web.backup_manager import get_backup_manager

    point = get_backup_manager().create_restore_point(record_id, "rp-1", "端点测试")

    target = workdir / f"restore_dst_{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/backup/restore",
        json={"restore_point_id": point.id, "target_dir": str(target)},
        headers=h,
    )
    assert r.json() == {"status": "ok"}
    assert (target / source.name).read_text(encoding="utf-8") == "payload"

    r = client.post(
        "/backup/restore",
        json={"restore_point_id": "nope", "target_dir": str(target)},
        headers=h,
    )
    assert r.json() == {"error": "Restore failed"}

    # retention_days=0 表示清理所有已完成备份
    r = client.post("/backup/cleanup", params={"retention_days": 0}, headers=h)
    assert r.json()["cleaned"] >= 2

    r = client.get("/backup/stats", headers=h)
    assert r.json()["restore_points"] >= 1


def test_backup_requires_auth(client):
    assert client.get("/backup/configs").status_code == 401
    assert client.get("/backup/stats").status_code == 401
