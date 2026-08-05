"""生成引擎."""

from __future__ import annotations

import logging
import math
import random
from collections import Counter
from itertools import product
from typing import Any

from .strategy import GenerationStrategy
from .ticket import Ticket

logger = logging.getLogger(__name__)


class GenerationEngine:
    """号码生成引擎.

    负责管理所有可用策略，并根据选中的策略生成投注单。
    """

    def __init__(self) -> None:
        self._strategies: dict[str, GenerationStrategy] = {}

    def register(self, strategy: GenerationStrategy) -> None:
        """注册一个生成策略."""
        self._strategies[strategy.metadata.id] = strategy

    def unregister(self, strategy_id: str) -> None:
        """注销指定策略."""
        self._strategies.pop(strategy_id, None)

    def get(self, strategy_id: str) -> GenerationStrategy | None:
        """获取指定策略."""
        return self._strategies.get(strategy_id)

    def list_strategies(self) -> list[GenerationStrategy]:
        """列出所有已注册策略."""
        return list(self._strategies.values())

    def generate(
        self,
        strategy_id: str,
        count: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[Ticket]:
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
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 7,
    max_red_overlap: int = 3,
    block_blue_match: bool = False,
    blue_compare_periods: int = 1,
) -> list[Ticket]:
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

    filtered: list[Ticket] = []
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
        if not too_many and block_blue_match and ticket_blue is not None and ticket_blue in blue_recent:
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
# 大乐透最后一层过滤：与历史开奖记录比对前区重合数和后区
# --------------------------------------------------------------------------- #

# 大乐透前区和值的理论范围：1+2+3+4+5 = 15，31+32+33+34+35 = 165
DLT_FRONT_SUM_MIN = 15
DLT_FRONT_SUM_MAX = 165
# 大乐透后区和值的理论范围：1+2 = 3，11+12 = 23
DLT_BACK_SUM_MIN = 3
DLT_BACK_SUM_MAX = 23


def filter_dlt_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 7,
    max_front_overlap: int = 0,
    block_back_match: bool = True,
    back_compare_periods: int = 1,
) -> list[Ticket]:
    """对大乐透号码做最后一层过滤：与最近 N 期开奖记录比对。

    规则：
    - 前区：计算生成号码与历史开奖号码的交集个数，超过 max_front_overlap 则淘汰。
    - 后区：若 block_back_match 为 True，后区号码在 back_compare_periods 期内与历史相同则淘汰。
      后区为 2 个号码，只要任一号码在历史中出现即视为匹配。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 7。
        max_front_overlap: 允许的前区最大重合数，默认 0（不允许重合）。
        block_back_match: 是否禁止后区与历史相同，默认 True。
        back_compare_periods: 后区禁止重复的对比期数，默认 1。

    Returns:
        过滤后的号码列表。
    """
    if not tickets or not draw_records:
        return tickets

    if compare_periods <= 0:
        return tickets

    recent = draw_records[-compare_periods:] if len(draw_records) >= compare_periods else draw_records
    recent_data: list[tuple[set[int], set[int]]] = []
    for r in recent:
        fronts = set(r.groups.get("front", []))
        backs = set(r.groups.get("back", []))
        if fronts and backs:
            recent_data.append((fronts, backs))

    # 后区比较期数
    back_recent: set[int] = set()
    if block_back_match:
        if back_compare_periods > 0:
            back_data = draw_records[-back_compare_periods:] if len(draw_records) >= back_compare_periods else draw_records
        else:
            back_data = []
        for r in back_data:
            backs = r.groups.get("back", [])
            back_recent.update(backs)

    if not recent_data and not back_recent:
        return tickets

    filtered: list[Ticket] = []
    discarded = 0

    for ticket in tickets:
        ticket_fronts = set(ticket.groups.get("front", []))
        ticket_backs = set(ticket.groups.get("back", []))

        too_many = False
        # 前区检查
        for hist_fronts, _ in recent_data:
            front_overlap = len(ticket_fronts & hist_fronts)
            if front_overlap > max_front_overlap:
                too_many = True
                break
        # 后区检查
        if not too_many and block_back_match and back_recent and (ticket_backs & back_recent):
            too_many = True

        if not too_many:
            filtered.append(ticket)
        else:
            discarded += 1

    if discarded > 0:
        logger.info(
            "DLT过滤：共 %d 个候选，淘汰 %d 个（前区重合上限 %d，后区%s，比较 %d 期），"
            "剩余 %d 个",
            len(tickets), discarded, max_front_overlap,
            "禁止相同" if block_back_match else "不限",
            compare_periods, len(filtered),
        )

    return filtered


