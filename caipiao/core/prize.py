"""彩种奖金计算（固定奖级）。

用于历史回测时把命中号码映射为理论奖金。
一等奖/二等奖/七乐彩高奖等为浮动奖金，无法精确计算，用 "浮动" 表示。
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def _ssq_prize(hits: Dict[str, int]) -> Tuple[str, int | None]:
    """双色球奖金：返回 (奖级描述, 固定奖金 or None)。"""
    red = hits.get("red", 0)
    blue = hits.get("blue", 0)
    if red == 6 and blue == 1:
        return ("一等奖", None)
    if red == 6 and blue == 0:
        return ("二等奖", None)
    if red == 5 and blue == 1:
        return ("三等奖", 3000)
    if (red == 5 and blue == 0) or (red == 4 and blue == 1):
        return ("四等奖", 200)
    if (red == 4 and blue == 0) or (red == 3 and blue == 1):
        return ("五等奖", 10)
    if blue == 1:
        return ("六等奖", 5)
    return ("未中奖", 0)


def _fc3d_prize(hits: Dict[str, int], groups: Dict[str, List[int]]) -> Tuple[str, int | None]:
    """福彩3D奖金：按直选/组选3/组选6判断。

    直选：命中 3 位且位置全对。
    组选：号码全部命中但位置不对（或顺序无关）。
    """
    pos_hits = hits.get("pos", 0)
    if pos_hits == 3:
        return ("直选", 1040)

    nums = groups.get("pos", [])
    if len(nums) == 3:
        unique = len(set(nums))
        if unique == 2:
            return ("组选3", 346)
        if unique == 3:
            return ("组选6", 173)
    return ("未中奖", 0)


def _qlc_prize(hits: Dict[str, int]) -> Tuple[str, int | None]:
    """七乐彩奖金：投注只选 7 个基本号，开奖为基本号 7 个 + 特别号 1 个。"""
    basic = hits.get("basic", 0)
    special = hits.get("special", 0)
    if basic == 7:
        return ("一等奖", None)
    if basic == 6 and special == 1:
        return ("二等奖", None)
    if basic == 6:
        return ("三等奖", None)
    if basic == 5 and special == 1:
        return ("四等奖", 200)
    if basic == 5:
        return ("五等奖", 50)
    if basic == 4 and special == 1:
        return ("六等奖", 10)
    if basic == 4:
        return ("七等奖", 5)
    return ("未中奖", 0)


_KL8_PRIZES = {
    1: {1: ("选一中一", 4)},
    2: {2: ("选二中二", 19)},
    3: {2: ("选三中二", 3), 3: ("选三中三", 53)},
    4: {2: ("选四中二", 3), 3: ("选四中三", 5), 4: ("选四中四", 100)},
    5: {3: ("选五中三", 3), 4: ("选五中四", 21), 5: ("选五中五", 1000)},
    6: {3: ("选六中三", 3), 4: ("选六中四", 10), 5: ("选六中五", 30), 6: ("选六中六", 3000)},
    7: {0: ("选七全不中", 2), 4: ("选七中四", 4), 5: ("选七中五", 28), 6: ("选七中六", 288), 7: ("选七中七", 10000)},
    8: {0: ("选八全不中", 2), 4: ("选八中四", 3), 5: ("选八中五", 10), 6: ("选八中六", 88), 7: ("选八中七", 800), 8: ("选八中八", 50000)},
    9: {0: ("选九全不中", 2), 4: ("选九中四", 3), 5: ("选九中五", 5), 6: ("选九中六", 20), 7: ("选九中七", 200), 8: ("选九中八", 2000), 9: ("选九中九", 300000)},
    10: {0: ("选十全不中", 2), 5: ("选十中五", 3), 6: ("选十中六", 5), 7: ("选十中七", 80), 8: ("选十中八", 800), 9: ("选十中九", 8000), 10: ("选十中十", None)},
}


def _kl8_prize(hits: Dict[str, int], groups: Dict[str, List[int]]) -> Tuple[str, int | None]:
    """快乐8奖金：根据投注个数与命中个数查表。"""
    pick = len(groups.get("main", []))
    hit = hits.get("main", 0)
    table = _KL8_PRIZES.get(pick, {})
    if hit in table:
        return table[hit]
    return ("未中奖", 0)


def calculate_prize(
    profile_key: str,
    hits: Dict[str, int],
    groups: Dict[str, List[int]],
) -> Tuple[str, int | None]:
    """根据彩种、命中数与投注号码计算理论奖金。

    Returns:
        (奖级描述, 奖金)。奖金为 None 表示浮动奖（如一等奖）。
    """
    if profile_key == "ssq":
        return _ssq_prize(hits)
    if profile_key == "3d":
        return _fc3d_prize(hits, groups)
    if profile_key == "qlc":
        return _qlc_prize(hits)
    if profile_key == "kl8":
        return _kl8_prize(hits, groups)
    return ("未知彩种", 0)
