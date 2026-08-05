"""福彩3D策略稳定化工具."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from typing import Any

from .....data.models import DrawRecord
from .utils import DIGIT_POOL, POSITION_COUNT, _slice_records


def _history_content_hash(
    records: list[DrawRecord], lookback: int | None = None
) -> str:
    """根据历史数据内容生成短 hash."""
    sliced = _slice_records(records, lookback)
    parts = []
    for r in sliced:
        pos_str = ",".join(str(n) for n in r.groups.get("pos", []))
        parts.append(f"{r.issue or ''}:{r.draw_date.isoformat()}:{pos_str}")
    content = ";".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def deterministic_seed(
    options: dict,
    history: list[DrawRecord],
    lookback: int | None = None,
    strategy_id: str = "",
) -> int:
    """若 options 中无 seed，则基于历史内容派生确定性 seed."""
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    h = _history_content_hash(history, lookback)
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode()).hexdigest()
    return int(raw, 16) % (2**31)


def stable_frequency(
    records: list[DrawRecord], lookback: int | None = None, smoothing: float = 1.0
) -> dict[int, dict[int, float]]:
    """返回拉普拉斯平滑后的按位概率分布 {pos: {digit: probability}}."""
    sliced = _slice_records(records, lookback)
    result: dict[int, dict[int, float]] = {}
    for pos in range(POSITION_COUNT):
        counter: dict[int, int] = {d: 0 for d in DIGIT_POOL}
        for r in sliced:
            nums = r.groups.get("pos", [])
            if pos < len(nums) and nums[pos] in DIGIT_POOL:
                counter[nums[pos]] += 1
        total = sum(counter.values()) + smoothing * len(DIGIT_POOL)
        result[pos] = {d: (counter[d] + smoothing) / total for d in DIGIT_POOL}
    return result


def stable_missing(
    records: list[DrawRecord],
    lookback: int | None = None,
    cap: int | None = None,
) -> dict[int, dict[int, float]]:
    """返回截断并归一化到 [0,1] 的按位遗漏值 {pos: {digit: normalized_missing}}.

    归一化使用绝对基准（除以 effective_cap = lookback），
    而非当前数据中的 max，确保不同数据窗口下遗漏值可比：
    0.0 = 最近一期出现过；1.0 = 整个窗口内从未出现。
    """
    sliced = _slice_records(records, lookback)
    result: dict[int, dict[int, float]] = {}
    effective_cap = cap if cap is not None else (len(sliced) if sliced else 1)
    effective_cap = max(effective_cap, 1)
    for pos in range(POSITION_COUNT):
        pos_records = [
            r.groups["pos"][pos]
            for r in sliced
            if len(r.groups.get("pos", [])) > pos
        ]
        missing: dict[int, int] = {d: effective_cap for d in DIGIT_POOL}
        for idx, n in enumerate(reversed(pos_records)):
            if missing[n] == effective_cap:
                missing[n] = idx
        capped = {d: min(v, effective_cap) for d, v in missing.items()}
        result[pos] = {d: capped[d] / effective_cap for d in DIGIT_POOL}
    return result


def _zscore_normalize(scores: dict[int, float]) -> dict[int, float]:
    """z-score 标准化: z = (x - mean) / std.

    输出均值 0、标准差 1，是 softmax logits 的标准输入形式。

    相比旧的 max 归一化 (x / max(x)):
    - 消除偏移: max-norm 最小值不为 0 (如频率约 0.13)，z-score 均值为 0
    - 对异常值稳健: max-norm 受最大值支配，z-score 用全局均值和方差
    - softmax 区分力恢复: z-score 后值域约 [-2, +2]，softmax(Δz≈4, T=1) ≈ 55x

    当所有值相同 (std≈0) 时返回全 0，使 softmax 输出均匀分布。
    """
    vals = [scores[d] for d in DIGIT_POOL]
    if len(vals) < 2:
        return {d: 0.0 for d in DIGIT_POOL}
    mean = statistics.mean(vals)
    try:
        std = statistics.stdev(vals)
    except statistics.StatisticsError:  # pragma: no cover
        std = 0.0  # pragma: no cover
    if std < 1e-10:
        return {d: 0.0 for d in DIGIT_POOL}
    return {d: (scores[d] - mean) / std for d in DIGIT_POOL}


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
    """合并热分和冷分，输出 0-9 的 softmax 概率分布.

    数学原理 (z-score 标准化):
    两路输入分别做 z-score 标准化 (x - mean) / std，
    输出均值 0、标准差 1，作为 softmax 的 logits。

    相比旧的 max 归一化 (x / max(x)):
    - 旧方法输出 [0.13, 1.0]，差异 ~0.18 → softmax(T=1) 几乎均匀 (熵 99.8%)
    - z-score 输出 [-2, +2]，差异 ~4 → softmax(T=1) 区分力 ~55x
    - 消除量级/偏移差异，使 hot_weight/cold_weight 反映真实意图
    """
    weight_sum = hot_weight + cold_weight
    if weight_sum <= 0:
        weight_sum = 1.0
    hot_z = _zscore_normalize(hot_scores)
    cold_z = _zscore_normalize(cold_scores)
    logits = [
        (hot_weight * hot_z[d] + cold_weight * cold_z[d]) / weight_sum
        for d in DIGIT_POOL
    ]
    return softmax_scores(logits, temperature)


def sample_weighted(
    rng: random.Random, values: list[Any], probabilities: list[float]
) -> Any:
    """加权采样，概率全为 0 时退化为均匀随机."""
    if len(values) != len(probabilities):
        raise ValueError("values 与 probabilities 长度不一致")
    total = sum(probabilities)
    if total <= 0:
        return rng.choice(values)
    return rng.choices(values, weights=probabilities, k=1)[0]


# --------------------------------------------------------------------------- #
# 冷号信号与均匀性检验（数学增强工具）
# --------------------------------------------------------------------------- #


def raw_missing_periods(
    records: list[DrawRecord], lookback: int | None = None
) -> dict[int, dict[int, int]]:
    """返回按位原始遗漏期数 {pos: {digit: periods}}.

    与 :func:`stable_missing` 不同，返回未归一化的原始期数，
    供 :func:`geometric_missing_zscore` 使用。

    遗漏期数 = 距离该数字最近一次出现过了多少期（0 = 最近一期出现）。
    若整个窗口内未出现，则等于窗口长度。
    """
    sliced = _slice_records(records, lookback)
    window = len(sliced) if sliced else 1
    result: dict[int, dict[int, int]] = {}
    for pos in range(POSITION_COUNT):
        pos_records = [
            r.groups["pos"][pos]
            for r in sliced
            if len(r.groups.get("pos", [])) > pos
        ]
        missing: dict[int, int] = {d: window for d in DIGIT_POOL}
        for idx, n in enumerate(reversed(pos_records)):
            if missing[n] == window:
                missing[n] = idx
        result[pos] = missing
    return result


def geometric_missing_zscore(
    missing_periods: dict[int, dict[int, int]], p: float = 0.1
) -> dict[int, dict[int, float]]:
    """将原始遗漏期数转为几何分布的 z-score {pos: {digit: z}}.

    数学原理:
    在均匀分布假设 (每位数字出现概率 p=0.1) 下，遗漏期数服从
    几何分布 Geom(p):

        E[X] = (1 - p) / p      = 9
        Var  = (1 - p) / p^2    = 90
        sigma = sqrt(1 - p) / p ≈ 9.49

    z-score = (observed - E[X]) / sigma

    - z ≈ 0 : 遗漏期数符合均匀分布的期望（正常随机波动）
    - z > 0 : 比期望更冷（遗漏更长）
    - z > 1.96 : 95% 置信水平下统计显著偏冷
    - z > 2.58 : 99% 置信水平下统计显著偏冷

    相比直接用归一化遗漏值，此方法引入了均匀分布先验，
    只有统计显著的偏离才获得高分，避免赌徒谬误
    （即认为"长期未出的数字应该补出"——在 i.i.d. 下不成立）。
    """
    expected = (1 - p) / p
    sigma = math.sqrt(1 - p) / p
    return {
        pos: {d: (missing_periods[pos][d] - expected) / sigma for d in DIGIT_POOL}
        for pos in missing_periods
    }


def chi_square_uniform_test(counts: list[int]) -> tuple:
    """χ² 拟合优度检验: 观测频率是否偏离均匀分布.

    数学原理:
        H0: 每个数字出现概率 = 1/10 (均匀分布)
        χ² = Σ (O_i - E_i)² / E_i,  E_i = N / 10
        自由度 df = 9

    临界值 (df=9):
        χ²(0.05) = 16.92   (5% 显著性)
        χ²(0.01) = 21.67   (1% 显著性)

    Returns:
        (chi2_statistic, is_uniform)
        - is_uniform=True: 无法拒绝均匀假设，冷热分析无统计学意义
        - is_uniform=False: 显著偏离均匀，冷热分析有价值
    """
    n = sum(counts)
    k = len(DIGIT_POOL)
    if n == 0:
        return 0.0, True
    expected = n / k
    if expected == 0:  # pragma: no cover
        return 0.0, True
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    return chi2, chi2 < 16.92
