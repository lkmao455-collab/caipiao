"""批量回测共享数据类.

本模块放置可被 UI 层与 core 层共享的批量回测数据类，避免 core 模块反向依赖 UI。
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
    # 每期中奖注的明细，用于在结果界面还原「中奖记录」面板
    # （含日期/期号/号码/奖级），由 merge_round_results 填充。
    winner_details: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)  # 各期错误信息


@dataclass(frozen=True)
class RoundBacktestContext:
    """一期回测所需的全部上下文（可序列化）。"""

    strategy_id: str
    profile_key: str
    tickets_per_round: int
    options: dict
    is_ml: bool
    needs_history: bool
    records: list
    seed: int
    plugin_dir: str | None = None


@dataclass(frozen=True)
class RoundTask:
    """一期回测任务。"""

    index: int
    actual: Any


@dataclass(frozen=True)
class RoundResult:
    """一期回测结果。"""

    index: int
    total_cost: int = 0
    hit_count: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    first_ticket_hit_count: int = 0
    winners: list[int] = field(default_factory=list)
    ticket_results: list[dict] = field(default_factory=list)
    ticket_index_hits: dict[int, int] = field(default_factory=dict)
    # 以下字段用于在主线程还原旧版 round_ready 信号所需的详情字典
    date_str: str = ""
    issue_str: str = ""
    actual_groups: dict = field(default_factory=dict)
    tickets: list = field(default_factory=list)
    error: str | None = None
