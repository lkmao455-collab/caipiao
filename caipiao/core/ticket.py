"""投注单（多彩种统一模型）.

``Ticket`` 现在是基于「号码组」的通用投注单，可表达任意彩种。
为保证双色球的历史行为与序列化格式完全不变，保留了：

- 旧构造方式 ``Ticket(red_balls, blue_ball, ...)``（自动归为双色球档案）；
- ``.red_balls`` / ``.blue_ball`` / ``RED_COUNT`` / ``BLUE_COUNT`` 访问器；
- 双色球的 ``to_dict``/``from_dict`` 旧字段（``red`` / ``blue``）。

其它彩种通过 ``Ticket(profile=..., groups=...)`` 或 ``Ticket.from_groups`` 构造。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union

from .ball import Ball
from .profile import SSQ, LotteryProfile, RenderGroup, get_profile


class Ticket:
    """一张投注单（默认双色球：6 红球 1-33 + 1 蓝球 1-16）。"""

    RED_COUNT = 6
    BLUE_COUNT = 1

    def __init__(
        self,
        red_balls: Union[Iterable[int], Iterable[Ball], None] = None,
        blue_ball: Union[int, Ball, None] = None,
        generated_at: datetime | None = None,
        strategy_name: str = "",
        basis: str = "",
        details: Dict[str, Any] | None = None,
        *,
        profile: Union[LotteryProfile, str, None] = None,
        groups: Optional[Dict[str, Iterable[int]]] = None,
        validate: bool = True,
    ) -> None:
        if groups is not None or profile is not None:
            # 通用构造：显式给出彩种档案与各组号码
            prof = (
                profile
                if isinstance(profile, LotteryProfile)
                else get_profile(profile or "ssq")
            )
            self.profile = prof
            self.groups: Dict[str, List[int]] = {
                k: [int(x) for x in v] for k, v in (groups or {}).items()
            }
        else:
            # 兼容旧的双色球构造：Ticket(red_balls, blue_ball)
            self.profile = SSQ
            reds = sorted(int(getattr(b, "number", b)) for b in (red_balls or []))
            if blue_ball is None:
                raise ValueError("双色球投注单必须提供蓝球")
            blue = int(getattr(blue_ball, "number", blue_ball))
            self.groups = {"red": reds, "blue": [blue]}

        self.generated_at = generated_at or datetime.now()
        self.strategy_name = strategy_name
        self.basis = basis
        self.details = details or {}
        self._sort_groups()
        if validate:
            self._validate()

    # ------------------------------------------------------------------ #
    # 构造工厂
    # ------------------------------------------------------------------ #
    @classmethod
    def from_groups(
        cls,
        profile: Union[LotteryProfile, str],
        groups: Dict[str, Iterable[int]],
        generated_at: datetime | None = None,
        strategy_name: str = "",
        basis: str = "",
        details: Dict[str, Any] | None = None,
        validate: bool = True,
    ) -> "Ticket":
        return cls(
            profile=profile,
            groups=groups,
            generated_at=generated_at,
            strategy_name=strategy_name,
            basis=basis,
            details=details,
            validate=validate,
        )

    # ------------------------------------------------------------------ #
    # 校验
    # ------------------------------------------------------------------ #
    def _sort_groups(self) -> None:
        """非按位组升序排列（按位组保持顺序，如 3D 的百十个位）。"""
        for g in self.profile.groups:
            nums = self.groups.get(g.key)
            if nums is not None and not g.positional:
                self.groups[g.key] = sorted(nums)

    def _validate(self) -> None:
        for g in self.profile.pick_groups:
            nums = self.groups.get(g.key)
            if nums is None:
                raise ValueError(f"缺少号码组：{g.name}")
            pmin, pmax = g.effective_pick_min, g.effective_pick_max
            if not (pmin <= len(nums) <= pmax):
                if pmin == pmax:
                    raise ValueError(f"{g.name}数量必须为 {pmin}，得到 {len(nums)}")
                raise ValueError(
                    f"{g.name}数量必须在 {pmin}-{pmax} 之间，得到 {len(nums)}"
                )
            g.validate_numbers(nums)

    # ------------------------------------------------------------------ #
    # 双色球兼容访问器
    # ------------------------------------------------------------------ #
    @property
    def red_balls(self) -> List[Ball]:
        """双色球红球（List[Ball]）；仅在包含 red 组时有意义。"""
        return [Ball.red(n) for n in self.groups.get("red", [])]

    @property
    def blue_ball(self) -> Optional[Ball]:
        """双色球蓝球（Ball）；仅在包含 blue 组时返回，否则为 None。"""
        blues = self.groups.get("blue")
        return Ball.blue(blues[0]) if blues else None

    # ------------------------------------------------------------------ #
    # 展示
    # ------------------------------------------------------------------ #
    def render_groups(self) -> List[RenderGroup]:
        """返回可供界面/打印统一渲染的号码组列表。"""
        result: List[RenderGroup] = []
        for g in self.profile.pick_groups:
            nums = self.groups.get(g.key, [])
            result.append(RenderGroup(g.name, list(nums), g.color, g.pad))
        return result

    def format_pretty(self) -> str:
        if self.profile.key == "ssq":
            reds = self.groups.get("red", [])
            blues = self.groups.get("blue", [])
            if not reds or not blues:
                raise ValueError("双色球投注单缺少红球或蓝球")
            reds_str = " ".join(f"{n:02d}" for n in reds)
            return f"红球: {reds_str} | 蓝球: {blues[0]:02d}"
        parts = []
        for rg in self.render_groups():
            nums = " ".join(f"{n:0{rg.pad}d}" for n in rg.numbers)
            parts.append(f"{rg.name}: {nums}")
        return " | ".join(parts)

    def format_compact(self) -> str:
        if self.profile.key == "ssq":
            reds = self.groups.get("red", [])
            blues = self.groups.get("blue", [])
            if not reds or not blues:
                raise ValueError("双色球投注单缺少红球或蓝球")
            reds_str = " ".join(f"{n:02d}" for n in reds)
            return f"{reds_str} + {blues[0]:02d}"
        parts = []
        for rg in self.render_groups():
            parts.append(" ".join(f"{n:0{rg.pad}d}" for n in rg.numbers))
        return " + ".join(parts)

    # ------------------------------------------------------------------ #
    # 序列化
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        if self.profile.key == "ssq":
            # 保持旧格式，历史文件向后兼容
            reds = self.groups.get("red", [])
            blues = self.groups.get("blue", [])
            if not reds or not blues:
                raise ValueError("双色球投注单缺少红球或蓝球，无法序列化")
            return {
                "red": list(reds),
                "blue": blues[0],
                "generated_at": self.generated_at.isoformat(),
                "strategy_name": self.strategy_name,
                "basis": self.basis,
                "details": self.details,
            }
        return {
            "profile": self.profile.key,
            "groups": {k: list(v) for k, v in self.groups.items()},
            "generated_at": self.generated_at.isoformat(),
            "strategy_name": self.strategy_name,
            "basis": self.basis,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ticket":
        generated_at = datetime.fromisoformat(data["generated_at"])
        common = dict(
            generated_at=generated_at,
            strategy_name=data.get("strategy_name", ""),
            basis=data.get("basis", ""),
            details=data.get("details", {}),
        )
        if "groups" in data:  # 通用格式
            return cls(profile=data.get("profile", "ssq"), groups=data["groups"], **common)
        # 旧的双色球格式
        if "red" not in data or "blue" not in data:
            raise ValueError("旧格式双色球数据缺少 red/blue 字段")
        return cls(red_balls=data["red"], blue_ball=data["blue"], **common)

    # ------------------------------------------------------------------ #
    # dunder
    # ------------------------------------------------------------------ #
    def _key(self):
        return (
            self.profile.key,
            tuple((k, tuple(self.groups[k])) for k in sorted(self.groups)),
        )

    def __repr__(self) -> str:
        return f"Ticket({self.format_pretty()})"

    def __str__(self) -> str:
        return self.format_pretty()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ticket):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())
