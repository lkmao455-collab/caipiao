"""一键找最优策略和参数后台扫描线程."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from .batch_backtest_worker import RoundBacktestContext, RoundTask
from .optimal_period_config import resolve_optimal_param
from .optimal_period_scan_thread import scan_param_values
from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile
from ..core.strategies.generic import needs_history
from ..data.repository import DrawRepository


@dataclass
class StrategyScanResult:
    """策略+参数扫描结果."""

    optimal_strategy_id: str
    optimal_strategy_name: str
    param_name: Optional[str]
    optimal_value: Optional[int]
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[str, Optional[int], BatchBacktestResult]]
    interrupted: bool = False


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

    def run(self) -> None:
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

            all_results: List[Tuple[str, Optional[int], BatchBacktestResult]] = []
            completed = 0
            total = len(candidates)
            interrupted = False

            for strategy in candidates:
                if self.isInterruptionRequested():
                    interrupted = True
                    break

                strategy_id = strategy.metadata.id
                resolved = resolve_optimal_param(strategy_id)

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

                if resolved is None:
                    # 无独立期数参数的策略，使用默认参数跑一次
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
                else:
                    param_name, param_values = resolved
                    value_results = scan_param_values(
                        base_context,
                        tasks,
                        param_name,
                        param_values,
                        progress_callback=None,
                        status_callback=lambda msg: self.status_message.emit(msg),
                        interruption_callback=self.isInterruptionRequested,
                    )
                    best = self._pick_best_param(value_results)
                    if best is not None:
                        all_results.append((strategy_id, best[0], best[1]))
                    else:
                        # 该策略所有参数均失败，记录一个失败结果
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

            best = self._pick_best_strategy(all_results)
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
            param_name = None
            if value is not None:
                resolved = resolve_optimal_param(strategy_id)
                param_name = resolved[0] if resolved else None

            scan_result = StrategyScanResult(
                optimal_strategy_id=strategy_id,
                optimal_strategy_name=strategy_name,
                param_name=param_name,
                optimal_value=value,
                optimal_result=result,
                all_results=all_results,
                interrupted=interrupted,
            )
            self.result_ready.emit(scan_result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    @staticmethod
    def _pick_best_param(
        results: List[Tuple[int, BatchBacktestResult]],
    ) -> Optional[Tuple[int, BatchBacktestResult]]:
        eligible = [item for item in results if not item[1].errors]
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda item: (
                item[1].total_fixed_prize,
                item[1].hit_count,
                -item[0],
            ),
        )

    @staticmethod
    def _pick_best_strategy(
        results: List[Tuple[str, Optional[int], BatchBacktestResult]],
    ) -> Optional[Tuple[str, Optional[int], BatchBacktestResult]]:
        eligible = [item for item in results if not item[2].errors]
        if not eligible:
            return None
        return sorted(
            eligible,
            key=lambda item: (
                -item[2].total_fixed_prize,
                -item[2].hit_count,
                item[0],
            ),
        )[0]