# 大乐透经验策略过滤自适应候选倍数相关常量
DLT_FILTER_SAFETY = 2.5
DLT_FILTER_MAX_CANDIDATES = 5000
# 通过率下限，避免极端严格参数导致除以过小值
_DLT_MIN_PASS_RATIO = 0.02


def estimate_dlt_pass_ratio(
    draw_records: list[Any],
    compare_periods: int,
    max_front_overlap: int,
    min_front_sum: int = DLT_FRONT_SUM_MIN,
    max_front_sum: int = DLT_FRONT_SUM_MAX,
    samples: int = 3000,
) -> float:
    """采样估算大乐透号码通过经验策略过滤的比例（0-1）。

    号码空间 C(35,5)*C(12,2) ≈ 3246 万种组合，无法全枚举，
    改用固定种子的均匀采样保证结果确定且可复现。
    判定逻辑与 ``filter_dlt_by_history`` 完全一致（前区部分）。
    """
    import random as _random

    recent_sets: list[set] = []
    if compare_periods > 0 and draw_records:
        recent = (
            draw_records[-compare_periods:]
            if len(draw_records) >= compare_periods
            else draw_records
        )
        for r in recent:
            fronts = set(r.groups.get("front", []))
            if fronts:
                recent_sets.append(fronts)

    if not recent_sets and min_front_sum <= DLT_FRONT_SUM_MIN and max_front_sum >= DLT_FRONT_SUM_MAX:
        return 1.0

    rng = _random.Random(20260725)
    passing = 0
    for _ in range(samples):
        front_combo = sorted(rng.sample(range(1, 36), 5))
        sum_value = sum(front_combo)
        if sum_value < min_front_sum or sum_value > max_front_sum:
            continue
        front_set = set(front_combo)
        ok = True
        for hs in recent_sets:
            if len(front_set & hs) > max_front_overlap:
                ok = False
                break
        if ok:
            passing += 1
    return passing / samples


def dlt_filtered_gen_count(
    count: int,
    draw_records: list[Any],
    compare_periods: int,
    max_front_overlap: int,
    min_front_sum: int = DLT_FRONT_SUM_MIN,
    max_front_sum: int = DLT_FRONT_SUM_MAX,
) -> tuple[int, float]:
    """计算大乐透经验过滤场景下的候选生成数量。

    按采样估算的通过率自适应放大，避免过滤后候选不足。

    Returns:
        ``(gen_count, pass_ratio)``，pass_ratio 为采样估算通过率（0-1）。
    """
    pass_ratio = estimate_dlt_pass_ratio(
        draw_records, compare_periods, max_front_overlap,
        min_front_sum, max_front_sum,
    )
    pass_ratio = max(pass_ratio, _DLT_MIN_PASS_RATIO)
    gen_count = math.ceil(count / pass_ratio * DLT_FILTER_SAFETY)
    gen_count = max(count * 3, min(DLT_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_ratio


def apply_dlt_experience_filter(
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_front_overlap: int,
    pass_ratio: float | None = None,
    min_front_sum: int = DLT_FRONT_SUM_MIN,
    max_front_sum: int = DLT_FRONT_SUM_MAX,
    block_back_match: bool = True,
    back_compare_periods: int = 1,
) -> list[Ticket]:
    """大乐透经验策略过滤的完整后处理：过滤 → 截断。

    主界面生成与批量历史回测共用，保证两条路径行为一致。
    （大乐透没有直选/组选之分，无需重新分配投注方式。）

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_front_overlap: 允许的前区最大重合个数。
        pass_ratio: 采样估算通过率，仅用于告警信息。
        min_front_sum: 允许的前区最小和值。
        max_front_sum: 允许的前区最大和值。
        block_back_match: 是否禁止后区与历史相同，默认 True。
        back_compare_periods: 后区禁止重复的对比期数，默认 1。
    """
    if tickets:
        filtered = filter_dlt_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_front_overlap=max_front_overlap,
            block_back_match=block_back_match,
            back_compare_periods=back_compare_periods,
        )
        if len(filtered) < count:
            logger.warning(
                "大乐透经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（估算通过率 %.1f%%，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                (pass_ratio if pass_ratio is not None else 0.0) * 100,
            )
        tickets = filtered[:count]
    return tickets


# --------------------------------------------------------------------------- #
# 通用经验策略过滤（和值范围 + 历史重合）
# --------------------------------------------------------------------------- #

def _filter_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    group_key: str,
    compare_periods: int,
    max_overlap: int,
    min_sum: int,
    max_sum: int,
    sum_range_default: tuple[int, int],
    use_multiset: bool,
    log_label: str,
) -> list[Ticket]:
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

    filtered: list[Ticket] = []
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
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 5,
    max_overlap: int = 1,
    min_sum: int = 0,
    max_sum: int = 27,
) -> list[Ticket]:
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
    draw_records: list[Any],
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
    recent_counters: list[Counter] = []
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
    draw_records: list[Any],
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
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_count: int | None = None,
    min_sum: int = 0,
    max_sum: int = 27,
) -> list[Ticket]:
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
# 排列3 经验策略过滤：与历史开奖记录比对相同号码数
# （与福彩3D规则完全一致，仅日志标签不同）
# --------------------------------------------------------------------------- #

