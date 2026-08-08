"""监控中间件 + 实时采集集成测试。

验证：
- MonitoringMiddleware 在每个 HTTP 请求后被记录到 monitor（/monitoring/api-stats 反映调用）
- lifespan 启动 RealtimeMonitor 后 /monitor/history 返回非空历史（含采集到的系统指标）
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_mon_test_"))
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


def test_monitoring_middleware_records_calls(client):
    from caipiao.web.monitoring import monitor

    # 触发若干次请求（含 404 以验证状态码被记录）
    # monitor 是进程级单例，可能已被其他测试用例写入，因此直接扫描原始记录，
    # 避免依赖 top_paths（仅返回调用频次最高的 10 条路径）。
    before = len(monitor._api_calls)
    client.get("/health")
    client.get("/does-not-exist-xyz")
    after = len(monitor._api_calls)
    assert after - before >= 2

    recent = list(monitor._api_calls)[-(after - before):]
    paths = {c.path: c.status_code for c in recent}
    assert paths.get("/health") == 200
    assert paths.get("/does-not-exist-xyz") == 404

    stats = monitor.get_api_stats(minutes=1)
    assert stats["status_counts"].get(404, 0) >= 1
    assert stats["status_counts"].get(200, 0) >= 1


def test_realtime_monitor_collects_history(client):
    from caipiao.web.realtime_monitor import get_monitor

    monitor = get_monitor()
    # lifespan 已启动采集循环（TestClient 上下文内），等待至少一轮采集
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if monitor.get_history(minutes=1):
            break
        time.sleep(0.2)
    history = monitor.get_history(minutes=1)
    assert len(history) >= 1
    assert history[0].cpu_percent >= 0
    assert history[0].memory_mb >= 0
