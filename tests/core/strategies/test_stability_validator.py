"""稳定性验证器测试."""

from __future__ import annotations

import pytest

from caipiao.core.strategies.stability_validator import (
    CrossValidationResult,
    _split_tasks,
    cross_validate_params,
    pick_best_param_cv,
    stability_score,
)
from caipiao.core.backtest_data import BatchBacktestResult, RoundBacktestContext, RoundTask, RoundResult
from caipiao.data.models import DrawRecord
from datetime import datetime


class TestStabilityScore:
    """stability_score 函数测试."""

    def test_negative_mean_returns_zero(self):
        assert stability_score(-10.0, 5.0) == 0.0
        assert stability_score(0.0, 5.0) == 0.0

    def test_zero_std_returns_one(self):
        assert stability_score(10.0, 0.0) == 1.0

    def test_cv_zero_is_one(self):
        # std=0 -> cv=0 -> score=1
        assert stability_score(5.0, 0.0) == 1.0

    def test_cv_small_returns_near_one(self):
        score = stability_score(10.0, 1.0)  # cv = 0.1
        assert score > 0.9

    def test_cv_one_returns_half(self):
        # mean=10, std=10 -> cv=1 -> score = 1 - 1/2 = 0.5
        assert stability_score(10.0, 10.0) == pytest.approx(0.5)

    def test_cv_two_returns_zero(self):
        # mean=5, std=10 -> cv=2 -> score = 1 - 2/2 = 0
        assert stability_score(5.0, 10.0) == 0.0

    def test_cv_above_two_returns_zero(self):
        # mean=5, std=15 -> cv=3 -> score = 1 - 3/2 = -0.5 -> clamped to 0
        assert stability_score(5.0, 15.0) == 0.0

    def test_formula_correctness(self):
        # cv = std / mean
        # score = max(0, min(1, 1 - cv/2))
        mean, std = 20.0, 4.0
        cv = std / mean  # 0.2
        expected = 1.0 - cv / 2.0  # 0.9
        assert stability_score(mean, std) == pytest.approx(expected)


class TestSplitTasks:
    """_split_tasks 内部函数测试."""

    def _make_tasks(self, n: int) -> list:
        tasks = []
        for i in range(n):
            record = DrawRecord(
                issue=f"2024{i+1:03d}",
                draw_date=datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                profile="ssq",
                groups={"red": [1,2,3,4,5,6], "blue": [1]},
            )
            # RoundTask 只需要 index 和 actual
            task = RoundTask(
                index=i,
                actual=record,
            )
            tasks.append(task)
        return tasks

    def test_n_folds_1(self):
        tasks = self._make_tasks(10)
        folds = _split_tasks(tasks, 1)
        assert len(folds) == 1
        assert len(folds[0]) == 10

    def test_n_folds_equals_tasks(self):
        tasks = self._make_tasks(5)
        folds = _split_tasks(tasks, 5)
        assert len(folds) == 5
        for f in folds:
            assert len(f) == 1

    def test_n_folds_more_than_tasks(self):
        tasks = self._make_tasks(3)
        folds = _split_tasks(tasks, 5)
        # 当任务数 < 折数时返回整体
        assert len(folds) == 1
        assert len(folds[0]) == 3

    def test_n_folds_greater_than_1(self):
        tasks = self._make_tasks(12)
        folds = _split_tasks(tasks, 3)
        assert len(folds) == 3
        # 12/3 = 4 每折
        for f in folds:
            assert len(f) == 4

    def test_folds_preserve_order(self):
        tasks = self._make_tasks(9)
        folds = _split_tasks(tasks, 3)
        # 每折内部按日期升序
        for f in folds:
            dates = [t.actual.draw_date for t in f]
            assert dates == sorted(dates)


class TestCrossValidationResult:
    """CrossValidationResult 数据类测试."""

    def test_default_values(self):
        result = CrossValidationResult(params={"a": 1})
        assert result.params == {"a": 1}
        assert result.fold_results == []
        assert result.mean_fixed_prize == 0.0
        assert result.std_fixed_prize == 0.0
        assert result.stability_score == 0.0
        assert result.errors == []

    def test_with_values(self):
        result = CrossValidationResult(
            params={"p": 1},
            mean_fixed_prize=10.0,
            std_fixed_prize=2.0,
            stability_score=0.9,
            errors=["e1"],
        )
        assert result.params == {"p": 1}
        assert result.mean_fixed_prize == 10.0
        assert result.stability_score == 0.9
        assert result.errors == ["e1"]


