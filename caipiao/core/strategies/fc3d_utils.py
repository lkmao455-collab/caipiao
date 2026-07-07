"""福彩3D专用统计工具函数."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from ...data.models import DrawRecord


POSITION_COUNT = 3
DIGIT_POOL = list(range(10))


def _slice_records(records: List[DrawRecord], lookback: Optional[int]) -> List[DrawRecord]:
    sorted_records = sorted(records, key=lambda r: r.draw_date)
    if lookback is None or lookback >= len(sorted_records):
        return sorted_records
    if lookback <= 0:
        return []
    return sorted_records[-lookback:]


def positional_frequency(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> Dict[int, Dict[int, int]]:
    """返回按位频率：{position: {digit: count}}。"""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Counter] = {i: Counter() for i in range(POSITION_COUNT)}
    for record in sliced:
        nums = record.groups.get("pos", [])
        for idx, n in enumerate(nums[:POSITION_COUNT]):
            if n in DIGIT_POOL:
                result[idx][n] += 1
    return {idx: dict(counter) for idx, counter in result.items()}


def positional_weights(
    records: List[DrawRecord], lookback: int = 100, smoothing: float = 1.0
) -> Dict[int, List[float]]:
    """带拉普拉斯平滑的按位权重。"""
    freq = positional_frequency(records, lookback)
    weights: Dict[int, List[float]] = {}
    for pos in range(POSITION_COUNT):
        pos_freq = freq.get(pos, {})
        total = sum(pos_freq.values()) + smoothing * len(DIGIT_POOL)
        weights[pos] = [
            (pos_freq.get(d, 0) + smoothing) / total for d in DIGIT_POOL
        ]
    return weights


def sum_tail_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """和尾（和值 mod 10）统计。"""
    sliced = _slice_records(records, lookback)
    tails = [sum(r.groups.get("pos", [])[:POSITION_COUNT]) % 10 for r in sliced]
    if not tails:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    tails.sort()
    n = len(tails)
    median = tails[n // 2] if n % 2 else (tails[n // 2 - 1] + tails[n // 2]) / 2
    return {"min": min(tails), "max": max(tails), "avg": sum(tails) / n, "median": median}


def span_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """跨度（最大-最小）统计。"""
    sliced = _slice_records(records, lookback)
    spans = []
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        if nums:
            spans.append(max(nums) - min(nums))
    if not spans:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    spans.sort()
    n = len(spans)
    median = spans[n // 2] if n % 2 else (spans[n // 2 - 1] + spans[n // 2]) / 2
    return {"min": min(spans), "max": max(spans), "avg": sum(spans) / n, "median": median}


def road_012_statistics(
    records: List[DrawRecord], lookback: int = 100
) -> Dict[int, List[float]]:
    """每位012路（mod 3）比例：{position: [p0, p1, p2]}。"""
    sliced = _slice_records(records, lookback)
    counts: Dict[int, List[int]] = {i: [0, 0, 0] for i in range(POSITION_COUNT)}
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        for idx, n in enumerate(nums):
            counts[idx][n % 3] += 1
    result: Dict[int, List[float]] = {}
    for pos, cnts in counts.items():
        total = sum(cnts)
        result[pos] = [c / total if total else 1 / 3 for c in cnts]
    return result


def fc3d_bet_type(numbers: List[int]) -> str:
    """判断3D号码形态：豹子号、组选3、组选6。"""
    if len(numbers) != POSITION_COUNT:
        return "未知"
    unique = len(set(numbers))
    if unique == 1:
        return "豹子号"
    if unique == 2:
        return "组选3"
    return "组选6"


def shape_ratio(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """历史形态比例：豹子/组三/组六。"""
    sliced = _slice_records(records, lookback)
    total = len(sliced)
    if total == 0:
        return {"leopard": 1 / 3, "group3": 1 / 3, "group6": 1 / 3}
    counts = {"leopard": 0, "group3": 0, "group6": 0}
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        bet_type = fc3d_bet_type(nums)
        if bet_type == "豹子号":
            counts["leopard"] += 1
        elif bet_type == "组选3":
            counts["group3"] += 1
        else:
            counts["group6"] += 1
    return {k: v / total for k, v in counts.items()}


def overall_odd_even_ratio(records: List[DrawRecord], lookback: int = 100) -> Tuple[float, float]:
    """整体奇偶比例（3D 9个数字中奇数判定）."""
    sliced = _slice_records(records, lookback)
    odd = even = 0
    for record in sliced:
        for n in record.groups.get("pos", [])[:POSITION_COUNT]:
            if n % 2 == 1:
                odd += 1
            else:
                even += 1
    total = odd + even
    if total == 0:
        return 0.5, 0.5
    return odd / total, even / total


def overall_high_low_ratio(
    records: List[DrawRecord], lookback: int = 100, border: int = 5
) -> Tuple[float, float]:
    """整体大小比例，>= border 为大号。"""
    sliced = _slice_records(records, lookback)
    high = low = 0
    for record in sliced:
        for n in record.groups.get("pos", [])[:POSITION_COUNT]:
            if n >= border:
                high += 1
            else:
                low += 1
    total = high + low
    if total == 0:
        return 0.5, 0.5
    return high / total, low / total


def sum_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """和值统计。"""
    sliced = _slice_records(records, lookback)
    sums = [sum(r.groups.get("pos", [])[:POSITION_COUNT]) for r in sliced]
    if not sums:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    sums.sort()
    n = len(sums)
    median = sums[n // 2] if n % 2 else (sums[n // 2 - 1] + sums[n // 2]) / 2
    return {"min": min(sums), "max": max(sums), "avg": sum(sums) / n, "median": median}
