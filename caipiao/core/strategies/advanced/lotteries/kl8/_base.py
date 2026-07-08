"""快乐8高级策略占位基类。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .....profile import KL8
from .....ticket import Ticket
from ...common.base import AdvancedStrategy, UnsupportedLotteryError


class KL8AdvancedStrategy(AdvancedStrategy):
    """快乐8高级策略占位基类。"""

    _id = ""
    _name = ""
    _description = ""
    is_ml = False
    _placeholder = True

    def __init__(self) -> None:
        self._profile = KL8

    def validate_options(self, options: Dict[str, Any]) -> None:
        """占位策略不需要历史数据校验。"""

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        raise UnsupportedLotteryError(
            f"{self.metadata.name} 暂不支持 快乐8 彩种"
        )
