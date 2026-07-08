"""双色球高级策略公共基类：固定彩种为 SSQ，提供基于概率的生成流程。"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ......data.models import DrawRecord
from .....profile import SSQ
from .....ticket import Ticket
from ...common.base import AdvancedStrategy


class SSQAdvancedStrategy(AdvancedStrategy):
    """双色球高级策略基类。"""

    def __init__(self) -> None:
        self._profile = SSQ

    @abstractmethod
    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        """计算红球出现概率并返回生成依据说明。"""
        ...

    def _weighted_sample(
        self, size: int, pick: int, weights: np.ndarray, rng: np.random.RandomState
    ) -> List[int]:
        """加权采样（不重复）。"""
        available = list(range(1, size + 1))
        w = weights.copy()
        selected = []
        for _ in range(min(pick, len(available))):
            w = w / w.sum()
            idx = rng.choice(len(available), p=w)
            selected.append(available[idx])
            available.pop(idx)
            w = np.delete(w, idx)
        return selected

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = self._get_history(options)
        seed = options.get("seed")

        proba, basis = self._compute_probabilities(records, options)
        basis += " 蓝球未单独建模，使用均匀随机采样。"

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        rng = np.random.RandomState(seed) if seed is not None else np.random.RandomState()
        red_group = self._profile.group("red")
        blue_group = self._profile.group("blue")
        pick = red_group.count
        size = red_group.hi - red_group.lo + 1

        for _ in range(count):
            weights = proba + 0.05
            weights = weights / weights.sum()
            numbers = sorted(self._weighted_sample(size, pick, weights, rng))
            blue = int(rng.choice(range(blue_group.lo, blue_group.hi + 1)))
            tickets.append(
                Ticket(
                    profile=self._profile,
                    groups={"red": numbers, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
