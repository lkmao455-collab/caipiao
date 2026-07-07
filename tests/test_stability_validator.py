"""Tests for caipiao.core.strategies.stability_validator."""

from datetime import datetime, timedelta

import pytest

from caipiao.core.backtest_data import BatchBacktestResult, RoundBacktestContext, RoundTask, RoundResult
from caipiao.core.strategies.stability_validator import (
    CrossValidationResult,
    cross_validate_params,
    pick_best_param_cv,
    stability_score,
)


def _make_context():
    from caipiao.data.models import DrawRecord
    records = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(200)
    ]
    return RoundBacktestContext(
        strategy_id="smart_hot_cold_3d",
        profile_key="3d",
        tickets_per_round=5,
        options={},
        is_ml=False,
        needs_history=True,
        records=records,
        seed=42,
    ), records


def test_stability_score_positive_low_cv():
    assert stability_score(100, 10) > 0.9


def test_stability_score_negative_mean():
    assert stability_score(-10, 0) == 0.0


def test_stability_score_high_cv():
    assert stability_score(100, 200) == 0.0


def test_cross_validate_params_runs():
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-30:])]
    combos = [{"lookback": 50}, {"lookback": 100}]
    results = cross_validate_params(context, tasks, combos, n_folds=2)
    assert len(results) == 2
    assert all(isinstance(r, CrossValidationResult) for r in results)


def test_pick_best_param_cv_prefers_stable():
    r1 = CrossValidationResult(
        params={"lookback": 50},
        mean_fixed_prize=100,
        std_fixed_prize=10,
        stability_score=stability_score(100, 10),
    )
    r2 = CrossValidationResult(
        params={"lookback": 100},
        mean_fixed_prize=150,
        std_fixed_prize=100,
        stability_score=stability_score(150, 100),
    )
    best = pick_best_param_cv([r1, r2])
    assert best is not None
    # 稳定性分数高者胜出
    assert best[1].stability_score >= max(r1.stability_score, r2.stability_score) - 1e-9


def test_cross_validate_params_uses_multiple_folds_for_subset(monkeypatch):
    """Regression: tasks 是日期区间子集时仍应产生 n_folds 个有效折."""
    context, all_records = _make_context()
    # 仅使用最后 150 条记录作为目标区间，任务 index 为子集局部索引 0..149
    target_records = all_records[-150:]
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(target_records)]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=task.index),
    )

    combos = [{"lookback": 50}]
    results = cross_validate_params(context, tasks, combos, n_folds=3)
    assert len(results) == 1
    result = results[0]
    assert not result.errors
    assert len(result.fold_results) == 3
    # 每折都应分到任务，且按日期排序后均分为 50/50/50
    assert [fr.total_rounds for fr in result.fold_results] == [50, 50, 50]


def test_cross_validate_params_skips_failed_folds(monkeypatch):
    """失败的折不应计入零奖金，稳定性评分只基于成功折."""
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-150:])]

    def fake_worker(ctx, task):
        # 仅让第一折（前 50 个任务）失败
        if task.index < 50:
            raise RuntimeError("fold 1 fails")
        return RoundResult(index=task.index, total_fixed_prize=10)

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        fake_worker,
    )

    combos = [{"lookback": 50}]
    results = cross_validate_params(context, tasks, combos, n_folds=3)
    assert len(results) == 1
    result = results[0]
    # 第一折失败被跳过，剩余两折成功
    assert len(result.fold_results) == 2
    assert result.mean_fixed_prize == 500
    assert result.std_fixed_prize == 0
    assert result.stability_score == 1.0
    assert len(result.errors) == 1


def test_cross_validate_params_all_folds_failed(monkeypatch):
    """某参数组合所有折均失败时，结果应标记为错误且稳定性分数为 0."""
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-150:])]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: (_ for _ in ()).throw(RuntimeError("always fails")),
    )

    combos = [{"lookback": 50}]
    results = cross_validate_params(context, tasks, combos, n_folds=3)
    assert len(results) == 1
    result = results[0]
    assert not result.fold_results
    assert result.errors
    assert result.mean_fixed_prize == 0
    assert result.std_fixed_prize == 0
    assert result.stability_score == 0


def test_cross_validate_params_downgrades_when_tasks_below_threshold(monkeypatch):
    """任务数低于 n_folds * 20 时应降级为单区间并发出状态消息."""
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-59:])]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=5),
    )

    statuses = []
    combos = [{"lookback": 50}]
    results = cross_validate_params(
        context, tasks, combos, n_folds=3, status_callback=statuses.append
    )
    assert len(results) == 1
    assert len(results[0].fold_results) == 1
    assert any("59" in s and "60" in s and "降级" in s for s in statuses)


def test_cross_validate_params_keeps_folds_at_threshold(monkeypatch):
    """任务数达到 n_folds * 20 时应保持多折交叉验证."""
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-60:])]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=5),
    )

    statuses = []
    combos = [{"lookback": 50}]
    results = cross_validate_params(
        context, tasks, combos, n_folds=3, status_callback=statuses.append
    )
    assert len(results) == 1
    assert len(results[0].fold_results) == 3
    assert not any("降级" in s for s in statuses)


def test_cross_validate_params_ml_downgrade_status(monkeypatch):
    """ML 策略默认应降级为单区间并发出状态消息."""
    context, _ = _make_context()
    context = RoundBacktestContext(**{**context.__dict__, "is_ml": True, "strategy_id": "xgboost_3d"})
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-150:])]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=5),
    )

    statuses = []
    combos = [{"history_count": 100}]
    results = cross_validate_params(
        context, tasks, combos, n_folds=3, status_callback=statuses.append
    )
    assert len(results) == 1
    assert len(results[0].fold_results) == 1
    assert any("ML" in s and "降级" in s for s in statuses)


def test_cross_validate_params_force_n_folds_for_ml_false(monkeypatch):
    """传入 force_n_folds_for_ml=False 时，ML 策略应保持调用方指定的折数."""
    context, _ = _make_context()
    context = RoundBacktestContext(**{**context.__dict__, "is_ml": True, "strategy_id": "xgboost_3d"})
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-150:])]

    monkeypatch.setattr(
        "caipiao.core.strategies.stability_validator.worker_round_backtest",
        lambda ctx, task: RoundResult(index=task.index, total_fixed_prize=5),
    )

    combos = [{"history_count": 100}]
    results = cross_validate_params(
        context, tasks, combos, n_folds=3, force_n_folds_for_ml=False
    )
    assert len(results) == 1
    assert len(results[0].fold_results) == 3
