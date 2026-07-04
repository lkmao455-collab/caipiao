import pytest
from datetime import datetime
from caipiao.ui.batch_backtest_worker import (
    RoundBacktestContext,
    RoundTask,
    RoundResult,
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
