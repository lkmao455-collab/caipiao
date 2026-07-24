"""开奖记录数据模型（多彩种统一模型）.

``DrawRecord`` 现在以「号码组」表达任意彩种的一期开奖。
为保证双色球行为与序列化格式不变，保留了：

- 旧构造 ``DrawRecord(issue, draw_date, red_balls, blue_ball)``（归为双色球）；
- ``.red_balls`` / ``.blue_ball`` 访问器；
- 双色球旧的 ``to_dict``/``from_dict`` 字段。

其它彩种通过 ``DrawRecord(issue, draw_date, profile=..., groups=...)`` 构造。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from ..core.profile import SSQ, LotteryProfile, get_profile


class DrawRecord:
    """一条开奖记录。

    双色球：``groups = {"red": [...6...], "blue": [x]}``。
    """

    def __init__(
        self,
        issue: str,
        draw_date: datetime,
        red_balls: Optional[List[int]] = None,
        blue_ball: Optional[int] = None,
        *,
        profile: LotteryProfile | str | None = None,
        groups: Optional[Dict[str, List[int]]] = None,
    ) -> None:
        self.issue = issue
        self.draw_date = draw_date
        if groups is not None or profile is not None:
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
            self.profile = SSQ
            if blue_ball is None:
                raise ValueError("双色球开奖记录必须提供蓝球")
            self.groups = {
                "red": sorted(int(x) for x in (red_balls or [])),
                "blue": [int(blue_ball)],
            }

    # --- 双色球兼容访问器 ---
    @property
    def red_balls(self) -> List[int]:
        return self.groups.get("red", [])

    @property
    def blue_ball(self) -> Optional[int]:
        """双色球蓝球；仅在包含 blue 组时返回，否则为 None。"""
        blues = self.groups.get("blue")
        return blues[0] if blues else None

    # --- 序列化 ---
    def to_dict(self) -> dict:
        if self.profile.key == "ssq":
            reds = self.groups.get("red", [])
            blues = self.groups.get("blue", [])
            if not reds or not blues:
                raise ValueError("双色球开奖记录缺少红球或蓝球，无法序列化")
            return {
                "issue": self.issue,
                "draw_date": self.draw_date.strftime("%Y-%m-%d"),
                "red_balls": list(reds),
                "blue_ball": blues[0],
            }
        return {
            "issue": self.issue,
            "draw_date": self.draw_date.strftime("%Y-%m-%d"),
            "profile": self.profile.key,
            "groups": {k: list(v) for k, v in self.groups.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DrawRecord":
        draw_date = datetime.strptime(data["draw_date"], "%Y-%m-%d")
        if "groups" in data:
            return cls(
                issue=data["issue"],
                draw_date=draw_date,
                profile=data.get("profile", "ssq"),
                groups=data["groups"],
            )
        return cls(
            issue=data["issue"],
            draw_date=draw_date,
            red_balls=data["red_balls"],
            blue_ball=data["blue_ball"],
        )

    def __repr__(self) -> str:
        if self.profile.key == "ssq":
            reds = self.groups.get("red", [])
            blues = self.groups.get("blue", [])
            if not reds or not blues:
                return f"DrawRecord({self.issue} {self.draw_date.date()} 无效记录)"
            reds_str = " ".join(f"{r:02d}" for r in reds)
            return (
                f"DrawRecord({self.issue} {self.draw_date.date()} "
                f"红:{reds_str} 蓝:{blues[0]:02d})"
            )
        parts = []
        for g in self.profile.groups:
            nums = self.groups.get(g.key, [])
            parts.append(f"{g.name}:" + " ".join(f"{n:0{g.pad}d}" for n in nums))
        return f"DrawRecord({self.issue} {self.draw_date.date()} " + " ".join(parts) + ")"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DrawRecord):
            return NotImplemented
        return (
            self.profile.key == other.profile.key
            and self.issue == other.issue
            and self.groups == other.groups
        )
