import pytest
from datetime import datetime, timedelta

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.profile import FC3D
from caipiao.core.strategies import HotColdStrategy, RandomStrategy, SmartHotColdStrategy
from caipiao.core.strategies.fc3d import FC3DSmartHotColdStrategy
from caipiao.data.models import DrawRecord
from caipiao.persistence.optimal_param_store import OptimalParamStore
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.core.backtest_data import RoundResult
from caipiao.core.strategies.stability_validator import CrossValidationResult
from caipiao.ui.optimal_period_config import (
    OPTIMAL_PERIOD_RANGES,
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


def _make_3d_records(n=120):
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(n)
    ]


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


def test_strategy_scan_finds_best(monkeypatch):
    records = _make_records(150)
    engine = GenerationEngine()
    engine.register(HotColdStrategy())
    engine.register(SmartHotColdStrategy())

    def fake_scan_param_values(base_context, tasks, param_name, param_values, **kwargs):
        # 模拟两个策略的扫描结果，smart_hot_cold 更优
        if base_context.strategy_id == "smart_hot_cold":
            prize = 200
        else:
            prize = 100
        return [
            (
                value,
                BatchBacktestResult(
                    total_rounds=len(tasks),
                    total_cost=2 * len(tasks),
                    hit_count=len(tasks),
                    total_fixed_prize=prize,
                ),
            )
            for value in param_values
        ]

    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.scan_param_values",
        fake_scan_param_values,
    )

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 5, 1),
        end_date=datetime(2023, 5, 10),
        tickets_per_round=1,
        base_options={"hot_weight": 60, "cold_weight": 40},
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, StrategyScanResult)
    assert result.optimal_strategy_id == "smart_hot_cold"
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


def test_strategy_scan_parameterless_strategy_has_none_value(monkeypatch):
    """无独立参数的历史策略（如 hot_cold）扫描结果中 optimal_value 应为 None."""
    records = _make_records(150)
    engine = GenerationEngine()
    engine.register(HotColdStrategy())

    def fake_scan_param_values(base_context, tasks, param_name, param_values, **kwargs):
        return [
            (
                None,
                BatchBacktestResult(
                    total_rounds=len(tasks),
                    total_cost=2 * len(tasks),
                    hit_count=len(tasks),
                    total_fixed_prize=100,
                ),
            )
        ]

    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.scan_param_values",
        fake_scan_param_values,
    )

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 5, 1),
        end_date=datetime(2023, 5, 5),
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


def test_non_3d_strategy_uses_single_param_scan(monkeypatch):
    """无多参数网格但有 resolve_optimal_param 的非 3D 策略应扫描参数范围."""
    records = _make_records(150)
    engine = GenerationEngine()
    engine.register(SmartHotColdStrategy())

    captured = {}

    def fake_scan_param_values(base_context, tasks, param_name, param_values, **kwargs):
        captured["param_name"] = param_name
        captured["param_values"] = param_values
        captured["strategy_id"] = base_context.strategy_id
        # 返回一个成功结果，避免真实进程池
        return [
            (
                value,
                BatchBacktestResult(
                    total_rounds=len(tasks),
                    total_cost=2 * len(tasks),
                    hit_count=len(tasks),
                    total_fixed_prize=value or 0,
                ),
            )
            for value in param_values
        ]

    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.scan_param_values",
        fake_scan_param_values,
    )

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=SSQ,
        data_repository=_MockRepository(records),
        start_date=datetime(2023, 5, 1),
        end_date=datetime(2023, 5, 5),
        tickets_per_round=1,
        base_options={},
        plugin_dir=None,
    )
    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, StrategyScanResult)
    assert captured.get("strategy_id") == "smart_hot_cold"
    assert captured.get("param_name") == "lookback"
    assert captured.get("param_values") == OPTIMAL_PERIOD_RANGES["lookback"]
    assert result.param_names.get("smart_hot_cold") == "lookback"


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


def test_pick_best_strategy_prefers_stability_score():
    """_pick_best_strategy 在收益相近时应优先稳定性分数."""
    results = [
        ("low_stability", None, BatchBacktestResult(total_fixed_prize=200, hit_count=2)),
        ("high_stability", None, BatchBacktestResult(total_fixed_prize=200, hit_count=2)),
    ]
    cv_summary = {
        "low_stability": {"stability_score": 0.2},
        "high_stability": {"stability_score": 0.8},
    }
    best = OptimalStrategyScanThread._pick_best_strategy(results, cv_summary)
    assert best is not None
    assert best[0] == "high_stability"


