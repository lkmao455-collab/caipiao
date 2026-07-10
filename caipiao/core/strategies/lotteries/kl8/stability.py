"""快乐8策略稳定化工具.

本模块为快乐8（1-80 每期开 20 个号）提供与福彩3D ``stability.py`` 同源
的数学稳定化工具，核心思想是在「彩票每号独立同分布」的零假设下提取
统计显著的冷热信号，避免赌徒谬误。

关键参数（均匀分布零假设）：
    每号每期被开出的概率 p = 20 / 80 = 0.25
    频率期望   E[f]   = N * p          （N = lookback 期数）
    遗漏期望   E[m]   = (1 - p) / p    = 3.0
    遗漏标准差 sigma  = sqrt(1-p) / p  ≈ 3.464
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from typing import Any, Dict, List, Optional

from .....data.models import DrawRecord


MAIN_KEY = "main"
MAIN_POOL = list(range(1, 81))
MAIN_POOL_SIZE = len(MAIN_POOL)
DRAW_PER_NUMBER_PROB = 20.0 / 80.0  # p = 0.25


def _slice_records(records: List[DrawRecord], lookback: Optional[int]) -> List[DrawRecord]:
    sorted_records = sorted(records, key=lambda r: r.draw_date)
    if lookback is None or lookback >= len(sorted_records):
        return sorted_records
    if lookback <= 0:
        return []
    return sorted_records[-lookback:]


# --------------------------------------------------------------------------- #
# 确定性随机种子（无用户 seed 时基于历史内容可复现）
# --------------------------------------------------------------------------- #
def _history_content_hash(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> str:
    """根据历史数据内容生成短 hash."""
    sliced = _slice_records(records, lookback)
    parts = []
    for r in sliced:
        nums = ",".join(str(n) for n in sorted(r.groups.get(MAIN_KEY, [])))
        parts.append(f"{r.issue or ''}:{r.draw_date.isoformat()}:{nums}")
    content = ";".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def deterministic_seed(
    options: dict,
    history: List[DrawRecord],
    lookback: Optional[int] = None,
    strategy_id: str = "",
) -> int:
    """若 options 中无 seed，则基于历史内容派生确定性 seed."""
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    h = _history_content_hash(history, lookback)
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode("utf-8")).hexdigest()
    return int(raw, 16) % (2**31)


# --------------------------------------------------------------------------- #
# 热号信号：拉普拉斯平滑频率
# --------------------------------------------------------------------------- #
def stable_frequency(
    records: List[DrawRecord], lookback: Optional[int] = None, smoothing: float = 1.0
) -> Dict[int, float]:
    """返回拉普拉斯平滑后的号码概率分布 {number: probability}.

    数学原理:
        每期开出 20 个号，N 期共 N*20 个号位（含跨期重复）。
        号码 i 出现 f_i 次，加平滑后归一为概率：

            p_i = (f_i + smoothing) / (N*20 + smoothing*80)

        Σ p_i = 1。在均匀分布零假设下 E[p_i] = 1/80 = 0.0125。
        拉普拉斯平滑避免未出现号码权重为 0 导致采样永远选不到它，
        并在 N 较小时把估计向先验（均匀）收缩，符合「彩票随机」原则。
    """
    counts = frequency_counts(records, lookback)
    total = sum(counts.values()) + smoothing * MAIN_POOL_SIZE
    return {n: (counts[n] + smoothing) / total for n in MAIN_POOL}


def frequency_counts(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> Dict[int, int]:
    """返回 lookback 窗口内每个号码的原始出现次数 {number: count}.

    供 :func:`chi_square_uniform_test` 使用原始观测计数（而非平滑概率），
    保证 χ² 统计量的无偏性。
    """
    sliced = _slice_records(records, lookback)
    counter: Dict[int, int] = {n: 0 for n in MAIN_POOL}
    for r in sliced:
        for n in r.groups.get(MAIN_KEY, []):
            if n in counter:
                counter[n] += 1
    return counter


# --------------------------------------------------------------------------- #
# 冷号信号：原始遗漏期数 → 几何分布 z-score
# --------------------------------------------------------------------------- #
def raw_missing_periods(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> Dict[int, int]:
    """返回每个号码的原始遗漏期数 {number: periods}.

    遗漏期数 = 距离该号码最近一次出现过了多少期（0 = 最近一期出现）。
    若整个窗口内未出现，则等于窗口长度。
    """
    sliced = _slice_records(records, lookback)
    window = len(sliced) if sliced else 1
    missing: Dict[int, int] = {n: window for n in MAIN_POOL}
    for idx, r in enumerate(reversed(sliced)):
        for n in r.groups.get(MAIN_KEY, []):
            if n in missing and missing[n] == window:
                missing[n] = idx
    return missing


def geometric_missing_zscore(
    missing_periods: Dict[int, int], p: float = DRAW_PER_NUMBER_PROB
) -> Dict[int, float]:
    """将原始遗漏期数转为几何分布的 z-score {number: z}.

    数学原理:
        在均匀分布假设（每号每期出现概率 p=0.25）下，遗漏期数服从
        几何分布 Geom(p)（从最近一次出现后开始计失败次数）：

            E[X]   = (1 - p) / p      = 3.0
            Var    = (1 - p) / p^2    = 12.0
            sigma  = sqrt(1 - p) / p  ≈ 3.464

        z-score = (observed - E[X]) / sigma

        - z ≈ 0   : 遗漏期数符合均匀分布期望（正常随机波动）
        - z > 1.96: 95% 置信水平下统计显著偏冷
        - z > 2.58: 99% 置信水平下统计显著偏冷

        相比直接用归一化遗漏值，此方法引入了均匀分布先验，
        只有统计显著的偏离才获得高分，避免赌徒谬误
        （即认为「长期未出的号应该补出」——在 i.i.d. 下不成立）。
    """
    expected = (1 - p) / p
    sigma = math.sqrt(1 - p) / p
    return {n: (missing_periods[n] - expected) / sigma for n in MAIN_POOL}


# --------------------------------------------------------------------------- #
# χ² 均匀性检验守卫
# --------------------------------------------------------------------------- #
def _chi_square_critical(df: int, alpha: float = 0.05) -> float:
    """χ² 分布上侧 α 分位数的 Wilson-Hilferty 近似.

        χ²(α, df) ≈ df * (1 - 2/(9df) + z_{1-α} * sqrt(2/(9df)))^3

    对 df>=9 误差 <0.2%，足以作为「是否显著偏离均匀」的判断阈值。
    """
    from statistics import NormalDist

    z = NormalDist().inv_cdf(1 - alpha)
    c = 2.0 / (9.0 * df)
    return df * (1 - c + z * math.sqrt(c)) ** 3


def chi_square_uniform_test(counts: List[int]) -> tuple:
    """χ² 拟合优度检验: 观测频率是否偏离均匀分布.

    数学原理:
        H0: 每个号码出现频率相等（均匀分布）
        E_i = Σcounts / k,   k = 号池大小 = 80
        χ² = Σ (O_i - E_i)² / E_i,  自由度 df = k - 1 = 79

    Returns:
        (chi2_statistic, is_uniform)
        - is_uniform=True : 无法拒绝均匀假设，冷热分析无统计学意义
        - is_uniform=False: 显著偏离均匀，冷热分析有价值

    说明: 快乐8每期开 20 个号，Σcounts = N*20 恰等于 ΣE_i，
    自由度约束天然满足。各号出现边际服从 Binomial(N, 0.25)，
    χ² 近似在 N 较大时成立，作为「守卫」用途足够稳健。
    """
    k = len(counts)
    if k < 2:
        return 0.0, True
    n = sum(counts)
    if n == 0:
        return 0.0, True
    expected = n / k
    if expected == 0:
        return 0.0, True
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    df = k - 1
    return chi2, chi2 < _chi_square_critical(df, 0.05)


# --------------------------------------------------------------------------- #
# 评分合成：z-score 标准化 + softmax 温度
# --------------------------------------------------------------------------- #
def _zscore_normalize(scores: Dict[int, float]) -> Dict[int, float]:
    """z-score 标准化: z = (x - mean) / std.

    输出均值 0、标准差 1，是 softmax logits 的标准输入形式。

    相比旧的 max 归一化 (x / max(x)):
    - 消除偏移: max-norm 最小值不为 0，z-score 均值为 0
    - 对异常值稳健: max-norm 受最大值支配，z-score 用全局均值和方差
    - softmax 区分力恢复: z-score 后值域约 [-2, +2]，softmax 区分力充足

    当所有值相同 (std≈0) 时返回全 0，使 softmax 输出均匀分布。
    """
    vals = [scores[n] for n in MAIN_POOL]
    if len(vals) < 2:
        return {n: 0.0 for n in MAIN_POOL}
    mean = statistics.mean(vals)
    try:
        std = statistics.stdev(vals)
    except statistics.StatisticsError:
        std = 0.0
    if std < 1e-10:
        return {n: 0.0 for n in MAIN_POOL}
    return {n: (scores[n] - mean) / std for n in MAIN_POOL}


def softmax_scores(values: List[float], temperature: float = 1.0) -> List[float]:
    """带温度参数的 softmax.

    temperature → ∞ 时退化为均匀分布（纯随机），
    temperature → 0 时高度集中在最大 logits 上。
    """
    if temperature <= 0:
        temperature = 1.0
    max_v = max(values)
    exps = [math.exp((v - max_v) / temperature) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def stable_scores(
    hot_scores: Dict[int, float],
    cold_scores: Dict[int, float],
    hot_weight: float,
    cold_weight: float,
    temperature: float = 1.0,
) -> List[float]:
    """合并热分和冷分，输出 1-80 的 softmax 概率分布（按号码升序）.

    数学原理 (z-score 标准化):
        两路输入分别做 z-score 标准化 (x - mean) / std，
        输出均值 0、标准差 1，作为 softmax 的 logits。
        消除量级/偏移差异，使 hot_weight/cold_weight 反映真实意图。
    """
    weight_sum = hot_weight + cold_weight
    if weight_sum <= 0:
        weight_sum = 1.0
    hot_z = _zscore_normalize(hot_scores)
    cold_z = _zscore_normalize(cold_scores)
    logits = [
        (hot_weight * hot_z[n] + cold_weight * cold_z[n]) / weight_sum
        for n in MAIN_POOL
    ]
    return softmax_scores(logits, temperature)


# --------------------------------------------------------------------------- #
# 加权采样
# --------------------------------------------------------------------------- #
def sample_weighted(
    rng: random.Random, values: List[Any], probabilities: List[float]
) -> Any:
    """加权采样，概率全为 0 时退化为均匀随机."""
    if len(values) != len(probabilities):
        raise ValueError("values 与 probabilities 长度不一致")
    total = sum(probabilities)
    if total <= 0:
        return rng.choice(values)
    return rng.choices(values, weights=probabilities, k=1)[0]


def weighted_sample_without_replacement(
    rng: random.Random, values: List[int], weights: List[float], k: int
) -> List[int]:
    """按概率加权无放回采样 k 个不同号码.

    数学原理 (顺序加权无放回采样, PPS sequential):
        1. 按权重比例抽取第 1 个号码：P(i) = w_i / Σw
        2. 移除已抽中号码，对剩余号码权重重新归一，再抽下一个
        3. 重复直至取满 k 个

    相比 ``rng.choices(k=k)`` 有放回采样再循环去重:
    - 有放回+去重在 k 较大（如选 10）时低效且分布扭曲
    - 本法始终保持边际概率的相对关系，输出分布忠实于设计概率

    注: 顺序加权无放回采样与「精确联合分布」的加权无放回采样略有差异，
    但对号码筛选用途影响可忽略，且可在 80 选 k 的高维空间高效执行
    （精确枚举 C(80,k) 不可行）。
    """
    pool = list(values)
    pool_w = list(weights)
    k = max(0, min(k, len(pool)))
    selected: List[int] = []
    for _ in range(k):
        total = sum(pool_w)
        if total <= 0:
            idx = rng.randrange(len(pool))
        else:
            r = rng.random() * total
            cumulative = 0.0
            idx = len(pool) - 1
            for i, w in enumerate(pool_w):
                cumulative += w
                if cumulative >= r:
                    idx = i
                    break
        selected.append(pool.pop(idx))
        pool_w.pop(idx)
    return selected
