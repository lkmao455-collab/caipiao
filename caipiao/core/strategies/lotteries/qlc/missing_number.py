"""七乐彩遗漏号追踪策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class QLCMissingNumberStrategy(GenerationStrategy):
    """优先选择高遗漏号码."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_qlc",
            name="遗漏号追踪",
            description="选择近期遗漏值较高的号码，适合追冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        primary = PROFILE.primary_group
        pick = primary.effective_pick_max
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 50, "min": 10, "max": 10000},
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": max(pick, min(12, primary.size // 2)),
                "min": pick,
                "max": primary.size,
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
        lookback = int(options.get("lookback", 50))
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)
        default_pool_size = max(pick, min(12, primary.size // 2))
        pool_size = int(options.get("pool_size", default_pool_size))
        rng = make_rng(options)

        analyzer = DrawAnalyzer(records, PROFILE)
        missing = analyzer.missing(primary.key, lookback)
        pool = [n for n, _ in missing[:pool_size]]

        basis = f"遗漏号追踪策略：基于最近 {lookback} 期，从高遗漏值候选池抽取 {pick} 个号码。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.choice(pool) for _ in range(primary.count)]
            else:
                chosen = min(pick, len(pool))
                groups[primary.key] = sorted(rng.sample(pool, chosen))
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
