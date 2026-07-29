"""八卦基础数据模块.

定义八卦（三爻卦）的基本信息，包括名称、符号、五行、爻象等。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Trigram:
    """八卦（三爻卦）."""

    name: str          # 卦名
    symbol: str        # Unicode符号
    number: int        # 先天八卦数
    later_number: int  # 后天八卦数
    element: str       # 五行属性
    nature: str        # 卦德（性质）
    direction: str     # 方位（后天八卦）
    body_part: str     # 身体部位
    family: str        # 家庭成员
    animal: str        # 动物
    season: str        # 季节
    yao: tuple[int, int, int]  # 爻象（从下到上，1=阳，0=阴）
    image: str         # 卦象描述

    def yao_text(self) -> List[str]:
        """返回从下到上的爻辞描述."""
        result = []
        for i, y in enumerate(self.yao):
            pos = ["初", "二", "三"][i]
            if y == 1:
                result.append(f"{pos}爻（阳）━━━━")
            else:
                result.append(f"{pos}爻（阴）━ ━")
        return result

    def to_upper(self) -> str:
        """上半部分符号（用于六爻卦展示）."""
        lines = []
        for y in reversed(self.yao):
            if y == 1:
                lines.append("━━━━━")
            else:
                lines.append("━ ━")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# 八卦数据
# 爻序：从下到上（初爻在最下面）
# ──────────────────────────────────────────────────────────────────────

BAGUA: Dict[str, Trigram] = {}


def _add_trigram(name: str, symbol: str, number: int, later_number: int,
                 element: str, nature: str, direction: str,
                 body_part: str, family: str, animal: str,
                 season: str, yao: tuple[int, int, int], image: str) -> Trigram:
    """添加一个八卦."""
    t = Trigram(
        name=name, symbol=symbol, number=number, later_number=later_number,
        element=element, nature=nature, direction=direction,
        body_part=body_part, family=family, animal=animal,
        season=season, yao=yao, image=image,
    )
    BAGUA[name] = t
    return t


# 先天八卦序
_add_trigram("乾", "☰", 1, 6, "金", "健", "西北", "头", "父", "马", "冬", (1, 1, 1), "天")
_add_trigram("兑", "☱", 2, 7, "金", "悦", "西", "口", "少女", "羊", "秋", (0, 1, 1), "泽")
_add_trigram("离", "☲", 3, 9, "火", "丽", "南", "目", "中女", "雉", "夏", (1, 0, 1), "火")
_add_trigram("震", "☳", 4, 3, "木", "动", "东", "足", "长男", "龙", "春", (0, 0, 1), "雷")
_add_trigram("巽", "☴", 5, 4, "木", "入", "东南", "股", "长女", "鸡", "春夏", (1, 1, 0), "风")
_add_trigram("坎", "☵", 6, 1, "水", "陷", "北", "耳", "中男", "豕", "冬", (0, 1, 0), "水")
_add_trigram("艮", "☶", 7, 8, "土", "止", "东北", "手", "少男", "狗", "冬春", (1, 0, 0), "山")
_add_trigram("坤", "☷", 8, 2, "土", "顺", "西南", "腹", "母", "牛", "夏秋", (0, 0, 0), "地")

# 名称索引
_TRIGRAM_NAMES = list(BAGUA.keys())
_TRIGRAM_BY_NUMBER = {t.number: t for t in BAGUA.values()}
_TRIGRAM_BY_LATER = {t.later_number: t for t in BAGUA.values()}
_TRIGRAM_BY_YAO = {t.yao: t for t in BAGUA.values()}


def get_trigram_by_name(name: str) -> Optional[Trigram]:
    """按名称获取八卦."""
    return BAGUA.get(name)


def get_trigram_by_number(number: int) -> Optional[Trigram]:
    """按先天八卦数获取八卦."""
    return _TRIGRAM_BY_NUMBER.get(number)


def get_trigram_by_later_number(later_number: int) -> Optional[Trigram]:
    """按后天八卦数获取八卦."""
    return _TRIGRAM_BY_LATER.get(later_number)


def get_trigram_by_yao(yao: tuple[int, int, int]) -> Optional[Trigram]:
    """按爻象获取八卦."""
    return _TRIGRAM_BY_YAO.get(yao)


def get_yao_from_number(number: int) -> tuple[int, int, int]:
    """将数字(1-8)转换为三爻卦象.

    用于梅花易数起卦：
    - 余数为1→乾(111), 2→兑(011), 3→离(101), 4→震(001)
    - 余数为5→巽(110), 6→坎(010), 7→艮(100), 0→坤(000)
    """
    mapping = {
        1: (1, 1, 1),  # 乾
        2: (0, 1, 1),  # 兑
        3: (1, 0, 1),  # 离
        4: (0, 0, 1),  # 震
        5: (1, 1, 0),  # 巽
        6: (0, 1, 0),  # 坎
        7: (1, 0, 0),  # 艮
        0: (0, 0, 0),  # 坤（余数为0时）
    }
    return mapping.get(number % 8, (0, 0, 0))


def get_trigram_by_meihua_number(number: int) -> Optional[Trigram]:
    """按梅花易数数字获取八卦."""
    yao = get_yao_from_number(number)
    return get_trigram_by_yao(yao)


def list_trigrams() -> List[Trigram]:
    """返回全部八卦列表（按先天数排序）."""
    return [get_trigram_by_number(i) for i in range(1, 9)]