PL3_SUM_MIN = 0
PL3_SUM_MAX = 27


def filter_pl3_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 5,
    max_overlap: int = 1,
    min_sum: int = PL3_SUM_MIN,
    max_sum: int = PL3_SUM_MAX,
) -> list[Ticket]:
    """对排列3号码做经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数。

    规则与福彩3D完全一致：
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
        sum_range_default=(PL3_SUM_MIN, PL3_SUM_MAX),
        use_multiset=True,
        log_label="排列3经验策略过滤",
    )


def estimate_pl3_pass_count(
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = PL3_SUM_MIN,
    max_sum: int = PL3_SUM_MAX,
) -> int:
    """枚举全部 1000 种排列3直选组合，返回能通过经验策略过滤的数量（理论通过数）。

    与 ``filter_pl3_by_history`` 使用完全相同的和值范围 + 多集合交集判定逻辑。
    """
    recent_counters: list[Counter] = []
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

    if not recent_counters and min_sum <= PL3_SUM_MIN and max_sum >= PL3_SUM_MAX:
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


PL3_FILTER_SAFETY = 2.5
PL3_FILTER_MAX_CANDIDATES = 1000


def pl3_filtered_gen_count(
    count: int,
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = PL3_SUM_MIN,
    max_sum: int = PL3_SUM_MAX,
) -> tuple[int, int]:
    """计算排列3经验过滤场景下的候选生成数量。

    Returns:
        ``(gen_count, pass_count)``，pass_count 为理论通过数（0-1000）。
    """
    pass_count = estimate_pl3_pass_count(
        draw_records, compare_periods, max_overlap, min_sum, max_sum
    )
    pass_ratio = max(pass_count / 1000.0, 0.05)
    gen_count = math.ceil(count / pass_ratio * PL3_FILTER_SAFETY)
    gen_count = max(count * 3, min(PL3_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_count


def apply_pl3_experience_filter(
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_count: int | None = None,
    min_sum: int = PL3_SUM_MIN,
    max_sum: int = PL3_SUM_MAX,
) -> list[Ticket]:
    """排列3经验策略过滤的完整后处理：过滤 → 截断。

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的相同号码最大个数。
        pass_count: 理论通过数，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_pl3_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "排列3经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（理论通过 %d/1000，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                pass_count if pass_count is not None else 0,
            )
        tickets = filtered[:count]
    return tickets


# --------------------------------------------------------------------------- #
# 排列5 经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数
# （号码空间 10^5 = 100000，用固定种子采样估算通过率）
# --------------------------------------------------------------------------- #

PL5_SUM_MIN = 0
PL5_SUM_MAX = 45

_PL5_PASS_ESTIMATE_SAMPLES = 5000
_PL5_PASS_ESTIMATE_SEED = 20260726


