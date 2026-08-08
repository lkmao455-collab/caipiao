"""数据分析平台持久化集成测试（漏斗 + A/B 测试定义持久化；事件流为运行时内存态）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_analytics_test_"))
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
    # 清理模块级缓存，避免污染其他测试
    _webdb._engine = None
    _webdb._SessionLocal = None


def test_funnel_persists_across_instance(tmp_db):
    from caipiao.web.analytics import (
        AnalyticsPlatform,
        FunnelDefinition,
        FunnelStep,
    )

    platform = AnalyticsPlatform()
    fid = "funnel_1"
    platform.create_funnel(
        FunnelDefinition(
            id=fid,
            name="注册漏斗",
            steps=[
                FunnelStep(name="访问", event_type="page", event_name="landing"),
                FunnelStep(name="注册", event_type="action", event_name="signup"),
            ],
            time_window_minutes=30,
        )
    )

    # 通过公共方法触发 _ensure_loaded（模拟重启后首次访问）
    fresh = AnalyticsPlatform()
    result = fresh.analyze_funnel(fid)
    assert result is not None
    assert result.definition.name == "注册漏斗"
    assert len(result.definition.steps) == 2
    assert result.definition.steps[0].event_name == "landing"
    assert result.definition.time_window_minutes == 30


def test_ab_test_assign_and_convert_persist(tmp_db):
    from caipiao.web.analytics import ABTest, ABTestVariant, AnalyticsPlatform

    platform = AnalyticsPlatform()
    tid = "ab_1"
    platform.create_ab_test(
        ABTest(
            id=tid,
            name="按钮颜色实验",
            variants=[
                ABTestVariant(name="control", weight=1),
                ABTestVariant(name="variant", weight=1),
            ],
            status="running",
        )
    )

    assigned = platform.assign_variant(tid, "user_a")
    assert assigned in ("control", "variant")
    platform.record_conversion(tid, assigned)

    # 全新实例应反映分配/转化计数
    fresh = AnalyticsPlatform()
    results = fresh.get_ab_test_results(tid)
    assert results is not None
    total_assigned = sum(v["assigned_users"] for v in results["variants"])
    total_conversions = sum(v["conversions"] for v in results["variants"])
    assert total_assigned == 1
    assert total_conversions == 1


def test_ab_test_delete_persists(tmp_db):
    from caipiao.web.analytics import ABTest, ABTestVariant, AnalyticsPlatform

    platform = AnalyticsPlatform()
    tid = "ab_del"
    platform.create_ab_test(
        ABTest(
            id=tid,
            name="待删实验",
            variants=[ABTestVariant(name="a", weight=1)],
        )
    )

    # 删除（通过持久层移除定义）
    platform._ab_tests.pop(tid)
    platform._persist_ab_test(tid)

    fresh = AnalyticsPlatform()
    assert fresh.get_ab_test_results(tid) is None
