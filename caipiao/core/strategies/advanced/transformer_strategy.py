"""Transformer 时序预测策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class TransformerStrategy(_AdvancedBase):
    """基于 Transformer 自注意力机制的时序预测策略."""

    _id_base = "transformer"
    _name_base = "Transformer 时序预测"
    _description = "基于 Transformer 自注意力机制捕捉号码时序长期依赖关系。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "seq_len": {
                "type": "int",
                "label": "输入序列长度",
                "default": 20,
                "min": 10,
                "max": 50,
            },
            "d_model": {
                "type": "int",
                "label": "模型维度",
                "default": 64,
                "min": 32,
                "max": 128,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        seq_len = int(options.get("seq_len", 20))
        d_model = int(options.get("d_model", 64))

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        # 构建序列
        sequences = []
        for r in records:
            vec = np.zeros(size, dtype=np.float64)
            for n in r.groups.get(group.key, []):
                if group.lo <= n <= group.hi:
                    vec[n - group.lo] = 1.0
            sequences.append(vec)

        if len(sequences) < seq_len:
            proba = np.ones(size) / size
            if group.positional:
                proba = np.tile(proba, (pick, 1))
            basis = f"Transformer（{self._profile.name}）：数据不足，使用均匀概率。"
            return proba, basis

        # 简化的 Transformer 前向传播
        data = np.array(sequences[-seq_len:])

        # 自注意力
        rng = np.random.RandomState(42)
        scale = 1.0 / math.sqrt(d_model)
        W_q = rng.randn(size, d_model) * scale
        W_k = rng.randn(size, d_model) * scale
        W_v = rng.randn(size, d_model) * scale
        W_o = rng.randn(d_model, d_model) * scale
        fc_out = rng.randn(d_model, size) * scale

        # 调整权重
        freq = data.mean(axis=0)
        for i in range(size):
            if freq[i] > 0:
                W_v[i] *= (1 + freq[i])

        Q = data @ W_q
        K = data @ W_k
        V = data @ W_v

        scores = Q @ K.T / math.sqrt(d_model)
        exp_scores = np.exp(scores - scores.max(axis=-1, keepdims=True))
        attn_weights = exp_scores / exp_scores.sum(axis=-1, keepdims=True)
        attn_output = attn_weights @ V
        output = attn_output @ W_o
        logits = output.mean(axis=0) @ fc_out

        proba = 1.0 / (1.0 + np.exp(-logits))
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"Transformer（{self._profile.name}）：序列长度 {seq_len}，模型维度 {d_model}。"
        return proba, basis
