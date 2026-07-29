"""彩种档案（Profile）与号码组（NumberGroup）定义.

本模块是「多彩种统一引擎」的核心抽象。每一个彩种由若干「号码组」组成，
每个号码组描述一段号池（范围、抽取数量、是否可重复、是否按位等）。

双色球（ssq）在此体系下就是「红球组 + 蓝球组」两个号码组，
福彩3D / 七乐彩 / 快乐8 各自用不同的号码组组合表达。

设计原则：本模块**不依赖** ticket / models / analyzer 等上层模块，
以避免循环引用；上层模块反过来依赖本模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class RenderGroup:
    """用于界面/打印统一渲染的一组号码。

    Attributes:
        name: 组名（如 "红球"）。
        numbers: 号码列表（已按展示顺序排列）。
        color: 小球颜色（十六进制）。
        pad: 补零宽度。
    """

    name: str
    numbers: List[int]
    color: str
    pad: int = 2


@dataclass(frozen=True)
class NumberGroup:
    """一个号码组的定义.

    Attributes:
        key: 组标识（如 "red"、"blue"、"basic"、"special"、"main"、"pos"）。
        name: 组中文名（用于界面/打印展示）。
        lo: 号池下界（含）。
        hi: 号池上界（含）。
        count: 一期开奖中该组开出的号码个数（3D 为位数=3）。
        pick_min: 玩家投注时该组最少选号个数，默认等于 count。
        pick_max: 玩家投注时该组最多选号个数，默认等于 count。
        positional: 是否按位（3D：每一位独立，顺序有意义）。
        allow_repeat: 组内号码是否可重复（3D 可重复）。
        color: 界面/打印中该组小球的颜色。
        pad: 展示时的补零宽度（3D 用 1，其余用 2）。
        is_primary: 是否为该彩种做整体统计（和值/奇偶/大小）的主号码组。
        draw_only: 该组只在开奖记录/统计中出现，不参与玩家生成（七乐彩特别号）。
    """

    key: str
    name: str
    lo: int
    hi: int
    count: int
    pick_min: Optional[int] = None
    pick_max: Optional[int] = None
    positional: bool = False
    allow_repeat: bool = False
    color: str = "#D32F2F"
    pad: int = 2
    is_primary: bool = False
    draw_only: bool = False

    @property
    def size(self) -> int:
        """号池大小（可取值个数）。"""
        return self.hi - self.lo + 1

    @property
    def values(self) -> List[int]:
        """号池全部可取值（升序）。"""
        return list(range(self.lo, self.hi + 1))

    @property
    def effective_pick_min(self) -> int:
        return self.count if self.pick_min is None else self.pick_min

    @property
    def effective_pick_max(self) -> int:
        return self.count if self.pick_max is None else self.pick_max

    @property
    def variable_pick(self) -> bool:
        """玩家可选号个数是否可变（快乐8）。"""
        return self.effective_pick_min != self.effective_pick_max

    @property
    def high_low_border(self) -> int:
        """大小号分界：>= 该值视为大号（双色球红球恰为 17）。"""
        return (self.lo + self.hi + 1) // 2

    def validate_numbers(self, numbers: List[int]) -> None:
        """校验一组号码是否符合本组约束（用于开奖记录/投注单校验）。"""
        for n in numbers:
            if not (self.lo <= n <= self.hi):
                raise ValueError(
                    f"{self.name}号码必须在 {self.lo}-{self.hi} 之间，得到 {n}"
                )
        if not self.allow_repeat and len(set(numbers)) != len(numbers):
            raise ValueError(f"{self.name}号码不能重复")


# 彩种分类常量
LOTTERY_CATEGORY_WELFARE = "welfare"
LOTTERY_CATEGORY_SPORTS = "sports"

CATEGORY_LABELS = {
    LOTTERY_CATEGORY_WELFARE: "福利彩票",
    LOTTERY_CATEGORY_SPORTS: "体育彩票",
}


@dataclass(frozen=True)
class LotteryProfile:
    """一个彩种的完整档案。"""

    key: str
    name: str
    groups: Tuple[NumberGroup, ...]
    data_url: str
    parser_key: str
    draw_weekdays: Tuple[int, ...]  # 空元组表示每日开奖
    storage_file: str
    model_prefix: str  # 机器学习模型文件前缀基名（会拼接后端名）
    subtitle: str = ""
    category: str = LOTTERY_CATEGORY_WELFARE  # 彩种大类：福利彩票 / 体育彩票

    # --- 便捷查询 ---
    def group(self, key: str) -> NumberGroup:
        for g in self.groups:
            if g.key == key:
                return g
        raise KeyError(f"彩种 {self.key} 不存在号码组 {key}")

    @property
    def group_keys(self) -> List[str]:
        return [g.key for g in self.groups]

    @property
    def pick_groups(self) -> List[NumberGroup]:
        """参与玩家生成的号码组（排除 draw_only）。"""
        return [g for g in self.groups if not g.draw_only]

    @property
    def primary_group(self) -> NumberGroup:
        for g in self.groups:
            if g.is_primary:
                return g
        if not self.groups:
            raise ValueError(f"彩种 {self.key} 没有定义任何号码组")
        return self.groups[0]

    @property
    def is_daily(self) -> bool:
        return len(self.draw_weekdays) == 0

    def xgboost_prefix(self) -> str:
        return f"{self.model_prefix}_xgboost" if self.key != "ssq" else "xgboost"

    def lightgbm_prefix(self) -> str:
        return f"{self.model_prefix}_lightgbm" if self.key != "ssq" else "lightgbm"

    def catboost_prefix(self) -> str:
        return f"{self.model_prefix}_catboost" if self.key != "ssq" else "catboost"


# --- 颜色常量（与现有双色球界面一致）---
_RED = "#D32F2F"
_BLUE = "#1976D2"
_GREEN = "#388E3C"
_ORANGE = "#F57C00"
_PURPLE = "#7B1FA2"
_TEAL = "#00897B"
_CYAN = "#00ACC1"


# 双色球：6 红(1-33) + 1 蓝(1-16)。红球为主统计组。
SSQ = LotteryProfile(
    key="ssq",
    name="双色球",
    subtitle="6 红球 (1-33) + 1 蓝球 (1-16)",
    groups=(
        NumberGroup("red", "红球", 1, 33, 6, color=_RED, is_primary=True),
        NumberGroup("blue", "蓝球", 1, 16, 1, color=_BLUE),
    ),
    data_url="http://data.17500.cn/ssq_asc.txt",
    parser_key="ssq",
    draw_weekdays=(1, 3, 6),  # 周二/四/日
    storage_file="draws.json",
    model_prefix="ssq",
)

# 福彩3D：3 位数字，每位 0-9，可重复、按位。每日开奖。
FC3D = LotteryProfile(
    key="3d",
    name="福彩3D",
    subtitle="3 位数字 (每位 0-9，可重复)",
    groups=(
        NumberGroup(
            "pos", "号码", 0, 9, 3,
            positional=True, allow_repeat=True, color=_ORANGE, pad=1,
            is_primary=True,
        ),
    ),
    data_url="http://data.17500.cn/3d_asc.txt",
    parser_key="3d",
    draw_weekdays=(),  # 每日
    storage_file="draws_3d.json",
    model_prefix="3d",
)

# 七乐彩：已停售，保留在此处供策略模块引用，但不加入 PROFILES 和 list_profiles()
QLC = LotteryProfile(
    key="qlc",
    name="七乐彩",
    subtitle="7 基本号 + 1 特别号 (1-30)",
    groups=(
        NumberGroup("basic", "基本号", 1, 30, 7, color=_RED, is_primary=True),
        NumberGroup("special", "特别号", 1, 30, 1, color=_BLUE, draw_only=True),
    ),
    data_url="http://data.17500.cn/7lc_asc.txt",
    parser_key="qlc",
    draw_weekdays=(0, 2, 4),  # 周一/三/五
    storage_file="draws_qlc.json",
    model_prefix="qlc",
)

# 快乐8：从 1-80 中开 20 个号；玩家选 1-10 个。每日开奖。
KL8 = LotteryProfile(
    key="kl8",
    name="快乐8",
    subtitle="从 1-80 开 20 号，玩家选 1-10 个",
    groups=(
        NumberGroup(
            "main", "号码", 1, 80, 20,
            pick_min=1, pick_max=10, color=_PURPLE, is_primary=True,
        ),
    ),
    data_url="http://data.17500.cn/kl8_asc.txt",
    parser_key="kl8",
    draw_weekdays=(),  # 每日
    storage_file="draws_kl8.json",
    model_prefix="kl8",
)

# 超级大乐透：5 前区(1-35) + 2 后区(1-12)。周一/三/六开奖。
DLT = LotteryProfile(
    key="dlt",
    name="超级大乐透",
    subtitle="5 前区 (1-35) + 2 后区 (1-12)",
    groups=(
        NumberGroup("front", "前区", 1, 35, 5, color=_RED, is_primary=True),
        NumberGroup("back", "后区", 1, 12, 2, color=_BLUE),
    ),
    data_url="http://data.17500.cn/dlt_asc.txt",
    parser_key="dlt",
    draw_weekdays=(0, 2, 5),  # 周一/三/六
    storage_file="draws_dlt.json",
    model_prefix="dlt",
    category=LOTTERY_CATEGORY_SPORTS,
)

# 排列3：3 位数字，每位 0-9，可重复、按位。每日开奖。
PL3 = LotteryProfile(
    key="pl3",
    name="排列3",
    subtitle="3 位数字 (每位 0-9，可重复)",
    groups=(
        NumberGroup(
            "pos", "号码", 0, 9, 3,
            positional=True, allow_repeat=True, color=_ORANGE, pad=1,
            is_primary=True,
        ),
    ),
    data_url="http://data.17500.cn/pl3_asc.txt",
    parser_key="pl3",
    draw_weekdays=(),  # 每日
    storage_file="draws_pl3.json",
    model_prefix="pl3",
    category=LOTTERY_CATEGORY_SPORTS,
)

# 排列5：5 位数字，每位 0-9，可重复、按位。每日开奖。
PL5 = LotteryProfile(
    key="pl5",
    name="排列5",
    subtitle="5 位数字 (每位 0-9，可重复)",
    groups=(
        NumberGroup(
            "pos", "号码", 0, 9, 5,
            positional=True, allow_repeat=True, color=_GREEN, pad=1,
            is_primary=True,
        ),
    ),
    data_url="http://data.17500.cn/pl5_asc.txt",
    parser_key="pl5",
    draw_weekdays=(),  # 每日
    storage_file="draws_pl5.json",
    model_prefix="pl5",
    category=LOTTERY_CATEGORY_SPORTS,
)

# 7星彩：7 位数字，每位 0-9，可重复、按位。周二/五/日开奖。
QXC = LotteryProfile(
    key="qxc",
    name="7星彩",
    subtitle="7 位数字 (每位 0-9，可重复)",
    groups=(
        NumberGroup(
            "pos", "号码", 0, 9, 7,
            positional=True, allow_repeat=True, color=_CYAN, pad=1,
            is_primary=True,
        ),
    ),
    data_url="http://data.17500.cn/7xc_asc.txt",
    parser_key="qxc",
    draw_weekdays=(1, 4, 6),  # 周二/五/日
    storage_file="draws_qxc.json",
    model_prefix="qxc",
    category=LOTTERY_CATEGORY_SPORTS,
)

# 广东36选7：7 个基本号 + 1 个特别号，均来自 1-36。周一/三/五开奖。
# 注意：广东36选7 暂无可用的公开文本数据源（17500.cn 未提供），
# 因此当前未注册到 PROFILES。找到稳定数据源后取消注释即可启用。
GD36X7 = LotteryProfile(
    key="gd36x7",
    name="广东36选7",
    subtitle="7 基本号 + 1 特别号 (1-36)",
    groups=(
        NumberGroup("basic", "基本号", 1, 36, 7, color=_RED, is_primary=True),
        NumberGroup("special", "特别号", 1, 36, 1, color=_BLUE, draw_only=True),
    ),
    data_url="",
    parser_key="gd36x7",
    draw_weekdays=(0, 2, 4),  # 周一/三/五
    storage_file="draws_gd36x7.json",
    model_prefix="gd36x7",
    category=LOTTERY_CATEGORY_SPORTS,
)


PROFILES: Dict[str, LotteryProfile] = {
    p.key: p for p in (SSQ, FC3D, KL8, DLT, PL3, PL5, QXC)
}

DEFAULT_KEY = "ssq"


def profile_keys() -> List[str]:
    """返回全部已注册彩种 key。"""
    return [p.key for p in list_profiles()]


def get_profile(key: str) -> LotteryProfile:
    """按 key 获取彩种档案；未知 key 返回默认（双色球）。"""
    return PROFILES.get(key, SSQ)


def list_profiles() -> List[LotteryProfile]:
    """按固定顺序返回全部彩种档案。"""
    return [SSQ, FC3D, KL8, DLT, PL3, PL5, QXC]


# 主界面导航中隐藏的彩种 key：功能、数据与策略全部保留，
# 仅不在彩种下拉框和「彩种」菜单中展示。
# 七乐彩在广州无销售，按用户要求从导航移除。
NAV_HIDDEN_PROFILE_KEYS = {"qlc"}


def list_profiles_by_category() -> Dict[str, List[LotteryProfile]]:
    """按彩种大类（福利彩票/体育彩票）分组返回档案。"""
    result: Dict[str, List[LotteryProfile]] = {}
    for p in list_profiles():
        result.setdefault(p.category, []).append(p)
    # 保持已知分类的展示顺序
    ordered: Dict[str, List[LotteryProfile]] = {}
    for cat in (LOTTERY_CATEGORY_WELFARE, LOTTERY_CATEGORY_SPORTS):
        if cat in result:
            ordered[cat] = result.pop(cat)
    ordered.update(result)
    return ordered


def category_label(category: str) -> str:
    """返回彩种大类的中文名称。"""
    return CATEGORY_LABELS.get(category, category)
