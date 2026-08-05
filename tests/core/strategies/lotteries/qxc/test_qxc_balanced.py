"""7星彩历史均衡策略测试."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from caipiao.core.strategies.lotteries.qxc.balanced import QXCBalancedStrategy
from caipiao.data.models import DrawRecord


def _make_qxc_records(count: int = 100) -> List[DrawRecord]:
    """创建测试用的7星彩记录."""
    records = []
    for i in range(count):
        nums = [(i + j) % 10 for j in range(7)]
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="qxc",
            groups={"pos": nums},
        ))
    return records


class TestQXCBalancedStrategy:
    """QXCBalancedStrategy 测试."""

    def test_metadata(self):
        strategy = QXCBalancedStrategy()
        assert strategy.metadata.id == "balanced_qxc"
        assert strategy.metadata.name == "历史均衡"
        assert strategy.metadata.configurable is True
        assert strategy._needs_history is True

    def test_get_config_schema(self):
        strategy = QXCBalancedStrategy()
        schema = strategy.get_config_schema()
        assert "history" in schema
        assert "lookback" in schema
        assert "max_attempts" in schema
        assert "seed" in schema
        # qxc 固定 pick=7
        assert "pick_count" not in schema

    def test_validate_options_insufficient_history(self):
        strategy = QXCBalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期历史数据"):
            strategy.validate_options({"history": []})

    def test_generate_basic(self):
        strategy = QXCBalancedStrategy()
        records = _make_qxc_records(100)
        tickets = strategy.generate(count=3, options={"history": records, "lookback": 50})
        assert len(tickets) == 3
        for ticket in tickets:
            assert ticket.profile.key == "qxc"
            assert "pos" in ticket.groups
            assert len(ticket.groups["pos"]) == 7
            assert ticket.strategy_name == "历史均衡"
            assert "历史均衡" in ticket.basis

    def test_generate_with_seed(self):
        strategy = QXCBalancedStrategy()
        records = _make_qxc_records(100)
        options = {"history": records, "lookback": 50, "seed": 42}
        t1 = strategy.generate(count=2, options=options)
        t2 = strategy.generate(count=2, options=options)
        for a, b in zip(t1, t2):
            assert a.groups == b.groups

    def test_strategy_uses_frequency_weights(self):
        strategy = QXCBalancedStrategy()
        records = _make_qxc_records(100)
        tickets = strategy.generate(count=10, options={"history": records, "lookback": 100})
        for ticket in tickets:
            for n in ticket.groups["pos"]:
                assert 0 <= n <= 9


class TestQXCBalancedStrategyEdgeCases:
    def test_generate_insufficient_history_raises(self):
        strategy = QXCBalancedStrategy()
        records = _make_qxc_records(10)
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": records})

    def test_generate_empty_history_raises(self):
        strategy = QXCBalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": []})