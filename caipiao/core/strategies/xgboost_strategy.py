"""XGBoost 机器学习策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ...data.models import DrawRecord
from ...ml.model_store import compute_lookback, find_current_model, new_model_path
from ...ml.predictor import MLPredictor
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


class XGBoostStrategy(GenerationStrategy):
    """基于 XGBoost 机器学习的号码生成策略.

    使用历史开奖数据训练模型，预测各号码出现概率后生成号码。
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
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
                "tooltip": "避免推荐号码过于集中。值越大，相邻号码被选中的概率越低。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError("XGBoost 策略需要至少 100 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        history = options.get("history", [])
        diversity = int(options.get("diversity_boost", 3)) / 10.0

        # XGBoost 作为科学实验应保持确定性：使用固定随机种子，
        # 在相同历史数据和参数下每次输出一致。
        FIXED_SEED = 42

        records = [r if isinstance(r, DrawRecord) else r for r in history]

        # 自动根据历史记录总数确定回看期数：
        # - 尽量使用更长的历史，让模型看到更多统计模式；
        # - 至少保留 100 期作为训练样本，避免样本过少导致训练失败。
        lookback = compute_lookback(len(records))

        # 优先加载与当前数据匹配的最新模型；不存在则用带时间戳的新路径训练。
        model_path = find_current_model(records, lookback) or new_model_path(lookback)

        predictor = MLPredictor(records, lookback=lookback, model_path=model_path)
        if not predictor.is_ready():
            predictor.train()

        red_proba, blue_proba = predictor.predict()
        red_proba_list = [round(float(p), 4) for p in red_proba]
        blue_proba_list = [round(float(p), 4) for p in blue_proba]
        details = {
            "lookback": lookback,
            "diversity_boost": int(diversity * 10),
            "red_probabilities": red_proba_list,
            "blue_probabilities": blue_proba_list,
        }

        basis = (
            f"XGBoost 智能分析策略：基于全部 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样，多样性增强 {int(diversity * 10)}。"
        )

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        # 第一组强制为模型预测概率最高的前 6 个红球 + 概率最高的 1 个蓝球
        top_red_indices = np.argsort(red_proba)[-6:]
        top_reds = sorted((int(idx) + 1) for idx in top_red_indices)
        top_blue = int(np.argmax(blue_proba)) + 1
        tickets.append(
            Ticket(
                red_balls=top_reds,
                blue_ball=top_blue,
                strategy_name=self.metadata.name,
                basis=basis + " 第一组为模型预测概率最高的前 6 个红球和 1 个蓝球。",
                details=details,
            )
        )

        # 其余注按概率加权采样，仍保持固定种子以确保可复现
        for i in range(1, count):
            np_rng = np.random.RandomState(FIXED_SEED + i)
            reds, blues = predictor.recommend(
                red_count=6, blue_count=1, diversity_boost=diversity, rng=np_rng
            )
            tickets.append(
                Ticket(
                    red_balls=sorted(reds),
                    blue_ball=blues[0],
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details,
                )
            )

        return tickets
