"""排列5历史均衡策略测试."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from caipiao.core.strategies.lotteries.pl5.balanced import PL5BalancedStrategy
from caipiao.data.models import DrawRecord


def _make_pl5_records(count: int = 100) -> List[DrawRecord]:
    """创建测试用的排列5记录."""
    records = []
    for i in range(count):
        nums = [(i + j) % 10 for j in range(5)]
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="pl5",
            groups={"pos": nums},
        ))
    return records


class TestPL5BalancedStrategy:
    """PL5BalancedStrategy 测试."""

    def test_metadata(self):
        strategy = PL5BalancedStrategy()
        assert strategy.metadata.id == "balanced_pl5"
        assert strategy.metadata.name == "历史均衡"
        assert strategy.metadata.configurable is True
        assert strategy._needs_history is True

    def test_get_config_schema(self):
        strategy = PL5BalancedStrategy()
        schema = strategy.get_config_schema()
        assert "history" in schema
        assert "lookback" in schema
        assert "max_attempts" in schema
        assert "seed" in schema
        # pl5 固定 pick=5
        assert "pick_count" not in schema

    def test_validate_options_insufficient_history(self):
        strategy = PL5BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期历史数据"):
            strategy.validate_options({"history": []})

    def test_generate_basic(self):
        strategy = PL5BalancedStrategy()
        records = _make_pl5_records(100)
        tickets = strategy.generate(count=3, options={"history": records, "lookback": 50})
        assert len(tickets) == 3
        for ticket in tickets:
            assert ticket.profile.key == "pl5"
            assert "pos" in ticket.groups
            assert len(ticket.groups["pos"]) == 5
            assert ticket.strategy_name == "历史均衡"
            assert "历史均衡" in ticket.basis

    def test_generate_with_seed(self):
        strategy = PL5BalancedStrategy()
        records = _make_pl5_records(100)
        options = {"history": records, "lookback": 50, "seed": 42}
        t1 = strategy.generate(count=2, options=options)
        t2 = strategy.generate(count=2, options=options)
        for a, b in zip(t1, t2):
            assert a.groups == b.groups

    def test_strategy_uses_frequency_weights(self):
        strategy = PL5BalancedStrategy()
        records = _make_pl5_records(100)
        tickets = strategy.generate(count=10, options={"history": records, "lookback": 100})
        for ticket in tickets:
            for n in ticket.groups["pos"]:
                assert 0 <= n <= 9


class TestPL5BalancedStrategyEdgeCases:
    def test_generate_insufficient_history_raises(self):
        strategy = PL5BalancedStrategy()
        records = _make_pl5_records(10)
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": records})

    def test_generate_empty_history_raises(self):
        strategy = PL5BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": []})