def filter_pl5_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 5,
    max_overlap: int = 2,
    min_sum: int = PL5_SUM_MIN,
    max_sum: int = PL5_SUM_MAX,
) -> list[Ticket]:
    """对排列5号码做经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数。

    规则：
    - 和值：五位数字之和 < min_sum 或 > max_sum 的号码直接淘汰。
    - 将生成号码（5 位）与最近 compare_periods 期开奖号码逐一比对。
    - 统计相同号码个数（使用多集合交集，正确处理含重复号码的情况）。
    - 只要任一期的相同号码数 > max_overlap，则淘汰该候选号码。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 5；<=0 表示不与历史比对。
        max_overlap: 允许的相同号码最大个数，默认 2；超过则淘汰。
        min_sum: 允许的最小和值，默认 0（不限制）。
        max_sum: 允许的最大和值，默认 45（不限制）。

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
        sum_range_default=(PL5_SUM_MIN, PL5_SUM_MAX),
        use_multiset=True,
        log_label="排列5经验策略过滤",
    )


def estimate_pl5_pass_ratio(
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = PL5_SUM_MIN,
    max_sum: int = PL5_SUM_MAX,
    samples: int = _PL5_PASS_ESTIMATE_SAMPLES,
) -> float:
    """采样估算排列5号码通过经验策略过滤的比例（0-1）。

    号码空间 10^5 = 100000 种组合，用固定种子的均匀采样保证结果确定且可复现。
    判定逻辑与 ``filter_pl5_by_history`` 完全一致。
    """
    recent_counters: list[Counter] = []
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

    if not recent_counters and min_sum <= PL5_SUM_MIN and max_sum >= PL5_SUM_MAX:
        return 1.0

    rng = random.Random(_PL5_PASS_ESTIMATE_SEED)
    passing = 0
    for _ in range(samples):
        combo = tuple(rng.randint(0, 9) for _ in range(5))
        sum_value = sum(combo)
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
    return passing / samples


PL5_FILTER_SAFETY = 2.5
PL5_FILTER_MAX_CANDIDATES = 5000
_PL5_MIN_PASS_RATIO = 0.02


def pl5_filtered_gen_count(
    count: int,
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = PL5_SUM_MIN,
    max_sum: int = PL5_SUM_MAX,
) -> tuple[int, float]:
    """计算排列5经验过滤场景下的候选生成数量。

    Returns:
        ``(gen_count, pass_ratio)``，pass_ratio 为采样估算通过率（0-1）。
    """
    pass_ratio = estimate_pl5_pass_ratio(
        draw_records, compare_periods, max_overlap, min_sum, max_sum
    )
    pass_ratio = max(pass_ratio, _PL5_MIN_PASS_RATIO)
    gen_count = math.ceil(count / pass_ratio * PL5_FILTER_SAFETY)
    gen_count = max(count * 3, min(PL5_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_ratio


def apply_pl5_experience_filter(
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_ratio: float | None = None,
    min_sum: int = PL5_SUM_MIN,
    max_sum: int = PL5_SUM_MAX,
) -> list[Ticket]:
    """排列5经验策略过滤的完整后处理：过滤 → 截断。

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的相同号码最大个数。
        pass_ratio: 采样估算通过率，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_pl5_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "排列5经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（估算通过率 %.1f%%，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                (pass_ratio if pass_ratio is not None else 0.0) * 100,
            )
        tickets = filtered[:count]
    return tickets


# --------------------------------------------------------------------------- #
# 7星彩 经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数
# （号码空间 10^7 = 10000000，用固定种子采样估算通过率）
# --------------------------------------------------------------------------- #

QXC_SUM_MIN = 0
QXC_SUM_MAX = 63

_QXC_PASS_ESTIMATE_SAMPLES = 5000
_QXC_PASS_ESTIMATE_SEED = 20260726


