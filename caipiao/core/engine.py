"""生成引擎."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from .strategy import GenerationStrategy
from .ticket import Ticket

logger = logging.getLogger(__name__)


class GenerationEngine:
    """号码生成引擎.

    负责管理所有可用策略，并根据选中的策略生成投注单。
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, GenerationStrategy] = {}

    def register(self, strategy: GenerationStrategy) -> None:
        """注册一个生成策略."""
        self._strategies[strategy.metadata.id] = strategy

    def unregister(self, strategy_id: str) -> None:
        """注销指定策略."""
        self._strategies.pop(strategy_id, None)

    def get(self, strategy_id: str) -> Optional[GenerationStrategy]:
        """获取指定策略."""
        return self._strategies.get(strategy_id)

    def list_strategies(self) -> List[GenerationStrategy]:
        """列出所有已注册策略."""
        return list(self._strategies.values())

    def generate(
        self,
        strategy_id: str,
        count: int = 1,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[Ticket]:
        """使用指定策略生成投注单."""
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise ValueError(f"未找到策略: {strategy_id}")
        options = options or {}
        strategy.validate_options(options)
        return strategy.generate(count=count, options=options)


# --------------------------------------------------------------------------- #
# 双色球最后一层过滤：与历史开奖记录比对红球重合数和蓝球
# --------------------------------------------------------------------------- #

def filter_ssq_by_history(
    tickets: List[Ticket],
    draw_records: List[Any],
    compare_periods: int = 7,
    max_red_overlap: int = 3,
    block_blue_match: bool = False,
    blue_compare_periods: int = 0,
) -> List[Ticket]:
    """对双色球号码做最后一层过滤：与最近 N 期开奖记录比对。

    规则：
    - 红球：计算生成号码与历史开奖号码的交集个数，超过 max_red_overlap 则淘汰。
    - 蓝球：若 block_blue_match 为 True，蓝球在 blue_compare_periods 期内与历史相同则淘汰。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 7。
        max_red_overlap: 允许的红球最大重合数，默认 3。
        block_blue_match: 是否禁止蓝球与历史相同，默认 False。
        blue_compare_periods: 蓝球禁止重复的对比期数，0 表示使用 compare_periods。

    Returns:
        过滤后的号码列表。
    """
    if not tickets or not draw_records:
        return tickets

    # 红球比较期数
    if compare_periods <= 0:
        return tickets

    recent = draw_records[-compare_periods:] if len(draw_records) >= compare_periods else draw_records
    recent_data: list[tuple[set[int], int]] = []
    for r in recent:
        reds = set(r.groups.get("red", []))
        blues = r.groups.get("blue", [])
        blue = blues[0] if blues else None
        if reds and blue is not None:
            recent_data.append((reds, blue))

    # 蓝球比较期数
    blue_recent: list[int] = []
    if block_blue_match:
        if blue_compare_periods > 0:
            blue_data = draw_records[-blue_compare_periods:] if len(draw_records) >= blue_compare_periods else draw_records
        else:
            blue_data = []  # blue_compare_periods=0 表示不过滤蓝球
        for r in blue_data:
            blues = r.groups.get("blue", [])
            if blues:
                blue_recent.append(blues[0])

    if not recent_data and not blue_recent:
        return tickets

    filtered: List[Ticket] = []
    discarded = 0

    for ticket in tickets:
        ticket_reds = set(ticket.groups.get("red", []))
        ticket_blues = ticket.groups.get("blue", [])
        ticket_blue = ticket_blues[0] if ticket_blues else None

        too_many = False
        # 红球检查
        for hist_reds, hist_blue in recent_data:
            red_overlap = len(ticket_reds & hist_reds)
            if red_overlap > max_red_overlap:
                too_many = True
                break
        # 蓝球检查
        if not too_many and block_blue_match and ticket_blue is not None:
            if ticket_blue in blue_recent:
                too_many = True

        if not too_many:
            filtered.append(ticket)
        else:
            discarded += 1

    if discarded > 0:
        logger.info(
            "SSQ过滤：共 %d 个候选，淘汰 %d 个（红球重合上限 %d，蓝球%s，比较 %d 期），"
            "剩余 %d 个",
            len(tickets), discarded, max_red_overlap,
            "禁止相同" if block_blue_match else "不限",
            compare_periods, len(filtered),
        )

    return filtered
