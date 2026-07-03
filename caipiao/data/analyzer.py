"""历史数据分析器（多彩种统一）.

``DrawAnalyzer`` 基于 ``LotteryProfile`` 对任意彩种做统计分析。
``LotteryAnalyzer`` 保留为双色球专用别名，方法签名与行为完全兼容。
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from ..core.profile import SSQ, LotteryProfile, NumberGroup
from .models import DrawRecord


class DrawAnalyzer:
    """基于历史开奖数据进行统计分析（彩种无关）."""

    def __init__(self, records: List[DrawRecord], profile: LotteryProfile | None = None) -> None:
        self.profile = profile or (records[0].profile if records else SSQ)
        self.records = sorted(records, key=lambda r: r.draw_date)

    # ------------------------------------------------------------------ #
    # 按组频率 / 热冷 / 遗漏
    # ------------------------------------------------------------------ #
    def frequency(self, group_key: str, last_n: Optional[int] = None) -> Dict[int, int]:
        records = self._slice(last_n)
        counter: Counter = Counter()
        for record in records:
            counter.update(record.groups.get(group_key, []))
        return dict(counter)

    def hot(self, group_key: str, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        freq = self.frequency(group_key, last_n)
        return [n for n, _ in Counter(freq).most_common(top_n)]

    def cold(self, group_key: str, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        freq = self.frequency(group_key, last_n)
        if group_key not in self.profile.group_keys:
            raise ValueError(f"Group {group_key} not found in profile {self.profile.key}")
        group = self.profile.group(group_key)
        return sorted(group.values, key=lambda n: freq.get(n, 0))[:top_n]

    def missing(self, group_key: str, last_n: int = 50) -> List[Tuple[int, int]]:
        records = self._slice(last_n)
        if group_key not in self.profile.group_keys:
            raise ValueError(f"Group {group_key} not found in profile {self.profile.key}")
        group = self.profile.group(group_key)
        missing: Dict[int, int] = {n: last_n for n in group.values}
        for idx, record in enumerate(reversed(records)):
            for ball in record.groups.get(group_key, []):
                if ball in missing and missing[ball] == last_n:
                    missing[ball] = idx
        return sorted(missing.items(), key=lambda x: x[1], reverse=True)

    # ------------------------------------------------------------------ #
    # 主号码组综合统计（奇偶、大小、和值、连号、常见组合）
    # ------------------------------------------------------------------ #
    def _primary_numbers(self, record: DrawRecord) -> List[int]:
        """取出用于整体统计的号码（默认主组，3D 取 pos 组全部，kl8 取 main 组全部）。"""
        g = self.profile.primary_group
        return list(record.groups.get(g.key, []))

    def odd_even_ratio(self, last_n: Optional[int] = None) -> Tuple[float, float]:
        records = self._slice(last_n)
        odd = sum(1 for r in records for b in self._primary_numbers(r) if b % 2 == 1)
        even = sum(1 for r in records for b in self._primary_numbers(r) if b % 2 == 0)
        total = odd + even
        if total == 0:
            return 0.5, 0.5
        return odd / total, even / total

    def high_low_ratio(self, last_n: Optional[int] = None) -> Tuple[float, float]:
        records = self._slice(last_n)
        border = self.profile.primary_group.high_low_border
        high = sum(1 for r in records for b in self._primary_numbers(r) if b >= border)
        low = sum(1 for r in records for b in self._primary_numbers(r) if b < border)
        total = high + low
        if total == 0:
            return 0.5, 0.5
        return high / total, low / total

    def sum_statistics(self, last_n: Optional[int] = None) -> Dict[str, float]:
        records = self._slice(last_n)
        sums = [sum(self._primary_numbers(r)) for r in records]
        if not sums:
            return {"min": 0, "max": 0, "avg": 0, "median": 0}
        sums.sort()
        n = len(sums)
        median = sums[n // 2] if n % 2 else (sums[n // 2 - 1] + sums[n // 2]) / 2
        return {
            "min": min(sums),
            "max": max(sums),
            "avg": sum(sums) / n,
            "median": median,
        }

    def consecutive_frequency(self, last_n: Optional[int] = None) -> float:
        records = self._slice(last_n)
        if not records:
            return 0.0
        count = 0
        for record in records:
            nums = sorted(self._primary_numbers(record))
            for i in range(len(nums) - 1):
                if nums[i] + 1 == nums[i + 1]:
                    count += 1
                    break
        return count / len(records)

    def common_pairs(self, top_n: int = 10, last_n: Optional[int] = None) -> List[Tuple[Tuple[int, int], int]]:
        records = self._slice(last_n)
        pair_counter: Counter = Counter()
        for record in records:
            nums = sorted(self._primary_numbers(record))
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = tuple(sorted([nums[i], nums[j]]))
                    pair_counter[pair] += 1
        return pair_counter.most_common(top_n)

    # ------------------------------------------------------------------ #
    # 按位组（3D）辅助统计
    # ------------------------------------------------------------------ #
    def positional_frequency(self, last_n: Optional[int] = None) -> Dict[int, Dict[int, int]]:
        """返回按位的频率，如 {0: {0:12, 1:15...}, ...}，仅对 positional 彩种有意义。"""
        records = self._slice(last_n)
        result: Dict[int, Counter] = {}
        for record in records:
            nums = record.groups.get(self.profile.primary_group.key, [])
            for idx, n in enumerate(nums):
                result.setdefault(idx, Counter())[n] += 1
        return {idx: dict(counter) for idx, counter in result.items()}

    def span(self, last_n: Optional[int] = None) -> Dict[str, float]:
        """跨度统计（仅对按位/有主组号码的彩种）：每期最大号-最小号。"""
        records = self._slice(last_n)
        spans = []
        for record in records:
            nums = self._primary_numbers(record)
            if nums:
                spans.append(max(nums) - min(nums))
        if not spans:
            return {"min": 0, "max": 0, "avg": 0, "median": 0}
        spans.sort()
        n = len(spans)
        median = spans[n // 2] if n % 2 else (spans[n // 2 - 1] + spans[n // 2]) / 2
        return {"min": min(spans), "max": max(spans), "avg": sum(spans) / n, "median": median}

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def last_draw(self) -> Optional[DrawRecord]:
        return self.records[-1] if self.records else None

    def _slice(self, last_n: Optional[int]) -> List[DrawRecord]:
        if last_n is None or last_n >= len(self.records):
            return self.records
        if last_n <= 0:
            return []
        return self.records[-last_n:]

    def summary(self) -> Dict:
        """返回综合统计摘要（尽量与原 LotteryAnalyzer.summary 字段一致）。"""
        primary = self.profile.primary_group.key
        result = {
            "total_records": len(self.records),
            "hot_30": self.hot(primary, 10, 30),
            "cold_30": self.cold(primary, 10, 30),
            "missing_50": self.missing(primary, 50)[:10],
            "odd_even_ratio": self.odd_even_ratio(100),
            "high_low_ratio": self.high_low_ratio(100),
            "sum_stats": self.sum_statistics(100),
            "consecutive_ratio": self.consecutive_frequency(100),
        }
        # 双色球额外保留旧字段名，便于 UI 兼容
        if self.profile.key == "ssq":
            result.update({
                "hot_reds_30": result["hot_30"],
                "cold_reds_30": result["cold_30"],
                "missing_reds_50": result["missing_50"],
                "hot_blues_30": self.hot("blue", 5, 30),
            })
        return result


# -------------------------------------------------------------------------- #
# 双色球兼容别名
# -------------------------------------------------------------------------- #
class _LegacyLotteryAnalyzer(DrawAnalyzer):
    """完全兼容原 ``LotteryAnalyzer`` 的双色球分析器.

    原方法 ``red_frequency`` / ``hot_reds`` / ``missing_reds`` 等全部保留，
    内部委托到 :class:`DrawAnalyzer` 的通用实现。
    """

    def __init__(self, records: List[DrawRecord]) -> None:
        super().__init__(records, profile=SSQ)

    # 原 SSQ 专用方法
    def red_frequency(self, last_n: Optional[int] = None) -> Dict[int, int]:
        return self.frequency("red", last_n)

    def blue_frequency(self, last_n: Optional[int] = None) -> Dict[int, int]:
        return self.frequency("blue", last_n)

    def hot_reds(self, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        return self.hot("red", top_n, last_n)

    def cold_reds(self, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        return self.cold("red", top_n, last_n)

    def hot_blues(self, top_n: int = 5, last_n: Optional[int] = None) -> List[int]:
        return self.hot("blue", top_n, last_n)

    def missing_reds(self, last_n: int = 50) -> List[Tuple[int, int]]:
        return self.missing("red", last_n)

    def missing_blues(self, last_n: int = 50) -> List[Tuple[int, int]]:
        return self.missing("blue", last_n)


LotteryAnalyzer = _LegacyLotteryAnalyzer
