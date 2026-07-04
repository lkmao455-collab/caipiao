import pytest
from caipiao.ui.optimal_period_config import (
    OPTIMAL_PERIOD_RANGES,
    STRATEGY_PARAM_MAP,
    resolve_optimal_param,
)


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