def filter_qxc_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 5,
    max_overlap: int = 3,
    min_sum: int = QXC_SUM_MIN,
    max_sum: int = QXC_SUM_MAX,
) -> list[Ticket]:
    """对7星彩号码做经验策略过滤：和值范围 + 与最近 N 期开奖记录比对相同号码数。

    规则：
    - 和值：七位数字之和 < min_sum 或 > max_sum 的号码直接淘汰。
    - 将生成号码（7 位）与最近 compare_periods 期开奖号码逐一比对。
    - 统计相同号码个数（使用多集合交集，正确处理含重复号码的情况）。
    - 只要任一期的相同号码数 > max_overlap，则淘汰该候选号码。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 5；<=0 表示不与历史比对。
        max_overlap: 允许的相同号码最大个数，默认 3；超过则淘汰。
        min_sum: 允许的最小和值，默认 0（不限制）。
        max_sum: 允许的最大和值，默认 63（不限制）。

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
        sum_range_default=(QXC_SUM_MIN, QXC_SUM_MAX),
        use_multiset=True,
        log_label="7星彩经验策略过滤",
    )


def estimate_qxc_pass_ratio(
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = QXC_SUM_MIN,
    max_sum: int = QXC_SUM_MAX,
    samples: int = _QXC_PASS_ESTIMATE_SAMPLES,
) -> float:
    """采样估算7星彩号码通过经验策略过滤的比例（0-1）。

    号码空间 10^7 = 10000000 种组合，用固定种子的均匀采样保证结果确定且可复现。
    判定逻辑与 ``filter_qxc_by_history`` 完全一致。
    """
    recent_counters: list[Counter] = []
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

    if not recent_counters and min_sum <= QXC_SUM_MIN and max_sum >= QXC_SUM_MAX:
        return 1.0

    rng = random.Random(_QXC_PASS_ESTIMATE_SEED)
    passing = 0
    for _ in range(samples):
        combo = tuple(rng.randint(0, 9) for _ in range(7))
        sum_value = sum(combo)
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
    return passing / samples


QXC_FILTER_SAFETY = 2.5
QXC_FILTER_MAX_CANDIDATES = 5000
_QXC_MIN_PASS_RATIO = 0.02


def qxc_filtered_gen_count(
    count: int,
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = QXC_SUM_MIN,
    max_sum: int = QXC_SUM_MAX,
) -> tuple[int, float]:
    """计算7星彩经验过滤场景下的候选生成数量。

    Returns:
        ``(gen_count, pass_ratio)``，pass_ratio 为采样估算通过率（0-1）。
    """
    pass_ratio = estimate_qxc_pass_ratio(
        draw_records, compare_periods, max_overlap, min_sum, max_sum
    )
    pass_ratio = max(pass_ratio, _QXC_MIN_PASS_RATIO)
    gen_count = math.ceil(count / pass_ratio * QXC_FILTER_SAFETY)
    gen_count = max(count * 3, min(QXC_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_ratio


def apply_qxc_experience_filter(
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_ratio: float | None = None,
    min_sum: int = QXC_SUM_MIN,
    max_sum: int = QXC_SUM_MAX,
) -> list[Ticket]:
    """7星彩经验策略过滤的完整后处理：过滤 → 截断。

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的相同号码最大个数。
        pass_ratio: 采样估算通过率，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_qxc_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "7星彩经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（估算通过率 %.1f%%，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                (pass_ratio if pass_ratio is not None else 0.0) * 100,
            )
        tickets = filtered[:count]
    return tickets


# --------------------------------------------------------------------------- #
# 快乐8 经验策略过滤：和值范围 + 与最近 N 期开奖记录比对重合数
# （快乐8从1-80开20个号，玩家选1-10个号，号码不重复、不按位）
# --------------------------------------------------------------------------- #

# 快乐8和值范围：选1个号最小=1，选10个号最大=71+72+...+80=755
# 默认设置为不限制
KL8_SUM_MIN = 0
KL8_SUM_MAX = 800

_KL8_PASS_ESTIMATE_SAMPLES = 3000
_KL8_PASS_ESTIMATE_SEED = 20260726


def filter_kl8_by_history(
    tickets: list[Ticket],
    draw_records: list[Any],
    compare_periods: int = 5,
    max_overlap: int = 5,
    min_sum: int = KL8_SUM_MIN,
    max_sum: int = KL8_SUM_MAX,
) -> list[Ticket]:
    """对快乐8号码做经验策略过滤：和值范围 + 与最近 N 期开奖记录比对重合数。

    规则：
    - 和值：选中号码之和 < min_sum 或 > max_sum 的号码直接淘汰。
    - 将生成号码与最近 compare_periods 期开奖号码逐一比对（集合交集）。
    - 只要任一期的重合号码数 > max_overlap，则淘汰该候选号码。

    Args:
        tickets: 策略生成的候选号码列表。
        draw_records: DrawRecord 列表（按时间升序）。
        compare_periods: 向前比较的期数，默认 5；<=0 表示不与历史比对。
        max_overlap: 允许的最大重合个数，默认 5；超过则淘汰。
        min_sum: 允许的最小和值，默认 0（不限制）。
        max_sum: 允许的最大和值，默认 800（不限制）。

    Returns:
        过滤后的号码列表。
    """
    return _filter_by_history(
        tickets, draw_records,
        group_key="main",
        compare_periods=compare_periods,
        max_overlap=max_overlap,
        min_sum=min_sum,
        max_sum=max_sum,
        sum_range_default=(KL8_SUM_MIN, KL8_SUM_MAX),
        use_multiset=False,
        log_label="快乐8经验策略过滤",
    )


