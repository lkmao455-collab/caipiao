"""批量历史回测后台线程.

对指定日期区间内的每一期开奖：
1. 使用该日期之前的历史数据训练模型（ML 策略）。
2. 生成指定数量的预测投注单。
3. 与当期真实开奖对比，计算命中和奖金。
4. 汇总总花费、总奖金、中奖次数。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from .batch_backtest_result import BatchBacktestResult
from ..core.engine import GenerationEngine
from ..core.prize import calculate_prize
from ..core.profile import LotteryProfile, SSQ
from ..core.strategies.generic import is_ml_strategy, needs_history
from ..core.ticket import Ticket
from ..ui.components.ball_display import compute_highlight_map
from ..data.models import DrawRecord
from ..data.repository import DrawRepository
from ..ml.catboost_model import LotteryCatBoostModel
from ..ml.generic_predictor import GenericMLPredictor
from ..ml.lgbm_model import LotteryLightGBMModel
from ..ml.model import LotteryXGBoostModel
from ..ml.model_store import compute_lookback, new_model_path
from ..ml.predictor import MLPredictor


def _is_winner(prize_amount) -> bool:
    """奖金为 None（浮动奖）或 >0 均视为中奖."""
    return prize_amount is None or prize_amount > 0


class BatchBacktestThread(QThread):
    """批量回测工作线程."""

    result_ready = Signal(object, object)
    progress = Signal(int, int)  # 当前期数, 总期数
    status_message = Signal(str)  # 过程状态文本
    round_ready = Signal(int, int, list)  # 当前期数, 总期数, 本期中奖记录

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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BatchBacktestThread")
        self.engine = engine
        self.strategy_id = strategy_id
        self.profile = profile
        self.data_repository = data_repository
        self.start_date = start_date
        self.end_date = end_date
        self.tickets_per_round = tickets_per_round
        self.options = options
        self._needs_history = needs_history(strategy_id)
        self._is_ml = is_ml_strategy(strategy_id) or strategy_id in {
            "xgboost",
            "lightgbm",
            "catboost",
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

            result = BatchBacktestResult(total_rounds=len(target_records))
            stopped = False
            for idx, actual in enumerate(target_records, start=1):
                if self.isInterruptionRequested():
                    stopped = True
                    break

                date_str = actual.draw_date.strftime("%Y-%m-%d")
                issue_str = actual.issue or "未知期号"
                self.status_message.emit(
                    f"[{idx}/{len(target_records)}] 开始测试 {date_str} 第 {issue_str} 期"
                )

                history = [
                    r for r in records if r.draw_date < actual.draw_date
                ]
                if self._needs_history and len(history) < 100:
                    self.status_message.emit(
                        f"  -> 历史数据不足（仅 {len(history)} 期），跳过本期"
                    )
                    self.progress.emit(idx, len(target_records))
                    continue

                options = dict(self.options)
                if self._needs_history:
                    options["history"] = history

                if self._is_ml:
                    self.status_message.emit("  -> 生成/训练模型中...")
                    options = self._prepare_ml_options(history, options)

                self.status_message.emit("  -> 生成预测号码中...")
                tickets = self.engine.generate(
                    self.strategy_id, count=self.tickets_per_round, options=options
                )

                round_winners: List[Dict[str, Any]] = []
                for t_idx, ticket in enumerate(tickets):
                    if self.isInterruptionRequested():
                        stopped = True
                        break
                    hits: Dict[str, int] = {}
                    for g in self.profile.groups:
                        actual_nums = actual.groups.get(g.key, [])
                        predicted_nums = ticket.groups.get(g.key, [])
                        if g.positional:
                            hits[g.key] = sum(
                                1 for a, p in zip(actual_nums, predicted_nums) if a == p
                            )
                        elif g.draw_only:
                            ticket_numbers: set[int] = set()
                            for pg in self.profile.pick_groups:
                                ticket_numbers.update(ticket.groups.get(pg.key, []))
                            hits[g.key] = len(set(actual_nums) & ticket_numbers)
                        else:
                            hits[g.key] = len(set(actual_nums) & set(predicted_nums))
                    prize_name, prize_amount = calculate_prize(
                        self.profile.key, hits, ticket.groups, actual.groups
                    )
                    result.total_cost += 2
                    is_winner = _is_winner(prize_amount)
                    if prize_amount is not None:
                        result.total_fixed_prize += prize_amount
                        if is_winner:
                            result.hit_count += 1
                    else:
                        result.float_prize_count += 1
                        result.hit_count += 1

                    # 第一注是否中奖
                    if t_idx == 0 and is_winner:
                        result.first_ticket_hit_count += 1

                    item = {
                        "date": date_str,
                        "issue": issue_str,
                        "ticket": ticket,
                        "hits": hits,
                        "matched_groups": compute_highlight_map(
                            self.profile, ticket, actual.groups
                        ),
                        "prize_name": prize_name,
                        "prize_amount": prize_amount,
                        "is_first": t_idx == 0,
                        "ticket_index": t_idx,
                    }
                    result.ticket_results.append(item)
                    if is_winner:
                        round_winners.append(item)
                        result.ticket_index_hits[t_idx] = result.ticket_index_hits.get(t_idx, 0) + 1

                if stopped:
                    break

                if round_winners:
                    self.status_message.emit(
                        f"  -> 本期中奖 {len(round_winners)} 注"
                    )
                else:
                    self.status_message.emit("  -> 本期未中奖")

                self.round_ready.emit(idx, len(target_records), round_winners)
                self.progress.emit(idx, len(target_records))

            self.status_message.emit(
                "批量回测完成，正在汇总结果..." if not stopped else "批量回测已停止。"
            )
            self.result_ready.emit(result, None)
        except Exception as exc:  # noqa: BLE001
            self.result_ready.emit(None, exc)

    def _prepare_ml_options(
        self, history: List[DrawRecord], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对 ML 策略：用当前历史数据训练临时模型并返回概率选项."""
        if self.profile.key == "ssq":
            if self.strategy_id.startswith("lightgbm"):
                model_class = LotteryLightGBMModel
                prefix = "lightgbm"
            elif self.strategy_id.startswith("catboost"):
                model_class = LotteryCatBoostModel
                prefix = "catboost"
            else:
                model_class = LotteryXGBoostModel
                prefix = "xgboost"
            lookback = compute_lookback(len(history))
            model_path = new_model_path(history, lookback, prefix=prefix, options=self.options)
            predictor = MLPredictor(
                history,
                lookback=lookback,
                model_path=model_path,
                model_class=model_class,
            )
            predictor.train()
            return options

        if self.strategy_id.startswith("lightgbm"):
            backend = "lightgbm"
        elif self.strategy_id.startswith("catboost"):
            backend = "catboost"
        else:
            backend = "xgboost"
        lookback = compute_lookback(len(history))
        prefix = (
            self.profile.lightgbm_prefix()
            if backend == "lightgbm"
            else self.profile.catboost_prefix()
            if backend == "catboost"
            else self.profile.xgboost_prefix()
        )
        model_path = new_model_path(history, lookback, prefix=prefix, options=self.options)
        predictor = GenericMLPredictor(
            history,
            profile=self.profile,
            lookback=lookback,
            model_path=model_path,
            backend=backend,
        )
        predictor.train()
        return options
