"""安全审计日志持久化集成测试（审计条目写入数据库，重启不丢失）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_audit_test_"))
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


def test_audit_log_persists_across_instance(tmp_db):
    from caipiao.web.security_audit import AuditLogger

    logger = AuditLogger()
    logger.log("u_1", "login", "auth", details={"ip": "1.2.3.4"}, success=True)
    logger.log("u_1", "delete_tenant", "tenant", success=False, error_message="forbidden")

    # 全新实例（模拟重启）应能从数据库加载审计日志
    fresh = AuditLogger()
    logs = fresh.get_logs(user_id="u_1")
    assert len(logs) == 2
    actions = {l.action for l in logs}
    assert "login" in actions
    assert "delete_tenant" in actions
    failed = [l for l in logs if l.action == "delete_tenant"][0]
    assert failed.success is False
    assert failed.error_message == "forbidden"


def test_audit_stats_reflect_persisted(tmp_db):
    from caipiao.web.security_audit import AuditLogger

    logger = AuditLogger()
    logger.log("u_a", "export", "report")
    logger.log("u_b", "export", "report")
    logger.log("u_a", "export", "report")

    fresh = AuditLogger()
    stats = fresh.get_stats()
    assert stats["total_logs"] == 3
    assert stats["action_counts"].get("export") == 3
    assert stats["user_counts"].get("u_a") == 2
