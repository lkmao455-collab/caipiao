"""马尔可夫链策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ....ml.markov_model import MarkovChainModel
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class MarkovChainStrategy(_AdvancedBase):
    """基于马尔可夫链的号码生成策略."""

    _id_base = "markov"
    _name_base = "马尔可夫链分析"
    _description = "基于状态转移矩阵分析号码出现的转移规律。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "order": {
                "type": "choice",
                "label": "马尔可夫链阶数",
                "choices": ["1", "2", "3"],
                "default": "2",
            },
            "lookback": {
                "type": "int",
                "label": "预测融合窗口",
                "default": 10,
                "min": 3,
                "max": 30,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        order = int(options.get("order", 2))
        lookback = int(options.get("lookback", 10))

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        if self._is_ssq():
            # SSQ: 红球二值序列
            sequences = []
            for r in records:
                vec = np.zeros(33, dtype=np.float64)
                for n in r.red_balls:
                    if 1 <= n <= 33:
                        vec[n - 1] = 1.0
                sequences.append(vec)
        elif self._is_3d():
            # FC3D: 按位 one-hot 序列
            sequences = []
            for r in records:
                nums = r.groups.get(group.key, [])
                vec = np.zeros(size, dtype=np.float64)
                for n in nums:
                    if group.lo <= n <= group.hi:
                        vec[n - group.lo] = 1.0
                sequences.append(vec)
        else:
            # 通用
            sequences = []
            for r in records:
                nums = r.groups.get(group.key, [])
                vec = np.zeros(size, dtype=np.float64)
                for n in nums:
                    if group.lo <= n <= group.hi:
                        vec[n - group.lo] = 1.0
                sequences.append(vec)

        model = MarkovChainModel(order=order)
        model.fit([], [])  # 使用内部逻辑

        # 直接计算转移概率
        n = len(sequences)
        if n < order + 1:
            proba = np.ones(size) / size
            basis = f"马尔可夫链分析（{self._profile.name}）：数据不足，使用均匀概率。"
            return proba, basis

        # 初始概率
        initial = np.mean(sequences, axis=0)
        initial = initial / initial.sum() if initial.sum() > 0 else np.ones(size) / size

        # 转移概率
        transition = np.zeros((size, size), dtype=np.float64)
        counts = np.zeros(size, dtype=np.float64)

        for i in range(order, n):
            prev_states = sequences[i - order:i]
            curr_state = sequences[i]
            for j in range(size):
                prev_weight = sum(
                    prev_states[k][j] * (order - k) for k in range(order)
                ) / (order * (order + 1) / 2)
                curr_weight = curr_state[j]
                transition[j] += curr_weight * (1 + prev_weight)
                counts[j] += (1 + prev_weight)

        for j in range(size):
            if counts[j] > 0:
                transition[j] /= counts[j]
            else:
                transition[j] = initial
            s = transition[j].sum()
            if s > 0:
                transition[j] /= s

        # 融合
        trans_prob = np.mean(transition, axis=0)
        proba = 0.7 * initial + 0.3 * trans_prob
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"马尔可夫链分析（{self._profile.name}，{order}阶）：基于 {len(records)} 期数据。"
        return proba, basis
