"""农历转换核心算法.

基于1900-2100年农历数据查表法，支持公历↔农历互转。
数据来源：紫金山天文台天文年历。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolarDate:
    """公历日期."""

    year: int
    month: int
    day: int

    def to_tuple(self) -> tuple[int, int, int]:
        return (self.year, self.month, self.day)


@dataclass(frozen=True)
class LunarDate:
    """农历日期."""

    year: int
    month: int
    day: int
    is_leap: bool = False

    def to_tuple(self) -> tuple[int, int, int, bool]:
        return (self.year, self.month, self.day, self.is_leap)


# ──────────────────────────────────────────────────────────────────────
# 农历数据表（1900-2100）
# 每个元素编码一年的农历信息：
# - 高4位：闰月月份（0表示无闰月）
# - 第16-19位：闰月大小月（1=30天，0=29天）
# - 低12位：1-12月大小月（1=30天，0=29天）
# ──────────────────────────────────────────────────────────────────────
_LUNAR_INFO = [
    0x04BD8, 0x04AE0, 0x0A570, 0x054D5, 0x0D260, 0x0D950, 0x16554, 0x056A0, 0x09AD0, 0x055D2,
    0x04AE0, 0x0A5B6, 0x0A4D0, 0x0D250, 0x1D255, 0x0B540, 0x0D6A0, 0x0ADA2, 0x095B0, 0x14977,
    0x04970, 0x0A4B0, 0x0B4B5, 0x06A50, 0x06D40, 0x1AB54, 0x02B60, 0x09570, 0x052F2, 0x04970,
    0x06566, 0x0D4A0, 0x0EA50, 0x06E95, 0x05AD0, 0x02B60, 0x186E3, 0x092E0, 0x1C8D7, 0x0C950,
    0x0D4A0, 0x1D8A6, 0x0B550, 0x056A0, 0x1A5B4, 0x025D0, 0x092D0, 0x0D2B2, 0x0A950, 0x0B557,
    0x06CA0, 0x0B550, 0x15355, 0x04DA0, 0x0A5B0, 0x14573, 0x052B0, 0x0A9A8, 0x0E950, 0x06AA0,
    0x0AEA6, 0x0AB50, 0x04B60, 0x0AAE4, 0x0A570, 0x05260, 0x0F263, 0x0D950, 0x05B57, 0x056A0,
    0x096D0, 0x04DD5, 0x04AD0, 0x0A4D0, 0x0D4D4, 0x0D250, 0x0D558, 0x0B540, 0x0B6A0, 0x195A6,
    0x095B0, 0x049B0, 0x0A974, 0x0A4B0, 0x0B27A, 0x06A50, 0x06D40, 0x0AF46, 0x0AB60, 0x09570,
    0x04AF5, 0x04970, 0x064B0, 0x074A3, 0x0EA50, 0x06B58, 0x055C0, 0x0AB60, 0x096D5, 0x092E0,
    0x0C960, 0x0D954, 0x0D4A0, 0x0DA50, 0x07552, 0x056A0, 0x0ABB7, 0x025D0, 0x092D0, 0x0cab5,
    0x0A950, 0x0B4A0, 0x0BAA4, 0x0AD50, 0x055D9, 0x04BA0, 0x0A5B0, 0x15176, 0x052B0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,
    0x0d520,
]

# 每年农历月份天数基准（29天）
LUNAR_MONTH_DAYS = 29

# 公历每月天数（非闰年）
_SOLAR_MONTH_DAYS = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# 农历月份名称
LUNAR_MONTH_NAMES = [
    "", "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "冬月", "腊月",
]

# 农历日期名称
LUNAR_DAY_NAMES = [
    "", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]


def _is_leap_year(year: int) -> bool:
    """判断公历闰年."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _solar_month_days(year: int, month: int) -> int:
    """返回公历某月的天数."""
    if month == 2 and _is_leap_year(year):
        return 29
    return _SOLAR_MONTH_DAYS[month]


def _lunar_year_days(year: int) -> int:
    """返回农历某年的总天数."""
    info = _LUNAR_INFO[year - 1900]
    total = 0
    for i in range(12):
        total += 30 if info & (1 << (16 + i)) else 29
    # 闰月天数
    leap_month = info >> 20
    if leap_month:
        total += 30 if info & (1 << (16 - 1)) else 29
    return total


