"""福彩3D遗漏号追踪策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _records_from_options, _sample_with_dedup
from .stability import sample_weighted, softmax_scores, stable_missing


class FC3DMissingNumberStrategy(GenerationStrategy):
    """3D遗漏号追踪：按位优先选择高遗漏号码。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_3d",
            name="遗漏号追踪",
            description="选择近期按位遗漏值较高的号码，适合追冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 50, "min": 10, "max": 10000},
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": 5,
                "min": 1,
                "max": 10,
            },
            "temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50, "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中，50=接近随机均匀分布"},
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
        if len(options.get("history", [])) < 20:
            raise ValueError("遗漏号追踪策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 50))
        pool_size = int(options.get("pool_size", 5))
        temperature = int(options.get("temperature", 10)) / 10.0
        dedup = bool(options.get("dedup", True))
        rng = _make_rng(options, records, lookback, self.metadata.id)

        missing = stable_missing(records, lookback, cap=lookback)

        basis = f"遗漏号追踪策略：lookback={lookback}，候选池={pool_size}，温度={temperature}。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        pos_probs: List[List[float]] = []
        for pos in range(3):
            ranked = sorted(range(10), key=lambda d: missing[pos][d], reverse=True)
            pool = ranked[:pool_size]
            pool_scores = [missing[pos][d] for d in pool]
            pool_probs = softmax_scores(pool_scores, temperature)
            probs = [0.0] * 10
            for d, p in zip(pool, pool_probs):
                probs[d] = p
            pos_probs.append(probs)
        details: Dict[str, Any] = {"pos_probabilities": pos_probs}

        def sample_one() -> List[int]:
            return [sample_weighted(rng, list(range(10)), pos_probs[pos]) for pos in range(3)]

        results = _sample_with_dedup(sample_one, count, dedup)
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
