"""排列5智能冷热号策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import numpy as np

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class PL5SmartHotColdStrategy(GenerationStrategy):
    """综合热号频率与冷号遗漏值加权生成."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_pl5",
            name="智能冷热号",
            description="结合历史数据中的热号频率与冷号遗漏值加权生成号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同，112和121视为相同。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema)
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))
        rng = make_rng(options)
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)

        analyzer = DrawAnalyzer(records, PROFILE)
        freq = analyzer.frequency(primary.key)
        max_freq = max(freq.values()) if freq else 1
        missing = dict(analyzer.missing(primary.key, lookback))
        max_missing = max(missing.values()) if missing else 1

        scores: Dict[int, float] = {n: 0.0 for n in primary.values}
        for n in primary.values:
            f = freq.get(n, 0)
            scores[n] += hot_weight * (f / max_freq)
        for n in primary.values:
            m = missing.get(n, 0)
            scores[n] += cold_weight * (m / max_missing)
        min_score = min(scores.values())
        weights = [max(0.1, scores[n] - min_score + 1.0) for n in primary.values]

        basis = (
            f"智能冷热号策略：综合最近 {lookback} 期热号频率（权重 {hot_weight}）"
            f"与冷号遗漏值（权重 {cold_weight}）加权评分后随机抽取 {pick} 个号码。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        dedup = bool(options.get("dedup", True))

        seen: set = set()
        tickets: List[Ticket] = []
        max_attempts = count * 50 if dedup else 1
        for _ in range(count):
            for attempt in range(max_attempts):
                groups: Dict[str, List[int]] = {}
                if primary.positional:
                    groups[primary.key] = [rng.choices(primary.values, weights=weights, k=1)[0] for _ in range(primary.count)]
                else:
                    selected = sorted(rng.choices(primary.values, weights=weights, k=pick))
                    while len(set(selected)) < pick and not primary.allow_repeat:
                        selected = sorted(rng.choices(primary.values, weights=weights, k=pick))
                    groups[primary.key] = selected
                self._fill_random_other(groups, rng)
                if primary.positional:
                    dedup_key = tuple(sorted(groups[primary.key]))
                else:
                    dedup_key = tuple(groups[primary.key])
                if not dedup or dedup_key not in seen:
                    if dedup:
                        seen.add(dedup_key)
                    break
            else:
                groups = {}
                if primary.positional:
                    groups[primary.key] = [rng.randint(primary.lo, primary.hi) for _ in range(primary.count)]
                else:
                    groups[primary.key] = sorted(rng.sample(primary.values, pick))
                self._fill_random_other(groups, rng)
            tickets.append(_make_ticket(groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
