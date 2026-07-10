"""快乐8 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, List, Optional

import numpy as np

from ......ml.common.model_store import compute_lookback, find_current_model, new_model_path
from ......ml.lotteries.kl8.predictor import KL8Predictor as MLPredictor
from .....profile import KL8
from .....strategy import GenerationStrategy
from ....common.records import records_from_options
from .._base import _add_pick_count_schema, _get_pick_count, _make_ticket

logger = logging.getLogger(__name__)


def _profile_prefix(backend: str) -> str:
    if backend == "xgboost":
        return KL8.xgboost_prefix()
    if backend == "lightgbm":
        return KL8.lightgbm_prefix()
    return KL8.catboost_prefix()


class _KL8MLStrategyBase(GenerationStrategy):
    """KL8 ML 策略私有基类，禁止外部直接实例化。"""

    _backend: str = "xgboost"
    _needs_history: bool = True
    is_ml: bool = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {
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
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, label="投注个数")
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def _load_predictor(self, options: Dict[str, Any]) -> MLPredictor:
        records = records_from_options(options)
        if len(records) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]
        lookback = compute_lookback(len(records))
        prefix = _profile_prefix(self._backend)

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

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        options = options or {}
        predictor = self._load_predictor(options)
        pick = _get_pick_count(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        seed = options.get("seed")
        if seed is None:
            seed = secrets.randbelow(2**31)

        proba = predictor.predict()
        details = {
            "lookback": predictor.lookback,
            "diversity_boost": int(diversity * 10),
            "pick_count": pick,
            "probabilities": [round(float(p), 4) for p in proba],
            "backend": self._backend,
        }
        basis = (
            f"{self.metadata.name}：基于最近 {len(predictor.records)} 期历史数据训练模型，"
            f"特征回看期数 {predictor.lookback}，按预测概率加权采样。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        tickets: List[Any] = []
        seen: set = set()
        seed_offset = 0
        while len(tickets) < count and seed_offset < count * 20:
            np_rng = np.random.RandomState(seed + seed_offset)
            numbers = predictor.recommend(
                pick=pick, diversity_boost=diversity, rng=np_rng
            )
            ticket = _make_ticket(
                groups={"main": sorted(numbers)},
                strategy_name=self.metadata.name,
                basis=basis,
                details=details.copy(),
            )
            key = tuple(ticket.groups["main"])
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)
            seed_offset += 1
        return tickets[:count]