def _lunar_month_days_info(year: int, month: int, is_leap: bool = False) -> int:
    """返回农历某月的天数（29或30天）."""
    info = _LUNAR_INFO[year - 1900]
    _leap_month = info >> 20

    if is_leap:
        # 闰月天数在第16位
        return 30 if info & (1 << 15) else 29
    else:
        # 普通月份天数在第17-28位（对应1-12月）
        if month > 12 or month < 1:
            raise ValueError(f"无效农历月份: {month}")
        return 30 if info & (1 << (16 + month - 1)) else 29


def _get_leap_month(year: int) -> int:
    """返回闰月月份，0表示无闰月."""
    return _LUNAR_INFO[year - 1900] >> 20


def solar_to_lunar(year: int, month: int, day: int) -> LunarDate:
    """公历转农历.

    Args:
        year: 公历年
        month: 公历月
        day: 公历日

    Returns:
        LunarDate 对象
    """
    if year < 1900 or year > 2100:
        raise ValueError("支持的年份范围为 1900-2100")

    # 计算距离 1900年1月31日（农历1900年正月初一）的天数
    _base_date = (1900, 1, 31)
    target_date = (year, month, day)

    # 计算天数差
    days_diff = 0
    y, m, d = 1900, 1, 31
    while (y, m, d) < target_date:
        days_diff += 1
        d += 1
        if d > _solar_month_days(y, m):
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1

    # 遍历农历年月日
    lunar_year = 1900
    lunar_month = 1
    lunar_day = 1
    is_leap = False

    # 先找年
    year_days = _lunar_year_days(lunar_year)
    while days_diff >= year_days:
        days_diff -= year_days
        lunar_year += 1
        if lunar_year > 2100:
            raise ValueError("超出支持范围")
        year_days = _lunar_year_days(lunar_year)

    # 再找月
    leap_month = _get_leap_month(lunar_year)
    month_num = 12 + (1 if leap_month else 0)
    month_idx = 0

    while month_idx < month_num:
        if month_idx < 12:
            m = month_idx + 1
            is_leap = False
        else:
            m = leap_month
            is_leap = True

        days = _lunar_month_days_info(lunar_year, m, is_leap)
        if days_diff < days:
            lunar_month = m
            lunar_day = days_diff + 1
            break
        days_diff -= days
        month_idx += 1
    else:
        lunar_month = 12
        lunar_day = days_diff + 1

    return LunarDate(year=lunar_year, month=lunar_month, day=lunar_day, is_leap=is_leap)


def lunar_to_solar(year: int, month: int, day: int, is_leap: bool = False) -> SolarDate:
    """农历转公历.

    Args:
        year: 农历年
        month: 农历月
        day: 农历日
        is_leap: 是否为闰月

    Returns:
        SolarDate 对象
    """
    if year < 1900 or year > 2100:
        raise ValueError("支持的年份范围为 1900-2100")

    # 计算距离 1900年正月初一 的天数
    days_diff = 0

    # 加上之前年份的天数
    for y in range(1900, year):
        days_diff += _lunar_year_days(y)

    # 加上之前月份的天数
    leap_month = _get_leap_month(year)
    month_num = 12 + (1 if leap_month else 0)
    month_idx = 0

    while month_idx < month_num:
        if month_idx < 12:
            m = month_idx + 1
            cur_leap = False
        else:
            m = leap_month
            cur_leap = True

        if m == month and cur_leap == is_leap:
            break

        days_diff += _lunar_month_days_info(year, m, cur_leap)
        month_idx += 1

    days_diff += day - 1

    # 基准：1900年1月31日
    base_year, base_month, base_day = 1900, 1, 31
    y, m, d = base_year, base_month, base_day

    for _ in range(days_diff):
        d += 1
        if d > _solar_month_days(y, m):
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1

    return SolarDate(year=y, month=m, day=d)


def lunar_month_name(month: int, is_leap: bool = False) -> str:
    """返回农历月份中文名."""
    if is_leap:
        return f"闰{LUNAR_MONTH_NAMES[month]}"
    return LUNAR_MONTH_NAMES[month]


def lunar_day_name(day: int) -> str:
    """返回农历日期中文名."""
    if 1 <= day <= 30:
        return LUNAR_DAY_NAMES[day]
    return str(day)


def get_weekday(year: int, month: int, day: int) -> int:
    """返回星期几（0=周一, 6=周日）."""
    import datetime
    return datetime.date(year, month, day).weekday()


def get_weekday_name(year: int, month: int, day: int) -> str:
    """返回星期几中文名."""
    names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return names[get_weekday(year, month, day)]
