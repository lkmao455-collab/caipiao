"""多租户系统持久化集成测试（租户、成员、资源用量持久化）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_tenant_test_"))
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret"
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
    os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
    return tmp


@pytest.fixture
def tmp_db():
    _make_env()
    from caipiao.web import db as _webdb

    _webdb._ensure_engine()
    _webdb.init_db()
    yield
    _webdb._engine = None
    _webdb._SessionLocal = None


def test_tenant_and_user_persist(tmp_db):
    from caipiao.web.tenant_manager import TenantManager

    mgr = TenantManager()
    t = mgr.create_tenant("ACME", plan="pro")
    tid = t.id
    mgr.add_user("u_1", tid, role="owner")

    # 全新实例（模拟重启）应能从数据库加载租户与成员
    fresh = TenantManager()
    loaded = fresh.get_tenant(tid)
    assert loaded is not None
    assert loaded.name == "ACME"
    assert loaded.plan == "pro"
    assert loaded.quota.max_users == 100

    users = fresh.get_tenant_users(tid)
    assert len(users) == 1
    assert users[0].user_id == "u_1"
    assert users[0].role == "owner"


def test_tenant_usage_persists(tmp_db):
    from caipiao.web.tenant_manager import TenantManager

    mgr = TenantManager()
    t = mgr.create_tenant("BizCorp", plan="basic")
    tid = t.id
    mgr.record_usage(tid, "api_calls", 42)
    mgr.record_usage(tid, "storage", 12.5)
    mgr.add_user("u_2", tid)

    fresh = TenantManager()
    usage = fresh.get_usage(tid)
    assert usage is not None
    assert usage.api_calls == 42
    assert usage.storage_mb == 12.5
    assert usage.users == 1

    stats = fresh.get_tenant_stats(tid)
    assert stats["plan"] == "basic"
    assert stats["api_calls"]["used"] == 42


def test_tenant_status_transitions_persist(tmp_db):
    from caipiao.web.tenant_manager import TenantManager

    mgr = TenantManager()
    t = mgr.create_tenant("TempCo")
    tid = t.id
    assert mgr.suspend_tenant(tid) is True

    fresh = TenantManager()
    assert fresh.get_tenant(tid).status == "suspended"
    assert fresh.activate_tenant(tid) is True

    fresh2 = TenantManager()
    assert fresh2.get_tenant(tid).status == "active"
    assert fresh2.delete_tenant(tid) is True

    fresh3 = TenantManager()
    assert fresh3.get_tenant(tid).status == "deleted"
    # 逻辑删除后仍可被列出（status 过滤）
    assert len(fresh3.list_tenants(status="deleted")) == 1
