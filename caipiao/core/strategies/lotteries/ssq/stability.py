"""双色球策略稳定化工具.

移植自福彩3D stability.py，适配双色球红球(1-33)/蓝球(1-16)结构。
提供 z-score 标准化、几何分布遗漏检验、χ²均匀性检验、温度控制 softmax。
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from typing import Any

from .....data.models import DrawRecord

RED_POOL = list(range(1, 34))   # 1-33
BLUE_POOL = list(range(1, 17))  # 1-16
RED_COUNT = 6
BLUE_COUNT = 1


def _slice_records(
    records: list[DrawRecord], lookback: int | None = None
) -> list[DrawRecord]:
    if lookback is None or lookback >= len(records):
        return records
    return records[-lookback:]


def _history_content_hash(
    records: list[DrawRecord], lookback: int | None = None
) -> str:
    sliced = _slice_records(records, lookback)
    parts = []
    for r in sliced:
        red_str = ",".join(str(n) for n in r.groups.get("red", []))
        blue_str = ",".join(str(n) for n in r.groups.get("blue", []))
        parts.append(f"{r.issue or ''}:{r.draw_date.isoformat()}:{red_str}:{blue_str}")
    content = ";".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def deterministic_seed(
    options: dict,
    history: list[DrawRecord],
    lookback: int | None = None,
    strategy_id: str = "",
) -> int:
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    h = _history_content_hash(history, lookback)
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode()).hexdigest()
    return int(raw, 16) % (2**31)


def stable_frequency(
    records: list[DrawRecord],
    lookback: int | None = None,
    smoothing: float = 1.0,
) -> dict[int, float]:
    """返回拉普拉斯平滑后的红球概率分布 {number: probability}."""
    sliced = _slice_records(records, lookback)
    counter: dict[int, int] = {n: 0 for n in RED_POOL}
    for r in sliced:
        for n in r.groups.get("red", []):
            if n in counter:
                counter[n] += 1
    total = sum(counter.values()) + smoothing * len(RED_POOL)
    return {n: (counter[n] + smoothing) / total for n in RED_POOL}


def stable_blue_frequency(
    records: list[DrawRecord],
    lookback: int | None = None,
    smoothing: float = 1.0,
) -> dict[int, float]:
    """返回拉普拉斯平滑后的蓝球概率分布 {number: probability}."""
    sliced = _slice_records(records, lookback)
    counter: dict[int, int] = {n: 0 for n in BLUE_POOL}
    for r in sliced:
        for n in r.groups.get("blue", []):
            if n in counter:
                counter[n] += 1
    total = sum(counter.values()) + smoothing * len(BLUE_POOL)
    return {n: (counter[n] + smoothing) / total for n in BLUE_POOL}


def raw_missing_periods(
    records: list[DrawRecord], lookback: int | None = None
) -> dict[int, int]:
    """返回红球原始遗漏期数 {number: periods}."""
    sliced = _slice_records(records, lookback)
    window = len(sliced) if sliced else 1
    missing: dict[int, int] = {n: window for n in RED_POOL}
    red_records = [r.groups.get("red", []) for r in sliced]
    for idx, reds in enumerate(reversed(red_records)):
        for n in reds:
            if n in missing and missing[n] == window:
                missing[n] = idx
    return missing


def raw_blue_missing_periods(
    records: list[DrawRecord], lookback: int | None = None
) -> dict[int, int]:
    """返回蓝球原始遗漏期数 {number: periods}."""
    sliced = _slice_records(records, lookback)
    window = len(sliced) if sliced else 1
    missing: dict[int, int] = {n: window for n in BLUE_POOL}
    blue_records = [r.groups.get("blue", []) for r in sliced]
    for idx, blues in enumerate(reversed(blue_records)):
        for n in blues:
            if n in missing and missing[n] == window:
                missing[n] = idx
    return missing


def geometric_missing_zscore(
    missing_periods: dict[int, int], p: float = 1 / 33
) -> dict[int, float]:
    """将红球遗漏期数转为几何分布 z-score.

    在均匀假设(p=1/33)下:
        E[X] = (1-p)/p = 32
        sigma = sqrt(1-p)/p ≈ 5.63
    z > 1.96 表示 95% 置信水平下统计显著偏冷。
    """
    expected = (1 - p) / p
    sigma = math.sqrt(1 - p) / p
    if sigma < 1e-10:
        return {n: 0.0 for n in missing_periods}
    return {n: (v - expected) / sigma for n, v in missing_periods.items()}


def geometric_blue_missing_zscore(
    missing_periods: dict[int, int], p: float = 1 / 16
) -> dict[int, float]:
    """将蓝球遗漏期数转为几何分布 z-score.

    在均匀假设(p=1/16)下:
        E[X] = (1-p)/p = 15
        sigma = sqrt(1-p)/p ≈ 3.84
    """
    expected = (1 - p) / p
    sigma = math.sqrt(1 - p) / p
    if sigma < 1e-10:
        return {n: 0.0 for n in missing_periods}
    return {n: (v - expected) / sigma for n, v in missing_periods.items()}


def _zscore_normalize(scores: dict[int, float]) -> dict[int, float]:
    """z-score 标准化: z = (x - mean) / std."""
    vals = list(scores.values())
    if len(vals) < 2:
        return {n: 0.0 for n in scores}
    mean = statistics.mean(vals)
    try:
        std = statistics.stdev(vals)
    except statistics.StatisticsError:  # pragma: no cover
        std = 0.0  # pragma: no cover
    if std < 1e-10:
        return {n: 0.0 for n in scores}
    return {n: (scores[n] - mean) / std for n in scores}


def softmax_scores(values: list[float], temperature: float = 1.0) -> list[float]:
    """带温度参数的 softmax."""
    if temperature <= 0:
        temperature = 1.0
    max_v = max(values)
    exps = [math.exp((v - max_v) / temperature) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def stable_scores(
    hot_scores: dict[int, float],
    cold_scores: dict[int, float],
    hot_weight: float,
    cold_weight: float,
    temperature: float = 1.0,
) -> list[float]:
    """合并热分和冷分，输出 softmax 概率分布（红球 1-33）."""
    weight_sum = hot_weight + cold_weight
    if weight_sum <= 0:
        weight_sum = 1.0
    hot_z = _zscore_normalize(hot_scores)
    cold_z = _zscore_normalize(cold_scores)
    logits = [
        (hot_weight * hot_z[n] + cold_weight * cold_z[n]) / weight_sum
        for n in RED_POOL
    ]
    return softmax_scores(logits, temperature)


def stable_blue_scores(
    hot_scores: dict[int, float],
    cold_scores: dict[int, float],
    hot_weight: float,
    cold_weight: float,
    temperature: float = 1.0,
) -> list[float]:
    """合并热分和冷分，输出 softmax 概率分布（蓝球 1-16）."""
    weight_sum = hot_weight + cold_weight
    if weight_sum <= 0:
        weight_sum = 1.0
    hot_z = _zscore_normalize(hot_scores)
    cold_z = _zscore_normalize(cold_scores)
    logits = [
        (hot_weight * hot_z[n] + cold_weight * cold_z[n]) / weight_sum
        for n in BLUE_POOL
    ]
    return softmax_scores(logits, temperature)


def chi_square_uniform_test(counts: list[int]) -> tuple[float, bool]:
    """χ² 拟合优度检验: 观测频率是否偏离均匀分布.

    H0: 每个号码出现概率相等。
    自由度 df = len(counts) - 1。
    """
    n = sum(counts)
    k = len(counts)
    if n == 0:
        return 0.0, True
    expected = n / k
    if expected == 0:  # pragma: no cover
        return 0.0, True
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    # 临界值取决于自由度
    if k == 33:
        critical = 46.19  # df=32, 5% 显著性
    elif k == 16:
        critical = 25.00  # df=15, 5% 显著性
    else:
        critical = k + 1.645 * math.sqrt(2 * (k - 1))  # 近似
    return chi2, chi2 < critical


def sample_weighted(
    rng: random.Random, values: list[Any], probabilities: list[float]
) -> Any:
    """加权采样."""
    total = sum(probabilities)
    if total <= 0:
        return rng.choice(values)
    return rng.choices(values, weights=probabilities, k=1)[0]


def weighted_sample_reds(
    red_probs: list[float],
    count: int,
    rng: random.Random,
) -> list[int]:
    """按概率分布无放回采样红球.

    使用 Gumbel-max trick (等价于 log-uniform + argmax) 实现无放回采样，
    保持概率分布形状，避免拒绝采样在概率集中时的低效。
    """
    log_probs = []
    for p in red_probs:
        if p > 0:
            log_probs.append(-math.log(rng.random()) / p)
        else:
            log_probs.append(float("inf"))
    # 按 Gumbel key 降序取前 count 个
    indexed = list(enumerate(log_probs))
    indexed.sort(key=lambda x: x[1], reverse=True)
    selected = sorted(RED_POOL[i] for i, _ in indexed[:count])
    return selected
