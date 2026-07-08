"""快乐8冷热号分析策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket


class KL8HotColdStrategy(GenerationStrategy):
    """基于历史频率选择热号或冷号."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold_kl8",
            name="冷热号分析",
            description="基于历史记录统计出现频率，优先选择热号或冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "mode": {
                "type": "choice",
                "label": "模式",
                "choices": ["hot", "cold", "mixed"],
                "default": "mixed",
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
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
        mode = options.get("mode", "mixed")
        if mode not in ("hot", "cold", "mixed"):
            raise ValueError("mode 必须是 hot、cold 或 mixed")
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        mode = options.get("mode", "mixed")
        records = records_from_options(options)
        rng = make_rng(options)
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)

        analyzer = DrawAnalyzer(records, PROFILE)
        freq = analyzer.frequency(primary.key)
        all_vals = primary.values[:]
        if not freq:
            ranked = all_vals[:]
            rng.shuffle(ranked)
        else:
            ranked = sorted(all_vals, key=lambda n: freq.get(n, 0), reverse=True)

        half = pick // 2
        if mode == "hot":
            pool = ranked[: max(pick, len(ranked) // 2)]
        elif mode == "cold":
            pool = ranked[-max(pick, len(ranked) // 2):]
        else:
            pool = ranked[:half] + ranked[-(pick - half):]

        basis = f"冷热号分析策略：{mode} 模式，基于历史频率选取候选池，投注 {pick} 个号码。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
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
                pick = rng.randint(g.effective_pick_min, g.effective_pick_max) if g.variable_pick else g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
