"""通用 ML 策略基类工厂.

按彩种绑定 ``LotteryProfile``，复用 ``caipiao.ml.generic_predictor.GenericMLPredictor``，
避免为每个彩种复制一份 ML 策略公共逻辑。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Type

import numpy as np

from ....core.profile import LotteryProfile
from ....core.strategy import GenerationStrategy
from ....core.ticket import Ticket
from ....data.models import DrawRecord
from ....ml.common.model_store import compute_lookback, find_current_model, new_model_path
from ....ml.generic_predictor import GenericMLPredictor
from .records import records_from_options

logger = logging.getLogger(__name__)


def _deterministic_seed(
    options: Dict[str, Any],
    records: List[DrawRecord],
    strategy_id: str,
) -> int:
    """若 options 中无显式 seed，则基于历史数据与策略 ID 派生确定性 seed."""
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    parts = []
    for r in records:
        parts.append(f"{r.issue or ''}:{r.draw_date.isoformat()}")
    content = ";".join(parts)
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode("utf-8")).hexdigest()
    return int(raw, 16) % (2**31)


def make_generic_ml_base(
    profile: LotteryProfile,
    predictor_class: Optional[Type[GenericMLPredictor]] = None,
) -> Type[GenerationStrategy]:
    """为指定彩种创建基于 GenericMLPredictor 的 ML 策略私有基类.

    Args:
        profile: 彩种档案。
        predictor_class: 可选的专属预测器类；默认使用 ``GenericMLPredictor``。
            传入的类应接受 ``(records, lookback, model_path, backend, temp_dir)``
            参数并在内部固定彩种。
    """

    class _GenericLotteryMLStrategyBase(GenerationStrategy):
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
                    "tooltip": "避免推荐号码过于集中。值越大，相邻号码被选中的概率越低。",
                },
                "history": {"type": "history", "label": "历史记录", "default": []},
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
            records = records_from_options(options)
            diversity = int(options.get("diversity_boost", 3)) / 10.0

            history_count = options.get("history_count", -1)
            if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
                records = records[-history_count:]

            lookback = compute_lookback(len(records))
            prefix = getattr(profile, f"{self._backend}_prefix")()
            model_path = (
                find_current_model(records, lookback, prefix=prefix, options=options)
                or new_model_path(records, lookback, prefix=prefix, options=options)
            )

            predictor_cls = predictor_class or GenericMLPredictor
            if predictor_class is None:
                predictor = predictor_cls(
                    records,
                    profile=profile,
                    lookback=lookback,
                    model_path=model_path,
                    backend=self._backend,
                )
            else:
                predictor = predictor_cls(
                    records,
                    lookback=lookback,
                    model_path=model_path,
                    backend=self._backend,
                )
            if not predictor.is_ready():
                predictor.train()

            proba = predictor.predict()
            proba_lists: Dict[str, Any] = {}
            for k, v in proba.items():
                if v.ndim == 1:
                    proba_lists[k] = [round(float(p), 4) for p in v]
                else:
                    proba_lists[k] = [[round(float(x), 4) for x in row] for row in v]

            details = {
                "lookback": lookback,
                "diversity_boost": int(diversity * 10),
                "probabilities": proba_lists,
                "backend": self._backend,
            }
            basis = (
                f"{self.metadata.name}：基于最近 {len(records)} 期历史数据训练模型，"
                f"特征回看期数 {lookback}，按预测概率加权采样。"
            )

            group_picks = {
                g.key: getattr(g, "effective_pick_max", g.count)
                for g in profile.pick_groups
            }
            base_seed = _deterministic_seed(options, records, self.metadata.id)

            tickets: List[Ticket] = []
            for i in range(count):
                np_rng = np.random.RandomState(base_seed + i)
                rec_groups = predictor.recommend(
                    group_picks=group_picks, diversity_boost=diversity, rng=np_rng
                )
                tickets.append(
                    Ticket(
                        profile=profile,
                        groups=rec_groups,
                        strategy_name=self.metadata.name,
                        basis=basis,
                        details=details.copy(),
                    )
                )
            return tickets

    return _GenericLotteryMLStrategyBase


def make_placeholder_ml_base(
    profile: LotteryProfile, reason: str
) -> Type[GenerationStrategy]:
    """为当前后端暂不支持的彩种创建占位 ML 策略私有基类.

    占位类仍具有正确的 metadata / schema，可在注册表中正常注册；
    调用 ``generate`` 时抛出 ``NotImplementedError`` 并说明原因。
    """

    class _PlaceholderLotteryMLStrategyBase(GenerationStrategy):
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

        def generate(
            self, count: int = 1, options: Optional[Dict[str, Any]] = None
        ) -> List[Ticket]:
            raise NotImplementedError(
                f"{profile.name} 的 {self.metadata.name} 尚未实现：{reason}"
            )

    return _PlaceholderLotteryMLStrategyBase
