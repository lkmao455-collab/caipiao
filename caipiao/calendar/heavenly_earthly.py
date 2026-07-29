"""天干地支计算模块.

提供年、月、日、时的天干地支推算，以及生肖计算。
"""

from __future__ import annotations

# 天干
HEAVENLY_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 地支
EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 生肖
SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

# 地支对应生肖索引
_BRANCH_SHENGXIAO = {
    "子": "鼠", "丑": "牛", "寅": "虎", "卯": "兔", "辰": "龙", "巳": "蛇",
    "午": "马", "未": "羊", "申": "猴", "酉": "鸡", "戌": "狗", "亥": "猪",
}

# 五行
WUXING = ["木", "火", "土", "金", "水"]

# 天干对应五行
STEM_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 地支对应五行
BRANCH_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 时辰对照表（24小时→地支）
_HOUR_BRANCHES = [
    (23, 1, "子"), (1, 3, "丑"), (3, 5, "寅"), (5, 7, "卯"),
    (7, 9, "辰"), (9, 11, "巳"), (11, 13, "午"), (13, 15, "未"),
    (15, 17, "申"), (17, 19, "酉"), (19, 21, "戌"), (21, 23, "亥"),
]

# 时辰中文名
SHICHEN_NAMES = [
    "子时", "丑时", "寅时", "卯时", "辰时", "巳时",
    "午时", "未时", "申时", "酉时", "戌时", "亥时",
]

# 农历月份天干起始
# 甲己之年丙作首，乙庚之年戊为头，丙辛之岁寻庚上，丁壬壬寅顺水流，若问戊癸何处觅，甲寅之上好追求
_MONTH_STEM_START = {
    "甲": 2, "己": 2,  # 丙
    "乙": 4, "庚": 4,  # 戊
    "丙": 6, "辛": 6,  # 庚
    "丁": 8, "壬": 8,  # 壬
    "戊": 0, "癸": 0,  # 甲
}

# 日干支推算基数（以1900年1月1日甲戌日为基准）
# 1900年1月1日 = 甲戌日 = 天干0(甲) + 地支10(戌)
_BASE_DAY_STEM = 0  # 甲
_BASE_DAY_BRANCH = 10  # 戌
_BASE_DATE = (1900, 1, 1)


def get_ganzhi_year(year: int) -> str:
    """计算农历年的天干地支.

    公式：(year - 4) % 60 = 干支序号
    """
    ganzhi_index = (year - 4) % 60
    stem_index = ganzhi_index % 10
    branch_index = ganzhi_index % 12
    return f"{HEAVENLY_STEMS[stem_index]}{EARTHLY_BRANCHES[branch_index]}"


def get_ganzhi_month(year: int, month: int, day: int) -> str:
    """计算农历月的天干地支.

    以节气为分界（立春为年分界，节气为月分界）。
    简化计算：基于农历年干推月干，农历月支固定。
    """
    # 农历月支：寅(1月)起
    month_branch_index = (month + 1) % 12  # 正月=寅(2), 二月=卯(3), ...

    # 年干推月干
    year_stem = get_ganzhi_year(year)[0]
    month_stem_start = _MONTH_STEM_START.get(year_stem, 0)
    month_stem_index = (month_stem_start + month - 1) % 10

    return f"{HEAVENLY_STEMS[month_stem_index]}{EARTHLY_BRANCHES[month_branch_index]}"


def _day_from_base(year: int, month: int, day: int) -> int:
    """计算距离基准日期的天数."""
    import datetime
    base = datetime.date(*_BASE_DATE)
    target = datetime.date(year, month, day)
    return (target - base).days


def get_ganzhi_day(year: int, month: int, day: int) -> str:
    """计算日期的天干地支.

    基于1900年1月1日甲戌日推算。
    """
    days_diff = _day_from_base(year, month, day)
    stem_index = (_BASE_DAY_STEM + days_diff) % 10
    branch_index = (_BASE_DAY_BRANCH + days_diff) % 12
    return f"{HEAVENLY_STEMS[stem_index]}{EARTHLY_BRANCHES[branch_index]}"


def get_ganzhi_hour(hour: int, day_stem: str) -> str:
    """计算时辰的天干地支.

    Args:
        hour: 24小时制的小时 (0-23)
        day_stem: 日干（用于推时干）

    Returns:
        时干支字符串
    """
    # 确定时辰地支
    branch_index = 0
    for start, end, branch in _HOUR_BRANCHES:
        if start <= hour < end or (start == 23 and hour >= 23):
            branch_index = EARTHLY_BRANCHES.index(branch)
            break

    # 日干推时干：甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸壬子时
    day_stem_map = {"甲": 0, "己": 0, "乙": 2, "庚": 2, "丙": 4, "辛": 4, "丁": 6, "壬": 6, "戊": 8, "癸": 8}
    hour_stem_start = day_stem_map.get(day_stem, 0)
    hour_stem_index = (hour_stem_start + branch_index) % 10

    return f"{HEAVENLY_STEMS[hour_stem_index]}{EARTHLY_BRANCHES[branch_index]}"


def get_shengxiao(year: int) -> str:
    """计算生肖.

    公式：(year - 4) % 12 = 生肖索引
    """
    index = (year - 4) % 12
    return SHENGXIAO[index]


def get_ganzhi(year: int, month: int, day: int, hour: int | None = None) -> dict:
    """获取完整的干支信息.

    Args:
        year: 公历年
        month: 公历月
        day: 公历日
        hour: 公历时（可选，24小时制）

    Returns:
        包含年干支、月干支、日干支、时干支、生肖的字典
    """
    year_gz = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz = get_ganzhi_day(year, month, day)

    result = {
        "year_ganzhi": year_gz,
        "month_ganzhi": month_gz,
        "day_ganzhi": day_gz,
        "shengxiao": get_shengxiao(year),
        "year_stem": year_gz[0],
        "year_branch": year_gz[1],
        "month_stem": month_gz[0],
        "month_branch": month_gz[1],
        "day_stem": day_gz[0],
        "day_branch": day_gz[1],
        "year_wuxing": STEM_WUXING.get(year_gz[0], ""),
        "month_wuxing": STEM_WUXING.get(month_gz[0], ""),
        "day_wuxing": STEM_WUXING.get(day_gz[0], ""),
    }

    if hour is not None:
        hour_gz = get_ganzhi_hour(hour, day_gz[0])
        result["hour_ganzhi"] = hour_gz
        result["hour_stem"] = hour_gz[0]
        result["hour_branch"] = hour_gz[1]
        result["hour_wuxing"] = STEM_WUXING.get(hour_gz[0], "")
        result["shichen"] = SHICHEN_NAMES[EARTHLY_BRANCHES.index(hour_gz[1])]

    return result


def get_chongsha(day_branch: str) -> str:
    """根据日支计算冲煞.

    六冲：子午、丑未、寅申、卯酉、辰戌、巳亥
    """
    chong_map = {
        "子": "午", "午": "子", "丑": "未", "未": "丑",
        "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
        "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
    }
    chong = chong_map.get(day_branch, "")
    shengxiao = _BRANCH_SHENGXIAO.get(chong, "")
    return f"冲{shengxiao}({day_branch}{chong})"


def get_shichen(hour: int) -> str:
    """获取时辰名称."""
    for i, (start, end, branch) in enumerate(_HOUR_BRANCHES):
        if start <= hour < end or (start == 23 and hour >= 23):
            return SHICHEN_NAMES[i]
    return "子时"
