"""福彩3D占位策略基类：提供合法随机投注单生成。"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import get_profile
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket


class BaseFC3DStrategy(GenerationStrategy):
    """福彩3D占位策略基类，各具体策略只需覆盖 metadata。"""

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        profile = get_profile("3d")
        tickets: List[Ticket] = []
        for _ in range(count):
            pos = [rng.randint(0, 9) for _ in range(3)]
            tickets.append(
                Ticket(
                    profile=profile,
                    groups={"pos": pos},
                    strategy_name=self.metadata.name,
                    basis=f"{self.metadata.name} 占位实现：随机生成合法3D号码。",
                )
            )
        return tickets
