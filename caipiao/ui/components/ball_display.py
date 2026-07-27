"""号码球展示组件."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core.ball import Ball, BallColor
from ...core.prize import fc3d_bet_type
from ...core.profile import LotteryProfile
from ...core.ticket import Ticket


def compute_highlight_map(
    profile: LotteryProfile, ticket: Ticket, actual_groups: dict[str, list[int]]
) -> dict[str, set[int]]:
    """计算投注单与开奖号码的命中高亮映射.

    对于非按位号码组，返回预测号码与实际开奖号码的交集；
    对于按位号码组（如福彩3D），返回命中位置的索引集合。
    """
    highlight: dict[str, set[int]] = {}
    for g in profile.groups:
        actual = actual_groups.get(g.key, [])
        predicted = ticket.groups.get(g.key, [])
        if g.positional:
            highlight[g.key] = {
                i for i, (a, p) in enumerate(zip(actual, predicted)) if a == p
            }
        else:
            highlight[g.key] = set(actual) & set(predicted)
    return highlight


class BallWidget(QFrame):
    """单个球的图形化展示."""

    def __init__(
        self,
        ball: Ball | None = None,
        number: int | None = None,
        color: str | None = None,
        pad: int = 2,
        size: int = 36,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ball = ball
        self.number = number if number is not None else (ball.number if ball else 0)
        self.color = color
        self.pad = pad
        self.size = size
        self.setFixedSize(size, size)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.color:
            color = QColor(self.color)
            border = QColor(self.color).darker(120)
        elif self.ball and self.ball.color == BallColor.RED:
            color = QColor("#D32F2F")
            border = QColor("#B71C1C")
        else:
            color = QColor("#1976D2")
            border = QColor("#0D47A1")

        painter.setPen(border)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, self.size - 2, self.size - 2)

        painter.setPen(QColor("white"))
        font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        painter.setFont(font)
        pad = self.pad
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.number:0{pad}d}"
        )


class TicketRowWidget(QWidget):
    """一行投注单展示."""

    def __init__(self, ticket, show_index: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from ...core.ticket import Ticket

        if not isinstance(ticket, Ticket):
            raise TypeError("ticket must be Ticket")
        self.ticket = ticket
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 4, 4, 4)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setSpacing(8)
        row_layout.setContentsMargins(0, 0, 0, 0)

        prediction = None
        if ticket.profile.key == "kl8":
            prediction = (ticket.details or {}).get("prediction")

        if show_index is not None:
            index_label = QLabel(f"{show_index:02d}.")
            index_label.setStyleSheet("color: #666; font-weight: bold;")
            row_layout.addWidget(index_label)

        if prediction:
            buy_label = QLabel("购买号码：")
            buy_label.setStyleSheet("color: #0A2540; font-weight: bold;")
            row_layout.addWidget(buy_label)

        render_groups = ticket.render_groups()
        for gi, rg in enumerate(render_groups):
            if gi > 0:
                sep = QLabel("+")
                sep.setStyleSheet("color: #999; font-size: 12pt; margin: 0 4px;")
                row_layout.addWidget(sep)
            for n in rg.numbers:
                row_layout.addWidget(BallWidget(number=n, color=rg.color, pad=rg.pad, size=36))

        row_layout.addStretch()
        self.layout.addWidget(row)

        if prediction:
            # 快乐8：预测号码（20个）与购买号码分开显示
            pred_row = QWidget(self)
            pred_layout = QHBoxLayout(pred_row)
            pred_layout.setSpacing(4)
            pred_layout.setContentsMargins(0, 0, 0, 0)
            pred_label = QLabel("预测号码：")
            pred_label.setStyleSheet("color: #666; font-size: 9pt;")
            pred_layout.addWidget(pred_label)
            color = render_groups[0].color if render_groups else None
            pad = render_groups[0].pad if render_groups else 2
            for n in prediction:
                pred_layout.addWidget(
                    BallWidget(number=n, color=color, pad=pad, size=26)
                )
            pred_layout.addStretch()
            self.layout.addWidget(pred_row)

        # 福彩3D / 排列3 显示投注方式建议
        if ticket.profile.key in ("3d", "pl3"):
            nums = ticket.groups.get("pos", [])
            bet_type = fc3d_bet_type(nums)
            bet_label = QLabel(f"建议投注方式：{bet_type}")
            bet_label.setStyleSheet(
                "color: #0A2540; background-color: #FFF3E0; "
                "border-radius: 4px; padding: 2px 8px; font-size: 9pt; font-weight: bold;"
            )
            self.layout.addWidget(bet_label)

        if ticket.basis:
            basis_label = QLabel(ticket.basis)
            basis_label.setWordWrap(True)
            basis_label.setStyleSheet("color: #888; font-size: 9pt; margin-left: 28px;")
            self.layout.addWidget(basis_label)
