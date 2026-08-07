"""构建复用核心层策略的 GenerationEngine（按彩种隔离，避免策略 id 冲突）。"""

from __future__ import annotations

import time

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import get_profile, list_profiles
from caipiao.core.strategies.factory import build_strategies

# 带过期时间的引擎缓存
_ENGINES: dict[str, tuple[GenerationEngine, float]] = {}
_ENGINE_TTL = 3600  # 引擎缓存1小时


def get_profile_engine(profile_key: str) -> GenerationEngine:
    """返回指定彩种的引擎（带缓存）。

    策略 id（如 smart_hot_cold）在各彩种间不全局唯一，因此按彩种分别构建引擎，
    与桌面端「当前彩种」的行为一致，也避免注册覆盖。
    """
    current_time = time.time()
    
    # 检查缓存是否有效
    if profile_key in _ENGINES:
        engine, timestamp = _ENGINES[profile_key]
        if current_time - timestamp < _ENGINE_TTL:
            return engine
    
    # 构建新引擎并缓存
    profile = get_profile(profile_key)
    engine = GenerationEngine()
    for strategy in build_strategies(profile):
        engine.register(strategy)
    _ENGINES[profile_key] = (engine, current_time)
    return engine


def invalidate_engine_cache(profile_key: str | None = None) -> int:
    """清除引擎缓存。"""
    if profile_key:
        if profile_key in _ENGINES:
            del _ENGINES[profile_key]
            return 1
        return 0
    else:
        count = len(_ENGINES)
        _ENGINES.clear()
        return count


def list_profile_strategies(profile_key: str) -> list:
    """返回某彩种的全部策略实例（用于列出可用策略）。"""
    profile = get_profile(profile_key)
    return build_strategies(profile)


def available_profiles() -> list:
    """返回所有已注册彩种。"""
    return list_profiles()
