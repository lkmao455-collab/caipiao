"""双色球马尔可夫链策略。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from caipiao.data.models import DrawRecord

from ._base import SSQAdvancedStrategy


class SSQMarkovStrategy(SSQAdvancedStrategy):
    """基于马尔可夫链的号码生成策略。"""

    _id = "markov"
    _name = "马尔可夫链分析"
    _description = "基于状态转移矩阵分析号码出现的转移规律。"

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

        size = 33

        sequences = []
        for r in records:
            vec = np.zeros(size, dtype=np.float64)
            for n in r.red_balls:
                if 1 <= n <= 33:
                    vec[n - 1] = 1.0
            sequences.append(vec)

        n = len(sequences)
        if n < order + 1:
            proba = np.ones(size) / size
            basis = "马尔可夫链分析（双色球）：数据不足，使用均匀概率。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
            return proba, basis

        initial = np.mean(sequences, axis=0)
        initial = initial / initial.sum() if initial.sum() > 0 else np.ones(size) / size

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

        trans_prob = np.mean(transition, axis=0)
        proba = 0.7 * initial + 0.3 * trans_prob
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        basis = (
            f"马尔可夫链分析（双色球，{order}阶）：基于 {len(records)} 期数据，"
            f"融合窗口 {lookback} 期。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )
        return proba, basis
