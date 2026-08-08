"""端点级测试：统计分析（stats）与 AI 深度分析（ai_analysis）两个路由。

这两个路由直接复用核心层 ``DrawAnalyzer`` / ``DrawRepository``，因此测试前把仓库里的
真实开奖数据复制到当前 DATA_ROOT，保证与生产同构。额外写入一份只有 5 期的 qxc 小数据集，
用于触发「样本不足」相关分支（准确率 0、建议调整策略）。
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

# 小样本彩种：仅本文件使用，用于覆盖样本不足分支
SMALL_KEY = "qxc"
SMALL_RECORDS = [
    {"issue": "2100001", "draw_date": "2021-01-01", "profile": "qxc", "groups": {"pos": [1, 2, 3, 4, 5, 6, 7]}},
    {"issue": "2100002", "draw_date": "2021-01-02", "profile": "qxc", "groups": {"pos": [1, 2, 3, 4, 5, 6, 8]}},
    {"issue": "2100003", "draw_date": "2021-01-03", "profile": "qxc", "groups": {"pos": [2, 3, 4, 5, 6, 7, 9]}},
    {"issue": "2100004", "draw_date": "2021-01-04", "profile": "qxc", "groups": {"pos": [0, 1, 2, 3, 4, 5, 6]}},
    {"issue": "2100005", "draw_date": "2021-01-05", "profile": "qxc", "groups": {"pos": [3, 4, 5, 6, 7, 8, 9]}},
]


def _make_env() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_web_stats_"))
    os.environ.setdefault("CAIPIAO_WEB_DB", f"sqlite:///{tmp / 'stats.db'}")
    os.environ.setdefault("CAIPIAO_WEB_DATA", str(tmp))
    os.environ.setdefault("CAIPIAO_WEB_SECRET", "test-secret-stats")
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
    os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
    return tmp


@pytest.fixture(scope="module")
def client():
    _make_env()
    from fastapi.testclient import TestClient

    from web_main import app as fastapi_app

    # 真实 DATA_ROOT 由最先导入 web_main 的测试模块决定，这里按其实际取值补齐数据，
    # 保证本文件单独运行和全量运行行为一致。
    from caipiao.web.config import DATA_ROOT

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for src in Path(".caipiao").glob("draws*.json"):
        dst = DATA_ROOT / src.name
        if not dst.exists():
            shutil.copy(src, dst)
    (DATA_ROOT / "draws_qxc.json").write_text(
        json.dumps(SMALL_RECORDS, ensure_ascii=False), encoding="utf-8"
    )

    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client) -> str:
    username = f"stats_{uuid.uuid4().hex[:10]}"
    r = client.post("/auth/register", json={"username": username, "password": "pw123456"})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": "pw123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# --------------------------------------------------------------------------- #
# /profiles/{key}/missing-analysis
# --------------------------------------------------------------------------- #
def test_missing_analysis_default_windows(client):
    r = client.get("/profiles/ssq/missing-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile_key"] == "ssq"
    assert body["primary_group"] == "red"
    assert body["windows"] == [10, 30, 50, 100]
    assert set(body["missing_by_window"]) == {"10", "30", "50", "100"}
    assert all({"number", "gap"} == set(i) for i in body["missing_by_window"]["10"])

    # 双色球红球 1-33 + 蓝球 1-16，趋势覆盖所有分组的全部号码
    assert len(body["trend_data"]) == 33 + 16
    assert {i["trend"] for i in body["trend_data"]} <= {"up", "down", "stable"}
    for item in body["trend_data"]:
        assert item["change"] == item["recent_gap"] - item["current_gap"]

    assert isinstance(body["hot_signals"], list)
    assert isinstance(body["cold_signals"], list)
    assert sum(body["gap_distribution"].values()) == len(body["trend_data"])


def test_missing_analysis_custom_windows(client):
    r = client.get("/profiles/dlt/missing-analysis", params={"windows": " 5 , 20 ,, 7 "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["windows"] == [5, 20, 7]
    assert set(body["missing_by_window"]) == {"5", "20", "7"}


def test_missing_analysis_small_dataset(client):
    r = client.get(f"/profiles/{SMALL_KEY}/missing-analysis", params={"windows": "3"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["windows"] == [3]
    assert body["primary_group"] == "pos"


# --------------------------------------------------------------------------- #
# /profiles/{key}/combo-analysis
# --------------------------------------------------------------------------- #
def test_combo_analysis(client):
    r = client.get("/profiles/ssq/combo-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile_key"] == "ssq"
    assert body["total_records"] > 0
    assert len(body["common_pairs"]) <= 15
    assert all(len(p["pair"]) == 2 and p["count"] > 0 for p in body["common_pairs"])
    # 三连号：每项为升序连续三个号码
    assert len(body["common_triples"]) <= 10
    for t in body["common_triples"]:
        nums = t["list"]
        assert len(nums) == 3
        assert nums[1] == nums[0] + 1 and nums[2] == nums[1] + 1
    assert isinstance(body["zone_distribution"], dict)
    assert isinstance(body["consecutive_frequency"], float)
    assert isinstance(body["consecutive_distribution"], dict)


def test_combo_analysis_small_dataset(client):
    r = client.get(f"/profiles/{SMALL_KEY}/combo-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_records"] == len(SMALL_RECORDS)


# --------------------------------------------------------------------------- #
# /profiles/{key}/trend-analysis
# --------------------------------------------------------------------------- #
def test_trend_analysis(client):
    r = client.get("/profiles/ssq/trend-analysis", params={"rounds": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_rounds"] == 12
    assert len(body["trends"]) == 12
    first = body["trends"][0]
    assert {"draw_date", "issue", "numbers"} == set(first)
    assert "red" in first["numbers"]
    # 结果按开奖日期升序
    dates = [t["draw_date"] for t in body["trends"]]
    assert dates == sorted(dates)


def test_trend_analysis_rounds_exceeds_data(client):
    r = client.get(f"/profiles/{SMALL_KEY}/trend-analysis", params={"rounds": 200})
    assert r.status_code == 200, r.text
    assert r.json()["total_rounds"] == len(SMALL_RECORDS)


def test_trend_analysis_rounds_validated(client):
    assert client.get("/profiles/ssq/trend-analysis", params={"rounds": 0}).status_code == 422
    assert client.get("/profiles/ssq/trend-analysis", params={"rounds": 201}).status_code == 422


# --------------------------------------------------------------------------- #
# /profiles/{key}/export
# --------------------------------------------------------------------------- #
def test_export_csv(client):
    r = client.get(f"/profiles/{SMALL_KEY}/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "qxc_data.csv" in r.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["日期", "期号"] + [f"号码_{i + 1}" for i in range(7)]
    assert len(rows) == 1 + len(SMALL_RECORDS)
    # 数据按日期倒序
    assert rows[1][0].startswith("2021-01-05")
    assert rows[-1][0].startswith("2021-01-01")
    assert rows[-1][2:] == ["1", "2", "3", "4", "5", "6", "7"]


def test_export_multi_group_profile(client):
    r = client.get("/profiles/ssq/export", params={"format": "csv"})
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    # 红球 6 列 + 蓝球 1 列
    assert len(rows[0]) == 2 + 6 + 1
    assert len(rows) > 100


def test_export_format_validated(client):
    assert client.get("/profiles/ssq/export", params={"format": "excel"}).status_code == 200
    assert client.get("/profiles/ssq/export", params={"format": "pdf"}).status_code == 422


# --------------------------------------------------------------------------- #
# /profiles/{key}/recommendations
# --------------------------------------------------------------------------- #
def test_recommendations_requires_auth(client):
    assert client.get("/profiles/ssq/recommendations").status_code == 401


def test_recommendations(client, token):
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/profiles/ssq/recommendations", params={"top_n": 3}, headers=h)
    assert r.status_code == 200, r.text
    items = r.json()
    assert 0 < len(items) <= 3
    for item in items:
        assert item["strategy_id"]
        assert item["strategy_name"]
        assert isinstance(item["score"], float)
        assert item["reason"]
        assert isinstance(item["suggested_params"], dict)
        assert isinstance(item["tags"], list)
    # 分数降序
    assert [i["score"] for i in items] == sorted((i["score"] for i in items), reverse=True)


def test_recommendations_top_n_validated(client, token):
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/profiles/ssq/recommendations", params={"top_n": 0}, headers=h).status_code == 422
    assert client.get("/profiles/ssq/recommendations", params={"top_n": 11}, headers=h).status_code == 422


# --------------------------------------------------------------------------- #
# /profiles/{key}/multi-period-analysis
# --------------------------------------------------------------------------- #
def test_multi_period_analysis(client):
    r = client.get("/profiles/ssq/multi-period-analysis", params={"periods": 8})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile_key"] == "ssq"
    assert body["periods_analyzed"] == 8
    assert len(body["zone_history"]) == 8
    assert all({"date", "zone1", "zone2", "zone3"} == set(z) for z in body["zone_history"])
    assert all(z["zone1"] + z["zone2"] + z["zone3"] == 6 for z in body["zone_history"])

    assert len(body["common_pairs"]) <= 10
    assert all(len(p["pair"]) == 2 for p in body["common_pairs"])

    assert len(body["consecutive_appearances"]) <= 10
    for item in body["consecutive_appearances"]:
        assert item["appearances"] >= 2
        assert len(item["positions"]) == item["appearances"]
        assert isinstance(item["streak"], bool)
    counts = [i["appearances"] for i in body["consecutive_appearances"]]
    assert counts == sorted(counts, reverse=True)

    strategies = {s["strategy"] for s in body["suggestions"]}
    assert {"热门组合", "冷热交替", "共现组合"} <= strategies
    for s in body["suggestions"]:
        assert s["numbers"]
        assert s["reason"]


def test_multi_period_analysis_small_dataset(client):
    r = client.get(f"/profiles/{SMALL_KEY}/multi-period-analysis", params={"periods": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["periods_analyzed"] == 2
    assert len(body["zone_history"]) == 2


def test_multi_period_analysis_periods_validated(client):
    assert client.get("/profiles/ssq/multi-period-analysis", params={"periods": 1}).status_code == 422
    assert client.get("/profiles/ssq/multi-period-analysis", params={"periods": 21}).status_code == 422


# --------------------------------------------------------------------------- #
# /profiles/compare-lotteries
# --------------------------------------------------------------------------- #
def test_compare_lotteries(client):
    r = client.get("/profiles/compare-lotteries", params={"keys": "ssq,dlt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["key"] for c in body["comparisons"]] == ["ssq", "dlt"]
    for c in body["comparisons"]:
        assert c["name"]
        assert c["category"] in {"welfare", "sports"}
        assert c["total_records"] > 0
        assert len(c["hot_numbers"]) == 5
        assert len(c["cold_numbers"]) == 5
        assert len(c["odd_even_ratio"]) == 2
        assert len(c["high_low_ratio"]) == 2
        assert c["sum_span"] >= 0

    types = [i["type"] for i in body["insights"]]
    assert types == ["odd_even", "sum"]
    assert all(i["description"] for i in body["insights"])


def test_compare_lotteries_skips_unknown_keys(client):
    r = client.get("/profiles/compare-lotteries", params={"keys": "ssq, nope ,dlt"})
    assert r.status_code == 200, r.text
    assert [c["key"] for c in r.json()["comparisons"]] == ["ssq", "dlt"]


def test_compare_lotteries_single_key_rejected(client):
    r = client.get("/profiles/compare-lotteries", params={"keys": "ssq"})
    assert r.status_code == 400
    assert "至少需要2个彩种" in r.json()["detail"]

    r = client.get("/profiles/compare-lotteries", params={"keys": " , "})
    assert r.status_code == 400


def test_compare_lotteries_all_unknown_yields_no_insights(client):
    r = client.get("/profiles/compare-lotteries", params={"keys": "nope1,nope2"})
    assert r.status_code == 200
    assert r.json() == {"comparisons": [], "insights": []}


# --------------------------------------------------------------------------- #
# /profiles/{key}/ai-analysis
# --------------------------------------------------------------------------- #
def _assert_ai_shape(body: dict, key: str) -> None:
    assert body["profile_key"] == key
    for p in body["patterns"]:
        assert p["pattern_type"] in {
            "consecutive", "hot_repeat", "zone_dominant", "odd_even_bias"
        }
        assert p["description"]
        assert 0 <= p["confidence"] <= 1
        assert p["frequency"] >= 0
    for a in body["anomalies"]:
        assert a["anomaly_type"] in {"cold_dominant", "zone_concentrated"}
        assert a["severity"] in {"low", "medium", "high"}
        assert a["draw_date"] and a["issue"]
    for pred in body["predictions"]:
        assert pred["numbers"]
        assert 0 <= pred["confidence"] <= 1
        assert pred["factors"]
    assert 0 <= body["model_accuracy"] <= 1
    assert body["analysis_summary"].endswith("。")


def test_ai_analysis_ssq(client):
    r = client.get("/profiles/ssq/ai-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_ai_shape(body, "ssq")
    assert body["patterns"], "双色球历史数据应能检测出模式"
    # 默认 depth=3 => 最多 6 个模式
    assert len(body["patterns"]) <= 6
    assert len(body["anomalies"]) <= 5
    # 三条预测路径在数据充足时都会命中
    assert len(body["predictions"]) == 3
    assert "模型准确率约" in body["analysis_summary"]


def test_ai_analysis_depth_limits_patterns(client):
    r = client.get("/profiles/kl8/ai-analysis", params={"depth": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_ai_shape(body, "kl8")
    assert len(body["patterns"]) <= 2

    r = client.get("/profiles/kl8/ai-analysis", params={"depth": 5})
    assert r.status_code == 200
    assert len(r.json()["patterns"]) <= 10


def test_ai_analysis_zone_concentrated_profile(client):
    """福彩3D 号码全在 0-9，必然落在 zone1，触发区间集中/主导分支。"""
    r = client.get("/profiles/3d/ai-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_ai_shape(body, "3d")
    assert any(p["pattern_type"] == "zone_dominant" for p in body["patterns"])
    assert any(a["anomaly_type"] == "zone_concentrated" for a in body["anomalies"])


def test_ai_analysis_small_dataset_has_zero_accuracy(client):
    r = client.get(f"/profiles/{SMALL_KEY}/ai-analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_ai_shape(body, SMALL_KEY)
    # 样本 < 20 期时准确率直接返回 0，摘要走「建议调整策略」分支
    assert body["model_accuracy"] == 0.0
    assert "建议调整策略" in body["analysis_summary"]


def test_ai_analysis_depth_validated(client):
    assert client.get("/profiles/ssq/ai-analysis", params={"depth": 0}).status_code == 422
    assert client.get("/profiles/ssq/ai-analysis", params={"depth": 6}).status_code == 422
