"""黄历宜忌、节气、节日模块.

提供每日宜忌、二十四节气、传统节日和公历节日信息。
"""

from __future__ import annotations

from .heavenly_earthly import (
    BRANCH_WUXING,
    EARTHLY_BRANCHES,
    STEM_WUXING,
    get_chongsha,
    get_ganzhi_day,
)

# ──────────────────────────────────────────────────────────────────────
# 黄历宜忌基础数据
# 基于天干地支推算的简化宜忌系统
# ──────────────────────────────────────────────────────────────────────

# 宜事分类
YI_CATEGORIES = {
    "祭祀": "祭祀祖先、神明",
    "祈福": "祈求福运、许愿",
    "求嗣": "祈求子嗣",
    "开光": "佛像、神像开光",
    "塑绘": "雕塑绘画",
    "出行": "外出旅行",
    "出行_1": "出差远行",
    "剃头": "理发",
    "修造": "修缮建造",
    "动土": "破土动工",
    "竖柱": "竖立柱子",
    "上梁": "上梁封顶",
    "开市": "商店开张营业",
    "交易": "买卖交易",
    "立券": "签订契约",
    "纳财": "收账进财",
    "开仓": "开仓出货",
    "出货财": "出售货物",
    "栽种": "种植作物",
    "牧养": "放牧饲养",
    "纳畜": "买入牲畜",
    "会亲友": "朋友聚会",
    "嫁娶": "结婚",
    "纳采": "下聘礼",
    "订盟": "订婚",
    "裁衣": "裁剪衣服",
    "合帐": "缝制蚊帐",
    "冠笄": "成人礼",
    "安机械": "安置机械",
    "安床": "安置床铺",
    "解除": "解除禁忌",
    "扫舍": "打扫房屋",
    "进人口": "雇人或收养",
    "开渠": "开挖水渠",
    "造桥": "建造桥梁",
    "开厕": "建造厕所",
    "造屋": "建造房屋",
    "合寿木": "准备棺材",
    "入殓": "将遗体入棺",
    "移柩": "移动棺材",
    "破土": "挖坟动土",
    "安葬": "下葬",
    "启钻": "捡骨迁坟",
    "修坟": "修缮坟墓",
}

# 忌事分类
JI_CATEGORIES = {
    "嫁娶": "不宜结婚",
    "移徙": "不宜搬家",
    "入宅": "不宜迁入新居",
    "安香": "不宜安放神位",
    "上梁": "不宜上梁",
    "安床": "不宜安床",
    "开市": "不宜开张",
    "出行": "不宜远行",
    "动土": "不宜破土动工",
    "伐木": "不宜砍伐树木",
    "行丧": "不宜举行丧事",
    "破土": "不宜挖坟动土",
    "安葬": "不宜下葬",
    "修坟": "不宜修坟",
}

# 宜忌推算规则（简化版，基于日干支）
# 实际黄历系统非常复杂，这里使用简化算法
_YI_RULES = {
    "甲": {
        "子": ["祭祀", "祈福", "出行", "交易", "立券", "纳财"],
        "丑": ["嫁娶", "裁衣", "冠笄", "造屋", "栽种", "牧养"],
        "寅": ["修造", "动土", "竖柱", "上梁", "开市", "交易"],
        "卯": ["嫁娶", "纳采", "订盟", "祈福", "祭祀", "出行"],
        "辰": ["祈福", "求嗣", "开光", "塑绘", "裁衣", "合帐"],
        "巳": ["开市", "交易", "立券", "纳财", "栽种", "牧养"],
        "午": ["嫁娶", "纳采", "订盟", "祭祀", "祈福", "出行"],
        "未": ["修造", "动土", "安机械", "栽种", "开渠", "造桥"],
        "申": ["嫁娶", "裁衣", "冠笄", "交易", "立券", "纳财"],
        "酉": ["祭祀", "祈福", "出行", "移徙", "入宅", "安香"],
        "戌": ["嫁娶", "纳采", "订盟", "祈福", "祭祀", "求嗣"],
        "亥": ["开市", "交易", "立券", "纳财", "栽种", "牧养"],
    },
    "乙": {
        "子": ["嫁娶", "裁衣", "冠笄", "修造", "动土", "开市"],
        "丑": ["祭祀", "祈福", "出行", "交易", "立券", "纳财"],
        "寅": ["嫁娶", "纳采", "订盟", "裁衣", "合帐", "冠笄"],
        "卯": ["祭祀", "祈福", "开光", "塑绘", "出行", "移徙"],
        "辰": ["开市", "交易", "立券", "纳财", "栽种", "牧养"],
        "巳": ["嫁娶", "纳采", "订盟", "祭祀", "祈福", "求嗣"],
        "午": ["修造", "动土", "竖柱", "上梁", "开市", "交易"],
        "未": ["嫁娶", "裁衣", "冠笄", "合帐", "安床", "解除"],
        "申": ["祭祀", "祈福", "出行", "移徙", "入宅", "安香"],
        "酉": ["开市", "交易", "立券", "纳财", "栽种", "牧养"],
        "戌": ["嫁娶", "纳采", "订盟", "裁衣", "冠笄", "修造"],
        "亥": ["祭祀", "祈福", "开光", "塑绘", "出行", "入殓"],
    },
}

