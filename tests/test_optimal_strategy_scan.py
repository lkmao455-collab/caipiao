import pytest
from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies import HotColdStrategy, RandomStrategy, SmartHotColdStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.ui.optimal_period_config import (
    build_param_combinations,
    resolve_optimal_param_grid,
)
from caipiao.ui.optimal_strategy_scan_thread import (
    OptimalStrategyScanThread,
    StrategyScanResult,
)


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


def _run_thread(thread):
    result = None
    error = None

    def on_finished(r, exc):
        nonlocal result, error
        result = r
        error = exc

    thread.result_ready.connect(on_finished)
    thread.run()
    return result, error


def test_strategy_scan_finds_best():
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(HotColdStrategy())
    engine.register(SmartHotColdStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
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
    assert isinstance(result, StrategyScanResult)
    assert result.optimal_strategy_id in ("hot_cold", "smart_hot_cold")
    assert result.optimal_result.total_rounds == 10



def test_strategy_scan_no_history_strategies():
    """引擎中无历史依赖策略时应返回明确错误."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(RandomStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 10),
        tickets_per_round=1,
        base_options={},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert result is None
    assert isinstance(error, ValueError)
    assert "没有使用历史数据的策略" in str(error)


def test_strategy_scan_insufficient_history():
    """历史记录不足 100 期时应返回数据不足错误."""
    records = _make_records(50)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
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


def test_strategy_scan_empty_date_range():
    """日期范围内没有记录时应返回明确错误."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
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


def test_pick_best_param_prefers_higher_prize_then_hits_then_lower_value():
    """_pick_best_param 应按固定奖金 > 中奖次数 > 参数值升序选择."""
    results = [
        (20, BatchBacktestResult(total_fixed_prize=100, hit_count=2)),
        (50, BatchBacktestResult(total_fixed_prize=200, hit_count=1)),
        (80, BatchBacktestResult(total_fixed_prize=200, hit_count=3)),
        (100, BatchBacktestResult(total_fixed_prize=200, hit_count=3)),
    ]
    best = OptimalStrategyScanThread._pick_best_param(results)
    assert best is not None
    assert best[0] == 80


def test_pick_best_param_skips_failed_results():
    """_pick_best_param 应跳过含 errors 的失败结果."""
    results = [
        (20, BatchBacktestResult(errors=["fail"])),
        (50, BatchBacktestResult(total_fixed_prize=10)),
    ]
    best = OptimalStrategyScanThread._pick_best_param(results)
    assert best is not None
    assert best[0] == 50


def test_pick_best_param_all_failed():
    """_pick_best_param 全部失败时返回 None."""
    results = [
        (20, BatchBacktestResult(errors=["fail"])),
        (50, BatchBacktestResult(errors=["fail"])),
    ]
    assert OptimalStrategyScanThread._pick_best_param(results) is None


def test_pick_best_strategy_prefers_higher_prize_then_hits_then_id():
    """_pick_best_strategy 应按固定奖金 > 中奖次数 > 策略 id 升序选择."""
    results = [
        ("balanced", None, BatchBacktestResult(total_fixed_prize=50, hit_count=2)),
        ("hot_cold", None, BatchBacktestResult(total_fixed_prize=100, hit_count=1)),
        ("missing_number", 50, BatchBacktestResult(total_fixed_prize=100, hit_count=2)),
        ("smart_hot_cold", 100, BatchBacktestResult(total_fixed_prize=100, hit_count=2)),
    ]
    best = OptimalStrategyScanThread._pick_best_strategy(results)
    assert best is not None
    assert best[0] == "missing_number"


def test_pick_best_strategy_skips_failed_results():
    """_pick_best_strategy 应跳过失败的策略结果."""
    results = [
        ("hot_cold", None, BatchBacktestResult(errors=["fail"])),
        ("smart_hot_cold", 50, BatchBacktestResult(total_fixed_prize=10)),
    ]
    best = OptimalStrategyScanThread._pick_best_strategy(results)
    assert best is not None
    assert best[0] == "smart_hot_cold"


def test_strategy_scan_parameterless_strategy_has_none_value():
    """无独立参数的历史策略（如 hot_cold）扫描结果中 optimal_value 应为 None."""
    records = _make_records(120)
    engine = GenerationEngine()
    engine.register(HotColdStrategy())

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 4, 1),
        end_date=datetime(2023, 4, 5),
        tickets_per_round=1,
        base_options={},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, StrategyScanResult)
    assert result.optimal_strategy_id == "hot_cold"
    assert result.optimal_value is None
    assert result.param_name is None
    assert result.optimal_result.total_rounds == 5


def test_resolve_optimal_param_grid_for_smart_hot_cold():
    grid = resolve_optimal_param_grid("smart_hot_cold_3d")
    assert "lookback" in grid
    assert "hot_weight" in grid
    assert "cold_weight" in grid
    assert "temperature" in grid


def test_build_param_combinations_with_locked():
    grid = {"lookback": [50, 100], "hot_weight": [30, 70]}
    combos = build_param_combinations(grid, locked={"lookback": 50})
    assert len(combos) == 2
    assert all(c["lookback"] == 50 for c in combos)
    assert {c["hot_weight"] for c in combos} == {30, 70}
