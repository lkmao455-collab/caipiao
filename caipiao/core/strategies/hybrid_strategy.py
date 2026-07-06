"""混合策略：红球XGBoost + 蓝球LSTM."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ...data.models import DrawRecord
from ...ml.blue_lstm import BlueBallLSTM
from ...ml.model_store import compute_lookback, find_current_model, new_model_path
from ...ml.predictor import MLPredictor
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket

logger = logging.getLogger(__name__)


class HybridStrategy(GenerationStrategy):
    """红球使用 XGBoost，蓝球使用 LSTM 的混合策略."""

    is_ml = False

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hybrid",
            name="智能混合分析",
            description="红球用 XGBoost 概率建模，蓝球用 LSTM 时序建模，取两者优势。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "diversity_boost": {
                "type": "int",
                "label": "多样性增强 (0-10)",
                "default": 3,
                "min": 0,
                "max": 10,
            },
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
            "blue_seq_len": {
                "type": "int",
                "label": "蓝球时序窗口",
                "default": 20,
                "min": 10,
                "max": 50,
            },
            "blue_epochs": {
                "type": "int",
                "label": "蓝球训练轮数",
                "default": 50,
                "min": 10,
                "max": 200,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError("混合策略需要至少 100 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        history = options.get("history", [])
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        blue_seq_len = int(options.get("blue_seq_len", 20))
        blue_epochs = int(options.get("blue_epochs", 50))

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

        # === 红球：XGBoost ===
        progress = options.get("_progress_callback")
        if progress:
            progress("正在训练 XGBoost 红球模型...")
        lookback = compute_lookback(len(records))
        model_path = find_current_model(records, lookback, prefix="xgboost", options=options) \
            or new_model_path(records, lookback, prefix="xgboost", options=options)
        xgb_predictor = MLPredictor(records, lookback=lookback, model_path=model_path)
        if not xgb_predictor.is_ready():
            xgb_predictor.train()
        if progress:
            progress("XGBoost 红球模型就绪")
        red_proba, _ = xgb_predictor.predict()

        # === 蓝球：LSTM ===
        if progress:
            progress("正在训练蓝球 LSTM 模型...")
        blue_list = [r.blue_ball for r in records if r.blue_ball is not None]
        blue_lstm = BlueBallLSTM(seq_len=blue_seq_len, hidden_size=64, num_layers=2)
        if blue_list:
            blue_lstm.train(blue_list, epochs=blue_epochs, progress_callback=progress)
            if progress:
                progress("蓝球 LSTM 训练完成")
            blue_proba = blue_lstm.predict(blue_list[-blue_seq_len:])
        else:
            if progress:
                progress("蓝球数据不足，使用均匀概率")
            blue_proba = np.ones(16) / 16.0

        # 剔除上期蓝球
        last_blue = blue_list[-1] if blue_list else 0
        blue_adj = blue_proba.copy()
        if 1 <= last_blue <= 16:
            blue_adj[last_blue - 1] = 0
        blue_sum = blue_adj.sum()
        if blue_sum > 0:
            blue_adj = blue_adj / blue_sum

        basis = (
            f"智能混合分析：红球 XGBoost（{len(records)}期，lookback={lookback}），"
            f"蓝球 LSTM（窗口={blue_seq_len}，{blue_epochs}轮）。"
        )

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        red_weights = red_proba + 0.05
        red_weights = red_weights / red_weights.sum()

        rng = np.random.RandomState(options.get("seed", 42))
        for i in range(count):
            reds = sorted(rng.choice(range(1, 34), size=6, replace=False, p=red_weights))
            blue = int(rng.choice(range(1, 17), p=blue_adj))
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
