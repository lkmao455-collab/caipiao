"""福彩3D专属生成策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ..profile import get_profile
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket
from ...data.models import DrawRecord


FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    history = options.get("history", []) or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records


def _make_rng(options: Dict[str, Any]) -> random.Random:
    seed = options.get("seed")
    return random.Random(seed) if seed is not None else random.Random()


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
        rng = _make_rng(options)
        basis = "完全随机策略：百、十、个位分别独立随机生成0-9数字。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"
        tickets: List[Ticket] = []
        for _ in range(count):
            groups = {"pos": [rng.randint(0, 9) for _ in range(3)]}
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups=groups, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


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
        rng = _make_rng(options)
        positional = options.get("positional", [])
        odd_count = int(options.get("odd_count", 1))

        odd_pool = [1, 3, 5, 7, 9]
        even_pool = [0, 2, 4, 6, 8]

        if positional:
            basis = f"奇偶均衡策略：按位控制奇偶为 {positional}。"
        else:
            basis = f"奇偶均衡策略：整体包含 {odd_count} 个奇数、{3 - odd_count} 个偶数。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            if positional:
                result = [
                    rng.choice(odd_pool if p == 1 else even_pool)
                    for p in positional
                ]
            else:
                result = rng.sample(odd_pool, odd_count) + rng.sample(even_pool, 3 - odd_count)
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


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
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        for key in ("include_pos", "exclude_pos"):
            value = options.get(key, [[], [], []])
            if len(value) != 3:
                raise ValueError(f"{key} 必须提供3个位置的列表")
            for idx, nums in enumerate(value):
                if not all(0 <= n <= 9 for n in nums):
                    raise ValueError(f"{key} 第{idx}位包含越界号码")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], []])

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

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for idx in range(3):
                include = set(include_pos[idx])
                exclude = set(exclude_pos[idx])
                if include:
                    chosen = rng.choice(list(include))
                else:
                    pool = [n for n in range(10) if n not in exclude]
                    chosen = rng.choice(pool)
                result.append(chosen)
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
