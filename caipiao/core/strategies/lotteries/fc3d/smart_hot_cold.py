"""福彩3D智能冷热号策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _records_from_options
from .stability import sample_weighted, stable_frequency, stable_missing, stable_scores


class FC3DSmartHotColdStrategy(GenerationStrategy):
    """3D智能冷热号：综合按位频率与遗漏值。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_3d",
            name="智能冷热号",
            description="结合历史数据中的按位热号频率与冷号遗漏值加权生成。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50, "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中（强烈偏向热/冷号），50=接近随机均匀分布"},
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码，112和121视为相同号码。",
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
        if len(options.get("history", [])) < 20:
            raise ValueError("智能冷热号策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        temperature = int(options.get("temperature", 10)) / 10.0
        rng = _make_rng(options, records, lookback, self.metadata.id)

        freq = stable_frequency(records, lookback)
        missing = stable_missing(records, lookback, cap=lookback)

        basis = (
            f"智能冷热号策略：lookback={lookback}，热权重={hot_weight}，"
            f"冷权重={cold_weight}，温度={temperature}。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        pos_probs: List[List[float]] = []
        for pos in range(3):
            pos_probs.append(stable_scores(
                freq[pos], missing[pos], hot_weight, cold_weight, temperature
            ))
        details: Dict[str, Any] = {"pos_probabilities": pos_probs}

        dedup = bool(options.get("dedup", True))

        seen: set = set()
        tickets: List[Ticket] = []
        max_attempts = count * 50 if dedup else 1
        for _ in range(count):
            for attempt in range(max_attempts):
                result = []
                for pos in range(3):
                    result.append(sample_weighted(rng, list(range(10)), pos_probs[pos]))
                key = tuple(sorted(result))
                if not dedup or key not in seen:
                    if dedup:
                        seen.add(key)
                    break
            else:
                for _ in range(200):
                    result = [
                        sample_weighted(rng, list(range(10)), pos_probs[pos])
                        for pos in range(3)
                    ]
                    if not dedup or tuple(sorted(result)) not in seen:
                        if dedup:
                            seen.add(tuple(sorted(result)))
                        break
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE, groups={"pos": result},
                    strategy_name=self.metadata.name, basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
