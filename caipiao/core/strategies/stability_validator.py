"""策略参数交叉验证与稳定性评分."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...data.models import DrawRecord
from ...ui.batch_backtest_result import BatchBacktestResult
from ...ui.batch_backtest_worker import RoundBacktestContext, RoundTask, merge_round_results, worker_round_backtest


@dataclass
class CrossValidationResult:
    params: Dict[str, Any]
    fold_results: List[BatchBacktestResult] = field(default_factory=list)
    mean_fixed_prize: float = 0.0
    std_fixed_prize: float = 0.0
    stability_score: float = 0.0
    errors: List[str] = field(default_factory=list)


def stability_score(mean_prize: float, std_prize: float) -> float:
    """返回 0~1 稳定性分数。收益为正且波动越小越稳定。"""
    if mean_prize <= 0:
        return 0.0
    # 变异系数越小越稳定，但避免除 0
    cv = std_prize / max(mean_prize, 1.0)
    # 将 cv 映射到 [0, 1]，cv=0 时 1，cv>=2 时 0
    return max(0.0, min(1.0, 1.0 - cv / 2.0))


def _split_folds(records: List[DrawRecord], n_folds: int) -> List[Tuple[int, int]]:
    """返回每折的起止索引（按时间顺序）."""
    n = len(records)
    if n_folds <= 1 or n < n_folds:
        return [(0, n)]
    fold_size = n // n_folds
    folds = []
    start = 0
    for i in range(n_folds):
        end = start + fold_size if i < n_folds - 1 else n
        folds.append((start, end))
        start = end
    return folds


def cross_validate_params(
    base_context: RoundBacktestContext,
    tasks: List[RoundTask],
    param_combinations: List[Dict[str, Any]],
    n_folds: int = 3,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> List[CrossValidationResult]:
    """对每套参数组合做 n_folds 交叉验证."""
    results: List[CrossValidationResult] = []
    total = len(param_combinations)

    # ML 策略交叉验证可能非常慢，降级为单区间回测
    if base_context.is_ml and n_folds != 1:
        n_folds = 1

    for idx, params in enumerate(param_combinations):
        if progress_callback:
            progress_callback(idx, total)
        if status_callback:
            status_callback(f"正在验证参数 {params}")

        context = RoundBacktestContext(
            strategy_id=base_context.strategy_id,
            profile_key=base_context.profile_key,
            tickets_per_round=base_context.tickets_per_round,
            options={**base_context.options, **params},
            is_ml=base_context.is_ml,
            needs_history=base_context.needs_history,
            records=base_context.records,
            seed=base_context.seed,
            plugin_dir=base_context.plugin_dir,
        )

        fold_results: List[BatchBacktestResult] = []
        errors: List[str] = []
        records = base_context.records
        sorted_records = sorted(records, key=lambda r: r.draw_date)
        folds = _split_folds(sorted_records, n_folds)

        for start, end in folds:
            fold_tasks = [t for t in tasks if start <= t.index < end]
            if not fold_tasks:
                continue
            round_results = [
                worker_round_backtest(context, task) for task in fold_tasks
            ]
            merged = merge_round_results(round_results, len(fold_tasks))
            if merged.errors:
                errors.extend(merged.errors)
            fold_results.append(merged)

        if not fold_results:
            results.append(CrossValidationResult(params=params, errors=["no fold results"]))
            continue

        prizes = [r.total_fixed_prize for r in fold_results]
        mean_prize = sum(prizes) / len(prizes)
        std_prize = math.sqrt(sum((p - mean_prize) ** 2 for p in prizes) / len(prizes))
        score = stability_score(mean_prize, std_prize)

        results.append(
            CrossValidationResult(
                params=params,
                fold_results=fold_results,
                mean_fixed_prize=mean_prize,
                std_fixed_prize=std_prize,
                stability_score=score,
                errors=errors,
            )
        )

    if progress_callback:
        progress_callback(total, total)
    return results


def pick_best_param_cv(
    cv_results: List[CrossValidationResult],
) -> Optional[Tuple[Dict[str, Any], CrossValidationResult]]:
    """按稳定性优先、收益高、波动低选择最优参数."""
    eligible = [r for r in cv_results if not r.errors]
    if not eligible:
        return None
    best = max(
        eligible,
        key=lambda r: (r.stability_score, r.mean_fixed_prize, -r.std_fixed_prize),
    )
    return best.params, best
