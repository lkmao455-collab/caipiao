"""BatchBacktestThread 集成测试.

验证后台线程能正确使用多进程 worker 完成批量历史回测，并按预期发出
result_ready 信号。
"""

import os
import pytest
from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import RandomStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.batch_backtest_thread import BatchBacktestThread


class MockRepository:
    """模拟数据仓库，仅实现 get_all() 接口."""

    def __init__(self, records):
        self._records = list(records)

    def get_all(self):
        return self._records[:]


def _make_records(n=10):
    return [
        DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        for i in range(n)
    ]


def test_batch_thread_runs_in_parallel():
    records = _make_records(5)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 5),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert exception is None, exception
    assert result is not None
    assert result.total_rounds == 5
    assert result.total_cost == 10


def test_batch_thread_progress_and_round_ready():
    records = _make_records(3)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 3),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )

    progress_calls = []
    round_ready_calls = []

    def on_progress(current, total):
        progress_calls.append((current, total))

    def on_round_ready(index, total, winners):
        round_ready_calls.append((index, total, winners))

    thread.progress.connect(on_progress)
    thread.round_ready.connect(on_round_ready)
    thread.run()

    assert len(progress_calls) == 3
    assert progress_calls[-1] == (3, 3)
    assert len(round_ready_calls) == 3
    assert all(call[1] == 3 for call in round_ready_calls)
    assert sorted(call[0] for call in round_ready_calls) == [1, 2, 3]


def test_batch_thread_empty_date_range():
    records = _make_records(5)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 1, 5),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert result is None
    assert isinstance(exception, ValueError)


def test_batch_thread_error_threshold_terminates_early():
    """当错误期数超过 30% 时，线程应提前终止并返回已收集的部分结果."""
    records = _make_records(5)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="hot_cold",
        profile=SSQ,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 5),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert exception is None
    assert result is not None
    assert result.total_rounds == 5
    # 5 期中历史不足的错误超过 30% 后提前终止，因此总花费小于完整 10 元
    assert result.total_cost < 10
    assert len(result.errors) >= 2
    assert all("history too short" in err for err in result.errors)


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="取消测试在 CI 多进程环境下不稳定",
)
def test_batch_thread_cancellation():
    """验证请求中断后线程能正常结束且不会崩溃.

    由于 as_completed 已经完成的任务无法撤回，本测试只保证取消流程不会抛异常。
    """
    records = _make_records(50)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 2, 19),
        tickets_per_round=1,
        options={},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    def on_progress(current, _total):
        if current >= 1:
            thread.requestInterruption()

    thread.result_ready.connect(on_finished)
    thread.progress.connect(on_progress)
    thread.run()

    assert exception is None
    assert result is not None
    assert result.total_rounds == 50

def test_batch_thread_ml_strategy():
    """验证 BatchBacktestThread 能正确运行 ML 策略（xgboost）。"""
    pytest.importorskip("xgboost")

    records = _make_ml_records(120)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="xgboost",
        profile=SSQ,
        start_date=datetime(2024, 4, 25),
        end_date=datetime(2024, 4, 29),
        tickets_per_round=1,
        options={"batch_backtest_workers": 1},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert exception is None, exception
    assert result is not None
    assert result.total_rounds == 5
    assert result.total_cost == 10
    assert len(result.errors) == 0


def test_normalize_max_workers():
    from caipiao.ui.batch_backtest_thread import (
        _DEFAULT_MAX_WORKERS,
        _normalize_max_workers,
    )

    assert _normalize_max_workers(1, cpu_count=4) == 1
    assert _normalize_max_workers(4, cpu_count=4) == 4
    assert _normalize_max_workers(8, cpu_count=4) == 4
    assert _normalize_max_workers(0, cpu_count=4) == 1
    assert _normalize_max_workers(-1, cpu_count=4) == 1
    assert _normalize_max_workers("2", cpu_count=4) == 2
    assert _normalize_max_workers("invalid", cpu_count=4) == _DEFAULT_MAX_WORKERS
    assert _normalize_max_workers(None, cpu_count=4) == _DEFAULT_MAX_WORKERS


def test_batch_thread_invalid_max_workers_uses_default():
    """非法的 batch_backtest_workers 应被归一化为有效值，不影响回测执行。"""
    records = _make_records(5)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = BatchBacktestThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 5),
        tickets_per_round=1,
        options={"batch_backtest_workers": "invalid"},
        data_repository=MockRepository(records),
        parent=None,
    )

    result = None
    exception = None

    def on_finished(r, exc):
        nonlocal result, exception
        result = r
        exception = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert exception is None, exception
    assert result is not None
    assert result.total_rounds == 5
    assert result.total_cost == 10


def _make_ml_records(n=120):
    """生成足够用于 ML 训练的历史记录（>=100 期）。"""
    records = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        base_offset = (i * 7) % 33
        nums = sorted({((base_offset + j * 13) % 33) + 1 for j in range(6)})
        while len(nums) < 6:
            nums.append(next(num for num in range(1, 34) if num not in nums))
            nums.sort()
        blue = (i * 5 + 3) % 16 + 1
        records.append(
            DrawRecord(
                issue=f"2024{i+1:03d}",
                draw_date=base + timedelta(days=i),
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records
