"""SSQ ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ......data.models import DrawRecord
from ......ml.common.model_store import compute_lookback, find_current_model, new_model_path
from ......ml.lotteries.ssq.predictor import SSQPredictor as MLPredictor
from .....profile import SSQ
from .....strategy import GenerationStrategy
from ....common.records import records_from_options

logger = logging.getLogger(__name__)


class _SSQMLStrategyBase(GenerationStrategy):
    """SSQ ML 策略私有基类，禁止外部直接实例化。"""

    _backend: str = "xgboost"
    _label: str = "XGBoost"
    _id: str = "ml_xgboost"
    is_ml: bool = True

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
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
                "tooltip": "-1 表示使用全部历史记录；正数表示只使用最近 N 期训练模型。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError(f"{self._label} 智能分析策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def _load_predictor(self, options: Dict[str, Any]) -> MLPredictor:
        records = records_from_options(options)
        if len(records) < 100:
            raise ValueError(f"{self._label} 智能分析策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]
        lookback = compute_lookback(len(records))

        prefix_map = {
            "xgboost": "ml_xgboost",
            "lightgbm": "ml_lightgbm",
            "catboost": "ml_catboost",
        }
        prefix = prefix_map.get(self._backend, self._backend)

        model_path = (
            find_current_model(records, lookback, prefix=prefix, options=options)
            or new_model_path(records, lookback, prefix=prefix, options=options)
        )
        predictor = MLPredictor(
            records, lookback=lookback, model_path=model_path, backend=self._backend
        )
        if not predictor.is_ready():
            predictor.train()
        return predictor

    def _model_class(self):
        if self._backend == "xgboost":
            from ......ml.model import LotteryXGBoostModel
            return LotteryXGBoostModel
        if self._backend == "lightgbm":
            from ......ml.lgbm_model import LotteryLightGBMModel
            return LotteryLightGBMModel
        if self._backend == "catboost":
            from ......ml.catboost_model import LotteryCatBoostModel
            return LotteryCatBoostModel
        raise ValueError(f"未知后端: {self._backend}")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        from .....ticket import Ticket

        options = options or {}
        predictor = self._load_predictor(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        seed = options.get("seed")
        if seed is None:
            seed = int(np.random.randint(0, 2**31))

        red_proba, blue_proba = predictor.predict()
        details = {
            "lookback": predictor.lookback,
            "diversity_boost": int(diversity * 10),
            "red_probabilities": [round(float(p), 4) for p in red_proba],
            "blue_probabilities": [round(float(p), 4) for p in blue_proba],
            "backend": self._backend,
        }
        basis = (
            f"{self._label} 智能分析策略：基于最近 {len(predictor.records)} 期历史数据训练模型，"
            f"特征回看期数 {predictor.lookback}，按预测概率加权采样。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        tickets: List[Ticket] = []
        seen: set = set()
        seed_offset = 0
        while len(tickets) < count and seed_offset < count * 20:
            np_rng = np.random.RandomState(seed + seed_offset)
            reds, blues = predictor.recommend(
                red_count=6, blue_count=1, diversity_boost=diversity, rng=np_rng
            )
            blue = int(blues[0]) if blues else 0
            ticket = Ticket(
                profile=SSQ,
                groups={"red": sorted(reds), "blue": [blue]},
                strategy_name=self.metadata.name,
                basis=basis,
                details=details,
            )
            key = (tuple(sorted(ticket.groups["red"])), ticket.groups["blue"][0])
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)
            seed_offset += 1
        return tickets[:count]
