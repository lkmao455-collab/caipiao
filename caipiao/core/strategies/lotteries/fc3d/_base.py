"""福彩3D策略共享工具与基类."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import numpy as np

from ....profile import get_profile
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from .....data.models import DrawRecord
from .....ml.generic_predictor import GenericMLPredictor
from .....ml.model_store import compute_lookback, find_current_model, new_model_path
from .stability import deterministic_seed
from .utils import DIGIT_POOL


FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    history = options.get("history", []) or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records


def _make_rng(
    options: Dict[str, Any],
    history: Optional[List[DrawRecord]] = None,
    lookback: Optional[int] = None,
    strategy_id: str = "",
) -> random.Random:
    if options.get("seed") is None and not history:
        return random.Random()
    seed = deterministic_seed(options, history or [], lookback, strategy_id)
    return random.Random(seed)


def _sample_with_dedup(
    sample_fn: Any,
    count: int,
    dedup: bool,
) -> List[List[int]]:
    """生成 count 组3位号码，可选按 sorted tuple 去重。"""
    seen: set = set()
    results: List[List[int]] = []
    max_attempts = count * 50 if dedup else 1
    for _ in range(count):
        result = sample_fn()
        if dedup:
            for _ in range(max_attempts):
                key = tuple(sorted(result))
                if key not in seen:
                    seen.add(key)
                    break
                result = sample_fn()
        results.append(result)
    return results


class _FC3DMLStrategy(GenerationStrategy):
    """福彩3D机器学习策略共享基类。"""

    _backend: str = "xgboost"
    is_ml: bool = True

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "diversity_boost": {
                "type": "int",
                "label": "多样性增强 (0-10)",
                "default": 3,
                "min": 0,
                "max": 10,
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]

        lookback = compute_lookback(len(records))
        if self._backend == "xgboost":
            prefix = FC3D_PROFILE.xgboost_prefix()
        elif self._backend == "lightgbm":
            prefix = FC3D_PROFILE.lightgbm_prefix()
        else:
            prefix = FC3D_PROFILE.catboost_prefix()

        model_path = (
            find_current_model(records, lookback, prefix=prefix, options=options)
            or new_model_path(records, lookback, prefix=prefix, options=options)
        )

        predictor = GenericMLPredictor(
            records, profile=FC3D_PROFILE, lookback=lookback, model_path=model_path, backend=self._backend
        )
        if not predictor.is_ready():
            predictor.train()

        proba = predictor.predict()
        proba_lists = {}
        for k, v in proba.items():
            if v.ndim == 1:
                proba_lists[k] = [round(float(p), 4) for p in v]
            else:
                proba_lists[k] = [[round(float(x), 4) for x in row] for row in v]

        pos_group = FC3D_PROFILE.group("pos")
        group_probabilities = []
        if "pos" in proba_lists:
            pos_proba = proba_lists["pos"]
            if pos_proba and isinstance(pos_proba[0], list):
                for pos in range(len(pos_proba)):
                    group_probabilities.append(
                        (
                            f"号码第{pos + 1}位概率",
                            pos_proba[pos],
                            pos_group.color,
                            1,
                            "数字 (0-9)",
                        )
                    )

        pos_probs = [gp[1] for gp in group_probabilities] if group_probabilities else []
        details = {
            "lookback": lookback,
            "diversity_boost": int(diversity * 10),
            "probabilities": proba_lists,
            "group_probabilities": group_probabilities,
            "pos_probabilities": pos_probs,
            "model_name": self._backend.upper(),
        }
        basis = (
            f"{self.metadata.name}：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样。"
        )

        group_picks = {"pos": 3}
        tickets: List[Ticket] = []
        det_seed = deterministic_seed(options, records, lookback, self.metadata.id)
        for i in range(count):
            np_rng = np.random.RandomState(det_seed + i)
            rec_groups = predictor.recommend(group_picks=group_picks, diversity_boost=diversity, rng=np_rng)
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups=rec_groups,
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
