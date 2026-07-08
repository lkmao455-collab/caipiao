"""福彩3D随机策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _sample_with_dedup


class FC3DRandomStrategy(GenerationStrategy):
    """3D完全随机：每位独立0-9。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_3d",
            name="完全随机",
            description="在福彩3D的百、十、个位上分别独立随机生成0-9数字。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
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
            }
        }

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        rng = _make_rng(options, [], None, self.metadata.id)
        dedup = bool(options.get("dedup", True))
        basis = "完全随机策略：百、十、个位分别独立随机生成0-9数字。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        results = _sample_with_dedup(
            lambda: [rng.randint(0, 9) for _ in range(3)],
            count, dedup,
        )
        tickets: List[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
