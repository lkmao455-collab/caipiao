"""彩种奖金计算（固定奖级）。

用于历史回测时把命中号码映射为理论奖金。
一等奖/二等奖等高奖等为浮动奖金，无法精确计算，用 "浮动" 表示。
"""

from __future__ import annotations

from typing import Any


def _ssq_prize(hits: dict[str, int]) -> tuple[str, int | None]:
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


def _fc3d_prize(
    hits: dict[str, int],
    ticket_groups: dict[str, list[int]],
    actual_groups: dict[str, list[int]] | None = None,
    details: dict[str, Any] | None = None,
) -> tuple[str, int | None]:
    """福彩3D奖金：按投注方式（直选/组选）与形态判断。

    - bet_mode == "直选"：3 位数字及顺序与开奖完全相同才中奖（1040）。
    - bet_mode == "组选"：投注号码是开奖号码的任意排列即中奖
      （组选3 → 346，组选6 → 173；位置全对也只发组选奖金）。
    - 无 bet_mode（历史数据）：保持旧逻辑，先判直选再判组选。

    必须有真实开奖号码 ``actual_groups`` 才能判定；否则统一视为未中奖，
    避免只根据投注号码自身特征误发奖金。
    """
    if actual_groups is None:
        return ("未中奖", 0)

    actual = actual_groups.get("pos", [])
    ticket = ticket_groups.get("pos", [])
    if len(actual) != 3 or len(ticket) != 3:
        return ("未中奖", 0)

    bet_mode = (details or {}).get("bet_mode")
    # 组选票不可能是豹子号（生成时已转直选）；异常数据兜底按直选规则
    if bet_mode == "组选" and len(set(ticket)) == 1:
        bet_mode = "直选"

    if bet_mode == "直选":
        if list(actual) == list(ticket):
            return ("直选", 1040)
        return ("未中奖", 0)

    if bet_mode == "组选":
        if sorted(actual) == sorted(ticket):
            unique = len(set(actual))
            if unique == 2:
                return ("组选3", 346)
            if unique == 3:
                return ("组选6", 173)
        return ("未中奖", 0)

    # 无 bet_mode（历史数据）：保持原逻辑
    if list(actual) == list(ticket):
        return ("直选", 1040)

    if sorted(actual) == sorted(ticket):
        unique = len(set(actual))
        if unique == 2:
            return ("组选3", 346)
        if unique == 3:
            return ("组选6", 173)

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


def _kl8_prize(hits: dict[str, int], groups: dict[str, list[int]]) -> tuple[str, int | None]:
    """快乐8奖金：根据投注个数与命中个数查表。"""
    pick = len(groups.get("main", []))
    hit = hits.get("main", 0)
    table = _KL8_PRIZES.get(pick, {})
    if hit in table:
        return table[hit]
    return ("未中奖", 0)


def _dlt_prize(hits: dict[str, int]) -> tuple[str, int | None]:
    """超级大乐透奖金：前区命中 + 后区命中。"""
    front = hits.get("front", 0)
    back = hits.get("back", 0)
    if front == 5 and back == 2:
        return ("一等奖", None)
    if front == 5 and back == 1:
        return ("二等奖", None)
    if front == 5 and back == 0:
        return ("三等奖", 10000)
    if front == 4 and back == 2:
        return ("四等奖", 3000)
    if front == 4 and back == 1:
        return ("五等奖", 300)
    if front == 3 and back == 2:
        return ("六等奖", 200)
    if front == 4 and back == 0:
        return ("七等奖", 100)
    if (front == 3 and back == 1) or (front == 2 and back == 2):
        return ("八等奖", 15)
    if (
        (front == 3 and back == 0)
        or (front == 1 and back == 2)
        or (front == 2 and back == 1)
        or (front == 0 and back == 2)
    ):
        return ("九等奖", 5)
    return ("未中奖", 0)


def _pl3_prize(
    hits: dict[str, int],
    ticket_groups: dict[str, list[int]],
    actual_groups: dict[str, list[int]] | None = None,
) -> tuple[str, int | None]:
    """排列3奖金：与福彩3D规则相同（直选/组选3/组选6）。"""
    if actual_groups is None:
        return ("未中奖", 0)

    actual = actual_groups.get("pos", [])
    ticket = ticket_groups.get("pos", [])
    if len(actual) != 3 or len(ticket) != 3:
        return ("未中奖", 0)

    if list(actual) == list(ticket):
        return ("直选", 1040)

    if sorted(actual) == sorted(ticket):
        unique = len(set(actual))
        if unique == 2:
            return ("组选3", 346)
        if unique == 3:
            return ("组选6", 173)

    return ("未中奖", 0)


