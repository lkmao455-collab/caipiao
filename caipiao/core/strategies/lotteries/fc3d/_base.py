"""福彩3D策略共享工具与基类."""

from __future__ import annotations

import itertools
import random
from datetime import datetime, timezone
from typing import Any

from .....data.models import DrawRecord
from ....profile import get_profile
from .stability import deterministic_seed
from .utils import fc3d_bet_type

FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: dict[str, Any]) -> list[DrawRecord]:
    history = options.get("history", []) or []
    records: list[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        elif isinstance(r, dict):
            # 处理字典格式的历史记录
            draw_date = r.get("draw_date")
            if isinstance(draw_date, str):
                draw_date = datetime.strptime(draw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).astimezone()
            elif not isinstance(draw_date, datetime):
                draw_date = datetime.now(timezone.utc).astimezone()
            records.append(
                DrawRecord(
                    issue=r.get("issue", ""),
                    draw_date=draw_date,
                    profile=r.get("profile", "3d"),
                    groups=r.get("groups", {}),
                )
            )
        else:
            # 处理对象格式的历史记录（向后兼容）
            records.append(
                DrawRecord(
                    issue=getattr(r, "issue", ""),
                    draw_date=getattr(r, "draw_date", datetime.now(timezone.utc).astimezone()),
                    profile=getattr(r, "profile", None),
                    groups=getattr(r, "groups", {}),
                )
            )
    return records


def _make_rng(
    options: dict[str, Any],
    history: list[DrawRecord] | None = None,
    lookback: int | None = None,
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
) -> list[list[int]]:
    """生成 count 组3位号码，可选按 sorted tuple 去重。

    适用于均匀分布或接近均匀分布的采样（random / odd_even / exclude_include）。
    对于概率加权的策略，请使用 _weighted_sample_without_replacement。
    """
    seen: set = set()
    results: list[list[int]] = []
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
    pos_probs: list[list[float]],
    count: int,
    rng: random.Random,
    shape_weights: dict[str, float] | None = None,
) -> list[list[int]]:
    """对3D组合做按概率加权无放回采样（组选去重）。

    数学原理:
    1. 枚举全部 1000 种直选组合 (a, b, c)
    2. 联合概率 P(a,b,c) = P百(a) * P十(b) * P个(c)
    3. 按 sorted tuple 聚合为组选概率（去重单位）
    4. 逐次加权抽取，每次抽中后从候选池移除

    若提供 shape_weights，则额外乘以该组合形态（豹子/组三/组六）的修正权重，
    使输出形态分布向理论比例回归。

    相比拒绝采样 (_sample_with_dedup):
    - 拒绝采样在概率集中时效率骤降: 高概率组合被选完后被迫选低概率组合，
      扭曲输出分布（低温 + count 较大时尤为严重）
    - 加权无放回采样始终保持边际概率的相对关系，输出分布忠实于设计概率

    适用于 smart_hot_cold / hot_cold / missing_number / ensemble 等概率加权策略。
    """
    group_probs: dict[tuple[int, ...], float] = {}
    group_perms: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    perm_probs: dict[tuple[int, ...], dict[tuple[int, ...], float]] = {}
    for combo in itertools.product(range(10), repeat=3):
        key = tuple(sorted(combo))
        p = pos_probs[0][combo[0]] * pos_probs[1][combo[1]] * pos_probs[2][combo[2]]
        if shape_weights:
            shape = fc3d_bet_type(list(combo))
            shape_key = {"豹子号": "leopard", "组选3": "group3", "组选6": "group6"}.get(shape)
            if shape_key:
                p *= shape_weights.get(shape_key, 1.0)
        group_probs[key] = group_probs.get(key, 0.0) + p
        group_perms.setdefault(key, []).append(combo)
        perm_probs.setdefault(key, {})[combo] = p

    keys: list[tuple[int, ...]] = list(group_probs.keys())
    weights: list[float] = [group_probs[k] for k in keys]

    n = min(count, len(keys))
    selected: list[list[int]] = []

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
        probs = [max(perm_probs[key][perm], 0.0) for perm in perms]
        perm_total = sum(probs)
        if perm_total <= 0:
            selected.append(list(rng.choice(perms)))
        else:
            selected.append(list(rng.choices(perms, weights=probs, k=1)[0]))

    return selected
