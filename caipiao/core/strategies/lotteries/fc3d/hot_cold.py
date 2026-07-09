"""福彩3D冷热号分析策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _records_from_options, _weighted_sample_without_replacement
from .stability import sample_weighted, softmax_scores, stable_frequency


class FC3DHotColdStrategy(GenerationStrategy):
    """3D冷热号分析：基于按位历史频率。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold_3d",
            name="冷热号分析",
            description="基于历史记录统计每位数字出现频率，优先选择热号或冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "label": "模式",
                "choices": ["hot", "cold", "mixed"],
                "default": "mixed",
            },
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50, "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中，50=接近随机均匀分布"},
            "history": {"type": "history", "label": "历史记录", "default": []},
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码。",
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
        if not options.get("history"):
            raise ValueError("冷热号分析策略需要历史开奖数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        rng = _make_rng(options, records, lookback, self.metadata.id)
        mode = options.get("mode", "mixed")
        temperature = int(options.get("temperature", 10)) / 10.0
        dedup = bool(options.get("dedup", True))

        freq = stable_frequency(records, lookback)
        basis = f"冷热号分析策略：{mode} 模式，lookback={lookback}，temperature={temperature}。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        pos_probs: List[List[float]] = []
        for pos in range(3):
            pos_freq = freq[pos]
            max_f = max(pos_freq[d] for d in range(10))
            max_f = max(max_f, 1e-10)
            norm = {d: pos_freq[d] / max_f for d in range(10)}
            if mode == "hot":
                scores = {d: norm[d] for d in range(10)}
            elif mode == "cold":
                scores = {d: 1.0 - norm[d] for d in range(10)}
            else:
                scores = {d: max(norm[d], 1.0 - norm[d]) for d in range(10)}
            pos_probs.append(softmax_scores([scores[d] for d in range(10)], temperature))

        details: Dict[str, Any] = {"pos_probabilities": pos_probs}

        if dedup:
            results = _weighted_sample_without_replacement(pos_probs, count, rng)
        else:
            results = [
                [sample_weighted(rng, list(range(10)), pos_probs[pos]) for pos in range(3)]
                for _ in range(count)
            ]
        tickets: List[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE, groups={"pos": result},
                    strategy_name=self.metadata.name, basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