# 天干对应的宜忌补充
_STEM_YI_EXTRAS = {
    "甲": ["开市", "交易"],
    "乙": ["嫁娶", "裁衣"],
    "丙": ["祭祀", "祈福"],
    "丁": ["修造", "动土"],
    "戊": ["开市", "纳财"],
    "己": ["嫁娶", "纳采"],
    "庚": ["出行", "移徙"],
    "辛": ["祭祀", "祈福"],
    "壬": ["开市", "交易"],
    "癸": ["嫁娶", "裁衣"],
}

# 地支对应的忌事补充
_BRANCH_JI_EXTRAS = {
    "子": ["行丧", "破土"],
    "丑": ["安葬", "修坟"],
    "寅": ["移徙", "入宅"],
    "卯": ["动土", "伐木"],
    "辰": ["安葬", "行丧"],
    "巳": ["嫁娶", "移徙"],
    "午": ["动土", "破土"],
    "未": ["嫁娶", "安香"],
    "申": ["出行", "移徙"],
    "酉": ["动土", "伐木"],
    "戌": ["安葬", "修坟"],
    "亥": ["嫁娶", "开市"],
}


def _get_yi_for_day(day_stem: str, day_branch: str) -> list[str]:
    """根据日干支推算宜事."""
    yi = []

    # 基础宜事
    if day_stem in _YI_RULES and day_branch in _YI_RULES[day_stem]:
        yi.extend(_YI_RULES[day_stem][day_branch])
    else:
        # 默认宜事
        yi.extend(["祭祀", "祈福", "出行", "交易"])

    # 天干补充
    if day_stem in _STEM_YI_EXTRAS:
        for item in _STEM_YI_EXTRAS[day_stem]:
            if item not in yi:
                yi.append(item)

    # 去重并限制数量（一般黄历显示4-6件宜事）
    seen = set()
    result = []
    for item in yi:
        if item not in seen:
            seen.add(item)
            result.append(item)
        if len(result) >= 6:
            break

    return result


def _get_ji_for_day(day_stem: str, day_branch: str) -> list[str]:
    """根据日干支推算忌事."""
    ji = []

    # 地支忌事
    if day_branch in _BRANCH_JI_EXTRAS:
        ji.extend(_BRANCH_JI_EXTRAS[day_branch])

    # 补充一些常见忌事
    common_ji = ["行丧", "伐木", "破土", "安葬"]
    for item in common_ji:
        if item not in ji:
            ji.append(item)

    # 去重并限制数量
    seen = set()
    result = []
    for item in ji:
        if item not in seen:
            seen.add(item)
            result.append(item)
        if len(result) >= 4:
            break

    return result


def get_almanac(year: int, month: int, day: int) -> dict:
    """获取指定日期的黄历信息.

    Args:
        year: 公历年
        month: 公历月
        day: 公历日

    Returns:
        包含宜忌、冲煞等信息的字典
    """
    day_gz = get_ganzhi_day(year, month, day)
    day_stem = day_gz[0]
    day_branch = day_gz[1]

    yi = _get_yi_for_day(day_stem, day_branch)
    ji = _get_ji_for_day(day_stem, day_branch)
    chongsha = get_chongsha(day_branch)

    return {
        "day_ganzhi": day_gz,
        "day_stem": day_stem,
        "day_branch": day_branch,
        "yi": yi,
        "ji": ji,
        "chongsha": chongsha,
        "shengsha": f"煞{_get_shengsha_direction(day_branch)}",
    }


def _get_shengsha_direction(branch: str) -> str:
    """根据日支确定煞的方位."""
    directions = ["东", "南", "西", "北", "东", "南", "西", "北", "东", "南", "西", "北"]
    index = EARTHLY_BRANCHES.index(branch)
    return directions[index % 4]


