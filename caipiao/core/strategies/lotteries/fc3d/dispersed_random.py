"""福彩3D分散随机策略.

完全随机生成候选号码，并通过局部搜索使输出在三维数字空间中尽量分散。
本模块独立实现，不依赖历史数据，也不复用其他策略的生成逻辑。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE


class FC3DDispersedRandomStrategy(GenerationStrategy):
    """3D分散随机：不依赖历史，通过局部搜索生成空间分散的随机号码."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="dispersed_random_3d",
            name="分散随机",
            description="完全随机生成候选号码，并通过局部搜索使输出在三维数字空间中尽量分散。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "candidate_multiplier": {
                "type": "int",
                "label": "候选池倍数",
                "default": 50,
                "min": 10,
                "max": 200,
                "tooltip": "候选池大小 = 生成数量 × 倍数。倍数越大，局部搜索空间越大，分散性越好。",
            },
            "max_iterations": {
                "type": "int",
                "label": "最大迭代次数",
                "default": 100,
                "min": 10,
                "max": 1000,
                "tooltip": "局部搜索最大轮数。",
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
        # 本策略不需要历史数据
        pass

    @staticmethod
    def _euclidean_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    @staticmethod
    def _min_pairwise_distance(selected: List[Tuple[int, int, int]]) -> float:
        n = len(selected)
        if n < 2:
            return float("inf")
        min_dist = float("inf")
        for i in range(n):
            for j in range(i + 1, n):
                d = FC3DDispersedRandomStrategy._euclidean_distance(
                    selected[i], selected[j]
                )
                if d < min_dist:
                    min_dist = d
        return min_dist

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)

        candidate_multiplier = int(options.get("candidate_multiplier", 50))
        max_iterations = int(options.get("max_iterations", 100))
        dedup = bool(options.get("dedup", True))
        seed = options.get("seed")

        rng = random.Random(seed) if seed is not None else random.Random()

        # 1. 生成候选池
        pool_size = max(count * candidate_multiplier, count * 2)
        candidates: List[Tuple[int, int, int]] = [
            (rng.randint(0, 9), rng.randint(0, 9), rng.randint(0, 9))
            for _ in range(pool_size)
        ]

        # 2. 去重（按组选 sorted tuple）
        if dedup:
            seen: Set[Tuple[int, int, int]] = set()
            unique: List[Tuple[int, int, int]] = []
            for nums in candidates:
                key = tuple(sorted(nums))
                if key not in seen:
                    seen.add(key)
                    unique.append(nums)
            candidates = unique
            if len(candidates) < count:
                raise ValueError(
                    f"去重后候选池不足（{len(candidates)} < {count}），"
                    f"请降低生成数量、增大 candidate_multiplier 或关闭去重。"
                )
            if count > 220:
                raise ValueError(
                    "去重模式下最多生成 220 组（3D组选组合上限）。"
                )

        # 3. Greedy Farthest Point 初始化
        selected: List[Tuple[int, int, int]] = [candidates[0]]
        remaining = candidates[1:]

        while len(selected) < count and remaining:
            best_idx = 0
            best_min_dist = -1.0
            for idx, cand in enumerate(remaining):
                min_dist = min(
                    self._euclidean_distance(cand, s) for s in selected
                )
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = idx
            selected.append(remaining.pop(best_idx))

        # 4. 局部搜索：单次交换优化最小 pairwise 距离
        current_min = self._min_pairwise_distance(selected)
        for _ in range(max_iterations):
            improved = False
            for sel_idx in range(len(selected)):
                for cand_idx, cand in enumerate(remaining):
                    original = selected[sel_idx]
                    selected[sel_idx] = cand
                    new_min = self._min_pairwise_distance(selected)
                    if new_min > current_min:
                        remaining[cand_idx] = original
                        current_min = new_min
                        improved = True
                        break
                    else:
                        selected[sel_idx] = original
                if improved:
                    break
            if not improved:
                break

        # 5. 构建 basis 与 Ticket
        basis = (
            f"分散随机策略：生成 {count} 注，候选池倍数={candidate_multiplier}，"
            f"最大迭代={max_iterations}，去重={dedup}。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"
        basis += "基于局部搜索使号码在三维数字空间中尽量分散。"

        tickets: List[Ticket] = []
        for nums in selected:
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": list(nums)},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
