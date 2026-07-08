"""LightGBM 机器学习策略."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import numpy as np

from ...data.models import DrawRecord
from ...ml.lgbm_model import LotteryLightGBMModel
from ...ml.model_store import compute_lookback, find_current_model, new_model_path
from ...ml.predictor import MLPredictor
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket

MODEL_PREFIX = "lightgbm"

logger = logging.getLogger(__name__)


def _last_draw_from_records(records: List[DrawRecord]) -> Optional[Dict[str, List[int]]]:
    """返回最近一期开奖号码；无记录返回 None."""
    if not records:
        return None
    return {k: list(v) for k, v in records[-1].groups.items()}


def _red_overlap(reds: List[int], last_reds: List[int]) -> int:
    """计算两组红球的交集个数."""
    return len(set(reds) & set(last_reds))


class LightGBMStrategy(GenerationStrategy):
    """基于 LightGBM 机器学习的号码生成策略.

    使用历史开奖数据训练模型，预测各号码出现概率后生成号码。
    结构与 XGBoost 策略一致，底层换用 LightGBM 模型。
    """

    is_ml = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
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
            "max_red_overlap": {
                "type": "int",
                "label": "与上期红球最大允许重复数",
                "default": 4,
                "min": 0,
                "max": 6,
                "tooltip": "生成的红球与上一期红球重复超过该值时，会舍弃重选。0 表示不允许与上期红球重复。",
            },
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
                "tooltip": "-1 表示使用全部历史记录；正数表示只使用最近 N 期训练模型。",
            },
            "allow_blue_repeat": {
                "type": "bool",
                "label": "允许蓝球与上期重复",
                "default": True,
                "tooltip": "勾选后生成的蓝球可以与上一期相同；不勾选则过滤掉与上期相同的蓝球。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError("LightGBM 策略需要至少 100 期历史数据")
        overlap = options.get("max_red_overlap", 4)
        if not isinstance(overlap, int) or not (0 <= overlap <= 6):
            raise ValueError("与上期红球最大允许重复数必须在 0-6 之间")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        history = options.get("history", [])
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        max_red_overlap = int(options.get("max_red_overlap", 4))
        allow_blue_repeat = bool(options.get("allow_blue_repeat", True))

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(history) > history_count:
            history = history[-history_count:]

        # LightGBM 作为科学实验应保持确定性：使用固定种子，
        # 在相同历史数据和参数下每次输出一致。
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
        model_path = find_current_model(
            records, lookback, prefix=MODEL_PREFIX, options=options
        ) or new_model_path(
            records, lookback, prefix=MODEL_PREFIX, options=options
        )

        predictor = MLPredictor(
            records,
            lookback=lookback,
            model_path=model_path,
            model_class=LotteryLightGBMModel,
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
        }

        basis = (
            f"LightGBM 智能分析策略：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样，多样性增强 {int(diversity * 10)}，"
            f"与上期红球最大允许重复数 {max_red_overlap}，"
            f"{'允许' if allow_blue_repeat else '不允许'}蓝球与上期重复。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        last_draw = _last_draw_from_records(records)
        last_reds = last_draw.get("red", []) if last_draw else []
        last_blue = last_draw.get("blue", [None])[0] if last_draw else None

        seen: Set[tuple] = set()
        seed_offset = 0
        max_attempts = 10

        while len(tickets) < count and seed_offset < count + max_attempts * 10:
            batch_size = count + 10
            batch = self._generate_batch(
                predictor=predictor,
                red_proba=red_proba,
                blue_proba=blue_proba,
                last_reds=last_reds,
                last_blue=last_blue,
                max_red_overlap=max_red_overlap,
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
                # 蓝球重复规则
                if not allow_blue_repeat and last_blue is not None and ticket.groups.get("blue", [None])[0] == last_blue:
                    continue
                reds = ticket.groups.get("red", [])
                if last_reds and _red_overlap(reds, last_reds) > max_red_overlap:
                    continue
                seen.add(key)
                tickets.append(ticket)
                if len(tickets) >= count:
                    break

        if len(tickets) < count:
            logger.warning(
                "LightGBM 策略经过 %d 次尝试仍只生成 %d 注有效号码（目标 %d 注）",
                seed_offset, len(tickets), count
            )

        return tickets[:count]

    def _generate_batch(
        self,
        predictor: MLPredictor,
        red_proba: np.ndarray,
        blue_proba: np.ndarray,
        last_reds: List[int],
        last_blue: Optional[int],
        max_red_overlap: int,
        diversity: float,
        fixed_seed: int,
        seed_offset: int,
        batch_size: int,
        basis: str,
        details: Dict[str, Any],
    ) -> List[Ticket]:
        """生成一批候选投注单（全部按概率加权采样）."""
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
