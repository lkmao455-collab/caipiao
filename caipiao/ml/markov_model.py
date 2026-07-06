"""马尔可夫链模型."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class MarkovChainModel:
    """基于马尔可夫链的彩票号码状态转移模型.

    分析号码出现的状态转移规律，预测下一期各号码出现的概率。
    """

    def __init__(self, order: int = 2) -> None:
        """Args:
            order: 马尔可夫链阶数（1=一阶，2=二阶）。
        """
        self.order = order
        self.red_transition: Optional[np.ndarray] = None
        self.blue_transition: Optional[np.ndarray] = None
        self.red_initial: Optional[np.ndarray] = None
        self.blue_initial: Optional[np.ndarray] = None
        self.is_trained = False

    def fit(
        self,
        red_sequences: List[List[int]],
        blue_sequences: List[int],
        red_count: int = 33,
        blue_count: int = 16,
        smoothing: float = 0.01,
    ) -> None:
        """训练马尔可夫链模型.

        Args:
            red_sequences: 历史红球序列（每期6个号码）。
            blue_sequences: 历史蓝球序列。
            red_count: 红球号码总数。
            blue_count: 蓝球号码总数。
            smoothing: 拉普拉斯平滑参数。
        """
        self.red_count = red_count
        self.blue_count = blue_count

        # 红球：将每期6个号码转换为二值向量序列
        red_binary = self._to_binary_sequence(red_sequences, red_count)
        self.red_transition, self.red_initial = self._build_transition(
            red_binary, red_count, smoothing
        )

        # 蓝球：one-hot 序列
        blue_binary = self._to_onehot_sequence(blue_sequences, blue_count)
        self.blue_transition, self.blue_initial = self._build_transition(
            blue_binary, blue_count, smoothing
        )

        self.is_trained = True
        logger.info(
            "马尔可夫链模型训练完成（阶数=%d，红球=%d期，蓝球=%d期）",
            self.order, len(red_sequences), len(blue_sequences),
        )

    def predict_proba(
        self, lookback: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """基于最近 lookback 期预测下一期各号码出现概率."""
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")
        red_p = self._predict_group(self.red_transition, self.red_initial, lookback)
        blue_p = self._predict_group(self.blue_transition, self.blue_initial, lookback)
        return red_p, blue_p

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #
    def _to_binary_sequence(
        self, sequences: List[List[int]], size: int
    ) -> List[np.ndarray]:
        """将号码列表序列转为二值向量序列。"""
        result = []
        for nums in sequences:
            vec = np.zeros(size, dtype=np.float64)
            for n in nums:
                if 1 <= n <= size:
                    vec[n - 1] = 1.0
            result.append(vec)
        return result

    def _to_onehot_sequence(
        self, sequences: List[int], size: int
    ) -> List[np.ndarray]:
        """将单值序列转为 one-hot 向量序列。"""
        result = []
        for n in sequences:
            vec = np.zeros(size, dtype=np.float64)
            if 1 <= n <= size:
                vec[n - 1] = 1.0
            result.append(vec)
        return result

    def _build_transition(
        self,
        binary_seq: List[np.ndarray],
        size: int,
        smoothing: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """构建状态转移矩阵和初始概率向量."""
        # 状态数 = 2^min(order, max_reasonable) ，但这里简化为基于最近N期的滑动窗口
        # 使用加权历史频率作为转移概率
        n = len(binary_seq)
        if n < self.order + 1:
            # 数据不足，返回均匀分布
            uniform = np.ones(size) / size
            return np.eye(size) * (1 - smoothing) + smoothing / size, uniform

        # 初始概率：基于所有期的平均出现频率
        initial = np.mean(binary_seq, axis=0)
        initial = initial / initial.sum() if initial.sum() > 0 else np.ones(size) / size

        # 转移矩阵：基于条件概率 P(当前出现 | 历史状态)
        transition = np.zeros((size, size), dtype=np.float64)
        counts = np.zeros(size, dtype=np.float64)

        for i in range(self.order, n):
            prev_states = binary_seq[i - self.order : i]
            curr_state = binary_seq[i]

            # 计算历史加权状态
            for j in range(size):
                # 历史状态：近N期该号码是否出现
                prev_weight = sum(
                    prev_states[k][j] * (self.order - k) for k in range(self.order)
                ) / (self.order * (self.order + 1) / 2)

                # 当前状态：该号码是否出现
                curr_weight = curr_state[j]
                transition[j] += curr_weight * (1 + prev_weight)
                counts[j] += (1 + prev_weight)

        # 平滑
        for j in range(size):
            if counts[j] > 0:
                transition[j] = transition[j] / counts[j]
            else:
                transition[j] = initial
            transition[j] = transition[j] * (1 - smoothing) + smoothing / size
            s = transition[j].sum()
            if s > 0:
                transition[j] /= s

        return transition, initial

    def _predict_group(
        self, transition: np.ndarray, initial: np.ndarray, lookback: int
    ) -> np.ndarray:
        """基于转移矩阵预测概率（融合历史频率和转移概率）。"""
        size = len(initial)
        # 使用初始概率作为先验，转移矩阵作为更新
        prior = initial.copy()

        # 融合：70% 历史频率 + 30% 转移概率
        trans_prob = np.mean(transition, axis=0)
        result = 0.7 * prior + 0.3 * trans_prob

        s = result.sum()
        if s > 0:
            result /= s
        else:
            result = np.ones(size) / size

        return result
