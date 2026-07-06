"""周期性分析策略 - 支持双色球和福彩3D."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ....data.models import DrawRecord
from ...profile import LotteryProfile, SSQ
from .base import _AdvancedBase

logger = logging.getLogger(__name__)


class PeriodicAnalysisStrategy(_AdvancedBase):
    """基于周期性分析的号码生成策略."""

    _id_base = "periodic"
    _name_base = "周期性分析"
    _description = "分析号码出现的周/月/季度周期性规律，多周期融合推荐。"

    def __init__(self, profile: LotteryProfile | None = None) -> None:
        super().__init__(profile)

    def get_config_schema(self) -> Dict[str, Any]:
        schema = super().get_config_schema()
        schema.update({
            "week_weight": {
                "type": "int",
                "label": "周周期权重 (0-100)",
                "default": 40,
                "min": 0,
                "max": 100,
            },
            "month_weight": {
                "type": "int",
                "label": "月周期权重 (0-100)",
                "default": 35,
                "min": 0,
                "max": 100,
            },
            "quarter_weight": {
                "type": "int",
                "label": "季度周期权重 (0-100)",
                "default": 25,
                "min": 0,
                "max": 100,
            },
        })
        return schema

    def _compute_probabilities(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, str]:
        week_w = int(options.get("week_weight", 40))
        month_w = int(options.get("month_weight", 35))
        quarter_w = int(options.get("quarter_weight", 25))

        group = self._profile.primary_group
        size = group.hi - group.lo + 1
        pick = group.count

        if records:
            current_date = records[-1].draw_date + timedelta(days=1)
        else:
            from datetime import datetime
            current_date = datetime.now()

        total_w = week_w + month_w + quarter_w
        if total_w == 0:
            total_w = 1

        week_proba = self._cycle_frequency(records, group.key, size, "weekday", current_date.weekday(), group)
        month_proba = self._cycle_frequency(records, group.key, size, "month", current_date.month, group)
        quarter = (current_date.month - 1) // 3
        quarter_proba = self._cycle_frequency(records, group.key, size, "quarter", quarter, group)

        proba = (week_w * week_proba + month_w * month_proba + quarter_w * quarter_proba) / total_w
        s = proba.sum()
        if s > 0:
            proba /= s
        else:
            proba = np.ones(size) / size

        if group.positional:
            proba = np.tile(proba, (pick, 1))

        basis = f"周期性分析（{self._profile.name}）：周权重 {week_w}，月权重 {month_w}，季度权重 {quarter_w}。"
        return proba, basis

    def _cycle_frequency(self, records, group_key, size, cycle_type, current_value, group):
        freq = np.zeros(size)
        count = 0
        for r in records:
            date = r.draw_date
            if cycle_type == "weekday":
                match = date.weekday() == current_value
            elif cycle_type == "month":
                match = date.month == current_value
            elif cycle_type == "quarter":
                match = (date.month - 1) // 3 == current_value
            else:
                match = False
            if match:
                count += 1
                for n in r.groups.get(group_key, []):
                    if group.lo <= n <= group.hi:
                        freq[n - group.lo] += 1
        if count > 0:
            freq /= count
        s = freq.sum()
        if s > 0:
            freq /= s
        else:
            freq = np.ones(size) / size
        return freq
