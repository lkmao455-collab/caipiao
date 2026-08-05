"""构建复用核心层策略的 GenerationEngine（按彩种隔离，避免策略 id 冲突）。"""

from __future__ import annotations

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import get_profile, list_profiles
from caipiao.core.strategies.factory import build_strategies

_ENGINES: dict[str, GenerationEngine] = {}


def get_profile_engine(profile_key: str) -> GenerationEngine:
    """返回指定彩种的引擎（带缓存）。

    策略 id（如 smart_hot_cold）在各彩种间不全局唯一，因此按彩种分别构建引擎，
    与桌面端「当前彩种」的行为一致，也避免注册覆盖。
    """
    if profile_key not in _ENGINES:
        profile = get_profile(profile_key)
        engine = GenerationEngine()
        for strategy in build_strategies(profile):
            engine.register(strategy)
        _ENGINES[profile_key] = engine
    return _ENGINES[profile_key]


def list_profile_strategies(profile_key: str) -> list:
    """返回某彩种的全部策略实例（用于列出可用策略）。"""
    profile = get_profile(profile_key)
    return build_strategies(profile)


def available_profiles() -> list:
    """返回所有已注册彩种。"""
    return list_profiles()
