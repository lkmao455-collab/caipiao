"""LSTM 策略（红球+蓝球均使用 LSTM）."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ...data.models import DrawRecord
from ...ml.blue_lstm import BlueBallLSTM
from ...ml.red_lstm import RedBallLSTM
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket

logger = logging.getLogger(__name__)


def _to_red_lists(records: list[DrawRecord]) -> list[list[int]]:
    return [r.red_balls for r in records]


def _to_blue_list(records: list[DrawRecord]) -> list[int]:
    return [r.blue_ball for r in records if r.blue_ball is not None]


class LSTMStrategy(GenerationStrategy):
    """基于 LSTM 时序模型的号码生成策略."""

    is_ml = True  # 每次 generate 都会训练 LSTM，属于 ML 策略

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lstm",
            name="LSTM 时序分析",
            description="基于 LSTM 神经网络捕捉号码时序规律，红球和蓝球分别建模。",
            configurable=True,
        )

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
                "tooltip": "-1 表示使用全部历史记录。",
            },
            "seq_len": {
                "type": "int",
                "label": "时序窗口长度",
                "default": 20,
                "min": 10,
                "max": 50,
                "tooltip": "用前 N 期数据预测下一期。",
            },
            "epochs": {
                "type": "int",
                "label": "训练轮数",
                "default": 50,
                "min": 10,
                "max": 200,
                "tooltip": "LSTM 训练轮数，越大越精确但耗时更长。",
            },
        }

    def validate_options(self, options: dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError("LSTM 策略需要至少 100 期历史数据")

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        options = options or {}
        history = options.get("history", [])
        seq_len = int(options.get("seq_len", 20))
        epochs = int(options.get("epochs", 50))
        seed = options.get("seed")

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(history) > history_count:
            history = history[-history_count:]

        records = [
            r if isinstance(r, DrawRecord) else DrawRecord(
                issue="", draw_date=r.generated_at,
                profile=r.profile.key, groups=r.groups,
            )
            for r in history
        ]

        red_lists = _to_red_lists(records)
        blue_list = _to_blue_list(records)

        progress = options.get("_progress_callback")

        # 训练红球 LSTM
        if progress:
            progress("正在训练红球 LSTM 模型...")
        red_lstm = RedBallLSTM(seq_len=seq_len, hidden_size=128, num_layers=2)
        red_lstm.train(red_lists, epochs=epochs, progress_callback=progress)
        if progress:
            progress("红球 LSTM 训练完成")
        red_proba = red_lstm.predict(red_lists[-seq_len:])

        # 训练蓝球 LSTM
        if progress:
            progress("正在训练蓝球 LSTM 模型...")
        blue_lstm = BlueBallLSTM(seq_len=seq_len, hidden_size=64, num_layers=2)
        if blue_list:
            blue_lstm.train(blue_list, epochs=epochs, progress_callback=progress)
            if progress:
                progress("蓝球 LSTM 训练完成")
            blue_proba = blue_lstm.predict(blue_list[-seq_len:])
        else:
            if progress:
                progress("蓝球数据不足，使用均匀概率")
            blue_proba = np.ones(16) / 16.0

        basis = (
            f"LSTM 时序分析策略：基于 {len(records)} 期历史数据，"
            f"时序窗口 {seq_len}，训练 {epochs} 轮。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        tickets: list[Ticket] = []
        if count <= 0:
            return tickets

        # 红球加权采样
        red_weights = red_proba + 0.05
        red_weights = red_weights / red_weights.sum()

        # 蓝球加权采样（不再无根据地剔除上期）
        blue_weights = blue_proba + 0.05
        blue_weights = blue_weights / blue_weights.sum()

        rng = np.random.RandomState(seed) if seed is not None else np.random.RandomState()

        for i in range(count):
            reds = sorted(rng.choice(range(1, 34), size=6, replace=False, p=red_weights))
            blue = int(rng.choice(range(1, 17), p=blue_weights))
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
