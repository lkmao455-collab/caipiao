"""排列3历史均衡策略."""

from __future__ import annotations

import random
from typing import Any

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class PL3BalancedStrategy(GenerationStrategy):
    """使奇偶、大小、和值接近历史平均."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_pl3",
            name="历史均衡",
            description="根据历史数据的奇偶比、大小比和和值分布生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
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

    def validate_options(self, options: dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        rng = make_rng(options)
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)

        analyzer = DrawAnalyzer(records, PROFILE)
        odd_ratio, _ = analyzer.odd_even_ratio(lookback)
        high_ratio, _ = analyzer.high_low_ratio(lookback)
        sum_stats = analyzer.sum_statistics(lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6.0 or 1.0
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])
        target_odd = round(pick * odd_ratio)
        target_high = round(pick * high_ratio)

        freq = analyzer.frequency(primary.key)
        max_freq = max(freq.values()) if freq else 1
        weights = [max(0.1, freq.get(n, 0) / max_freq + 0.2) for n in primary.values]

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"使 {pick} 个号码的奇偶比、大小比、和值接近历史平均。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: list[Ticket] = []
        for _ in range(count):
            best: dict[str, list[int]] | None = None
            best_score = float("inf")
            for _ in range(max_attempts):
                if primary.allow_repeat:
                    candidate_primary = sorted(rng.choices(primary.values, weights=weights, k=pick))
                else:
                    candidate_primary = sorted(rng.sample(primary.values, pick))
                odd_count = sum(1 for n in candidate_primary if n % 2 == 1)
                high_count = sum(1 for n in candidate_primary if n >= primary.high_low_border)
                total = sum(candidate_primary)
                score = (
                    abs(odd_count - target_odd)
                    + abs(high_count - target_high)
                    + (0 if sum_min <= total <= sum_max else abs(total - avg_sum) / 10.0)
                )
                if score < best_score:
                    best_score = score
                    groups: dict[str, list[int]] = {primary.key: candidate_primary}
                    self._fill_random_other(groups, rng)
                    best = groups
                if best_score <= 0.5:
                    break
            if best is None:
                if primary.allow_repeat:
                    candidate_primary = sorted(rng.choices(primary.values, k=pick))
                else:
                    candidate_primary = sorted(rng.sample(primary.values, pick))
                groups = {primary.key: candidate_primary}
                self._fill_random_other(groups, rng)
                best = groups
            tickets.append(_make_ticket(best, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: dict[str, list[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = rng.randint(g.effective_pick_min, g.effective_pick_max) if g.variable_pick else g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
