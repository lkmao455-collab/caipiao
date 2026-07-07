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