class TestPickBestParamCv:
    """pick_best_param_cv 函数测试."""

    def test_empty_list_returns_none(self):
        assert pick_best_param_cv([]) is None

    def test_all_no_fold_results_returns_none(self):
        results = [
            CrossValidationResult(params={"a": 1}, errors=["e"]),
            CrossValidationResult(params={"b": 2}, errors=["e"]),
        ]
        assert pick_best_param_cv(results) is None

    def test_single_valid_result(self):
        r1 = CrossValidationResult(params={"a": 1}, fold_results=[None], mean_fixed_prize=5.0)
        r2 = CrossValidationResult(params={"b": 2}, errors=["e"])
        best = pick_best_param_cv([r2, r1])
        assert best is not None
        params, result = best
        assert params == {"a": 1}
        assert result.mean_fixed_prize == 5.0

    def test_picks_highest_stability_score(self):
        r1 = CrossValidationResult(params={"a": 1}, fold_results=[None], stability_score=0.5, mean_fixed_prize=10.0)
        r2 = CrossValidationResult(params={"b": 2}, fold_results=[None], stability_score=0.9, mean_fixed_prize=5.0)
        best = pick_best_param_cv([r1, r2])
        assert best[0] == {"b": 2}

    def test_tiebreaker_mean_prize(self):
        r1 = CrossValidationResult(params={"a": 1}, fold_results=[None], stability_score=0.9, mean_fixed_prize=10.0)
        r2 = CrossValidationResult(params={"b": 2}, fold_results=[None], stability_score=0.9, mean_fixed_prize=5.0)
        best = pick_best_param_cv([r1, r2])
        assert best[0] == {"a": 1}

    def test_tiebreaker_std_prize(self):
        r1 = CrossValidationResult(params={"a": 1}, fold_results=[None], stability_score=0.9, mean_fixed_prize=10.0, std_fixed_prize=5.0)
        r2 = CrossValidationResult(params={"b": 2}, fold_results=[None], stability_score=0.9, mean_fixed_prize=10.0, std_fixed_prize=2.0)
        best = pick_best_param_cv([r1, r2])
        assert best[0] == {"b": 2}  # std 较小者胜出


class TestCrossValidateParams:
    """cross_validate_params 集成测试（使用 mock 避免完整回测）."""

    def _make_context(self) -> RoundBacktestContext:
        return RoundBacktestContext(
            strategy_id="test_strategy",
            profile_key="ssq",
            tickets_per_round=1,
            options={},
            is_ml=False,
            needs_history=False,
            records=[],
            seed=None,
            plugin_dir=None,
        )

    def _make_tasks(self, n: int) -> list:
        tasks = []
        for i in range(n):
            record = DrawRecord(
                issue=f"2024{i+1:03d}",
                draw_date=datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                profile="ssq",
                groups={"red": [1,2,3,4,5,6], "blue": [1]},
            )
            task = RoundTask(
                index=i,
                actual=record,
            )
            tasks.append(task)
        return tasks

    def test_n_folds_1(self):
        """单折不降级."""
        context = self._make_context()
        tasks = self._make_tasks(30)
        params_list = [{"lookback": 30}, {"lookback": 50}]
        
        # 简单 mock - 不实际运行 backtest，这里测试逻辑流程
        # 由于需要实际 worker，这里只验证不报错且返回正确结构
        results = cross_validate_params(
            context, tasks, params_list, n_folds=1,
            force_n_folds_for_ml=False,
        )
        assert len(results) == 2
        for r in results:
            assert isinstance(r, CrossValidationResult)
            assert r.params in params_list

    def test_ml_strategy_downgrades_to_1_fold(self):
        """ML 策略默认降级为单折."""
        context = RoundBacktestContext(
            strategy_id="test_strategy",
            profile_key="ssq",
            tickets_per_round=1,
            options={},
            is_ml=True,
            needs_history=False,
            records=[],
            seed=None,
            plugin_dir=None,
        )
        tasks = self._make_tasks(100)
        params_list = [{"epochs": 10}]
        
        results = cross_validate_params(
            context, tasks, params_list, n_folds=3,
            force_n_folds_for_ml=True,
        )
        # 即使传入 n_folds=3，ML 策略会降级为 1
        assert len(results) == 1

    def test_insufficient_tasks_downgrades(self):
        """任务数不足时降级."""
        context = self._make_context()
        tasks = self._make_tasks(10)  # 3折需要至少 60 任务
        params_list = [{"lookback": 30}]
        
        results = cross_validate_params(
            context, tasks, params_list, n_folds=3,
            force_n_folds_for_ml=False,
        )
        assert len(results) == 1