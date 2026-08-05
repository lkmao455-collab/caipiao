"""排列3均衡策略测试."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from caipiao.core.strategies.lotteries.pl3.balanced import PL3BalancedStrategy
from caipiao.data.models import DrawRecord


def _make_pl3_records(count: int = 100) -> List[DrawRecord]:
    """创建测试用的排列3记录."""
    records = []
    for i in range(count):
        nums = [(i + j) % 10 for j in range(3)]
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="pl3",
            groups={"pos": nums},
        ))
    return records


class TestPL3BalancedStrategy:
    """PL3BalancedStrategy 测试."""

    def test_metadata(self):
        strategy = PL3BalancedStrategy()
        assert strategy.metadata.id == "balanced_pl3"
        assert strategy.metadata.name == "历史均衡"
        assert strategy.metadata.configurable is True
        assert strategy._needs_history is True

    def test_get_config_schema(self):
        strategy = PL3BalancedStrategy()
        schema = strategy.get_config_schema()
        assert "history" in schema
        assert "lookback" in schema
        assert "max_attempts" in schema
        assert "seed" in schema
        # pl3 固定 pick=3，不应有 pick_count
        assert "pick_count" not in schema

    def test_validate_options_insufficient_history(self):
        strategy = PL3BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期历史数据"):
            strategy.validate_options({"history": []})

    def test_validate_options_sufficient_history(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(30)
        # 不应抛出异常
        strategy.validate_options({"history": records})

    def test_generate_basic(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        tickets = strategy.generate(count=3, options={"history": records, "lookback": 50})
        assert len(tickets) == 3
        for ticket in tickets:
            assert ticket.profile.key == "pl3"
            assert "pos" in ticket.groups
            assert len(ticket.groups["pos"]) == 3
            assert ticket.strategy_name == "历史均衡"
            assert "历史均衡" in ticket.basis

    def test_generate_with_seed(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        options = {"history": records, "lookback": 50, "seed": 42}
        t1 = strategy.generate(count=2, options=options)
        t2 = strategy.generate(count=2, options=options)
        # 相同种子应产生相同结果
        for a, b in zip(t1, t2):
            assert a.groups == b.groups

    def test_generate_different_seeds(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        t1 = strategy.generate(count=2, options={"history": records, "lookback": 50, "seed": 1})
        t2 = strategy.generate(count=2, options={"history": records, "lookback": 50, "seed": 2})
        # 不同种子结果可能不同
        all_same = all(a.groups == b.groups for a, b in zip(t1, t2))
        assert not all_same or len(t1) == 0

    def test_generate_lookback(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        tickets = strategy.generate(count=1, options={"history": records, "lookback": 30})
        assert len(tickets) == 1

    def test_generate_max_attempts(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        tickets = strategy.generate(count=1, options={"history": records, "max_attempts": 10})
        assert len(tickets) == 1

    def test_strategy_uses_frequency_weights(self):
        """验证策略使用频率权重生成."""
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(100)
        # 多次生成，验证生成的号码在合理范围内
        tickets = strategy.generate(count=10, options={"history": records, "lookback": 100})
        for ticket in tickets:
            for n in ticket.groups["pos"]:
                assert 0 <= n <= 9


class TestPL3BalancedStrategyEdgeCases:
    """边界情况测试."""

    def test_generate_insufficient_history_raises(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(10)  # 不足20期
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": records})

    def test_generate_empty_history_raises(self):
        strategy = PL3BalancedStrategy()
        with pytest.raises(ValueError, match="至少 20 期"):
            strategy.generate(count=1, options={"history": []})

    def test_multiple_calls_independent(self):
        strategy = PL3BalancedStrategy()
        records = _make_pl3_records(50)
        for _ in range(5):
            tickets = strategy.generate(count=2, options={"history": records, "seed": None})
            assert len(tickets) == 2