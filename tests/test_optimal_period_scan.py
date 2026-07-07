import pytest
from caipiao.core.backtest_data import RoundBacktestContext, RoundTask
from caipiao.ui.optimal_period_config import (
    OPTIMAL_PERIOD_RANGES,
    STRATEGY_PARAM_MAP,
    resolve_optimal_param,
)
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.data.models import DrawRecord
from datetime import datetime


class _MockExecutor:
    """在单进程内立即执行提交的函数，便于测试 scan_param_values."""

    def __init__(self, *args, **kwargs):
        pass

    def submit(self, fn, *args, **kwargs):
        class F:
            def result(self):
                return fn(*args, **kwargs)

            def cancel(self):
                pass

        return F()

    def shutdown(self, *args, **kwargs):
        pass


def test_scan_param_values_returns_results(monkeypatch):
    """scan_param_values 应返回每个参数值对应的 BatchBacktestResult."""
    from caipiao.ui.optimal_period_scan_thread import scan_param_values

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
    tasks = [RoundTask(index=0, actual=record)]

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor", _MockExecutor
    )

    results = scan_param_values(context, tasks, "lookback", [10, 20])
    assert len(results) == 2
    assert all(isinstance(r[1], BatchBacktestResult) for r in results)


def test_scan_param_values_supports_none_value(monkeypatch):
    """参数值为 None 时，不应向 options 注入参数，用于无参策略扫描."""
    from caipiao.ui.optimal_period_scan_thread import scan_param_values

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
    tasks = [RoundTask(index=0, actual=record)]

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor", _MockExecutor
    )

    results = scan_param_values(context, tasks, "unused_param", [None])
    assert len(results) == 1
    assert results[0][0] is None
    assert isinstance(results[0][1], BatchBacktestResult)


def test_resolve_param_for_smart_hot_cold():
    result = resolve_optimal_param("smart_hot_cold")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"
    assert values == OPTIMAL_PERIOD_RANGES["lookback"]


def test_resolve_param_for_xgboost():
    result = resolve_optimal_param("xgboost")
    assert result is not None
    param_name, values = result
    assert param_name == "history_count"
    assert values == OPTIMAL_PERIOD_RANGES["history_count"]


def test_resolve_param_for_generic_balanced():
    result = resolve_optimal_param("balanced_3d")
    assert result is not None
    param_name, values = result
    assert param_name == "lookback"


def test_resolve_param_unsupported():
    assert resolve_optimal_param("random") is None
    assert resolve_optimal_param("odd_even") is None


from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import SmartHotColdStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.optimal_period_scan_thread import OptimalPeriodScanThread, ScanResult


class _MockRepository:
    def __init__(self, records):
        self._records = list(records)

    def get_all(self):
        return self._records[:]


def _make_records(n=120):
    records = []
    base = datetime(2023, 1, 1)
    for i in range(n):
        base_offset = (i * 7) % 33
        nums = sorted({((base_offset + j * 13) % 33) + 1 for j in range(6)})
        while len(nums) < 6:
            nums.append(next(num for num in range(1, 34) if num not in nums))
            nums.sort()
        blue = (i * 5 + 3) % 16 + 1
        records.append(
            DrawRecord(
                issue=f"2023{i+1:03d}",
                draw_date=base + timedelta(days=i),
                red_balls=sorted(nums),
                blue_ball=blue,
            )
        )
    return records


def test_scan_thread_finds_optimal_lookback():
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert error is None, error
    assert isinstance(result, ScanResult)
    assert result.param_name == "lookback"
    assert result.optimal_value in result.all_values
    assert result.optimal_result.total_rounds == 10


def test_scan_thread_unsupported_strategy():
    records = _make_records(10)
    engine = GenerationEngine()
    from caipiao.core.strategies import RandomStrategy

    engine.register(RandomStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="random",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 1, 10),
        tickets_per_round=1,
        base_options={},
        plugin_dir=None,
    )

    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()

    assert result is None
    assert isinstance(error, ValueError)


# --------------------------------------------------------------------------- #
# Helpers for synchronous, in-process scan tests
# --------------------------------------------------------------------------- #
class _MockFuture:
    def __init__(self):
        self._result = None
        self._exception = None

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result

    def cancel(self):
        pass


class _MockProcessPoolExecutor:
    """在单进程内立即执行提交的函数，便于测试失败隔离与中断逻辑."""

    def __init__(self, *args, **kwargs):
        pass

    def submit(self, fn, *args, **kwargs):
        future = _MockFuture()
        try:
            future._result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            future._exception = exc
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def _run_thread(thread: OptimalPeriodScanThread):
    """同步运行线程并返回 (result, error)."""
    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()
    return result, error


def test_scan_thread_skips_failed_values(monkeypatch):
    """单个参数值失败时不应导致整体扫描失败."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor",
        _MockProcessPoolExecutor,
    )

    from caipiao.ui.optimal_period_scan_thread import _run_one_value

    original = _run_one_value

    def _patched_run_one_value(context, tasks, total_rounds):
        if context.options.get("lookback") == 50:
            raise RuntimeError("simulated failure for lookback=50")
        return original(context, tasks, total_rounds)

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread._run_one_value",
        _patched_run_one_value,
    )

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, ScanResult)
    assert result.optimal_value != 50
    failed = [value for value, res in result.all_results if res.errors]
    assert 50 in failed


def test_scan_thread_failed_value_not_optimal(monkeypatch):
    """失败的最小参数值不应被选为最优，即使成功结果奖金均为零."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor",
        _MockProcessPoolExecutor,
    )

    from caipiao.ui.batch_backtest_result import BatchBacktestResult

    def _patched_run_one_value(context, tasks, total_rounds):
        lookback = context.options.get("lookback")
        if lookback == 20:
            return BatchBacktestResult(
                total_rounds=total_rounds,
                errors=["simulated failure for lookback=20"],
            )
        return BatchBacktestResult(total_rounds=total_rounds)

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread._run_one_value",
        _patched_run_one_value,
    )

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, ScanResult)
    assert result.optimal_value == 50
    failed = [value for value, res in result.all_results if res.errors]
    assert 20 in failed


def test_scan_thread_insufficient_history():
    """需要历史数据的策略在记录不足 100 期时应返回数据不足错误."""
    records = _make_records(50)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 1, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert result is None
    assert isinstance(error, ValueError)
    assert "历史数据不足" in str(error)
    assert "100" in str(error)


def test_scan_thread_empty_date_range():
    """日期范围内没有记录时应返回明确错误."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 1, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert result is None
    assert isinstance(error, ValueError)
    assert "没有开奖记录" in str(error)


def test_scan_thread_interruption(monkeypatch):
    """请求中断后，ScanResult 应标记为 interrupted."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    monkeypatch.setattr(
        "caipiao.ui.optimal_period_scan_thread.ProcessPoolExecutor",
        _MockProcessPoolExecutor,
    )

    thread = OptimalPeriodScanThread(
        engine=engine,
        strategy_id="smart_hot_cold",
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 30),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    class _InterruptAfter:
        def __init__(self, n):
            self._count = 0
            self._n = n

        def __call__(self):
            self._count += 1
            return self._count > self._n

    monkeypatch.setattr(thread, "isInterruptionRequested", _InterruptAfter(2))

    result, error = _run_thread(thread)

    assert isinstance(result, ScanResult)
    assert result.interrupted is True
    assert len(result.all_results) < len(OPTIMAL_PERIOD_RANGES["lookback"])
