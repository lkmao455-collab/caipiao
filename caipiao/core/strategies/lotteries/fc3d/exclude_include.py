"""福彩3D排除/必含策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE, _make_rng, _sample_with_dedup


class FC3DExcludeIncludeStrategy(GenerationStrategy):
    """3D排除/必含：支持按位必含/排除。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include_3d",
            name="排除/必含",
            description="排除不想要的号码，或强制包含某些幸运号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "include_pos": {
                "type": "list_int_list",
                "label": "必含 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组必含数字，空列表表示不约束。",
            },
            "exclude_pos": {
                "type": "list_int_list",
                "label": "排除 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组排除数字，空列表表示不约束。",
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
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], []])
        for key, value in (("include_pos", include_pos), ("exclude_pos", exclude_pos)):
            if len(value) != 3:
                raise ValueError(f"{key} 必须提供3个位置的列表")
            for idx, nums in enumerate(value):
                if not all(0 <= n <= 9 for n in nums):
                    raise ValueError(f"{key} 第{idx}位包含越界号码")
        for idx in range(3):
            if not include_pos[idx] and set(exclude_pos[idx]) == set(range(10)):
                raise ValueError(f"第{idx + 1}位排除后没有可用号码")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        rng = _make_rng(options)
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], []])
        dedup = bool(options.get("dedup", True))

        basis_parts = ["排除/必含策略："]
        for idx in range(3):
            inc = set(include_pos[idx])
            exc = set(exclude_pos[idx])
            if inc:
                basis_parts.append(f"第{idx+1}位必含 {sorted(inc)}；")
            if exc:
                basis_parts.append(f"第{idx+1}位排除 {sorted(exc)}；")
        basis = " ".join(basis_parts) + "其余位在可用范围内随机。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        def sample_one() -> List[int]:
            result = []
            for idx in range(3):
                include = set(include_pos[idx])
                exclude = set(exclude_pos[idx])
                if include:
                    chosen = rng.choice(list(include))
                else:
                    available = set(range(10)) - exclude
                    chosen = rng.choice(list(available))
                result.append(chosen)
            return result

        results = _sample_with_dedup(sample_one, count, dedup)
        tickets: List[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
