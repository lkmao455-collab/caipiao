"""生成引擎."""

from __future__ import annotations

import logging
import math
import random
from collections import Counter
from itertools import product
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
        tickets = strategy.generate(count=count, options=options)
        if tickets and tickets[0].profile.key == "3d":
            from .strategies.lotteries.fc3d.utils import assign_fc3d_bet_modes

            assign_fc3d_bet_modes(tickets)
        return tickets


# --------------------------------------------------------------------------- #
# 双色球最后一层过滤：与历史开奖记录比对红球重合数和蓝球
# --------------------------------------------------------------------------- #

def filter_ssq_by_history(
    tickets: List[Ticket],
    draw_records: List[Any],
    compare_periods: int = 7,
    max_red_overlap: int = 3,
    block_blue_match: bool = False,
    blue_compare_periods: int = 1,
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
        blue_compare_periods: 蓝球禁止重复的对比期数，默认 1。

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


# --------------------------------------------------------------------------- #
# 通用经验策略过滤（和值范围 + 历史重合）
# --------------------------------------------------------------------------- #

def _filter_by_history(
    tickets: List[Ticket],
    draw_records: List[Any],
    group_key: str,
    compare_periods: int,
    max_overlap: int,
    min_sum: int,
    max_sum: int,
    sum_range_default: tuple[int, int],
    use_multiset: bool,
    log_label: str,
) -> List[Ticket]:
    """通用经验策略过滤：和值范围 + 与最近 N 期开奖记录比对重合数。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        group_key: 号码组 key（如 "pos"、"basic"）。
        compare_periods: 向前比较的期数；<=0 表示不与历史比对。
        max_overlap: 允许的重合最大个数；超过则淘汰。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
        sum_range_default: (默认最小和值, 默认最大和值)，用于判断是否启用和值过滤。
        use_multiset: True 用 Counter（处理重复号码，如 3D），False 用 set。
        log_label: 日志标签（如 "3D经验策略过滤"）。

    Returns:
        过滤后的号码列表。
    """
    if not tickets:
        return tickets

    # 构建历史比对结构
    history: list = []
    if draw_records and compare_periods > 0:
        recent = (
            draw_records[-compare_periods:]
            if len(draw_records) >= compare_periods
            else draw_records
        )
        for r in recent:
            nums = r.groups.get(group_key, [])
            if nums:
                history.append(Counter(nums) if use_multiset else set(nums))

    no_sum_filter = min_sum <= sum_range_default[0] and max_sum >= sum_range_default[1]
    if not history and no_sum_filter:
        return tickets

    filtered: List[Ticket] = []
    discarded = 0

    for ticket in tickets:
        nums = ticket.groups.get(group_key, [])
        sum_value = sum(nums)
        if sum_value < min_sum or sum_value > max_sum:
            discarded += 1
            continue

        ticket_struct = Counter(nums) if use_multiset else set(nums)
        too_many = False
        for hist_struct in history:
            if use_multiset:
                # 多集合交集：112 vs 123 -> {1:1, 2:1} -> 2 个相同
                overlap = sum((ticket_struct & hist_struct).values())
            else:
                overlap = len(ticket_struct & hist_struct)
            if overlap > max_overlap:
                too_many = True
                break

        if not too_many:
            filtered.append(ticket)
        else:
            discarded += 1

    if discarded > 0:
        logger.info(
            "%s：共 %d 个候选，淘汰 %d 个（重合上限 %d，比较 %d 期，"
            "和值 %d-%d），剩余 %d 个",
            log_label, len(tickets), discarded, max_overlap, compare_periods,
            min_sum, max_sum, len(filtered),
        )

    return filtered


# --------------------------------------------------------------------------- #
# 福彩3D 经验策略过滤：与历史开奖记录比对相同号码数
# --------------------------------------------------------------------------- #

def filter_fc3d_by_history(
    tickets: List[Ticket],
    draw_records: List[Any],
    compare_periods: int = 5,
    max_overlap: int = 1,
    min_sum: int = 0,
    max_sum: int = 27,
) -> List[Ticket]:
    """对福彩3D号码做经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数。

    规则：
    - 和值：三位数字之和 < min_sum 或 > max_sum 的号码直接淘汰。
    - 将生成号码（3 位）与最近 compare_periods 期开奖号码逐一比对。
    - 统计相同号码个数（使用多集合交集，正确处理 112 等含重复号码的情况）。
    - 只要任一期的相同号码数 > max_overlap，则淘汰该候选号码。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 5；<=0 表示不与历史比对。
        max_overlap: 允许的相同号码最大个数，默认 1；超过则淘汰。
        min_sum: 允许的最小和值，默认 0（不限制）。
        max_sum: 允许的最大和值，默认 27（不限制）。

    Returns:
        过滤后的号码列表。
    """
    return _filter_by_history(
        tickets, draw_records,
        group_key="pos",
        compare_periods=compare_periods,
        max_overlap=max_overlap,
        min_sum=min_sum,
        max_sum=max_sum,
        sum_range_default=(0, 27),
        use_multiset=True,
        log_label="3D经验策略过滤",
    )


def estimate_fc3d_pass_count(
    draw_records: List[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = 0,
    max_sum: int = 27,
) -> int:
    """枚举全部 1000 种3D直选组合，返回能通过经验策略过滤的数量（理论通过数）。

    用于生成前估算过滤强度，从而自适应放大候选生成数量，避免过滤后候选不足。
    与 ``filter_fc3d_by_history`` 使用完全相同的和值范围 + 多集合交集判定逻辑。

    Args:
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数；<=0 表示不与历史比对。
        max_overlap: 允许的相同号码最大个数。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。

    Returns:
        通过过滤的组合数（0-1000）。
    """
    recent_counters: List[Counter] = []
    if compare_periods > 0 and draw_records:
        recent = (
            draw_records[-compare_periods:]
            if len(draw_records) >= compare_periods
            else draw_records
        )
        for r in recent:
            nums = r.groups.get("pos", [])
            if nums:
                recent_counters.append(Counter(nums))

    if not recent_counters and min_sum <= 0 and max_sum >= 27:
        return 1000

    passing = 0
    for combo in product(range(10), repeat=3):
        sum_value = combo[0] + combo[1] + combo[2]
        if sum_value < min_sum or sum_value > max_sum:
            continue
        cc = Counter(combo)
        ok = True
        for hc in recent_counters:
            if sum((cc & hc).values()) > max_overlap:
                ok = False
                break
        if ok:
            passing += 1
    return passing


# 3D 经验策略过滤自适应候选倍数相关常量
# 安全系数：补偿加权采样下实际通过率低于均匀理论值的情况（实测最低约理论的 0.48 倍）
FC3D_FILTER_SAFETY = 2.5
# 候选生成数量上限：3D 直选全空间为 1000，再大也无意义
FC3D_FILTER_MAX_CANDIDATES = 1000


def fc3d_filtered_gen_count(
    count: int,
    draw_records: List[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = 0,
    max_sum: int = 27,
) -> tuple[int, int]:
    """计算 3D 经验过滤场景下的候选生成数量。

    按理论通过率自适应放大，避免过滤后候选不足。

    Returns:
        ``(gen_count, pass_count)``，pass_count 为理论通过数（0-1000）。
    """
    pass_count = estimate_fc3d_pass_count(
        draw_records, compare_periods, max_overlap, min_sum, max_sum
    )
    # 通过率下限 0.05，避免极端严格参数导致除以过小值
    pass_ratio = max(pass_count / 1000.0, 0.05)
    gen_count = math.ceil(count / pass_ratio * FC3D_FILTER_SAFETY)
    gen_count = max(count * 3, min(FC3D_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_count


def apply_fc3d_experience_filter(
    tickets: List[Ticket],
    draw_records: List[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_count: Optional[int] = None,
    min_sum: int = 0,
    max_sum: int = 27,
) -> List[Ticket]:
    """3D 经验策略过滤的完整后处理：过滤 → 截断 → 重新分配投注方式。

    主界面生成与批量历史回测共用，保证两条路径行为一致。
    截断后必须重新调用 ``assign_fc3d_bet_modes``：放大候选时 bet_mode 是在
    放大后的列表上分配的（前一半全为组选），直接截断会导致最终号码几乎全为
    组选，重新分配可恢复直选/组选 1:1 配比。

    Args:
        tickets: 放大后生成的候选号码（已在 engine.generate 内分配过 bet_mode）。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的相同号码最大个数。
        pass_count: 理论通过数，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_fc3d_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "3D经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（理论通过 %d/1000，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                pass_count if pass_count is not None else 0,
            )
        tickets = filtered[:count]
    if tickets:
        from .strategies.lotteries.fc3d.utils import assign_fc3d_bet_modes

        assign_fc3d_bet_modes(tickets)
    return tickets


# --------------------------------------------------------------------------- #
# 七乐彩经验策略过滤：和值范围 + 与最近 N 期开奖记录比对基本号重合数
# （参照福彩3D实现；基本号 1-30 选 7 且不重复，用普通集合交集即可）
# --------------------------------------------------------------------------- #

# 七乐彩基本号和值的理论范围：1+2+...+7 = 28，24+25+...+30 = 189；
# 设置项放宽到 0-210，默认值即"不限制"
QLC_SUM_MIN = 0
QLC_SUM_MAX = 210


def filter_qlc_by_history(
    tickets: List[Ticket],
    draw_records: List[Any],
    compare_periods: int = 5,
    max_overlap: int = 2,
    min_sum: int = QLC_SUM_MIN,
    max_sum: int = QLC_SUM_MAX,
) -> List[Ticket]:
    """对七乐彩号码做经验策略过滤：和值范围 + 与最近 N 期开奖比对基本号重合数。

    规则：
    - 和值：7 个基本号之和 < min_sum 或 > max_sum 的号码直接淘汰。
    - 将生成号码与最近 compare_periods 期开奖基本号逐一比对（集合交集）。
    - 只要任一期的重合号码数 > max_overlap，则淘汰该候选号码。
    - 特别号为开奖专用（draw_only），不参与投注，不纳入比对。

    Args:
        tickets: 策略生成的候选号码列表（groups["basic"] 为 7 个基本号）。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 5；<=0 表示不与历史比对。
        max_overlap: 允许的基本号最大重合个数，默认 2；超过则淘汰。
        min_sum: 允许的最小和值，默认 0（不限制）。
        max_sum: 允许的最大和值，默认 210（不限制）。

    Returns:
        过滤后的号码列表。
    """
    return _filter_by_history(
        tickets, draw_records,
        group_key="basic",
        compare_periods=compare_periods,
        max_overlap=max_overlap,
        min_sum=min_sum,
        max_sum=max_sum,
        sum_range_default=(QLC_SUM_MIN, QLC_SUM_MAX),
        use_multiset=False,
        log_label="七乐彩经验策略过滤",
    )


# 七乐彩号码空间 C(30,7) ≈ 203 万，全枚举不现实，用固定种子采样估算通过率
_QLC_PASS_ESTIMATE_SAMPLES = 3000
_QLC_PASS_ESTIMATE_SEED = 20260713


def estimate_qlc_pass_ratio(
    draw_records: List[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = QLC_SUM_MIN,
    max_sum: int = QLC_SUM_MAX,
    samples: int = _QLC_PASS_ESTIMATE_SAMPLES,
) -> float:
    """采样估算七乐彩号码通过经验策略过滤的比例（0-1）。

    号码空间约 203 万种组合，无法像福彩3D那样全枚举，
    改用固定种子的均匀采样保证结果确定且可复现。
    判定逻辑与 ``filter_qlc_by_history`` 完全一致。
    """
    recent_sets: List[set] = []
    if compare_periods > 0 and draw_records:
        recent = (
            draw_records[-compare_periods:]
            if len(draw_records) >= compare_periods
            else draw_records
        )
        for r in recent:
            nums = r.groups.get("basic", [])
            if nums:
                recent_sets.append(set(nums))

    if not recent_sets and min_sum <= QLC_SUM_MIN and max_sum >= QLC_SUM_MAX:
        return 1.0

    rng = random.Random(_QLC_PASS_ESTIMATE_SEED)
    passing = 0
    for _ in range(samples):
        combo = rng.sample(range(1, 31), 7)
        sum_value = sum(combo)
        if sum_value < min_sum or sum_value > max_sum:
            continue
        combo_set = set(combo)
        ok = True
        for hs in recent_sets:
            if len(combo_set & hs) > max_overlap:
                ok = False
                break
        if ok:
            passing += 1
    return passing / samples


# 七乐彩经验策略过滤自适应候选倍数相关常量
QLC_FILTER_SAFETY = 2.5
QLC_FILTER_MAX_CANDIDATES = 5000
# 通过率下限，避免极端严格参数导致除以过小值
_QLC_MIN_PASS_RATIO = 0.02


def qlc_filtered_gen_count(
    count: int,
    draw_records: List[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = QLC_SUM_MIN,
    max_sum: int = QLC_SUM_MAX,
) -> tuple[int, float]:
    """计算七乐彩经验过滤场景下的候选生成数量。

    按采样估算的通过率自适应放大，避免过滤后候选不足。

    Returns:
        ``(gen_count, pass_ratio)``，pass_ratio 为采样估算通过率（0-1）。
    """
    pass_ratio = estimate_qlc_pass_ratio(
        draw_records, compare_periods, max_overlap, min_sum, max_sum
    )
    pass_ratio = max(pass_ratio, _QLC_MIN_PASS_RATIO)
    gen_count = math.ceil(count / pass_ratio * QLC_FILTER_SAFETY)
    gen_count = max(count * 3, min(QLC_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_ratio


def apply_qlc_experience_filter(
    tickets: List[Ticket],
    draw_records: List[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_ratio: Optional[float] = None,
    min_sum: int = QLC_SUM_MIN,
    max_sum: int = QLC_SUM_MAX,
) -> List[Ticket]:
    """七乐彩经验策略过滤的完整后处理：过滤 → 截断。

    主界面生成与批量历史回测共用，保证两条路径行为一致。
    （七乐彩没有直选/组选之分，无需重新分配投注方式。）

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的基本号最大重合个数。
        pass_ratio: 采样估算通过率，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_qlc_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "七乐彩经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（估算通过率 %.1f%%，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                (pass_ratio if pass_ratio is not None else 0.0) * 100,
            )
        tickets = filtered[:count]
    return tickets
