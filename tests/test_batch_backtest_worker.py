import pytest
from datetime import datetime
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.ui.batch_backtest_worker import (
    RoundBacktestContext,
    RoundTask,
    RoundResult,
    merge_round_results,
    worker_round_backtest,
)
from caipiao.data.models import DrawRecord


def test_worker_returns_round_result():
    record = DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1),
        red_balls=[1, 2, 3, 4, 5, 6],
        blue_ball=7,
    )
    context = RoundBacktestContext(
        strategy_id="random",
        profile_key="ssq",
        tickets_per_round=1,
        options={},
        is_ml=False,
        needs_history=False,
        records=[record],
        seed=42,
    )
    task = RoundTask(index=0, actual=record)
    result = worker_round_backtest(context, task)
    assert isinstance(result, RoundResult)
    assert result.index == 0
    assert result.error is None


def test_merge_round_results():
    r1 = RoundResult(index=0, total_cost=4, hit_count=1, total_fixed_prize=10)
    r2 = RoundResult(index=1, total_cost=4, hit_count=0, total_fixed_prize=0)
    merged = merge_round_results([r2, r1], total_rounds=2)
    assert isinstance(merged, BatchBacktestResult)
    assert merged.total_cost == 8
    assert merged.hit_count == 1
    assert merged.total_fixed_prize == 10
    assert merged.total_rounds == 2
    assert merged.float_prize_count == 0
    assert merged.first_ticket_hit_count == 0


def test_merge_round_results_sorts_by_index():
    r0 = RoundResult(
        index=0, total_cost=2, hit_count=1, first_ticket_hit_count=1,
        ticket_results=[{"round": 0, "ticket_index": 0}],
    )
    r1 = RoundResult(
        index=1, total_cost=2, hit_count=0, first_ticket_hit_count=0,
        ticket_results=[{"round": 1, "ticket_index": 0}],
    )
    r2 = RoundResult(
        index=2, total_cost=2, hit_count=1, first_ticket_hit_count=0,
        ticket_results=[{"round": 2, "ticket_index": 0}],
    )
    merged = merge_round_results([r2, r0, r1], total_rounds=3)
    assert merged.total_cost == 6
    assert merged.hit_count == 2
    assert merged.first_ticket_hit_count == 1
    assert [tr["round"] for tr in merged.ticket_results] == [0, 1, 2]


def test_merge_round_results_skips_error_rounds():
    r0 = RoundResult(index=0, total_cost=2, hit_count=1)
    r1 = RoundResult(index=1, error="history too short")
    r2 = RoundResult(index=2, total_cost=2, hit_count=0)
    merged = merge_round_results([r2, r0, r1], total_rounds=3)
    assert merged.total_cost == 4
    assert merged.hit_count == 1
    assert merged.total_rounds == 3


def test_prepare_ml_options_signature():
    # 仅验证函数可导入并返回 dict
    from caipiao.ui.batch_backtest_worker import prepare_ml_options

    result = prepare_ml_options([], {}, "ssq", datetime(2024, 1, 1), "/tmp")
    assert isinstance(result, dict)


def test_worker_round_backtest_with_plugin_strategy(tmp_path):
    """worker 应能在子进程中加载插件目录并使用自定义策略。"""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "test_lucky_plugin.py"
    plugin_file.write_text(
        '''
from __future__ import annotations
from typing import Any, Dict, List, Optional
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket

class TestLuckyStrategy(GenerationStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="test_lucky",
            name="测试幸运策略",
            description="仅用于测试的确定性策略。",
            version="1.0.0",
            author="test",
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {}

    def generate(self, count: int = 1, options: Optional[Dict[str, Any]] = None) -> List[Ticket]:
        options = options or {}
        return [
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7, strategy_name=self.metadata.name)
            for _ in range(count)
        ]
''',
        encoding="utf-8",
    )

    record = DrawRecord(
        issue="2024001",
        draw_date=datetime(2024, 1, 1),
        red_balls=[1, 2, 3, 4, 5, 6],
        blue_ball=7,
    )
    context = RoundBacktestContext(
        strategy_id="test_lucky",
        profile_key="ssq",
        tickets_per_round=2,
        options={},
        is_ml=False,
        needs_history=False,
        records=[record],
        seed=42,
        plugin_dir=str(plugin_dir),
    )
    task = RoundTask(index=0, actual=record)
    result = worker_round_backtest(context, task)

    assert isinstance(result, RoundResult)
    assert result.error is None
    assert result.total_cost == 4
    assert result.hit_count == 2
    assert result.first_ticket_hit_count == 1
