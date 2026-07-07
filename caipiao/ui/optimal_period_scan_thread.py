"""一键找最优期数后台扫描线程."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from .batch_backtest_thread import _normalize_max_workers
from ..core.backtest_worker import merge_round_results, worker_round_backtest
from .batch_backtest_worker import init_worker_process
from ..core.backtest_data import RoundBacktestContext, RoundTask
from .optimal_period_config import resolve_optimal_param
from ..core.profile import LotteryProfile
from ..core.strategies.generic import needs_history
from ..data.repository import DrawRepository


@dataclass
class ScanResult:
    """参数扫描结果."""

    param_name: str
    optimal_value: int
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[int, BatchBacktestResult]]
    interrupted: bool = False

    @property
    def all_values(self) -> List[int]:
        """所有扫描过的参数值."""
        return [value for value, _ in self.all_results]


def _build_context(
    base_context: RoundBacktestContext,
    param_name: str,
    value: Optional[int],
) -> RoundBacktestContext:
    """根据参数值构建对应的回测上下文.

    当 ``value`` 为 ``None`` 时，不向 options 注入参数，用于无参策略扫描.
    """
    options = dict(base_context.options)
    if value is not None:
        options[param_name] = value
    return RoundBacktestContext(
        strategy_id=base_context.strategy_id,
        profile_key=base_context.profile_key,
        tickets_per_round=base_context.tickets_per_round,
        options=options,
        is_ml=base_context.is_ml,
        needs_history=base_context.needs_history,
        records=base_context.records,
        seed=base_context.seed,
        plugin_dir=base_context.plugin_dir,
    )


def _run_one_value(
    context: RoundBacktestContext, tasks: List[RoundTask], total_rounds: int
) -> BatchBacktestResult:
    """扫描单个参数值，返回汇总结果."""
    round_results = [worker_round_backtest(context, task) for task in tasks]
    return merge_round_results(round_results, total_rounds=total_rounds)


def scan_param_values(
    base_context: RoundBacktestContext,
    tasks: List[RoundTask],
    param_name: str,
    param_values: List[Optional[int]],
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    interruption_callback: Optional[Callable[[], bool]] = None,
) -> List[Tuple[Optional[int], BatchBacktestResult]]:
    """对单一策略扫描多个参数取值，返回每个取值对应的结果.

    ``param_values`` 中可包含 ``None``，用于无参策略的占位扫描.
    """
    all_results: List[Tuple[Optional[int], BatchBacktestResult]] = []
    max_workers = _normalize_max_workers(
        base_context.options.get("batch_backtest_workers")
    )
    completed = 0
    total = len(param_values)

    executor = None
    futures: List[Any] = []
    try:
        executor = ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=init_worker_process,
            initargs=(base_context.seed,),
        )

        for value in param_values:
            context = _build_context(base_context, param_name, value)
            futures.append(
                (
                    value,
                    executor.submit(
                        _run_one_value, context, tasks, len(tasks)
                    ),
                )
            )

        for value, future in futures:
            if interruption_callback is not None and interruption_callback():
                break
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = BatchBacktestResult(
                    total_rounds=len(tasks),
                    errors=[repr(exc)],
                )
            all_results.append((value, result))
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total)
            if status_callback is not None:
                status_callback(f"已完成 {param_name}={value} 的扫描（{completed}/{total}）")
    finally:
        if executor is not None:
            for _, f in futures:
                f.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    return all_results


class OptimalPeriodScanThread(QThread):
    """对单一参数扫描多个取值，找出固定奖金合计最高的参数值."""

    progress = Signal(int, int)  # 当前完成组数, 总组数
    status_message = Signal(str)  # 状态文本
    result_ready = Signal(object, object)  # ScanResult | None, error | None

    def __init__(
        self,
        engine,
        strategy_id: str,
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
        self.setObjectName("OptimalPeriodScanThread")
        self.engine = engine
        self.strategy_id = strategy_id
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.base_options = base_options
        self.plugin_dir = plugin_dir

    def run(self) -> None:
        try:
            resolved = resolve_optimal_param(self.strategy_id)
            if resolved is None:
                self.result_ready.emit(
                    None,
                    ValueError(f"策略 {self.strategy_id} 不支持一键找最优期数"),
                )
                return

            param_name, param_values = resolved

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

            min_required = min(v for v in param_values if v > 0)
            if needs_history(self.strategy_id):
                min_required = max(min_required, 100)
            if len(records) < min_required:
                self.result_ready.emit(
                    None,
                    ValueError(
                        f"历史数据不足，至少需要 {min_required} 期才能扫描 {param_name}"
                    ),
                )
                return

            earliest_target_date = target_records[0].draw_date
            history_before_target = [
                r for r in records if r.draw_date < earliest_target_date
            ]
            if len(history_before_target) < min_required:
                self.result_ready.emit(
                    None,
                    ValueError(
                        f"历史数据不足，目标日期前至少需要 {min_required} 期才能扫描 {param_name}"
                    ),
                )
                return

            base_context = RoundBacktestContext(
                strategy_id=self.strategy_id,
                profile_key=self.profile.key,
                tickets_per_round=self.tickets_per_round,
                options=dict(self.base_options),
                is_ml=self.strategy_id.startswith(("xgboost", "lightgbm", "catboost")),
                needs_history=True,
                records=records,
                seed=42,
                plugin_dir=self.plugin_dir,
            )
            tasks = [
                RoundTask(index=i, actual=r) for i, r in enumerate(target_records)
            ]

            all_results = scan_param_values(
                base_context,
                tasks,
                param_name,
                param_values,
                progress_callback=lambda completed, total: self.progress.emit(
                    completed, total
                ),
                status_callback=lambda msg: self.status_message.emit(msg),
                interruption_callback=self.isInterruptionRequested,
            )
            interrupted = len(all_results) < len(param_values)

            if not all_results:
                self.result_ready.emit(
                    None, ValueError("没有完成任何参数扫描")
                )
                return

            # If every value failed, report the overall scan as failed.
            if all(result.errors for _, result in all_results):
                self.result_ready.emit(
                    None,
                    ValueError(
                        f"所有 {len(param_values)} 个参数值扫描均失败: "
                        + "; ".join(
                            f"{value}: {result.errors[0]}"
                            for value, result in all_results
                        )
                    ),
                )
                return

            best = self._pick_best(all_results)
            if best is None:
                self.result_ready.emit(
                    None,
                    ValueError("所有参数组合均失败"),
                )
                return
            scan_result = ScanResult(
                param_name=param_name,
                optimal_value=best[0],
                optimal_result=best[1],
                all_results=all_results,
                interrupted=interrupted,
            )
            self.result_ready.emit(scan_result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _build_context(
        self,
        base_context: RoundBacktestContext,
        param_name: str,
        value: int,
    ) -> RoundBacktestContext:
        """根据参数值构建对应的回测上下文."""
        return _build_context(base_context, param_name, value)

    @staticmethod
    def _run_one_value(
        context: RoundBacktestContext, tasks: List[RoundTask], total_rounds: int
    ) -> BatchBacktestResult:
        """扫描单个参数值，返回汇总结果."""
        return _run_one_value(context, tasks, total_rounds)

    @staticmethod
    def _pick_best(
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
