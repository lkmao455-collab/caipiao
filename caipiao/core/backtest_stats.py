"""回测胜率统计模块.

提供号码组合回测的胜率统计功能，包括：
- 各奖级中奖次数
- 总投入/总回报/收益率
- 号码组合分析
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .prize import calculate_prize
from .ticket import Ticket

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """单期回测结果."""

    issue: str
    draw_date: Any
    ticket: Ticket
    prize_level: str
    prize_amount: int | None
    investment: int = 2  # 默认每注 2 元
    hits: dict[str, int] = field(default_factory=dict)


@dataclass
class BacktestStats:
    """回测统计结果."""

    total_periods: int = 0
    total_tickets: int = 0
    total_investment: int = 0
    total_return: int = 0

    # 各奖级统计
    prize_counts: dict[str, int] = field(default_factory=dict)
    prize_amounts: dict[str, int] = field(default_factory=dict)

    # 号码统计
    number_frequency: dict[int, int] = field(default_factory=dict)
    hot_numbers: list[int] = field(default_factory=list)
    cold_numbers: list[int] = field(default_factory=list)

    # 详细结果
    results: list[BacktestResult] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        """中奖率（至少中一个奖级）."""
        if self.total_tickets == 0:
            return 0.0
        win_count = sum(1 for r in self.results if r.prize_level != "未中奖")
        return win_count / self.total_tickets

    @property
    def roi(self) -> float:
        """投资回报率."""
        if self.total_investment == 0:
            return 0.0
        return (self.total_return - self.total_investment) / self.total_investment

    @property
    def average_return_per_ticket(self) -> float:
        """每注平均回报."""
        if self.total_tickets == 0:
            return 0.0
        return self.total_return / self.total_tickets

    def summary(self) -> dict[str, Any]:
        """返回统计摘要."""
        return {
            "总期数": self.total_periods,
            "总注数": self.total_tickets,
            "总投入": self.total_investment,
            "总回报": self.total_return,
            "收益率": f"{self.roi:.2%}",
            "中奖率": f"{self.win_rate:.2%}",
            "每注平均回报": f"{self.average_return_per_ticket:.2f}",
            "各奖级中奖次数": dict(self.prize_counts),
        }


def analyze_ticket_numbers(tickets: list[Ticket]) -> dict[int, int]:
    """分析号码出现频率."""
    counter: Counter = Counter()
    for ticket in tickets:
        for nums in ticket.groups.values():
            counter.update(nums)
    return dict(counter.most_common())


def find_hot_cold_numbers(
    tickets: list[Ticket],
    recent_count: int = 30,
) -> tuple[list[int], list[int]]:
    """找出热号和冷号.

    Args:
        tickets: 历史票据列表
        recent_count: 近期期数

    Returns:
        (热号列表, 冷号列表)
    """
    if not tickets:
        return [], []

    recent_tickets = tickets[-recent_count:]
    all_numbers: list[int] = []
    for ticket in recent_tickets:
        for nums in ticket.groups.values():
            all_numbers.extend(nums)

    counter = Counter(all_numbers)
    hot = [n for n, _ in counter.most_common(10)]

    all_nums_set = set(all_numbers)
    cold = sorted(all_nums_set, key=lambda n: counter.get(n, 0))[:10]

    return hot, cold


def run_backtest(
    tickets_by_period: dict[str, list[Ticket]],
    draw_records: dict[str, Any],
    profile_key: str = "ssq",
    investment_per_ticket: int = 2,
) -> BacktestStats:
    """运行回测统计.

    Args:
        tickets_by_period: {期号: [Ticket列表]}
        draw_records: {期号: DrawRecord}
        profile_key: 彩种 key
        investment_per_ticket: 每注投入金额

    Returns:
        BacktestStats 统计结果
    """
    stats = BacktestStats()
    all_tickets: list[Ticket] = []

    for issue, tickets in tickets_by_period.items():
        if issue not in draw_records:
            continue

        draw_record = draw_records[issue]
        stats.total_periods += 1

        for ticket in tickets:
            stats.total_tickets += 1
            stats.total_investment += investment_per_ticket
            all_tickets.append(ticket)

            # 计算命中数
            hits = _calculate_hits(ticket, draw_record, profile_key)

            # 计算奖金
            prize_level, prize_amount = calculate_prize(
                profile_key, hits, ticket.groups,
                actual_groups=draw_record.groups,
                details=ticket.details,
            )

            if prize_amount is not None:
                stats.total_return += prize_amount

            stats.prize_counts[prize_level] = stats.prize_counts.get(prize_level, 0) + 1
            if prize_amount:
                stats.prize_amounts[prize_level] = (
                    stats.prize_amounts.get(prize_level, 0) + prize_amount
                )

            stats.results.append(
                BacktestResult(
                    issue=issue,
                    draw_date=draw_record.draw_date,
                    ticket=ticket,
                    prize_level=prize_level,
                    prize_amount=prize_amount,
                    investment=investment_per_ticket,
                )
            )

    # 分析号码频率
    stats.number_frequency = analyze_ticket_numbers(all_tickets)
    hot, cold = find_hot_cold_numbers(all_tickets)
    stats.hot_numbers = hot
    stats.cold_numbers = cold

    return stats


def _calculate_hits(
    ticket: Ticket,
    draw_record: Any,
    profile_key: str,
) -> dict[str, int]:
    """计算投注单与开奖记录的命中数."""
    hits: dict[str, int] = {}

    if profile_key == "ssq":
        ticket_reds = set(ticket.groups.get("red", []))
        draw_reds = set(draw_record.groups.get("red", []))
        hits["red"] = len(ticket_reds & draw_reds)

        ticket_blue = ticket.groups.get("blue", [])
        draw_blue = draw_record.groups.get("blue", [])
        hits["blue"] = 1 if (ticket_blue and draw_blue and ticket_blue[0] == draw_blue[0]) else 0

    elif profile_key == "3d":
        ticket_pos = ticket.groups.get("pos", [])
        draw_pos = draw_record.groups.get("pos", [])
        hits["pos"] = sum(1 for t, d in zip(ticket_pos, draw_pos) if t == d)

    elif profile_key == "kl8":
        ticket_main = set(ticket.groups.get("main", []))
        draw_main = set(draw_record.groups.get("main", []))
        hits["main"] = len(ticket_main & draw_main)

    elif profile_key == "dlt":
        ticket_front = set(ticket.groups.get("front", []))
        draw_front = set(draw_record.groups.get("front", []))
        hits["front"] = len(ticket_front & draw_front)

        ticket_back = set(ticket.groups.get("back", []))
        draw_back = set(draw_record.groups.get("back", []))
        hits["back"] = len(ticket_back & draw_back)

    elif profile_key == "pl3" or profile_key == "pl5" or profile_key == "qxc":
        ticket_pos = ticket.groups.get("pos", [])
        draw_pos = draw_record.groups.get("pos", [])
        hits["pos"] = sum(1 for t, d in zip(ticket_pos, draw_pos) if t == d)

    return hits


def format_backtest_report(stats: BacktestStats) -> str:
    """格式化回测报告."""
    lines = [
        "=" * 50,
        "回测统计报告",
        "=" * 50,
        "",
        f"总期数: {stats.total_periods}",
        f"总注数: {stats.total_tickets}",
        f"总投入: {stats.total_investment} 元",
        f"总回报: {stats.total_return} 元",
        f"收益率: {stats.roi:.2%}",
        f"中奖率: {stats.win_rate:.2%}",
        "",
        "各奖级统计:",
        "-" * 30,
    ]

    for level, count in sorted(stats.prize_counts.items()):
        amount = stats.prize_amounts.get(level, 0)
        lines.append(f"  {level}: {count} 次, 奖金 {amount} 元")

    lines.extend([
        "",
        "热号 (出现频率最高):",
        "-" * 30,
        f"  {', '.join(str(n) for n in stats.hot_numbers)}",
        "",
        "冷号 (出现频率最低):",
        "-" * 30,
        f"  {', '.join(str(n) for n in stats.cold_numbers)}",
        "",
        "=" * 50,
    ])

    return "\n".join(lines)
