"""多期联合预测模块.

提供多期联合预测功能，可以同时预测未来 N 期的号码出现概率。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..data.models import DrawRecord
from .features import build_prediction_features
from .predictor import MLPredictor

logger = logging.getLogger(__name__)


@dataclass
class PeriodPrediction:
    """单期预测结果."""

    period_index: int  # 期序号（0=下一期，1=下下期，...）
    red_proba: np.ndarray  # 33 个红球概率
    blue_proba: np.ndarray  # 16 个蓝球概率
    confidence: float  # 预测置信度（0-1）


@dataclass
class MultiPeriodResult:
    """多期预测结果."""

    predictions: List[PeriodPrediction] = field(default_factory=list)
    trend_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendation: Dict[str, Any] = field(default_factory=dict)

    @property
    def period_count(self) -> int:
        return len(self.predictions)

    def get_red_trend(self) -> Dict[int, List[float]]:
        """获取各红球在多期中的概率趋势."""
        trend: Dict[int, List[float]] = {}
        for pred in self.predictions:
            for i, prob in enumerate(pred.red_proba):
                if i not in trend:
                    trend[i] = []
                trend[i].append(float(prob))
        return trend

    def get_blue_trend(self) -> Dict[int, List[float]]:
        """获取各蓝球在多期中的概率趋势."""
        trend: Dict[int, List[float]] = {}
        for pred in self.predictions:
            for i, prob in enumerate(pred.blue_proba):
                if i not in trend:
                    trend[i] = []
                trend[i].append(float(prob))
        return trend

    def get_stable_numbers(self, threshold: float = 0.7) -> List[int]:
        """获取在多期中稳定出现的号码（概率波动小且较高）."""
        red_trend = self.get_red_trend()
        stable = []
        for num, probs in red_trend.items():
            if len(probs) >= 2:
                mean_prob = np.mean(probs)
                std_prob = np.std(probs)
                if mean_prob > 0.02 and std_prob / mean_prob < (1 - threshold):
                    stable.append(num + 1)  # 转换为 1-33
        return sorted(stable)

    def get_rising_numbers(self) -> List[int]:
        """获取概率上升趋势的号码."""
        red_trend = self.get_red_trend()
        rising = []
        for num, probs in red_trend.items():
            if len(probs) >= 2:
                # 简单线性趋势
                x = np.arange(len(probs))
                slope = np.polyfit(x, probs, 1)[0]
                if slope > 0.001:
                    rising.append(num + 1)
        return sorted(rising)

    def summary(self) -> Dict[str, Any]:
        """返回预测摘要."""
        return {
            "预测期数": self.period_count,
            "稳定号码": self.get_stable_numbers(),
            "上升趋势号码": self.get_rising_numbers(),
            "各期预测": [
                {
                    "期号": i + 1,
                    "红球概率TOP5": sorted(
                        [(j + 1, float(p)) for j, p in enumerate(pred.red_proba)],
                        key=lambda x: x[1],
                        reverse=True,
                    )[:5],
                    "蓝球概率TOP3": sorted(
                        [(j + 1, float(p)) for j, p in enumerate(pred.blue_proba)],
                        key=lambda x: x[1],
                        reverse=True,
                    )[:3],
                }
                for i, pred in enumerate(self.predictions)
            ],
        }


def predict_multi_period(
    predictor: MLPredictor,
    periods: int = 5,
    red_count: int = 6,
    blue_count: int = 1,
) -> MultiPeriodResult:
    """多期联合预测.

    通过递归预测的方式，预测未来 N 期的号码出现概率。
    每次预测后，将预测结果作为历史数据的一部分用于下一期预测。

    Args:
        predictor: 已训练的预测器
        periods: 预测期数
        red_count: 每期推荐红球数量
        blue_count: 每期推荐蓝球数量

    Returns:
        MultiPeriodResult 多期预测结果
    """
    if periods < 1:
        raise ValueError("预测期数必须大于 0")
    if periods > 20:
        raise ValueError("预测期数不能超过 20")

    result = MultiPeriodResult()

    # 获取当前特征
    current_records = predictor.records.copy()

    for i in range(periods):
        # 预测当前期
        X = build_prediction_features(current_records, predictor.lookback)
        if X.size == 0:
            logger.warning("第 %d 期预测失败：历史数据不足", i + 1)
            break

        try:
            red_proba, blue_proba = predictor.model.predict_proba(X)
        except Exception as exc:
            logger.warning("第 %d 期预测失败: %s", i + 1, exc)
            break

        # 计算置信度（基于概率分布的熵）
        red_entropy = -np.sum(red_proba * np.log(red_proba + 1e-10))
        blue_entropy = -np.sum(blue_proba * np.log(blue_proba + 1e-10))
        confidence = max(0, 1 - (red_entropy + blue_entropy) / 10)

        result.predictions.append(
            PeriodPrediction(
                period_index=i,
                red_proba=red_proba,
                blue_proba=blue_proba,
                confidence=confidence,
            )
        )

        # 为下一期预测生成虚拟记录
        # 使用当前预测的高概率号码作为虚拟开奖记录
        from ..core.ticket import Ticket
        from datetime import datetime, timedelta

        # 选择概率最高的号码
        top_reds = np.argsort(red_proba)[-red_count:] + 1
        top_blue = np.argmax(blue_proba) + 1

        # 创建虚拟记录
        last_date = current_records[-1].draw_date if current_records else datetime.now()
        next_date = last_date + timedelta(days=1)

        virtual_record = DrawRecord(
            issue=f"virtual_{i}",
            draw_date=next_date,
            red_balls=sorted(top_reds.tolist()),
            blue_ball=int(top_blue),
        )

        # 添加到记录列表（用于下一期预测）
        current_records = current_records + [virtual_record]

    # 趋势分析
    result.trend_analysis = {
        "stable_numbers": result.get_stable_numbers(),
        "rising_numbers": result.get_rising_numbers(),
    }

    # 生成推荐
    if result.predictions:
        last_pred = result.predictions[-1]
        top_reds = np.argsort(last_pred.red_proba)[-red_count:] + 1
        top_blues = np.argsort(last_pred.blue_proba)[-blue_count:] + 1
        result.recommendation = {
            "red": sorted(top_reds.tolist()),
            "blue": sorted(top_blues.tolist()),
        }

    return result


def format_multi_period_report(result: MultiPeriodResult) -> str:
    """格式化多期预测报告."""
    lines = [
        "=" * 50,
        "多期联合预测报告",
        "=" * 50,
        "",
        f"预测期数: {result.period_count}",
        "",
    ]

    for i, pred in enumerate(result.predictions):
        top_reds = np.argsort(pred.red_proba)[-5:] + 1
        top_blues = np.argsort(pred.blue_proba)[-3:] + 1

        lines.extend([
            f"第 {i + 1} 期预测:",
            "-" * 30,
            f"  红球 TOP5: {', '.join(str(n) for n in sorted(top_reds))}",
            f"  蓝球 TOP3: {', '.join(str(n) for n in sorted(top_blues))}",
            f"  置信度: {pred.confidence:.2%}",
            "",
        ])

    stable = result.get_stable_numbers()
    rising = result.get_rising_numbers()

    if stable:
        lines.extend([
            "稳定号码（多期概率波动小）:",
            "-" * 30,
            f"  {', '.join(str(n) for n in stable)}",
            "",
        ])

    if rising:
        lines.extend([
            "上升趋势号码:",
            "-" * 30,
            f"  {', '.join(str(n) for n in rising)}",
            "",
        ])

    if result.recommendation:
        lines.extend([
            "综合推荐:",
            "-" * 30,
            f"  红球: {', '.join(str(n) for n in result.recommendation.get('red', []))}",
            f"  蓝球: {', '.join(str(n) for n in result.recommendation.get('blue', []))}",
            "",
        ])

    lines.extend([
        "=" * 50,
        "注意：多期预测仅供参考，彩票开奖是随机事件",
        "=" * 50,
    ])

    return "\n".join(lines)
