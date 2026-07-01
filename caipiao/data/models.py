"""数据模型."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class DrawRecord:
    """一条开奖记录.

    Attributes:
        issue: 开奖期号，如 "2026073"。
        draw_date: 开奖日期。
        red_balls: 6 个红球号码，已排序。
        blue_ball: 蓝球号码。
    """

    issue: str
    draw_date: datetime
    red_balls: List[int]
    blue_ball: int

    def to_dict(self) -> dict:
        return {
            "issue": self.issue,
            "draw_date": self.draw_date.strftime("%Y-%m-%d"),
            "red_balls": self.red_balls,
            "blue_ball": self.blue_ball,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DrawRecord":
        return cls(
            issue=data["issue"],
            draw_date=datetime.strptime(data["draw_date"], "%Y-%m-%d"),
            red_balls=data["red_balls"],
            blue_ball=data["blue_ball"],
        )

    def __repr__(self) -> str:
        reds = " ".join(f"{r:02d}" for r in self.red_balls)
        return f"DrawRecord({self.issue} {self.draw_date.date()} 红:{reds} 蓝:{self.blue_ball:02d})"
