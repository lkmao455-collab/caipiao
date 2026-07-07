"""福彩3D策略稳定化工具."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional

from ...data.models import DrawRecord
from .fc3d_utils import DIGIT_POOL, POSITION_COUNT, _slice_records


def _history_content_hash(
    records: List[DrawRecord], lookback: Optional[int] = None
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


def stable_frequency(
    records: List[DrawRecord], lookback: Optional[int] = None, smoothing: float = 1.0
) -> Dict[int, Dict[int, float]]:
    """返回拉普拉斯平滑后的按位概率分布 {pos: {digit: probability}}."""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Dict[int, float]] = {}
    for pos in range(POSITION_COUNT):
        counter: Dict[int, int] = {d: 0 for d in DIGIT_POOL}
        for r in sliced:
            nums = r.groups.get("pos", [])
            if pos < len(nums) and nums[pos] in DIGIT_POOL:
                counter[nums[pos]] += 1
        total = sum(counter.values()) + smoothing * len(DIGIT_POOL)
        result[pos] = {d: (counter[d] + smoothing) / total for d in DIGIT_POOL}
    return result


def stable_missing(
    records: List[DrawRecord],
    lookback: Optional[int] = None,
    cap: Optional[int] = None,
) -> Dict[int, Dict[int, float]]:
    """返回截断并归一化到 [0,1] 的按位遗漏值 {pos: {digit: normalized_missing}}."""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Dict[int, float]] = {}
    effective_cap = cap if cap is not None else (len(sliced) if sliced else 1)
    effective_cap = max(effective_cap, 1)
    for pos in range(POSITION_COUNT):
        pos_records = [
            r.groups["pos"][pos]
            for r in sliced
            if len(r.groups.get("pos", [])) > pos
        ]
        missing: Dict[int, int] = {d: effective_cap for d in DIGIT_POOL}
        for idx, n in enumerate(reversed(pos_records)):
            if missing[n] == effective_cap:
                missing[n] = idx
        capped = {d: min(v, effective_cap) for d, v in missing.items()}
        max_val = max(capped.values()) if capped else 1
        max_val = max(max_val, 1)
        result[pos] = {d: capped[d] / max_val for d in DIGIT_POOL}
    return result


def softmax_scores(values: List[float], temperature: float = 1.0) -> List[float]:
    """带温度参数的 softmax."""
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
    """合并热分和冷分，输出 0-9 的 softmax 概率分布."""
    # 分别 min-max 归一化到 [0, 1]
    hot_vals = [hot_scores[d] for d in DIGIT_POOL]
    cold_vals = [cold_scores[d] for d in DIGIT_POOL]

    def _normalize(vals: List[float]) -> List[float]:
        min_v = min(vals)
        max_v = max(vals)
        span = max_v - min_v
        if span <= 0:
            return [1.0] * len(vals)
        return [(v - min_v) / span for v in vals]

    hot_norm = _normalize(hot_vals)
    cold_norm = _normalize(cold_vals)

    combined = [
        hot_weight * hot_norm[d] + cold_weight * cold_norm[d]
        for d in DIGIT_POOL
    ]
    return softmax_scores(combined, temperature)


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
