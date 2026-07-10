"""福彩3D分散随机策略测试."""

from __future__ import annotations

import pytest

from caipiao.core.strategies.lotteries.fc3d.dispersed_random import (
    FC3DDispersedRandomStrategy,
)


def test_dispersed_random_strategy_exists():
    strategy = FC3DDispersedRandomStrategy()
    assert strategy.metadata.id == "dispersed_random_3d"
    tickets = strategy.generate(count=5, options={})
    assert len(tickets) == 5