# ──────────────────────────────────────────────────────────────────────
# 二十四节气
# ──────────────────────────────────────────────────────────────────────

# 节气名称
SOLAR_TERMS = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]

# 节气近似日期（实际日期每年略有变化，±1-2天）
_SOLAR_TERM_DATES = {
    "小寒": (1, 6), "大寒": (1, 20),
    "立春": (2, 4), "雨水": (2, 19),
    "惊蛰": (3, 6), "春分": (3, 21),
    "清明": (4, 5), "谷雨": (4, 20),
    "立夏": (5, 6), "小满": (5, 21),
    "芒种": (6, 6), "夏至": (6, 21),
    "小暑": (7, 7), "大暑": (7, 23),
    "立秋": (8, 7), "处暑": (8, 23),
    "白露": (9, 8), "秋分": (9, 23),
    "寒露": (10, 8), "霜降": (10, 23),
    "立冬": (11, 7), "小雪": (11, 22),
    "大雪": (12, 7), "冬至": (12, 22),
}

# 节气详细信息
SOLAR_TERM_INFO = {
    "小寒": {"order": 23, "desc": "天渐寒，尚未大冷"},
    "大寒": {"order": 24, "desc": "一年中最冷的时节"},
    "立春": {"order": 1, "desc": "春季开始"},
    "雨水": {"order": 2, "desc": "降雨开始，雨量渐增"},
    "惊蛰": {"order": 3, "desc": "春雷初响，蛰虫惊醒"},
    "春分": {"order": 4, "desc": "昼夜平分"},
    "清明": {"order": 5, "desc": "天气晴朗，草木繁茂"},
    "谷雨": {"order": 6, "desc": "雨水充足，谷物生长"},
    "立夏": {"order": 7, "desc": "夏季开始"},
    "小满": {"order": 8, "desc": "麦类等作物籽粒渐满"},
    "芒种": {"order": 9, "desc": "麦类成熟，稻谷播种"},
    "夏至": {"order": 10, "desc": "一年中白昼最长的一天"},
    "小暑": {"order": 11, "desc": "天气开始炎热"},
    "大暑": {"order": 12, "desc": "一年中最热的时节"},
    "立秋": {"order": 13, "desc": "秋季开始"},
    "处暑": {"order": 14, "desc": "暑气渐消"},
    "白露": {"order": 15, "desc": "天气渐凉，露凝而白"},
    "秋分": {"order": 16, "desc": "昼夜平分"},
    "寒露": {"order": 17, "desc": "露气寒冷，将要凝结"},
    "霜降": {"order": 18, "desc": "天气渐冷，开始有霜"},
    "立冬": {"order": 19, "desc": "冬季开始"},
    "小雪": {"order": 20, "desc": "开始降雪"},
    "大雪": {"order": 21, "desc": "降雪增多"},
    "冬至": {"order": 22, "desc": "一年中白昼最短的一天"},
}


def get_solar_term(year: int, month: int) -> list[tuple[str, int, int]]:
    """获取指定月份的节气.

    Returns:
        [(节气名, 月, 日), ...] 的列表
    """
    terms = []
    for name, (m, d) in _SOLAR_TERM_DATES.items():
        if m == month:
            # 简单处理：某些年份节气日期可能±1天
            actual_day = d
            if year % 4 == 0 and month in (2, 8):
                actual_day = d - 1 if d > 1 else d
            terms.append((name, m, actual_day))
    return sorted(terms, key=lambda x: x[2])


def get_current_solar_term(year: int, month: int, day: int) -> str | None:
    """获取当前日期所在的节气.

    Returns:
        节气名称，如果没有则返回None
    """
    for name, (m, d) in _SOLAR_TERM_DATES.items():
        if m == month and abs(day - d) <= 1:
            return name
    return None


# ──────────────────────────────────────────────────────────────────────
# 传统节日（农历）
# ──────────────────────────────────────────────────────────────────────

TRADITIONAL_FESTIVALS = {
    (1, 1): "春节",
    (1, 15): "元宵节",
    (5, 5): "端午节",
    (7, 7): "七夕节",
    (7, 15): "中元节",
    (8, 15): "中秋节",
    (9, 9): "重阳节",
    (12, 30): "除夕",
    (12, 29): "除夕",  # 小月时除夕为腊月廿九
}


