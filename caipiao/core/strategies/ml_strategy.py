"""统一机器学习策略（XGBoost / LightGBM / CatBoost）.

合并原来三个独立的 ML 策略文件，通过 backend 参数切换后端。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import numpy as np

from ...data.models import DrawRecord
from ...ml.model_store import compute_lookback, find_current_model, new_model_path
from ...ml.predictor import MLPredictor
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket

logger = logging.getLogger(__name__)

# 后端到模型类和名称的映射
_BACKENDS = {
    "xgboost": {
        "label": "XGBoost",
        "model_class": None,
        "prefix_key": "xgboost_prefix",
    },
    "lightgbm": {
        "label": "LightGBM",
        "model_class": None,
        "prefix_key": "lightgbm_prefix",
    },
    "catboost": {
        "label": "CatBoost",
        "model_class": None,
        "prefix_key": "catboost_prefix",
    },
}


def _get_model_class(backend: str):
    """延迟导入模型类，避免未安装时报错。"""
    info = _BACKENDS[backend]
    if info["model_class"] is not None:
        return info["model_class"]

    if backend == "lightgbm":
        from ...ml.lgbm_model import LotteryLightGBMModel
        info["model_class"] = LotteryLightGBMModel
    elif backend == "catboost":
        from ...ml.catboost_model import LotteryCatBoostModel
        info["model_class"] = LotteryCatBoostModel
    elif backend == "xgboost":
        from ...ml.model import LotteryXGBoostModel
        info["model_class"] = LotteryXGBoostModel
    return info["model_class"]


class MLStrategy(GenerationStrategy):
    """统一机器学习策略，通过 backend 参数切换 XGBoost / LightGBM / CatBoost。"""

    is_ml = True

    def __init__(self, backend: str = "xgboost") -> None:
        if backend not in _BACKENDS:
            raise ValueError(f"不支持的后端: {backend}")
        self._backend = backend
        self._info = _BACKENDS[backend]

    @property
    def metadata(self) -> StrategyMetadata:
        label = self._info["label"]
        return StrategyMetadata(
            id=f"ml_{self._backend}",
            name=f"{label} 智能分析",
            description=f"基于 {label} 模型分析历史数据，生成概率优先的号码组合。",
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
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        backend = self._backend
        info = _BACKENDS[backend]

        history = options.get("history", [])
        diversity = int(options.get("diversity_boost", 3)) / 10.0

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(history) > history_count:
            history = history[-history_count:]

        FIXED_SEED = 42

        records = [
            r if isinstance(r, DrawRecord) else DrawRecord(
                issue="",
                draw_date=r.generated_at,
                profile=r.profile.key,
                groups=r.groups,
            )
            for r in history
        ]
        lookback = compute_lookback(len(records))

        profile = records[0].profile if records else None
        if profile is not None:
            prefix = getattr(profile, info["prefix_key"])()
        else:
            prefix = backend

        model_path = find_current_model(
            records, lookback, prefix=prefix, options=options
        ) or new_model_path(records, lookback, prefix=prefix, options=options)

        model_class = _get_model_class(backend)
        predictor = MLPredictor(
            records, lookback=lookback, model_path=model_path,
            model_class=model_class,
        )
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
            "backend": backend,
        }

        label = info["label"]
        basis = (
            f"{label} 智能分析策略：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样，多样性增强 {int(diversity * 10)}。"
        )

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        seen: Set[tuple] = set()
        seed_offset = 0
        max_attempts = 10

        while len(tickets) < count and seed_offset < count + max_attempts * 10:
            batch_size = count + 10
            batch = self._generate_batch(
                predictor=predictor,
                red_proba=red_proba,
                blue_proba=blue_proba,
                diversity=diversity,
                fixed_seed=FIXED_SEED,
                seed_offset=seed_offset,
                batch_size=batch_size,
                basis=basis,
                details=details,
            )
            seed_offset += batch_size

            for ticket in batch:
                key = self._ticket_key(ticket)
                if key in seen:
                    continue
                seen.add(key)
                tickets.append(ticket)
                if len(tickets) >= count:
                    break

        if len(tickets) < count:
            logger.warning(
                "%s 策略经过 %d 次尝试仍只生成 %d 注有效号码（目标 %d 注）",
                label, seed_offset, len(tickets), count
            )

        return tickets[:count]

    def _generate_batch(
        self,
        predictor: MLPredictor,
        red_proba: np.ndarray,
        blue_proba: np.ndarray,
        diversity: float,
        fixed_seed: int,
        seed_offset: int,
        batch_size: int,
        basis: str,
        details: Dict[str, Any],
    ) -> List[Ticket]:
        tickets: List[Ticket] = []
        for i in range(batch_size):
            np_rng = np.random.RandomState(fixed_seed + seed_offset + i)
            reds, blues = predictor.recommend(
                red_count=6, blue_count=1, diversity_boost=diversity, rng=np_rng
            )
            blue = int(blues[0]) if blues else 0
            tickets.append(
                Ticket(
                    red_balls=sorted(reds),
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details,
                )
            )
        return tickets

    @staticmethod
    def _ticket_key(ticket: Ticket) -> tuple:
        reds = tuple(sorted(ticket.groups.get("red", [])))
        blue = ticket.groups.get("blue", [None])[0]
        return reds, blue
