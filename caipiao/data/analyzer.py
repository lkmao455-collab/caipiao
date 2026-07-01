"""历史数据分析器."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .models import DrawRecord


class LotteryAnalyzer:
    """基于历史开奖数据进行统计分析."""

    def __init__(self, records: List[DrawRecord]) -> None:
        self.records = sorted(records, key=lambda r: r.draw_date)

    def red_frequency(self, last_n: Optional[int] = None) -> Dict[int, int]:
        """统计红球出现频率."""
        records = self._slice(last_n)
        counter: Counter = Counter()
        for record in records:
            counter.update(record.red_balls)
        return dict(counter)

    def blue_frequency(self, last_n: Optional[int] = None) -> Dict[int, int]:
        """统计蓝球出现频率."""
        records = self._slice(last_n)
        counter: Counter = Counter(r.blue_ball for r in records)
        return dict(counter)

    def hot_reds(self, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        """返回最热红球."""
        freq = self.red_frequency(last_n)
        return [n for n, _ in Counter(freq).most_common(top_n)]

    def cold_reds(self, top_n: int = 10, last_n: Optional[int] = None) -> List[int]:
        """返回最冷红球."""
        freq = self.red_frequency(last_n)
        all_reds = list(range(1, 34))
        return sorted(all_reds, key=lambda n: freq.get(n, 0))[:top_n]

    def hot_blues(self, top_n: int = 5, last_n: Optional[int] = None) -> List[int]:
        """返回最热蓝球."""
        freq = self.blue_frequency(last_n)
        return [n for n, _ in Counter(freq).most_common(top_n)]

    def missing_reds(self, last_n: int = 50) -> List[Tuple[int, int]]:
        """返回红球遗漏值（已连续多少期未出现）."""
        records = self._slice(last_n)
        missing: Dict[int, int] = {n: last_n for n in range(1, 34)}
        for idx, record in enumerate(reversed(records)):
            for ball in record.red_balls:
                if missing[ball] == last_n:
                    missing[ball] = idx
        return sorted(missing.items(), key=lambda x: x[1], reverse=True)

    def missing_blues(self, last_n: int = 50) -> List[Tuple[int, int]]:
        """返回蓝球遗漏值."""
        records = self._slice(last_n)
        missing: Dict[int, int] = {n: last_n for n in range(1, 17)}
        for idx, record in enumerate(reversed(records)):
            ball = record.blue_ball
            if missing[ball] == last_n:
                missing[ball] = idx
        return sorted(missing.items(), key=lambda x: x[1], reverse=True)

    def odd_even_ratio(self, last_n: Optional[int] = None) -> Tuple[float, float]:
        """统计最近红球奇偶比例."""
        records = self._slice(last_n)
        odd = sum(1 for r in records for b in r.red_balls if b % 2 == 1)
        even = sum(1 for r in records for b in r.red_balls if b % 2 == 0)
        total = odd + even
        if total == 0:
            return 0.5, 0.5
        return odd / total, even / total

    def high_low_ratio(self, last_n: Optional[int] = None) -> Tuple[float, float]:
        """统计最近红球大小比例（以 17 为界）."""
        records = self._slice(last_n)
        high = sum(1 for r in records for b in r.red_balls if b >= 17)
        low = sum(1 for r in records for b in r.red_balls if b < 17)
        total = high + low
        if total == 0:
            return 0.5, 0.5
        return high / total, low / total

    def sum_statistics(self, last_n: Optional[int] = None) -> Dict[str, float]:
        """红球和值统计."""
        records = self._slice(last_n)
        sums = [sum(r.red_balls) for r in records]
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
        """统计包含连号记录的比例."""
        records = self._slice(last_n)
        if not records:
            return 0.0
        count = 0
        for record in records:
            reds = record.red_balls
            for i in range(len(reds) - 1):
                if reds[i] + 1 == reds[i + 1]:
                    count += 1
                    break
        return count / len(records)

    def common_pairs(self, top_n: int = 10, last_n: Optional[int] = None) -> List[Tuple[Tuple[int, int], int]]:
        """统计常见两号组合."""
        records = self._slice(last_n)
        pair_counter: Counter = Counter()
        for record in records:
            reds = record.red_balls
            for i in range(len(reds)):
                for j in range(i + 1, len(reds)):
                    pair = tuple(sorted([reds[i], reds[j]]))
                    pair_counter[pair] += 1
        return pair_counter.most_common(top_n)

    def last_draw(self) -> Optional[DrawRecord]:
        """返回最新一期记录."""
        return self.records[-1] if self.records else None

    def _slice(self, last_n: Optional[int]) -> List[DrawRecord]:
        """按最近期数切片."""
        if last_n is None or last_n >= len(self.records):
            return self.records
        return self.records[-last_n:]

    def summary(self) -> Dict:
        """返回综合统计摘要."""
        return {
            "total_records": len(self.records),
            "hot_reds_30": self.hot_reds(10, 30),
            "cold_reds_30": self.cold_reds(10, 30),
            "hot_blues_30": self.hot_blues(5, 30),
            "missing_reds_50": self.missing_reds(50)[:10],
            "odd_even_ratio": self.odd_even_ratio(100),
            "high_low_ratio": self.high_low_ratio(100),
            "sum_stats": self.sum_statistics(100),
            "consecutive_ratio": self.consecutive_frequency(100),
        }