def get_traditional_festivals(lunar_month: int, lunar_day: int) -> list[str]:
    """获取农历日期对应的传统节日.

    Returns:
        节日名称列表
    """
    festivals = []

    # 基本节日
    key = (lunar_month, lunar_day)
    if key in TRADITIONAL_FESTIVALS:
        festivals.append(TRADITIONAL_FESTIVALS[key])

    return festivals


# ──────────────────────────────────────────────────────────────────────
# 公历节日
# ──────────────────────────────────────────────────────────────────────

SOLAR_FESTIVALS = {
    (1, 1): "元旦",
    (2, 14): "情人节",
    (3, 8): "妇女节",
    (3, 12): "植树节",
    (4, 1): "愚人节",
    (5, 1): "劳动节",
    (5, 4): "青年节",
    (6, 1): "儿童节",
    (7, 1): "建党节",
    (8, 1): "建军节",
    (9, 10): "教师节",
    (10, 1): "国庆节",
    (12, 25): "圣诞节",
}


def get_festivals(month: int, day: int) -> list[str]:
    """获取公历日期对应的节日.

    Returns:
        节日名称列表
    """
    festivals = []
    key = (month, day)
    if key in SOLAR_FESTIVALS:
        festivals.append(SOLAR_FESTIVALS[key])
    return festivals


# ──────────────────────────────────────────────────────────────────────
# 吉时推算
# ──────────────────────────────────────────────────────────────────────

# 五行相生关系
_WUXING_SHENG = {
    "木": "火", "火": "土", "土": "金", "金": "水", "水": "木"
}

# 五行相克关系
_WUXING_KE = {
    "木": "土", "土": "水", "水": "火", "火": "金", "金": "木"
}

# 地支六合
_SIX_COMBOS = {
    "子": "丑", "丑": "子",
    "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯",
    "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳",
    "午": "未", "未": "午",
}

# 地支六冲
_SIX_CLASHES = {
    "子": "午", "午": "子",
    "丑": "未", "未": "丑",
    "寅": "申", "申": "寅",
    "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰",
    "巳": "亥", "亥": "巳",
}

# 地支三合
_THREE_COMBOS = [
    ("申", "子", "辰"),  # 水局
    ("亥", "卯", "未"),  # 木局
    ("寅", "午", "戌"),  # 火局
    ("巳", "酉", "丑"),  # 金局
]

# 时辰地支列表
_SHICHEN_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


def _get_wuxing_relation(wx1: str, wx2: str) -> str:
    """获取两个五行之间的关系."""
    if wx1 == wx2:
        return "比和"
    if _WUXING_SHENG.get(wx1) == wx2:
        return "相生"
    if _WUXING_SHENG.get(wx2) == wx1:
        return "相生"
    if _WUXING_KE.get(wx1) == wx2:
        return "相克"
    if _WUXING_KE.get(wx2) == wx1:
        return "相克"
    return "无"


def _get_shichen_score(day_stem: str, day_branch: str, shichen_branch: str) -> int:
    """计算某个时辰对当日的吉利程度评分.

    评分规则：
    - 日支与时支六合：+30分
    - 日支与时支三合：+20分
    - 日干与时干相生：+15分
    - 日支五行与时支五行相生：+10分
    - 日支与时支六冲：-30分
    - 日干五行与时支五行相克：-10分
    - 基础分：50分
    """
    score = 50

    # 六合
    if _SIX_COMBOS.get(day_branch) == shichen_branch:
        score += 30

    # 三合
    for combo in _THREE_COMBOS:
        if day_branch in combo and shichen_branch in combo:
            score += 20
            break

    # 六冲
    if _SIX_CLASHES.get(day_branch) == shichen_branch:
        score -= 30

    # 日干与时干相生
    day_stem_wx = STEM_WUXING.get(day_stem, "")
    shichen_wx = BRANCH_WUXING.get(shichen_branch, "")
    if day_stem_wx and shichen_wx:
        relation = _get_wuxing_relation(day_stem_wx, shichen_wx)
        if relation == "相生":
            score += 15
        elif relation == "相克":
            score -= 10

    # 日支五行与时支五行相生
    day_branch_wx = BRANCH_WUXING.get(day_branch, "")
    if day_branch_wx and shichen_wx:
        relation = _get_wuxing_relation(day_branch_wx, shichen_wx)
        if relation == "相生":
            score += 10
        elif relation == "相克":
            score -= 10

    return score