def test_scan_respects_locked_params(monkeypatch, tmp_path):
    """扫描应使用注入的 OptimalParamStore 并尊重锁定参数."""
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "smart_hot_cold_3d", "lookback", 50)

    records = _make_3d_records(120)
    engine = GenerationEngine()
    engine.register(FC3DSmartHotColdStrategy())

    captured = {}

    def fake_cross_validate(base_context, tasks, combos, **kwargs):
        captured["combos"] = combos
        captured["n_folds"] = kwargs.get("n_folds")
        return [
            CrossValidationResult(
                params=combos[0] if combos else {},
                stability_score=0.9,
                mean_fixed_prize=100,
                std_fixed_prize=10,
                fold_results=[BatchBacktestResult()],
            )
        ]

    def fake_worker(context, task):
        return RoundResult(index=task.index)

    def fake_merge(results, total_rounds):
        return BatchBacktestResult(
            total_rounds=total_rounds,
            total_cost=2 * total_rounds,
            hit_count=total_rounds,
            total_fixed_prize=100 * total_rounds,
        )

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.cross_validate_params",
        fake_cross_validate,
    )
    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.worker_round_backtest",
        fake_worker,
    )
    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.merge_round_results",
        fake_merge,
    )

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=FC3D,
        data_repository=_MockRepository(records),
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 4, 10),
        tickets_per_round=1,
        base_options={},
        param_store=store,
        plugin_dir=None,
    )

    result, error = _run_thread(thread)

    assert error is None, error
    assert isinstance(result, StrategyScanResult)
    assert result.optimal_strategy_id == "smart_hot_cold_3d"
    assert result.locked_params.get("smart_hot_cold_3d", {}).get("lookback") == 50
    assert result.cv_results.get("smart_hot_cold_3d", {}).get("stability_score") == 0.9
    assert "combos" in captured
    assert all(c["lookback"] == 50 for c in captured["combos"])


def test_scan_downgrades_n_folds_for_large_grid(monkeypatch, tmp_path):
    """大网格扫描时应自动降级为 n_folds=1 以提升速度."""
    store = OptimalParamStore(data_dir=tmp_path)
    records = _make_3d_records(120)
    engine = GenerationEngine()
    engine.register(FC3DSmartHotColdStrategy())

    captured = {}
    statuses = []

    def fake_cross_validate(base_context, tasks, combos, **kwargs):
        captured["n_folds"] = kwargs.get("n_folds")
        return [
            CrossValidationResult(
                params=combos[0] if combos else {},
                stability_score=0.9,
                mean_fixed_prize=100,
                std_fixed_prize=10,
                fold_results=[BatchBacktestResult()],
            )
        ]

    def fake_worker(context, task):
        return RoundResult(index=task.index)

    def fake_merge(results, total_rounds):
        return BatchBacktestResult(
            total_rounds=total_rounds,
            total_cost=2 * total_rounds,
            hit_count=total_rounds,
            total_fixed_prize=100 * total_rounds,
        )

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.cross_validate_params",
        fake_cross_validate,
    )
    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.worker_round_backtest",
        fake_worker,
    )
    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.merge_round_results",
        fake_merge,
    )

    # 构造一个大网格：smart_hot_cold_3d 原始网格 240 种组合
    monkeypatch.setattr(
        "caipiao.ui.optimal_strategy_scan_thread.resolve_optimal_param_grid",
        lambda sid: {
            "lookback": list(range(30, 150, 10)),
            "hot_weight": [30, 50, 70, 90],
            "cold_weight": [10, 30, 50, 70],
            "temperature": [5, 10, 20],
        } if sid == "smart_hot_cold_3d" else {},
    )

    thread = OptimalStrategyScanThread(
        engine=engine,
        profile=FC3D,
        data_repository=_MockRepository(records),
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 4, 10),
        tickets_per_round=1,
        base_options={},
        param_store=store,
        plugin_dir=None,
    )
    thread.status_message.connect(statuses.append)
    result, error = _run_thread(thread)

    assert error is None, error
    assert captured.get("n_folds") == 1
    assert any("降级" in s for s in statuses)
