"""双色球占位策略基类：提供合法随机投注单生成。"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import get_profile
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket


class BaseSSQStrategy(GenerationStrategy):
    """双色球占位策略基类，各具体策略只需覆盖 metadata。"""

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        profile = get_profile("ssq")
        tickets: List[Ticket] = []
        for _ in range(count):
            red = sorted(rng.sample(range(1, 34), 6))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    profile=profile,
                    groups={"red": red, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=f"{self.metadata.name} 占位实现：随机生成合法双色球号码。",
                )
            )
        return tickets
