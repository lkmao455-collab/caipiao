"""起卦引擎模块.

提供时间起卦（梅花易数）、铜钱起卦（六爻）、随机起卦三种方式。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..calendar.heavenly_earthly import get_ganzhi_day, get_ganzhi_hour, get_shichen
from .bagua import (
    Trigram,
    get_trigram_by_yao,
    get_yao_from_number,
)
from .yijing import (
    Hexagram,
    get_changed_hexagram,
    get_hexagram,
    get_yao_positions,
)


@dataclass
class DivinationResult:
    """占卜结果."""

    hexagram: Hexagram               # 本卦
    changed_hexagram: Hexagram | None  # 变卦
    yao: tuple[int, ...]             # 六爻（从下到上，1=阳，0=阴，2=老阳，3=老阴）
    method: str                      # 起卦方法
    time_str: str                    # 起卦时间描述
    upper_trigram: Trigram           # 上卦
    lower_trigram: Trigram           # 下卦
    moving_yao: list[int]            # 动爻位置（0-based）
    analysis: str                    # 卦象分析
    recommended_numbers: list[int] = field(default_factory=list)  # 推荐号码

    def yao_display(self) -> list[str]:
        """返回六爻显示文本."""
        return get_yao_positions(self.yao)

    def summary(self) -> str:
        """返回卦象摘要."""
        moving = ""
        if self.moving_yao:
            positions = [f"第{i+1}爻" for i in self.moving_yao]
            moving = f"（动爻：{'、'.join(positions)}）"

        result = f"本卦：{self.hexagram.full_name} {self.hexagram.symbol}\n"
        result += f"上卦：{self.upper_trigram.name}（{self.upper_trigram.element}）\n"
        result += f"下卦：{self.lower_trigram.name}（{self.lower_trigram.element}）\n"
        result += f"{moving}\n\n"
        result += f"【卦辞】{self.hexagram.gua_ci}\n\n"
        result += f"【象辞】{self.hexagram.xiang_ci}\n\n"

        if self.changed_hexagram:
            result += f"变卦：{self.changed_hexagram.full_name}\n"
            result += f"【卦辞】{self.changed_hexagram.gua_ci}\n\n"

        result += f"【解析】{self.analysis}\n"

        return result


# ──────────────────────────────────────────────────────────────────────
# 时间起卦（梅花易数）
# ──────────────────────────────────────────────────────────────────────

def time_divination(
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    hour: int | None = None,
) -> DivinationResult:
    """时间起卦（梅花易数）.

    原理：
    - 上卦 = (年数 + 月 + 日) % 8
    - 下卦 = (年数 + 月 + 日 + 时) % 8
    - 动爻 = (年数 + 月 + 日 + 时) % 6

    Args:
        year: 公历年（默认当前年）
        month: 公历月（默认当前月）
        day: 公历日（默认当日）
        hour: 24小时制的小时（默认当前小时）

    Returns:
        DivinationResult 占卜结果
    """
    now = datetime.now(timezone.utc).astimezone()
    year = year or now.year
    month = month or now.month
    day = day or now.day
    hour = hour if hour is not None else now.hour

    # 梅花易数：年数取地支序号（子=1, 丑=2, ..., 亥=12）
    year_branch_index = (year - 4) % 12
    year_num = year_branch_index + 1

    # 上卦数 = (年数 + 月 + 日) % 8
    upper_num = (year_num + month + day) % 8
    # 下卦数 = (年数 + 月 + 日 + 时) % 8
    lower_num = (year_num + month + day + hour) % 8
    # 动爻 = (年数 + 月 + 日 + 时) % 6
    moving_yao_pos = (year_num + month + day + hour) % 6 - 1  # 0-based

    # 获取三爻卦
    upper_yao = get_yao_from_number(upper_num)
    lower_yao = get_yao_from_number(lower_num)

    upper_trigram = get_trigram_by_yao(upper_yao)
    lower_trigram = get_trigram_by_yao(lower_yao)

    if not upper_trigram or not lower_trigram:
        raise ValueError("无法解析卦象")

    # 获取本卦
    hexagram = get_hexagram(upper_trigram.name, lower_trigram.name)
    if not hexagram:
        raise ValueError(f"无法找到卦象：{upper_trigram.name}上{lower_trigram.name}下")

    # 构建六爻（从下到上），标记动爻
    yao_list = list(lower_yao) + list(upper_yao)
    yao_list[moving_yao_pos] = 2 if yao_list[moving_yao_pos] == 1 else 3  # 变爻
    yao_tuple = tuple(yao_list)

    # 获取变卦
    changed = get_changed_hexagram(yao_tuple)

    # 生成时间描述
    day_gz = get_ganzhi_day(year, month, day)
    hour_gz = get_ganzhi_hour(hour, day_gz[0])
    shichen = get_shichen(hour)
    time_str = f"{year}年{month}月{day}日 {shichen}（{hour_gz}）"

    # 生成分析
    analysis = _generate_analysis(hexagram, changed, upper_trigram, lower_trigram, moving_yao_pos, "time")

    # 生成推荐号码
    numbers = _generate_numbers(yao_tuple, hexagram)

    return DivinationResult(
        hexagram=hexagram,
        changed_hexagram=changed,
        yao=yao_tuple,
        method="时间起卦（梅花易数）",
        time_str=time_str,
        upper_trigram=upper_trigram,
        lower_trigram=lower_trigram,
        moving_yao=[moving_yao_pos],
        analysis=analysis,
        recommended_numbers=numbers,
    )


# ──────────────────────────────────────────────────────────────────────
# 随机起卦
# ──────────────────────────────────────────────────────────────────────

def batch_time_divination(
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    hours: list[int] | None = None,
) -> list[DivinationResult]:
    """批量时间起卦，为每个指定的小时生成一组卦象.

    Args:
        year: 公历年（默认当前年）
        month: 公历月（默认当前月）
        day: 公历日（默认当日）
        hours: 小时列表（24小时制），每个小时生成一卦

    Returns:
        DivinationResult 列表
    """
    if not hours:
        return [time_divination(year, month, day)]

    results = []
    for h in hours:
        result = time_divination(year, month, day, hour=h)
        results.append(result)
    return results


def random_divination(seed: int | None = None) -> DivinationResult:
    """随机起卦.

    Args:
        seed: 随机种子（可选，用于重现结果）

    Returns:
        DivinationResult 占卜结果
    """
    rng = random.Random(seed)

    # 随机生成6爻
    yao_list = []
    moving_yao = []

    for i in range(6):
        # 随机决定是否为老阳(2)、少阳(1)、老阴(3)、少阴(0)
        r = rng.random()
        if r < 0.125:  # 1/8 老阳
            yao_list.append(2)
            moving_yao.append(i)
        elif r < 0.5:  # 3/8 少阳
            yao_list.append(1)
        elif r < 0.625:  # 1/8 老阴
            yao_list.append(3)
            moving_yao.append(i)
        else:  # 3/8 少阴
            yao_list.append(0)

    yao_tuple = tuple(yao_list)

    # 获取上下卦（将动爻转换为普通爻用于查找卦象）
    lower_yao_raw = tuple(yao_list[:3])
    upper_yao_raw = tuple(yao_list[3:])
    lower_yao = tuple(y if y < 2 else (1 if y == 2 else 0) for y in lower_yao_raw)
    upper_yao = tuple(y if y < 2 else (1 if y == 2 else 0) for y in upper_yao_raw)

    upper_trigram = get_trigram_by_yao(upper_yao)
    lower_trigram = get_trigram_by_yao(lower_yao)

    if not upper_trigram or not lower_trigram:
        raise ValueError("无法解析卦象")

    hexagram = get_hexagram(upper_trigram.name, lower_trigram.name)
    if not hexagram:
        raise ValueError(f"无法找到卦象：{upper_trigram.name}上{lower_trigram.name}下")

    changed = get_changed_hexagram(yao_tuple)

    now = datetime.now(timezone.utc).astimezone()
    time_str = f"{now.year}年{now.month}月{now.day}日 {now.hour}时{now.minute}分"

    analysis = _generate_analysis(hexagram, changed, upper_trigram, lower_trigram, moving_yao, "random")
    numbers = _generate_numbers(yao_tuple, hexagram)

    return DivinationResult(
        hexagram=hexagram,
        changed_hexagram=changed,
        yao=yao_tuple,
        method="随机起卦",
        time_str=time_str,
        upper_trigram=upper_trigram,
        lower_trigram=lower_trigram,
        moving_yao=moving_yao,
        analysis=analysis,
        recommended_numbers=numbers,
    )


def manual_divination(yao_values: list[int]) -> DivinationResult:
    """手动输入爻象起卦.

    Args:
        yao_values: 6个爻值的列表（1=阳，0=阴）

    Returns:
        DivinationResult 占卜结果
    """
    if len(yao_values) != 6:
        raise ValueError("必须提供6个爻值")

    yao_tuple = tuple(yao_values)

    lower_yao = tuple(yao_values[:3])
    upper_yao = tuple(yao_values[3:])

    upper_trigram = get_trigram_by_yao(upper_yao)
    lower_trigram = get_trigram_by_yao(lower_yao)

    if not upper_trigram or not lower_trigram:
        raise ValueError("无法解析卦象")

    hexagram = get_hexagram(upper_trigram.name, lower_trigram.name)
    if not hexagram:
        raise ValueError(f"无法找到卦象：{upper_trigram.name}上{lower_trigram.name}下")

    changed = get_changed_hexagram(yao_tuple)

    now = datetime.now(timezone.utc).astimezone()
    time_str = f"{now.year}年{now.month}月{now.day}日 {now.hour}时{now.minute}分"

    analysis = _generate_analysis(hexagram, changed, upper_trigram, lower_trigram, [], "manual")
    numbers = _generate_numbers(yao_tuple, hexagram)

    return DivinationResult(
        hexagram=hexagram,
        changed_hexagram=changed,
        yao=yao_tuple,
        method="手动输入",
        time_str=time_str,
        upper_trigram=upper_trigram,
        lower_trigram=lower_trigram,
        moving_yao=[],
        analysis=analysis,
        recommended_numbers=numbers,
    )


# ──────────────────────────────────────────────────────────────────────
# 分析与推荐
# ──────────────────────────────────────────────────────────────────────

def _generate_analysis(
    hexagram: Hexagram,
    changed: Hexagram | None,
    upper: Trigram,
    lower: Trigram,
    moving_yao: int | list[int],
    method: str,
) -> str:
    """生成卦象分析."""
    lines = []

    # 卦象基本信息
    lines.append(f"【{hexagram.full_name}】{hexagram.description}")
    lines.append("")

    # 五行分析
    upper_element = upper.element
    lower_element = lower.element
    lines.append(f"上卦{upper.name}属{upper_element}，下卦{lower.name}属{lower_element}")

    # 五行生克关系
    wuxing_relation = _get_wuxing_relation(upper_element, lower_element)
    lines.append(f"五行关系：{wuxing_relation}")

    # 卦德
    lines.append(f"上卦卦德为「{upper.nature}」，下卦卦德为「{lower.nature}」")

    # 变卦分析
    if changed:
        lines.append("")
        lines.append(f"变卦为「{changed.full_name}」，{changed.description}")

    # 综合判断
    lines.append("")
    if hexagram.nature == "吉":
        lines.append("综合判断：此卦大吉，宜积极进取。")
    elif hexagram.nature == "凶":
        lines.append("综合判断：此卦有凶，宜谨慎行事。")
    else:
        lines.append("综合判断：此卦平和，宜守正道，随机应变。")

    return "\n".join(lines)


def _get_wuxing_relation(element1: str, element2: str) -> str:
    """获取五行关系."""
    wuxing_cycle = {
        "木": "火", "火": "土", "土": "金", "金": "水", "水": "木"
    }
    wuxing克制 = {
        "木": "土", "土": "水", "水": "火", "火": "金", "金": "木"
    }

    if wuxing_cycle.get(element1) == element2:
        return f"{element1}生{element2}，相生关系"
    elif wuxing_cycle.get(element2) == element1:
        return f"{element2}生{element1}，相生关系"
    elif wuxing克制.get(element1) == element2:
        return f"{element1}克{element2}，相克关系"
    elif wuxing克制.get(element2) == element1:
        return f"{element2}克{element1}，相克关系"
    elif element1 == element2:
        return f"同属{element1}，比和关系"
    else:
        return "五行关系需结合具体分析"


def _generate_numbers(yao: tuple[int, ...], hexagram: Hexagram) -> list[int]:
    """根据卦象生成推荐号码.

    基于先天八卦数和爻象推算：
    - 乾=1, 兑=2, 离=3, 震=4, 巽=5, 坎=6, 艮=7, 坤=8
    - 通过组合运算生成0-9的数字
    """
    numbers = set()

    # 先天八卦数映射
    xiantian_num = {"乾": 1, "兑": 2, "离": 3, "震": 4, "巽": 5, "坎": 6, "艮": 7, "坤": 8}

    # 上下卦数字
    upper_num = xiantian_num.get(hexagram.upper, 1)
    lower_num = xiantian_num.get(hexagram.lower, 1)

    # 基于卦数生成数字
    numbers.add((upper_num + lower_num) % 10)
    numbers.add((upper_num * lower_num) % 10)
    numbers.add(abs(upper_num - lower_num))
    numbers.add(upper_num % 10)
    numbers.add(lower_num % 10)

    # 基于爻象生成数字
    yao_sum = sum(1 if y in (1, 2) else 0 for y in yao)
    numbers.add(yao_sum % 10)
    numbers.add((yao_sum * 3) % 10)

    # 动爻位置
    for i, y in enumerate(yao):
        if y in (2, 3):
            numbers.add(i + 1)
            numbers.add((i + 1) * 2 % 10)

    # 确保有6-8个不同的数字
    all_nums = list(range(10))
    random.shuffle(all_nums)
    for n in all_nums:
        if len(numbers) >= 8:
            break
        numbers.add(n)

    # 返回排序后的数字（转换为1-33范围，适用于双色球）
    result = sorted(numbers)[:8]
    # 调整到1-33范围
    result = [(n % 33) + 1 for n in result]

    return result[:8]
