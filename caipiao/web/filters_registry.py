"""Web 侧后过滤注册表：映射彩种 → 核心层 ``filter_*_by_history`` 函数。

核心层零侵入：这里只**引用**既有的过滤函数，由生成/回测路由在产出号码后调用，
对 ``tickets`` 与 ``draw_records`` 两个参数由服务端填充，其余参数由前端/请求提供。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from caipiao.core import engine as _engine_mod


@dataclass
class FilterParam:
    """一个可配置过滤参数的元数据（用于前端动态渲染）。"""

    name: str
    type: str  # "int" | "bool"
    default: Any
    min: int | None = None
    max: int | None = None
    description: str = ""


@dataclass
class ProfileFilter:
    """某彩种可用的后过滤函数及参数 schema。"""

    fn: Callable[..., list]
    params: list[FilterParam]


def _int(name: str, default: int, min_v: int | None = None, max_v: int | None = None, desc: str = "") -> FilterParam:
    return FilterParam(name, "int", default, min_v, max_v, desc)


def _bool(name: str, default: bool, desc: str = "") -> FilterParam:
    return FilterParam(name, "bool", default, None, None, desc)


# 各彩种过滤参数 schema（tickets / draw_records 由服务端填充，不在此列出）
_PROFILE_FILTERS: dict[str, ProfileFilter] = {
    "ssq": ProfileFilter(
        _engine_mod.filter_ssq_by_history,
        [
            _int("compare_periods", 7, 1, desc="向前比较的期数"),
            _int("max_red_overlap", 3, 0, desc="红球允许的最大重合数"),
            _bool("block_blue_match", False, "禁止蓝球与历史相同"),
            _int("blue_compare_periods", 1, 1, desc="蓝球禁止重复的对比期数"),
        ],
    ),
    "dlt": ProfileFilter(
        _engine_mod.filter_dlt_by_history,
        [
            _int("compare_periods", 7, 1, desc="向前比较的期数"),
            _int("max_front_overlap", 0, 0, desc="前区允许的最大重合数"),
            _bool("block_back_match", True, "禁止后区与历史相同"),
            _int("back_compare_periods", 1, 1, desc="后区禁止重复的对比期数"),
        ],
    ),
    "fc3d": ProfileFilter(
        _engine_mod.filter_fc3d_by_history,
        [
            _int("compare_periods", 5, 1, desc="向前比较的期数"),
            _int("max_overlap", 1, 0, desc="允许的最大相同号码数"),
            _int("min_sum", 0, 0, 27, desc="和值下限"),
            _int("max_sum", 27, 0, 27, desc="和值上限"),
        ],
    ),
    "pl3": ProfileFilter(
        _engine_mod.filter_pl3_by_history,
        [
            _int("compare_periods", 5, 1, desc="向前比较的期数"),
            _int("max_overlap", 1, 0, desc="允许的最大相同号码数"),
            _int("min_sum", 0, 0, 27, desc="和值下限"),
            _int("max_sum", 27, 0, 27, desc="和值上限"),
        ],
    ),
    "pl5": ProfileFilter(
        _engine_mod.filter_pl5_by_history,
        [
            _int("compare_periods", 5, 1, desc="向前比较的期数"),
            _int("max_overlap", 2, 0, desc="允许的最大相同号码数"),
            _int("min_sum", 0, 0, 45, desc="和值下限"),
            _int("max_sum", 45, 0, 45, desc="和值上限"),
        ],
    ),
    "qxc": ProfileFilter(
        _engine_mod.filter_qxc_by_history,
        [
            _int("compare_periods", 5, 1, desc="向前比较的期数"),
            _int("max_overlap", 3, 0, desc="允许的最大相同号码数"),
            _int("min_sum", 0, 0, 63, desc="和值下限"),
            _int("max_sum", 63, 0, 63, desc="和值上限"),
        ],
    ),
    "kl8": ProfileFilter(
        _engine_mod.filter_kl8_by_history,
        [
            _int("compare_periods", 5, 1, desc="向前比较的期数"),
            _int("max_overlap", 5, 0, desc="允许的最大重合数"),
            _int("min_sum", 0, 0, 840, desc="和值下限"),
            _int("max_sum", 840, 0, 840, desc="和值上限"),
        ],
    ),
}


def get_profile_filter(profile_key: str) -> ProfileFilter | None:
    """返回某彩种的后过滤定义；未知彩种返回 None。"""
    return _PROFILE_FILTERS.get(profile_key)


def available_filter_profile_keys() -> list[str]:
    """列出所有支持后过滤的彩种 key。"""
    return list(_PROFILE_FILTERS.keys())


def apply_filters(
    profile_key: str,
    tickets: list,
    draw_records: list,
    post_filters: list[dict[str, Any]] | None,
) -> list:
    """按请求中的 post_filters 应用对应过滤函数。

    ``post_filters`` 元素形如 ``{"name": <profile_key>, "params": {...}}``；
    仅当 name 与当前彩种匹配且参数合法时应用。返回过滤后的 tickets（至少返回原列表）。
    """
    if not post_filters:
        return tickets
    prof = get_profile_filter(profile_key)
    if prof is None:
        return tickets
    result = tickets
    for pf in post_filters:
        if pf.get("name") != profile_key:
            continue
        raw_params = pf.get("params") or {}
        params: dict[str, Any] = {}
        for p in prof.params:
            if p.name in raw_params:
                params[p.name] = raw_params[p.name]
        try:
            result = prof.fn(result, draw_records, **params)
        except Exception:
            # 单个过滤失败不阻断整体，回退到过滤前结果
            continue
    return result
