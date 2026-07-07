"""批量历史回测后台线程.

对指定日期区间内的每一期开奖：
1. 使用该日期之前的历史数据训练模型（ML 策略）。
2. 生成指定数量的预测投注单。
3. 与当期真实开奖对比，计算命中和奖金。
4. 汇总总花费、总奖金、中奖次数。

本模块现在使用多进程池并行执行每期回测，主线程仅负责任务派发、
结果合并与进度上报。
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from ..core.backtest_worker import merge_round_results, worker_round_backtest
from .batch_backtest_worker import init_worker_process
from ..core.backtest_data import RoundBacktestContext, RoundTask
from .components.ball_display import compute_highlight_map
from ..core.engine import GenerationEngine
from ..core.profile import LotteryProfile
from ..core.strategies.generic import is_ml_strategy, needs_history
from ..data.repository import DrawRepository


_DEFAULT_MAX_WORKERS = max(1, min(os.cpu_count() // 2, 4))


def _normalize_max_workers(value: Any, cpu_count: Optional[int] = None) -> int:
    """校验并归一化 worker 数量.

    - 转换为整数，失败时使用默认值。
    - 最小值为 1。
    - 最大值为 ``os.cpu_count()``（取不到时按 4 兜底），防止用户配置过大导致 OOM。
    """
    try:
        max_workers = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_WORKERS

    upper = cpu_count if cpu_count is not None else os.cpu_count()
    if upper is None or upper < 1:
        upper = 4
    return max(1, min(max_workers, upper))


class BatchBacktestThread(QThread):
    """批量回测工作线程."""

    result_ready = Signal(object, object)
    progress = Signal(int, int)  # 当前完成期数, 总期数
    status_message = Signal(str)  # 过程状态文本
    round_ready = Signal(int, int, list)  # 当前完成期数, 总期数, 本期中奖记录

    def __init__(
        self,
        engine: GenerationEngine,
        strategy_id: str,
        profile: LotteryProfile,
        data_repository: DrawRepository,
        start_date: datetime,
        end_date: datetime,
        tickets_per_round: int,
        options: Dict[str, Any],
        plugin_dir: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BatchBacktestThread")
        # ``engine`` 参数保留以兼容既有调用方，但 worker 会在子进程中重新构建
        # 引擎并加载插件策略，因此此处保存的 ``self.engine`` 不再参与回测。
        self.engine = engine
        self.strategy_id = strategy_id
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.options = options
        self.plugin_dir = plugin_dir
        self._needs_history = needs_history(strategy_id)
        self._is_ml = is_ml_strategy(strategy_id) or strategy_id in {
            "xgboost", "lightgbm", "catboost",
            "ml_xgboost", "ml_lightgbm", "ml_catboost",
        }

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

            context = RoundBacktestContext(
                strategy_id=self.strategy_id,
                profile_key=self.profile.key,
                tickets_per_round=self.tickets_per_round,
                options=dict(self.options),
                is_ml=self._is_ml,
                needs_history=self._needs_history,
                records=records,
                seed=42,
                plugin_dir=self.plugin_dir,
            )
            tasks = [
                RoundTask(index=i, actual=r) for i, r in enumerate(target_records)
            ]

            max_workers = _normalize_max_workers(
                self.options.get("batch_backtest_workers", _DEFAULT_MAX_WORKERS)
            )
            executor = None
            futures = []
            round_results = []
            completed = 0
            errors = []

            try:
                executor = ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=init_worker_process,
                    initargs=(context.seed,),
                )
                futures = [
                    executor.submit(worker_round_backtest, context, task)
                    for task in tasks
                ]

                for future in as_completed(futures):
                    if self.isInterruptionRequested():
                        break

                    result = future.result()
                    round_results.append(result)
                    if result.error:
                        errors.append(result.error)
                    else:
                        # 还原旧版 round_ready 信号契约：第三个参数为中奖详情字典列表
                        round_winners: List[Dict[str, Any]] = []
                        for t_idx in result.winners:
                            ticket = result.tickets[t_idx]
                            tr = result.ticket_results[t_idx]
                            round_winners.append(
                                {
                                    "date": result.date_str,
                                    "issue": result.issue_str,
                                    "ticket": ticket,
                                    "hits": tr["hits"],
                                    "matched_groups": compute_highlight_map(
                                        self.profile, ticket, result.actual_groups
                                    ),
                                    "prize_name": tr["prize_name"],
                                    "prize_amount": tr["prize_amount"],
                                    "is_first": t_idx == 0,
                                    "ticket_index": t_idx,
                                }
                            )
                        self.round_ready.emit(result.index + 1, len(tasks), round_winners)

                    completed += 1
                    self.progress.emit(completed, len(tasks))
                    self.status_message.emit(f"已完成 {completed}/{len(tasks)} 期")

                    if len(errors) > len(tasks) * 0.3:
                        self.status_message.emit(
                            f"错误期数超过 30%（{len(errors)}/{len(tasks)}），提前终止"
                        )
                        break

            except Exception as exc:  # noqa: BLE001
                self.result_ready.emit(None, exc)
                return
            finally:
                if executor is not None:
                    for f in futures:
                        f.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)

            if errors and completed == 0:
                self.result_ready.emit(
                    None, Exception(f"全部 {len(errors)} 期回测均失败：{errors[0]}")
                )
                return

            merged = merge_round_results(round_results, total_rounds=len(tasks))
            merged.errors = errors
            self.status_message.emit("批量回测完成，正在汇总结果...")
            self.result_ready.emit(merged, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)
