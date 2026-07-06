"""统一统计策略（冷热号 / 遗漏号 / 智能加权）.

合并原来三个独立的统计策略文件，通过 mode 参数切换分析模式。
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

from ...data.analyzer import DrawAnalyzer
from ...data.models import DrawRecord
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


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


class StatsStrategy(GenerationStrategy):
    """统一统计策略，通过 mode 切换：hot / cold / mixed / smart / missing。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="stats",
            name="统计分析",
            description="基于历史频率和遗漏值的统计分析，支持冷热号、遗漏号、智能加权等多种模式。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "label": "分析模式",
                "choices": ["hot", "cold", "mixed", "smart", "missing"],
                "default": "smart",
                "tooltip": (
                    "hot=热号优先；cold=冷号优先；mixed=冷热混合；"
                    "smart=频率+遗漏值加权评分；missing=高遗漏值优先。"
                ),
            },
            "hot_weight": {
                "type": "int",
                "label": "热号权重 (smart模式)",
                "default": 60,
                "min": 0,
                "max": 100,
                "tooltip": "smart模式下频率因素的权重，0-100。",
            },
            "cold_weight": {
                "type": "int",
                "label": "冷号权重 (smart模式)",
                "default": 40,
                "min": 0,
                "max": 100,
                "tooltip": "smart模式下遗漏值因素的权重，0-100。",
            },
            "lookback": {
                "type": "int",
                "label": "回看期数",
                "default": 100,
                "min": 20,
                "max": 5000,
                "tooltip": "统计分析时回看的历史期数。",
            },
            "pool_size": {
                "type": "int",
                "label": "候选池大小 (missing模式)",
                "default": 12,
                "min": 6,
                "max": 20,
                "tooltip": "missing模式下从高遗漏号码中选取的候选池大小。",
            },
            "history": {
                "type": "history",
                "label": "历史记录",
                "default": [],
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        mode = options.get("mode", "smart")
        if mode not in ("hot", "cold", "mixed", "smart", "missing"):
            raise ValueError("mode 必须是 hot/cold/mixed/smart/missing")
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError("该策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        mode = options.get("mode", "smart")
        history = options.get("history", []) or []
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        records = _to_draw_records(history)
        analyzer = DrawAnalyzer(records)

        if mode in ("hot", "cold", "mixed"):
            reds_pool, blues_pool, basis = self._freq_mode(analyzer, mode)
        elif mode == "missing":
            reds_pool, blues_pool, basis = self._missing_mode(analyzer, options)
        else:  # smart
            reds_pool, blues_pool, basis = self._smart_mode(analyzer, options)

        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(reds_pool, 6))
            blue = rng.choice(blues_pool)
            tickets.append(
                Ticket(
                    red_balls=reds,
                    blue_ball=blue,
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets

    def _freq_mode(self, analyzer: DrawAnalyzer, mode: str):
        """频率模式：热号/冷号/混合。"""
        freq = analyzer.frequency("red")
        all_reds = list(range(1, 34))
        ranked = sorted(all_reds, key=lambda n: freq.get(n, 0), reverse=True)

        if mode == "hot":
            pool = ranked[:16]
            text = "优先选择近期热号"
        elif mode == "cold":
            pool = ranked[-16:]
            text = "优先选择近期冷号"
        else:
            pool = ranked[:8] + ranked[-8:]
            text = "热号与冷号混合"

        blue_freq = analyzer.frequency("blue")
        blues_pool = sorted(range(1, 17), key=lambda n: blue_freq.get(n, 0), reverse=True)[:8]

        basis = f"统计分析（{text}）：基于历史记录统计频率后选取候选池。"
        return pool, blues_pool, basis

    def _missing_mode(self, analyzer: DrawAnalyzer, options: Dict[str, Any]):
        """遗漏模式：高遗漏值优先。"""
        pool_size = int(options.get("pool_size", 12))
        lookback = int(options.get("lookback", 100))

        freq_red = analyzer.frequency("red")
        missing_raw = analyzer.missing("red")
        missing_red = dict(missing_raw) if isinstance(missing_raw, list) else missing_raw
        all_reds = list(range(1, 34))
        ranked = sorted(all_reds, key=lambda n: missing_red.get(n, 0), reverse=True)
        reds_pool = ranked[:pool_size]

        freq_blue = analyzer.frequency("blue")
        blues_pool = sorted(range(1, 17), key=lambda n: freq_blue.get(n, 0), reverse=True)[:8]

        basis = f"统计分析（遗漏号优先）：回看 {lookback} 期，选取高遗漏值号码候选池。"
        return reds_pool, blues_pool, basis

    def _smart_mode(self, analyzer: DrawAnalyzer, options: Dict[str, Any]):
        """智能模式：频率+遗漏值加权评分。"""
        hot_w = int(options.get("hot_weight", 60))
        cold_w = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))

        freq_red = analyzer.frequency("red")
        missing_raw = analyzer.missing("red")
        missing_red = dict(missing_raw) if isinstance(missing_raw, list) else missing_raw
        max_freq = max(freq_red.values()) if freq_red else 1
        max_miss = max(missing_red.values()) if missing_red else 1

        all_reds = list(range(1, 34))
        scores = {}
        for n in all_reds:
            f_score = freq_red.get(n, 0) / max_freq if max_freq else 0
            m_score = missing_red.get(n, 0) / max_miss if max_miss else 0
            scores[n] = hot_w * f_score + cold_w * m_score

        ranked = sorted(all_reds, key=lambda n: scores[n], reverse=True)
        reds_pool = ranked[:12]

        freq_blue = analyzer.frequency("blue")
        blues_pool = sorted(range(1, 17), key=lambda n: freq_blue.get(n, 0), reverse=True)[:8]

        basis = (
            f"统计分析（智能加权）：回看 {lookback} 期，"
            f"热号权重 {hot_w}，冷号权重 {cold_w}，综合评分选取候选池。"
        )
        return reds_pool, blues_pool, basis
