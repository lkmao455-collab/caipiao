"""福彩3D策略共享工具与基类."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

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
    """生成 count 组3位号码，可选按 sorted tuple 去重。"""
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