def _pl5_prize(hits: dict[str, int]) -> tuple[str, int | None]:
    """排列5奖金：仅直选，5 位全部匹配。"""
    if hits.get("pos", 0) == 5:
        return ("直选", 100000)
    return ("未中奖", 0)


def _qxc_prize(
    hits: dict[str, int],
    ticket_groups: dict[str, list[int]],
    actual_groups: dict[str, list[int]] | None = None,
) -> tuple[str, int | None]:
    """7星彩奖金：按从右到左连续命中位数判定。"""
    if actual_groups is None:
        return ("未中奖", 0)

    actual = actual_groups.get("pos", [])
    ticket = ticket_groups.get("pos", [])
    if len(actual) != 7 or len(ticket) != 7:
        return ("未中奖", 0)

    # 从右到左统计连续命中位数
    consecutive = 0
    for a, p in zip(reversed(actual), reversed(ticket)):
        if a == p:
            consecutive += 1
        else:
            break

    if consecutive == 7:
        return ("一等奖", None)
    if consecutive == 6:
        return ("二等奖", None)
    if consecutive == 5:
        return ("三等奖", 3000)
    if consecutive == 4:
        return ("四等奖", 500)
    if consecutive == 3:
        return ("五等奖", 30)
    if consecutive == 2:
        return ("六等奖", 5)
    return ("未中奖", 0)


def _gd36x7_prize(hits: dict[str, int]) -> tuple[str, int | None]:
    """广东36选7奖金：与七乐彩规则相同，仅号池为 1-36。"""
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


def fc3d_bet_type(numbers: list[int]) -> str:
    """根据福彩3D投注号码判断可购买的投注方式。

    规则：
    - 三位数字各不相同：可买组选6（顺序不限）。
    - 恰好两位相同：可买组选3（顺序不限）。
    - 三位全相同：豹子号，只能直选（或按站点规则购买）。

    返回的字符串用于界面展示，如 "组选6"、"组选3"、"豹子号（直选）"。
    """
    if len(numbers) != 3:
        return "未知"
    unique = len(set(numbers))
    if unique == 3:
        return "组选6"
    if unique == 2:
        return "组选3"
    return "豹子号（直选）"


def calculate_prize(
    profile_key: str,
    hits: dict[str, int],
    ticket_groups: dict[str, list[int]],
    actual_groups: dict[str, list[int]] | None = None,
    details: dict[str, Any] | None = None,
) -> tuple[str, int | None]:
    """根据彩种、命中数、投注号码与真实开奖号码计算理论奖金。

    Args:
        profile_key: 彩种标识。
        hits: 各号码组命中数。
        ticket_groups: 当前投注号码分组。
        actual_groups: 当期真实开奖号码分组。福彩 3D 的组选/直选判定
            依赖真实号码；其他彩种可省略。
        details: 投注单附加信息（Ticket.details）。福彩 3D 用其中的
            ``bet_mode``（"直选"/"组选"）区分投注方式；缺省保持旧逻辑。

    Returns:
        (奖级描述, 奖金)。奖金为 None 表示浮动奖（如一等奖）。
    """
    if profile_key == "ssq":
        return _ssq_prize(hits)
    if profile_key == "3d":
        return _fc3d_prize(hits, ticket_groups, actual_groups, details)
    if profile_key == "kl8":
        return _kl8_prize(hits, ticket_groups)
    if profile_key == "dlt":
        return _dlt_prize(hits)
    if profile_key == "pl3":
        return _pl3_prize(hits, ticket_groups, actual_groups)
    if profile_key == "pl5":
        return _pl5_prize(hits)
    if profile_key == "qxc":
        return _qxc_prize(hits, ticket_groups, actual_groups)
    # 广东36选7 已临时从注册表中移除；保留奖金函数供后续启用
    if profile_key == "gd36x7":
        return _gd36x7_prize(hits)
    return ("未知彩种", 0)
