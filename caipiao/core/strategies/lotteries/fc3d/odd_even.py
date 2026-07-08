"""福彩3D奇偶均衡策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _sample_with_dedup


class FC3DOddEvenStrategy(GenerationStrategy):
    """3D奇偶均衡：控制整体奇数个数或按位奇偶。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even_3d",
            name="奇偶均衡",
            description="控制福彩3D号码中奇数和偶数的比例。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": 1,
                "min": 0,
                "max": 3,
            },
            "positional": {
                "type": "list_int",
                "label": "按位奇偶（可选）",
                "default": [],
                "min": 0,
                "max": 1,
                "tooltip": "长度为3的列表，1表示奇数，0表示偶数，空则使用整体奇数个数。",
            },
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
        positional = options.get("positional", [])
        if positional and len(positional) != 3:
            raise ValueError("按位奇偶必须提供3个值")
        if positional and any(p not in (0, 1) for p in positional):
            raise ValueError("按位奇偶值必须是0或1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        rng = _make_rng(options, [], None, self.metadata.id)
        positional = options.get("positional", [])
        odd_count = int(options.get("odd_count", 1))
        dedup = bool(options.get("dedup", True))

        odd_pool = [1, 3, 5, 7, 9]
        even_pool = [0, 2, 4, 6, 8]

        if positional:
            basis = f"奇偶均衡策略：按位控制奇偶为 {positional}。"
        else:
            basis = f"奇偶均衡策略：整体包含 {odd_count} 个奇数、{3 - odd_count} 个偶数。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        def sample_one() -> List[int]:
            if positional:
                return [rng.choice(odd_pool if p == 1 else even_pool) for p in positional]
            else:
                result = [rng.choice(odd_pool) for _ in range(odd_count)] + [rng.choice(even_pool) for _ in range(3 - odd_count)]
                rng.shuffle(result)
                return result

        results = _sample_with_dedup(sample_one, count, dedup)
        tickets: List[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
