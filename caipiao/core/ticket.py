"""双色球投注单."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from .ball import Ball, BallColor


class Ticket:
    """一张双色球投注单.

    包含 6 个不重复的红球（1-33）和 1 个蓝球（1-16）。
    """

    RED_COUNT = 6
    BLUE_COUNT = 1

    def __init__(
        self,
        red_balls: Iterable[int] | Iterable[Ball],
        blue_ball: int | Ball,
        generated_at: datetime | None = None,
        strategy_name: str = "",
        basis: str = "",
        details: Dict[str, Any] | None = None,
    ) -> None:
        self.red_balls: List[Ball] = sorted(
            [b if isinstance(b, Ball) else Ball.red(b) for b in red_balls],
            key=lambda b: b.number,
        )
        self.blue_ball: Ball = (
            blue_ball if isinstance(blue_ball, Ball) else Ball.blue(blue_ball)
        )
        self.generated_at = generated_at or datetime.now()
        self.strategy_name = strategy_name
        self.basis = basis
        self.details = details or {}
        self._validate()

    def _validate(self) -> None:
        """校验投注单合法性."""
        if len(self.red_balls) != self.RED_COUNT:
            raise ValueError(f"红球数量必须为 {self.RED_COUNT}，得到 {len(self.red_balls)}")
        if len({b.number for b in self.red_balls}) != self.RED_COUNT:
            raise ValueError("红球号码不能重复")
        for ball in self.red_balls:
            if ball.color != BallColor.RED:
                raise ValueError("红球列表中包含非红球")
        if self.blue_ball.color != BallColor.BLUE:
            raise ValueError("蓝球必须是蓝色球")

    def to_dict(self) -> dict:
        """序列化为字典."""
        return {
            "red": [b.number for b in self.red_balls],
            "blue": self.blue_ball.number,
            "generated_at": self.generated_at.isoformat(),
            "strategy_name": self.strategy_name,
            "basis": self.basis,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ticket":
        """从字典反序列化."""
        return cls(
            red_balls=data["red"],
            blue_ball=data["blue"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            strategy_name=data.get("strategy_name", ""),
            basis=data.get("basis", ""),
            details=data.get("details", {}),
        )

    def format_pretty(self) -> str:
        """格式化为易读字符串."""
        reds = " ".join(f"{b.number:02d}" for b in self.red_balls)
        return f"红球: {reds} | 蓝球: {self.blue_ball.number:02d}"

    def format_compact(self) -> str:
        """格式化为紧凑字符串，方便复制."""
        reds = " ".join(f"{b.number:02d}" for b in self.red_balls)
        return f"{reds} + {self.blue_ball.number:02d}"

    def __repr__(self) -> str:
        return f"Ticket({self.format_pretty()})"

    def __str__(self) -> str:
        return self.format_pretty()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ticket):
            return NotImplemented
        return (
            self.red_balls == other.red_balls
            and self.blue_ball == other.blue_ball
        )

    def __hash__(self) -> int:
        return hash((tuple(self.red_balls), self.blue_ball))
