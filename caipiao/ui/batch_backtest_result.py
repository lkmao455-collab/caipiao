"""批量历史回测汇总结果数据类.

本模块独立存放 ``BatchBacktestResult``，避免 ``batch_backtest_worker``
与 ``batch_backtest_thread`` 之间产生循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class BatchBacktestResult:
    """批量回测汇总结果."""

    total_cost: int = 0  # 总花费（每注 2 元）
    total_fixed_prize: int = 0  # 固定奖金合计
    float_prize_count: int = 0  # 中得浮动奖次数
    hit_count: int = 0  # 中奖次数（含浮动奖）
    total_rounds: int = 0  # 回测期数
    first_ticket_hit_count: int = 0  # 第一注中奖次数
    ticket_index_hits: Dict[int, int] = field(default_factory=dict)  # 第 n 注中奖次数
    ticket_results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)  # 各期错误信息
