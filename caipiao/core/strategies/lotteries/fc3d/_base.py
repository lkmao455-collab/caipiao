"""福彩3D策略共享工具与基类."""

from __future__ import annotations

import itertools
import random
from typing import Any, Dict, List, Optional, Tuple

from ....profile import get_profile
from ....ticket import Ticket
from .....data.models import DrawRecord
from .stability import deterministic_seed


FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    history = options.get("history", []) or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records


def _make_rng(
    options: Dict[str, Any],
    history: Optional[List[DrawRecord]] = None,
    lookback: Optional[int] = None,
    strategy_id: str = "",
) -> random.Random:
    if options.get("seed") is None and not history:
        return random.Random()
    seed = deterministic_seed(options, history or [], lookback, strategy_id)
    return random.Random(seed)


def _sample_with_dedup(
    sample_fn: Any,
    count: int,
    dedup: bool,
) -> List[List[int]]:
    """生成 count 组3位号码，可选按 sorted tuple 去重。

    适用于均匀分布或接近均匀分布的采样（random / odd_even / exclude_include）。
    对于概率加权的策略，请使用 _weighted_sample_without_replacement。
    """
    seen: set = set()
    results: List[List[int]] = []
    max_attempts = count * 50 if dedup else 1
    for _ in range(count):
        result = sample_fn()
        if dedup:
            for _ in range(max_attempts):
                key = tuple(sorted(result))
                if key not in seen:
                    seen.add(key)
                    break
                result = sample_fn()
        results.append(result)
    return results


def _weighted_sample_without_replacement(
    pos_probs: List[List[float]],
    count: int,
    rng: random.Random,
) -> List[List[int]]:
    """对3D组合做按概率加权无放回采样（组选去重）。

    数学原理:
    1. 枚举全部 1000 种直选组合 (a, b, c)
    2. 联合概率 P(a,b,c) = P百(a) * P十(b) * P个(c)
    3. 按 sorted tuple 聚合为组选概率（去重单位）
    4. 逐次加权抽取，每次抽中后从候选池移除

    相比拒绝采样 (_sample_with_dedup):
    - 拒绝采样在概率集中时效率骤降: 高概率组合被选完后被迫选低概率组合，
      扭曲输出分布（低温 + count 较大时尤为严重）
    - 加权无放回采样始终保持边际概率的相对关系，输出分布忠实于设计概率

    适用于 smart_hot_cold / hot_cold / missing_number 等概率加权策略。
    """
    group_probs: Dict[Tuple[int, ...], float] = {}
    group_perms: Dict[Tuple[int, ...], List[Tuple[int, ...]]] = {}
    for combo in itertools.product(range(10), repeat=3):
        key = tuple(sorted(combo))
        p = pos_probs[0][combo[0]] * pos_probs[1][combo[1]] * pos_probs[2][combo[2]]
        group_probs[key] = group_probs.get(key, 0.0) + p
        group_perms.setdefault(key, []).append(combo)

    keys: List[Tuple[int, ...]] = list(group_probs.keys())
    weights: List[float] = [group_probs[k] for k in keys]

    n = min(count, len(keys))
    selected: List[List[int]] = []

    for _ in range(n):
        total = sum(weights)
        if total <= 0:
            break
        r = rng.random() * total
        cumulative = 0.0
        idx = len(weights) - 1
        for i, w in enumerate(weights):
            cumulative += w
            if cumulative >= r:
                idx = i
                break
        key = keys.pop(idx)
        weights.pop(idx)
        perms = group_perms[key]
        selected.append(list(rng.choice(perms)))

    return selected
