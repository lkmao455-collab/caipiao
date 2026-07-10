"""福彩3D三策略融合策略回归测试."""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from caipiao.core.strategies.lotteries.fc3d.ensemble import FC3DStrategyFusionStrategy
from caipiao.data.models import DrawRecord


def make_record(nums: list[int]) -> DrawRecord:
    """构造一条 3D 历史记录。"""
    return DrawRecord(
        issue="",
        draw_date=datetime.now(timezone.utc),
        profile="3d",
        groups={"pos": list(nums)},
    )


def test_zscore_list_uses_population_std():
    """N10: _zscore_list 应使用总体标准差。"""
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    # 总体标准差 sqrt(((1-3)^2 + ... + (5-3)^2)/5) = sqrt(2)
    expected = [(v - 3.0) / (2.0 ** 0.5) for v in vals]
    result = FC3DStrategyFusionStrategy._zscore_list(vals)
    for r, e in zip(result, expected):
        assert abs(r - e) < 1e-9
