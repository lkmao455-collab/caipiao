"""球的定义."""

from __future__ import annotations

from enum import Enum, auto


class BallColor(Enum):
    """球的颜色."""

    RED = auto()
    BLUE = auto()


class Ball:
    """表示一个双色球号码.

    Attributes:
        number: 号码数值.
        color: 球的颜色.
    """

    MIN_RED = 1
    MAX_RED = 33
    MIN_BLUE = 1
    MAX_BLUE = 16

    def __init__(self, number: int, color: BallColor) -> None:
        self.number = int(number)
        self.color = color
        self._validate()

    def _validate(self) -> None:
        """校验号码范围."""
        if self.color == BallColor.RED and not (self.MIN_RED <= self.number <= self.MAX_RED):
            raise ValueError(
                f"红球号码必须在 {self.MIN_RED}-{self.MAX_RED} 之间，"
                f"得到 {self.number}"
            )
        if self.color == BallColor.BLUE and not (self.MIN_BLUE <= self.number <= self.MAX_BLUE):
            raise ValueError(
                f"蓝球号码必须在 {self.MIN_BLUE}-{self.MAX_BLUE} 之间，"
                f"得到 {self.number}"
            )

    @classmethod
    def red(cls, number: int) -> Ball:
        """快速创建红球."""
        return cls(number, BallColor.RED)

    @classmethod
    def blue(cls, number: int) -> Ball:
        """快速创建蓝球."""
        return cls(number, BallColor.BLUE)

    def __repr__(self) -> str:
        return f"Ball({self.number}, {self.color.name})"

    def __str__(self) -> str:
        return f"{self.number:02d}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ball):
            return NotImplemented
        return self.number == other.number and self.color == other.color

    def __hash__(self) -> int:
        return hash((self.number, self.color))