# 快乐8号码空间 C(80,20) 极大，用固定种子采样估算通过率
_KL8_PASS_ESTIMATE_SAMPLES = 3000
_KL8_PASS_ESTIMATE_SEED = 20260726


def estimate_kl8_pass_ratio(
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = KL8_SUM_MIN,
    max_sum: int = KL8_SUM_MAX,
    pick_count: int = 10,
    samples: int = _KL8_PASS_ESTIMATE_SAMPLES,
) -> float:
    """采样估算快乐8号码通过经验策略过滤的比例（0-1）。

    号码空间 C(80,20) 极大，用固定种子的均匀采样保证结果确定且可复现。
    判定逻辑与 ``filter_kl8_by_history`` 完全一致。
    """
    recent_sets: list[set] = []
    if compare_periods > 0 and draw_records:
        recent = (
            draw_records[-compare_periods:]
            if len(draw_records) >= compare_periods
            else draw_records
        )
        for r in recent:
            nums = r.groups.get("main", [])
            if nums:
                recent_sets.append(set(nums))

    if not recent_sets and min_sum <= KL8_SUM_MIN and max_sum >= KL8_SUM_MAX:
        return 1.0

    rng = random.Random(_KL8_PASS_ESTIMATE_SEED)
    passing = 0
    for _ in range(samples):
        combo = sorted(rng.sample(range(1, 81), pick_count))
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


KL8_FILTER_SAFETY = 2.5
KL8_FILTER_MAX_CANDIDATES = 5000
_KL8_MIN_PASS_RATIO = 0.02


def kl8_filtered_gen_count(
    count: int,
    draw_records: list[Any],
    compare_periods: int,
    max_overlap: int,
    min_sum: int = KL8_SUM_MIN,
    max_sum: int = KL8_SUM_MAX,
    pick_count: int = 10,
) -> tuple[int, float]:
    """计算快乐8经验过滤场景下的候选生成数量。

    Returns:
        ``(gen_count, pass_ratio)``，pass_ratio 为采样估算通过率（0-1）。
    """
    pass_ratio = estimate_kl8_pass_ratio(
        draw_records, compare_periods, max_overlap, min_sum, max_sum, pick_count
    )
    pass_ratio = max(pass_ratio, _KL8_MIN_PASS_RATIO)
    gen_count = math.ceil(count / pass_ratio * KL8_FILTER_SAFETY)
    gen_count = max(count * 3, min(KL8_FILTER_MAX_CANDIDATES, gen_count))
    return gen_count, pass_ratio


def apply_kl8_experience_filter(
    tickets: list[Ticket],
    draw_records: list[Any],
    count: int,
    compare_periods: int,
    max_overlap: int,
    pass_ratio: float | None = None,
    min_sum: int = KL8_SUM_MIN,
    max_sum: int = KL8_SUM_MAX,
) -> list[Ticket]:
    """快乐8经验策略过滤的完整后处理：过滤 → 截断。

    Args:
        tickets: 放大后生成的候选号码。
        draw_records: 用于比对的开奖记录（回测场景须为目标期之前的记录）。
        count: 最终需要的注数。
        compare_periods: 向前比较的期数。
        max_overlap: 允许的最大重合个数。
        pass_ratio: 采样估算通过率，仅用于告警信息。
        min_sum: 允许的最小和值。
        max_sum: 允许的最大和值。
    """
    if tickets:
        filtered = filter_kl8_by_history(
            tickets,
            draw_records,
            compare_periods=compare_periods,
            max_overlap=max_overlap,
            min_sum=min_sum,
            max_sum=max_sum,
        )
        if len(filtered) < count:
            logger.warning(
                "快乐8经验策略过滤：生成 %d 候选，过滤后仅剩 %d，"
                "不足 %d 注（估算通过率 %.1f%%，建议放宽过滤参数）",
                len(tickets), len(filtered), count,
                (pass_ratio if pass_ratio is not None else 0.0) * 100,
            )
        tickets = filtered[:count]
    return tickets
