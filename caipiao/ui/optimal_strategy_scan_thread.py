"""一键找最优策略和参数后台扫描线程."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from ..core.backtest_data import BatchBacktestResult, RoundBacktestContext, RoundTask
from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile
from ..core.strategies.generic import needs_history
from ..data.repository import DrawRepository
from ..persistence.optimal_param_store import OptimalParamStore
from ..core.backtest_worker import merge_round_results, worker_round_backtest
from .optimal_period_config import (
    build_param_combinations,
    resolve_optimal_param,
    resolve_optimal_param_grid,
)
from .optimal_period_scan_thread import scan_param_values


@dataclass
class StrategyScanResult:
    """策略+参数扫描结果."""

    optimal_strategy_id: str
    optimal_strategy_name: str
    param_name: Optional[str]
    optimal_value: Optional[int]
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[str, Optional[int], BatchBacktestResult]]
    cv_results: Dict[str, Any] = field(default_factory=dict)
    locked_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    interrupted: bool = False
    # 每个策略的代表性参数名（向后兼容）
    param_names: Dict[str, Optional[str]] = field(default_factory=dict)
    # 每个策略扫描到的最佳完整参数集合
    best_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class OptimalStrategyScanThread(QThread):
    """扫描所有使用历史数据的策略，找出最优策略及其参数."""

    progress = Signal(int, int)  # 当前完成策略数, 总策略数
    status_message = Signal(str)  # 状态文本
    result_ready = Signal(object, object)  # StrategyScanResult | None, error | None

    def __init__(
        self,
        engine: GenerationEngine,
        profile: LotteryProfile,
        data_repository: DrawRepository,
        start_date: datetime,
        end_date: datetime,
        tickets_per_round: int,
        base_options: Dict[str, Any],
        plugin_dir: Optional[str] = None,
        param_store: Optional[OptimalParamStore] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OptimalStrategyScanThread")
        self.engine = engine
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.base_options = base_options
        self.plugin_dir = plugin_dir
        self.param_store = param_store

    def run(self) -> None:
        # 局部导入避免与 stability_validator 的循环导入（stability_validator 仅依赖 core 模块）
        from ..core.strategies.stability_validator import (
            cross_validate_params,
            pick_best_param_cv,
        )

        try:
            records = self.data_repository.get_all()
            target_records = [
                r
                for r in records
                if self.start_date.date() <= r.draw_date.date() <= self.end_date.date()
            ]
            target_records.sort(key=lambda r: r.draw_date)
            if not target_records:
                self.result_ready.emit(
                    None, ValueError("指定日期范围内没有开奖记录")
                )
                return

            if len(records) < 100:
                self.result_ready.emit(
                    None,
                    ValueError("历史数据不足，所有候选策略至少需要 100 期历史数据"),
                )
                return

            candidates = [
                s for s in self.engine.list_strategies() if needs_history(s.metadata.id)
            ]
            if not candidates:
                self.result_ready.emit(
                    None, ValueError("当前没有使用历史数据的策略可用")
                )
                return

            tasks = [
                RoundTask(index=i, actual=r) for i, r in enumerate(target_records)
            ]

            store = self.param_store or OptimalParamStore()
            all_results: List[Tuple[str, Optional[int], BatchBacktestResult]] = []
            param_names: Dict[str, Optional[str]] = {}
            best_params_map: Dict[str, Dict[str, Any]] = {}
            cv_summary: Dict[str, Dict[str, Any]] = {}
            locked_params: Dict[str, Dict[str, Any]] = {}
            completed = 0
            total = len(candidates)
            interrupted = False

            for strategy in candidates:
                if self.isInterruptionRequested():
                    interrupted = True
                    break

                strategy_id = strategy.metadata.id
                locked = store.get_locked(self.profile.key, strategy_id)
                locked_params[strategy_id] = dict(locked)
                grid = resolve_optimal_param_grid(strategy_id)

                base_context = RoundBacktestContext(
                    strategy_id=strategy_id,
                    profile_key=self.profile.key,
                    tickets_per_round=self.tickets_per_round,
                    options=dict(self.base_options),
                    is_ml=strategy_id.startswith(("xgboost", "lightgbm", "catboost")),
                    needs_history=True,
                    records=records,
                    seed=42,
                    plugin_dir=self.plugin_dir,
                )

                if not grid:
                    # 无网格配置的策略，回退到单一回测
                    results = scan_param_values(
                        base_context,
                        tasks,
                        "",
                        [None],  # 占位，实际不使用
                        progress_callback=None,
                        status_callback=None,
                        interruption_callback=self.isInterruptionRequested,
                    )
                    value, result = results[0]
                    all_results.append((strategy_id, None, result))
                    param_names[strategy_id] = None
                else:
                    combos = build_param_combinations(grid, locked)
                    # 对非 ML 策略做 CV；ML 策略数据量大，先 n_folds=1
                    n_folds = 1 if base_context.is_ml else 3
                    cv_results = cross_validate_params(
                        base_context,
                        tasks,
                        combos,
                        n_folds=n_folds,
                        progress_callback=None,
                        status_callback=lambda msg: self.status_message.emit(msg),
                    )
                    best = pick_best_param_cv(cv_results)
                    if best is not None:
                        best_params, best_cv = best
                        # 用最佳参数在整个区间跑一次，得到与旧版兼容的 BatchBacktestResult
                        full_context = RoundBacktestContext(
                            **{
                                **base_context.__dict__,
                                "options": {**base_context.options, **best_params},
                            }
                        )
                        round_results = [
                            worker_round_backtest(full_context, task) for task in tasks
                        ]
                        full_result = merge_round_results(
                            round_results, len(tasks)
                        )
                        # 取一个代表值用于旧版 param_name/optimal_value（取第一个非锁定参数）
                        free_keys = [k for k in grid.keys() if k not in locked]
                        param_name = free_keys[0] if free_keys else None
                        param_value = best_params.get(param_name) if param_name else None
                        all_results.append((strategy_id, param_value, full_result))
                        param_names[strategy_id] = param_name
                        cv_summary[strategy_id] = {
                            "best_params": best_params,
                            "stability_score": best_cv.stability_score,
                            "mean_fixed_prize": best_cv.mean_fixed_prize,
                            "std_fixed_prize": best_cv.std_fixed_prize,
                        }
                        best_params_map[strategy_id] = best_params
                    else:
                        # 该策略所有参数组合均失败，记录一个失败结果
                        all_results.append(
                            (
                                strategy_id,
                                None,
                                BatchBacktestResult(
                                    total_rounds=len(tasks),
                                    errors=[f"{strategy_id} 所有参数扫描均失败"],
                                ),
                            )
                        )
                        param_names[strategy_id] = None

                completed += 1
                self.progress.emit(completed, total)
                self.status_message.emit(
                    f"已完成 {strategy.metadata.name} 的策略扫描（{completed}/{total}）"
                )

            if not all_results:
                self.result_ready.emit(
                    None, ValueError("没有完成任何策略扫描")
                )
                return

            if all(result.errors for _, _, result in all_results):
                self.result_ready.emit(
                    None,
                    ValueError(
                        "所有策略扫描均失败: "
                        + "; ".join(
                            f"{sid}: {result.errors[0]}"
                            for sid, _, result in all_results
                        )
                    ),
                )
                return

            best = self._pick_best_strategy(all_results, cv_summary)
            if best is None:
                self.result_ready.emit(
                    None, ValueError("所有策略组合均失败")
                )
                return

            strategy_id, value, result = best
            strategy = self.engine.get(strategy_id)
            strategy_name = (
                strategy.metadata.name if strategy is not None else strategy_id
            )
            param_name = param_names.get(strategy_id)
            if param_name is None and value is not None:
                # 向后兼容：非网格策略通过旧接口解析参数名
                resolved = resolve_optimal_param(strategy_id)
                param_name = resolved[0] if resolved else None

            scan_result = StrategyScanResult(
                optimal_strategy_id=strategy_id,
                optimal_strategy_name=strategy_name,
                param_name=param_name,
                optimal_value=value,
                optimal_result=result,
                all_results=all_results,
                cv_results=cv_summary,
                locked_params=locked_params,
                interrupted=interrupted,
                param_names=param_names,
                best_params=best_params_map,
            )
            self.result_ready.emit(scan_result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    @staticmethod
    def _pick_best_strategy(
        results: List[Tuple[str, Optional[int], BatchBacktestResult]],
        cv_summary: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Tuple[str, Optional[int], BatchBacktestResult]]:
        eligible = [item for item in results if not item[2].errors]
        if not eligible:
            return None
        summary = cv_summary or {}
        return sorted(
            eligible,
            key=lambda item: (
                -summary.get(item[0], {}).get("stability_score", 0.0),
                -item[2].total_fixed_prize,
                -item[2].hit_count,
                item[0],
            ),
        )[0]
