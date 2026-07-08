"""高级策略基类 - 支持多彩种."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.analyzer import DrawAnalyzer
from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ, FC3D
from ...strategy import GenerationStrategy, StrategyMetadata
from ...ticket import Ticket


def _to_draw_records(history: list) -> List[DrawRecord]:
    """将历史记录统一转为 DrawRecord 列表。"""
    records = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(DrawRecord(
                issue="",
                draw_date=r.generated_at,
                profile=r.profile.key,
                groups=r.groups,
            ))
    return records


class _AdvancedBase(GenerationStrategy):
    """高级策略基类，支持双色球和福彩3D。"""

    _id_base: str = ""
    _name_base: str = ""
    _description: str = ""
    is_ml: bool = False

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        self._profile = profile or SSQ

    @property
    def profile(self) -> LotteryProfile:
        return self._profile

    @profile.setter
    def profile(self, value: LotteryProfile) -> None:
        self._profile = value

    @property
    def metadata(self) -> StrategyMetadata:
        suffix = ""
        if self._profile.key != "ssq":
            suffix = f" ({self._profile.name})"
        return StrategyMetadata(
            id=f"{self._id_base}_{self._profile.key}" if self._profile.key != "ssq" else self._id_base,
            name=f"{self._name_base}{suffix}",
            description=self._description,
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 30:
            raise ValueError(f"{self.metadata.name} 策略需要至少 30 期历史数据")

    def _get_history(self, options: Dict[str, Any]) -> List[DrawRecord]:
        """从 options 中提取并处理历史记录。"""
        history = options.get("history", [])
        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(history) > history_count:
            history = history[-history_count:]
        return _to_draw_records(history)

    def _is_ssq(self) -> bool:
        return self._profile.key == "ssq"

    def _is_3d(self) -> bool:
        return self._profile.key == "3d"

    def _group_key(self) -> str:
        """返回主号码组的 key。"""
        return self._profile.primary_group.key

    def _group_size(self) -> int:
        """返回号码池大小。"""
        g = self._profile.primary_group
        return g.hi - g.lo + 1

    def _pick_count(self) -> int:
        """返回需要选取的号码个数。"""
        return self._profile.primary_group.count

    def _make_ticket_from_numbers(
        self, numbers: List[int], basis: str, blue: int | None = None, **kwargs
    ) -> Ticket:
        """根据彩种 profile 构建 Ticket。"""
        g = self._profile.primary_group
        if g.positional:
            groups = {g.key: numbers[:g.count]}
        else:
            groups = {g.key: sorted(numbers[:g.count])}

        # SSQ 需要蓝球
        if self._is_ssq() and blue is not None:
            groups["blue"] = [blue]

        return Ticket(
            profile=self._profile,
            groups=groups,
            strategy_name=self.metadata.name,
            basis=basis,
            **kwargs,
        )

    def _weighted_sample(
        self, size: int, pick: int, weights: np.ndarray, rng: np.random.RandomState
    ) -> List[int]:
        """加权采样（不重复）。"""
        lo = self._profile.primary_group.lo
        available = list(range(lo, lo + size))
        w = weights.copy()
        selected = []
        for _ in range(min(pick, len(available))):
            w = w / w.sum()
            idx = rng.choice(len(available), p=w)
            selected.append(available[idx])
            available.pop(idx)
            w = np.delete(w, idx)
        return selected

    @abstractmethod
    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        """计算号码出现概率。

        Returns:
            proba: 概率数组
            basis: 生成依据说明
        """
        ...

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = self._get_history(options)
        seed = options.get("seed")

        proba, basis = self._compute_probabilities(records, options)
        if self._is_ssq():
            basis += " 蓝球未单独建模，使用均匀随机采样。"

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        rng = np.random.RandomState(seed) if seed is not None else np.random.RandomState()
        group = self._profile.primary_group
        pick = group.count
        size = group.hi - group.lo + 1

        for i in range(count):
            if group.positional:
                # 按位生成
                numbers = []
                for pos in range(group.count):
                    pos_proba = proba[pos] if proba.ndim == 2 else proba
                    pos_proba = pos_proba + 0.05
                    pos_proba = pos_proba / pos_proba.sum()
                    num = int(rng.choice(range(group.lo, group.hi + 1), p=pos_proba))
                    numbers.append(num)
            else:
                # 组合生成
                weights = proba + 0.05
                weights = weights / weights.sum()
                numbers = self._weighted_sample(size, pick, weights, rng)

            # SSQ 需要单独生成蓝球
            blue = None
            if self._is_ssq():
                blue_group = self._profile.group("blue")
                blue_proba = np.ones(blue_group.hi - blue_group.lo + 1) / (blue_group.hi - blue_group.lo + 1)
                blue = int(rng.choice(range(blue_group.lo, blue_group.hi + 1), p=blue_proba))

            tickets.append(self._make_ticket_from_numbers(numbers, basis, blue=blue))

        return tickets
