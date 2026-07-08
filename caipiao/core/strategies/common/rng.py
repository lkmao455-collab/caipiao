"""随机数生成器工具."""

from __future__ import annotations

import random
from typing import Any, Dict, Optional


def make_rng(options: Dict[str, Any], seed: Optional[int] = None) -> random.Random:
    """根据 options 或显式 seed 创建 Random 实例。"""
    effective_seed = seed if seed is not None else options.get("seed")
    return random.Random(effective_seed) if effective_seed is not None else random.Random()
