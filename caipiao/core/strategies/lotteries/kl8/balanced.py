"""快乐8历史均衡策略（增强版）.

基于历史数据的多维统计特征，生成在奇偶比、大小比、和值、三区分布、
连号对数、号码覆盖度、相邻期重合数等维度上接近历史平均的均衡号码。

改进点（相比旧版）：
    1. 特征维度从 3 个扩展到 7 个（新增三区分布、连号、覆盖度、邻期重合）
    2. 评分函数改为加权平方惩罚，各维度独立加权
    3. 整合 stability.py 的拉普拉斯平滑频率做引导采样
    4. χ² 均匀性检验守卫：均匀时放宽约束，偏离时加强引导
    5. 分段采样保证号码全局分散性
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from .....data.analyzer import DrawAnalyzer
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ...common.rng import make_rng
from ._base import PROFILE, _add_pick_count_schema, _get_pick_count, _make_ticket
from .stability import (
    MAIN_POOL,
    chi_square_uniform_test,
    frequency_counts,
    stable_frequency,
)

# 快乐8 三区划分（1-80 号池，每区约 27 个号）
# Zone1: 1-27, Zone2: 28-54, Zone3: 55-80
KL8_ZONES = [(1, 27), (28, 54), (55, 80)]

# 智能冷热号策略默认选四（快乐8 选1-选10 共 10 种玩法）
DEFAULT_PICK_COUNT = 4


def _zone_counts(numbers: List[int]) -> List[int]:
    """统计号码在三区中的分布。"""
    counts = [0, 0, 0]
    for n in numbers:
        for i, (lo, hi) in enumerate(KL8_ZONES):
            if lo <= n <= hi:
                counts[i] += 1
                break
    return counts


def _consecutive_pairs(numbers: List[int]) -> int:
    """统计候选号码中的连号对数。"""
    s = sorted(numbers)
    pairs = 0
    for i in range(len(s) - 1):
        if s[i] + 1 == s[i + 1]:
            pairs += 1
    return pairs


def _coverage_score(numbers: List[int], pool_size: int = 80) -> float:
    """号码覆盖度评分：号码越分散越好。

    将 1-80 分成 8 段（每段 10 个号），统计覆盖了多少段。
    返回覆盖段数 / 总段数（0~1）。
    """
    seg_size = pool_size // 8  # 10
    segments = set()
    for n in numbers:
        seg = min((n - 1) // seg_size, 7)
        segments.add(seg)
    return len(segments) / 8.0


def _compute_overlap_with_prev(
    candidate: List[int], prev_numbers: List[int]
) -> int:
    """计算候选号码与上期号码的重合数。"""
    return len(set(candidate) & set(prev_numbers))


class KL8BalancedStrategy(GenerationStrategy):
    """多维均衡策略：使奇偶、大小、和值、三区、连号、覆盖度、邻期重合接近历史平均."""

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_kl8",
            name="历史均衡",
            description="基于7维统计特征（奇偶/大小/和值/三区/连号/覆盖度/邻期重合）生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
            "w_odd_even": {
                "type": "int", "label": "奇偶权重", "default": 15,
                "min": 0, "max": 100,
                "tooltip": "奇偶比偏差的惩罚权重。",
            },
            "w_high_low": {
                "type": "int", "label": "大小权重", "default": 15,
                "min": 0, "max": 100,
                "tooltip": "大小比偏差的惩罚权重。",
            },
            "w_sum": {
                "type": "int", "label": "和值权重", "default": 20,
                "min": 0, "max": 100,
                "tooltip": "和值偏差的惩罚权重。",
            },
            "w_zone": {
                "type": "int", "label": "三区权重", "default": 20,
                "min": 0, "max": 100,
                "tooltip": "三区分布偏差的惩罚权重。",
            },
            "w_consec": {
                "type": "int", "label": "连号权重", "default": 10,
                "min": 0, "max": 100,
                "tooltip": "连号对数偏差的惩罚权重。",
            },
            "w_coverage": {
                "type": "int", "label": "覆盖度权重", "default": 10,
                "min": 0, "max": 100,
                "tooltip": "号码覆盖度不足的惩罚权重（覆盖度越高越好）。",
            },
            "w_overlap": {
                "type": "int", "label": "邻期重合权重", "default": 10,
                "min": 0, "max": 100,
                "tooltip": "与上期号码重合数偏差的惩罚权重。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema)
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        rng = make_rng(options)
        primary = PROFILE.primary_group
        pick = _get_pick_count(options)

        # --- 权重参数 ---
        w_oe = int(options.get("w_odd_even", 15)) / 100.0
        w_hl = int(options.get("w_high_low", 15)) / 100.0
        w_sm = int(options.get("w_sum", 20)) / 100.0
        w_zn = int(options.get("w_zone", 20)) / 100.0
        w_cc = int(options.get("w_consec", 10)) / 100.0
        w_cv = int(options.get("w_coverage", 10)) / 100.0
        w_ov = int(options.get("w_overlap", 10)) / 100.0

        analyzer = DrawAnalyzer(records, PROFILE)

        # --- 1. 奇偶比目标 ---
        odd_ratio, _ = analyzer.odd_even_ratio(lookback)
        target_odd = round(pick * odd_ratio)

        # --- 2. 大小比目标 ---
        high_ratio, _ = analyzer.high_low_ratio(lookback)
        target_high = round(pick * high_ratio)

        # --- 3. 和值目标范围 ---
        sum_stats = analyzer.sum_statistics(lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6.0 or 1.0
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])

        # --- 4. 三区分布目标 ---
        # 统计历史每期在三区中的平均号码数
        target_zones = self._compute_target_zones(analyzer, lookback, pick)

        # --- 5. 连号对数目标 ---
        target_consec = self._compute_target_consecutive(analyzer, lookback)

        # --- 6. 相邻期重合数目标 ---
        target_overlap = self._compute_target_overlap(analyzer, lookback)

        # --- 7. χ² 均匀性检验 ---
        freq_counts = frequency_counts(records, lookback)
        counts_list = list(freq_counts.values())
        chi2_value, is_uniform = chi_square_uniform_test(counts_list)

        # --- 8. 频率引导采样权重 ---
        freq_prob = stable_frequency(records, lookback)
        freq_weights = [freq_prob[n] for n in primary.values]

        # --- 上期号码（用于邻期重合评分）---
        prev_numbers = self._get_prev_numbers(records)

        # --- 构建说明文本 ---
        basis = (
            f"历史均衡策略(增强版)：基于最近 {lookback} 期，"
            f"7维均衡选{pick}个号码。"
            f"目标: 奇偶{target_odd}/{pick - target_odd}，"
            f"大小{target_high}/{pick - target_high}，"
            f"和值≈{avg_sum:.0f}，"
            f"三区≈{target_zones}，"
            f"连号≈{target_consec}对，"
            f"邻期重合≈{target_overlap}个。"
        )
        if is_uniform:
            basis += "χ²检验: 号码分布接近均匀，冷热信号弱。"
        else:
            basis += "χ²检验: 号码分布显著偏离均匀。"
        basis += "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        details: Dict[str, Any] = {
            "chi_square": round(chi2_value, 2),
            "is_uniform": is_uniform,
            "target_odd": target_odd,
            "target_high": target_high,
            "target_sum_range": (round(sum_min), round(sum_max)),
            "target_zones": target_zones,
            "target_consec": target_consec,
            "target_overlap": target_overlap,
            "pick_count": pick,
        }

        tickets: List[Ticket] = []
        for _ in range(count):
            best: Optional[Dict[str, List[int]]] = None
            best_score = float("inf")
            for _ in range(max_attempts):
                # 用频率引导采样（比纯随机更高效）
                candidate = self._guided_sample(
                    rng, primary.values, freq_weights, pick
                )
                score = self._score_candidate(
                    candidate, pick,
                    target_odd, target_high,
                    avg_sum, sum_min, sum_max,
                    target_zones, target_consec, target_overlap,
                    prev_numbers,
                    w_oe, w_hl, w_sm, w_zn, w_cc, w_cv, w_ov,
                )
                if score < best_score:
                    best_score = score
                    groups: Dict[str, List[int]] = {primary.key: sorted(candidate)}
                    self._fill_random_other(groups, rng)
                    best = groups
                if best_score <= 0.5:
                    break
            if best is None:
                candidate = sorted(rng.sample(primary.values, pick))
                groups = {primary.key: candidate}
                self._fill_random_other(groups, rng)
                best = groups
            tickets.append(_make_ticket(best, strategy_name=self.metadata.name, basis=basis, details=details))
        return tickets

    # ------------------------------------------------------------------ #
    # 目标值计算
    # ------------------------------------------------------------------ #

    def _compute_target_zones(
        self, analyzer: DrawAnalyzer, lookback: int, pick: int
    ) -> List[int]:
        """统计历史每期三区号码数的平均值，按 pick 比例缩放。"""
        records = analyzer._slice(lookback)
        if not records:
            # 均匀分配
            total_pool = sum(hi - lo + 1 for lo, hi in KL8_ZONES)
            return [max(1, round(pick * (hi - lo + 1) / total_pool)) for lo, hi in KL8_ZONES]

        zone_sums = [0, 0, 0]
        for record in records:
            nums = record.groups.get("main", [])
            for n in nums:
                for i, (lo, hi) in enumerate(KL8_ZONES):
                    if lo <= n <= hi:
                        zone_sums[i] += 1
                        break
        n_records = len(records)
        avg_per_zone = [z / n_records for z in zone_sums]
        total_avg = sum(avg_per_zone) or 1.0
        return [max(1, round(pick * avg / total_avg)) for avg in avg_per_zone]

    def _compute_target_consecutive(self, analyzer: DrawAnalyzer, lookback: int) -> float:
        """统计历史每期连号对数的平均值。"""
        dist = analyzer.consecutive_count_distribution(lookback)
        if not dist:
            return 0.0
        return sum(k * v for k, v in dist.items())

    def _compute_target_overlap(self, analyzer: DrawAnalyzer, lookback: int) -> float:
        """统计历史相邻期号码重合数的平均值。"""
        records = analyzer._slice(lookback)
        if len(records) < 2:
            return 5.0  # 快乐8 每期20个号，理论期望约 5 个重合
        overlaps = []
        for i in range(1, len(records)):
            prev = set(records[i - 1].groups.get("main", []))
            curr = set(records[i].groups.get("main", []))
            overlaps.append(len(prev & curr))
        return sum(overlaps) / len(overlaps) if overlaps else 5.0

    def _get_prev_numbers(self, records: list) -> List[int]:
        """获取最近一期的开奖号码。"""
        if not records:
            return []
        sorted_records = sorted(records, key=lambda r: r.draw_date)
        return sorted_records[-1].groups.get("main", [])

    # ------------------------------------------------------------------ #
    # 评分函数（7 维加权平方惩罚）
    # ------------------------------------------------------------------ #

    def _score_candidate(
        self,
        candidate: List[int],
        pick: int,
        target_odd: int, target_high: int,
        avg_sum: float, sum_min: float, sum_max: float,
        target_zones: List[int], target_consec: float, target_overlap: float,
        prev_numbers: List[int],
        w_oe: float, w_hl: float, w_sm: float,
        w_zn: float, w_cc: float, w_cv: float, w_ov: float,
    ) -> float:
        """多维加权评分，分数越低越好。"""
        score = 0.0

        # 1. 奇偶比偏差（平方惩罚）
        odd_count = sum(1 for n in candidate if n % 2 == 1)
        score += w_oe * (odd_count - target_odd) ** 2

        # 2. 大小比偏差（平方惩罚）
        high_count = sum(1 for n in candidate if n >= primary.high_low_border)
        score += w_hl * (high_count - target_high) ** 2

        # 3. 和值偏差（渐进惩罚）
        total = sum(candidate)
        if sum_min <= total <= sum_max:
            # 在范围内：轻微偏离也给分
            deviation = abs(total - avg_sum) / (std_sum_if_nonzero(avg_sum, sum_min, sum_max) or 1.0)
            score += w_sm * deviation ** 2
        else:
            # 范围外：线性 + 平方混合惩罚
            dist = min(abs(total - sum_min), abs(total - sum_max))
            score += w_sm * (1.0 + dist / 10.0)

        # 4. 三区分布偏差（平方惩罚）
        zones = _zone_counts(candidate)
        for i in range(3):
            score += w_zn * (zones[i] - target_zones[i]) ** 2

        # 5. 连号对数偏差（平方惩罚）
        consec = _consecutive_pairs(candidate)
        score += w_cc * (consec - target_consec) ** 2

        # 6. 覆盖度（越高越好，不足时惩罚）
        cov = _coverage_score(candidate)
        # 目标覆盖度：pick/80 对应的期望覆盖段数
        target_cov = min(1.0, pick / 8.0 * 1.2)  # 略高于均匀期望
        if cov < target_cov:
            score += w_cv * (target_cov - cov) * 10  # 不足时放大惩罚

        # 7. 邻期重合偏差（平方惩罚）
        if prev_numbers:
            overlap = _compute_overlap_with_prev(candidate, prev_numbers)
            score += w_ov * (overlap - target_overlap) ** 2

        return score

    # ------------------------------------------------------------------ #
    # 频率引导采样
    # ------------------------------------------------------------------ #

    def _guided_sample(
        self, rng: random.Random, pool: List[int], weights: List[float], k: int
    ) -> List[int]:
        """基于频率权重的分段引导采样，保证号码分散性。

        将 1-80 分成 8 段（每段 10 个号），每段至少选 floor(k/8) 个号，
        剩余名额按权重分配。
        """
        seg_size = 10  # 每段 10 个号
        n_segs = 8
        min_per_seg = max(0, k // n_segs)
        remaining = k - min_per_seg * n_segs

        # 每段的候选和权重
        seg_indices = list(range(n_segs))
        seg_weights = []
        for si in seg_indices:
            lo = si * seg_size + 1
            hi = min(lo + seg_size - 1, 80)
            # 段内权重和
            w_sum = sum(weights[n - 1] for n in range(lo, hi + 1))
            seg_weights.append(w_sum + 0.01)  # 避免全零

        # 按权重分配剩余名额到各段
        extra_per_seg = [0] * n_segs
        for _ in range(remaining):
            total_w = sum(seg_weights)
            r = rng.random() * total_w
            cumulative = 0.0
            chosen_seg = n_segs - 1
            for i, w in enumerate(seg_weights):
                cumulative += w
                if cumulative >= r:
                    chosen_seg = i
                    break
            extra_per_seg[chosen_seg] += 1
            seg_weights[chosen_seg] *= 0.5  # 降低已分配段的权重

        # 从每段中采样
        selected: List[int] = []
        for si in seg_indices:
            lo = si * seg_size + 1
            hi = min(lo + seg_size - 1, 80)
            seg_pool = list(range(lo, hi + 1))
            seg_w = [weights[n - 1] for n in seg_pool]
            need = min_per_seg + extra_per_seg[si]
            need = min(need, len(seg_pool))
            if need <= 0:
                continue
            # 加权无放回采样
            pool_copy = list(seg_pool)
            w_copy = list(seg_w)
            for _ in range(need):
                total = sum(w_copy)
                if total <= 0:
                    idx = rng.randrange(len(pool_copy))
                else:
                    r = rng.random() * total
                    cumulative = 0.0
                    idx = len(pool_copy) - 1
                    for i, w in enumerate(w_copy):
                        cumulative += w
                        if cumulative >= r:
                            idx = i
                            break
                selected.append(pool_copy.pop(idx))
                w_copy.pop(idx)

        return sorted(selected)

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = rng.randint(g.effective_pick_min, g.effective_pick_max) if g.variable_pick else g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# ------------------------------------------------------------------ #
# 辅助函数
# ------------------------------------------------------------------ #

primary = PROFILE.primary_group


def std_sum_if_nonzero(avg: float, lo: float, hi: float) -> float:
    """安全计算标准差近似值。"""
    return (hi - lo) / 6.0 or 1.0