def get_lucky_hours(year: int, month: int, day: int, min_score: int = 60) -> list[dict]:
    """获取当日吉时.

    基于日干支与时辰的五行生克、六合六冲等关系推算。

    Args:
        year: 公历年
        month: 公历月
        day: 公历日
        min_score: 最低吉利分数阈值（默认60分以上为吉时）

    Returns:
        吉时列表，每项包含：
        - branch: 时辰地支
        - name: 时辰名称
        - hours: 对应的24小时制小时列表
        - score: 吉利评分
        - description: 吉利描述
    """
    day_gz = get_ganzhi_day(year, month, day)
    day_stem = day_gz[0]
    day_branch = day_gz[1]

    lucky_hours = []

    for branch in _SHICHEN_BRANCHES:
        score = _get_shichen_score(day_stem, day_branch, branch)

        # 确定对应的小时
        if branch == "子":
            hours = [23, 0]
        else:
            idx = _SHICHEN_BRANCHES.index(branch)
            hours = [idx * 2 - 1, idx * 2]
            if branch == "丑":
                hours = [1, 2]
            elif branch == "寅":
                hours = [3, 4]
            elif branch == "卯":
                hours = [5, 6]
            elif branch == "辰":
                hours = [7, 8]
            elif branch == "巳":
                hours = [9, 10]
            elif branch == "午":
                hours = [11, 12]
            elif branch == "未":
                hours = [13, 14]
            elif branch == "申":
                hours = [15, 16]
            elif branch == "酉":
                hours = [17, 18]
            elif branch == "戌":
                hours = [19, 20]
            elif branch == "亥":
                hours = [21, 22]

        # 生成描述
        description = _get_lucky_description(day_stem, day_branch, branch, score)

        if score >= min_score:
            lucky_hours.append({
                "branch": branch,
                "name": f"{branch}时",
                "hours": hours,
                "score": score,
                "description": description,
            })

    # 按分数从高到低排序
    lucky_hours.sort(key=lambda x: x["score"], reverse=True)

    return lucky_hours


def _get_lucky_description(day_stem: str, day_branch: str, shichen_branch: str, score: int) -> str:
    """生成吉利描述."""
    reasons = []

    if _SIX_COMBOS.get(day_branch) == shichen_branch:
        reasons.append("六合")
    for combo in _THREE_COMBOS:
        if day_branch in combo and shichen_branch in combo:
            reasons.append("三合")
            break
    if _SIX_CLASHES.get(day_branch) == shichen_branch:
        reasons.append("六冲")

    day_stem_wx = STEM_WUXING.get(day_stem, "")
    shichen_wx = BRANCH_WUXING.get(shichen_branch, "")
    if day_stem_wx and shichen_wx:
        relation = _get_wuxing_relation(day_stem_wx, shichen_wx)
        if relation == "相生":
            reasons.append("干支相生")
        elif relation == "相克":
            reasons.append("干支相克")

    if score >= 80:
        level = "大吉"
    elif score >= 70:
        level = "吉"
    elif score >= 60:
        level = "小吉"
    else:
        level = "平"

    if reasons:
        return f"{level}（{'、'.join(reasons)}）"
    return level


def get_all_shichen_scores(year: int, month: int, day: int) -> list[dict]:
    """获取当日所有时辰的评分（用于展示）.

    Returns:
        所有时辰的评分列表
    """
    day_gz = get_ganzhi_day(year, month, day)
    day_stem = day_gz[0]
    day_branch = day_gz[1]

    all_scores = []

    for branch in _SHICHEN_BRANCHES:
        score = _get_shichen_score(day_stem, day_branch, branch)
        description = _get_lucky_description(day_stem, day_branch, branch, score)

        if branch == "子":
            hours = [23, 0]
        else:
            idx = _SHICHEN_BRANCHES.index(branch)
            hours = [idx * 2 - 1, idx * 2]
            if branch == "丑":
                hours = [1, 2]
            elif branch == "寅":
                hours = [3, 4]
            elif branch == "卯":
                hours = [5, 6]
            elif branch == "辰":
                hours = [7, 8]
            elif branch == "巳":
                hours = [9, 10]
            elif branch == "午":
                hours = [11, 12]
            elif branch == "未":
                hours = [13, 14]
            elif branch == "申":
                hours = [15, 16]
            elif branch == "酉":
                hours = [17, 18]
            elif branch == "戌":
                hours = [19, 20]
            elif branch == "亥":
                hours = [21, 22]

        all_scores.append({
            "branch": branch,
            "name": f"{branch}时",
            "hours": hours,
            "score": score,
            "description": description,
        })

    return all_scores
