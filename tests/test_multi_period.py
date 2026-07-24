"""多期联合预测测试."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord
from caipiao.ml.multi_period import (
    MultiPeriodResult,
    PeriodPrediction,
    format_multi_period_report,
    predict_multi_period,
)
from caipiao.ml.predictor import MLPredictor


class TestPeriodPrediction:
    """PeriodPrediction 数据类测试."""

    def test_initial_state(self):
        pred = PeriodPrediction(
            period_index=0,
            red_proba=np.random.rand(33),
            blue_proba=np.random.rand(16),
            confidence=0.8,
        )
        assert pred.period_index == 0
        assert pred.confidence == 0.8


class TestMultiPeriodResult:
    """MultiPeriodResult 数据类测试."""

    def test_initial_state(self):
        result = MultiPeriodResult()
        assert result.period_count == 0

    def test_period_count(self):
        result = MultiPeriodResult()
        result.predictions = [
            PeriodPrediction(0, np.random.rand(33), np.random.rand(16), 0.8),
            PeriodPrediction(1, np.random.rand(33), np.random.rand(16), 0.7),
        ]
        assert result.period_count == 2

    def test_get_red_trend(self):
        result = MultiPeriodResult()
        result.predictions = [
            PeriodPrediction(0, np.array([0.1, 0.2, 0.3] + [0.0] * 30), np.random.rand(16), 0.8),
            PeriodPrediction(1, np.array([0.15, 0.25, 0.35] + [0.0] * 30), np.random.rand(16), 0.7),
        ]
        trend = result.get_red_trend()
        assert 0 in trend
        assert len(trend[0]) == 2

    def test_get_stable_numbers(self):
        result = MultiPeriodResult()
        # 创建稳定概率（波动小）
        stable_probs = np.full(33, 0.03)
        stable_probs[0] = 0.1
        stable_probs[1] = 0.1
        result.predictions = [
            PeriodPrediction(0, stable_probs.copy(), np.random.rand(16), 0.8),
            PeriodPrediction(1, stable_probs.copy(), np.random.rand(16), 0.7),
        ]
        stable = result.get_stable_numbers(threshold=0.9)
        assert 1 in stable or 2 in stable

    def test_summary(self):
        result = MultiPeriodResult()
        result.predictions = [
            PeriodPrediction(0, np.random.rand(33), np.random.rand(16), 0.8),
        ]
        result.recommendation = {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}
        summary = result.summary()
        assert "预测期数" in summary
        assert "各期预测" in summary


class TestPredictMultiPeriod:
    """多期预测测试."""

    def test_empty_records(self):
        """测试空记录 - 应返回空结果而不是抛异常."""
        predictor = MLPredictor(records=[], lookback=50)
        result = predict_multi_period(predictor, periods=1)
        assert result.period_count == 0

    def test_invalid_periods(self):
        """测试无效期数."""
        records = _make_ssq_records(100)
        predictor = MLPredictor(records=records, lookback=50)
        with pytest.raises(ValueError, match="预测期数必须大于 0"):
            predict_multi_period(predictor, periods=0)

    def test_too_many_periods(self):
        """测试过多期数."""
        records = _make_ssq_records(100)
        predictor = MLPredictor(records=records, lookback=50)
        with pytest.raises(ValueError, match="预测期数不能超过 20"):
            predict_multi_period(predictor, periods=21)


class TestFormatMultiPeriodReport:
    """报告格式化测试."""

    def test_empty_report(self):
        result = MultiPeriodResult()
        report = format_multi_period_report(result)
        assert "多期联合预测报告" in report
        assert "预测期数: 0" in report

    def test_report_with_data(self):
        result = MultiPeriodResult()
        result.predictions = [
            PeriodPrediction(
                0,
                np.random.rand(33),
                np.random.rand(16),
                0.8,
            ),
        ]
        result.recommendation = {"red": [1, 2, 3, 4, 5, 6], "blue": [7]}
        report = format_multi_period_report(result)
        assert "第 1 期预测" in report
        assert "综合推荐" in report


def _make_ssq_records(count: int = 100) -> list:
    """创建测试用的双色球记录."""
    records = []
    for i in range(count):
        reds = sorted([(i + j) % 33 + 1 for j in range(6)])
        blue = (i % 16) + 1
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=reds,
            blue_ball=blue,
        ))
    return records
