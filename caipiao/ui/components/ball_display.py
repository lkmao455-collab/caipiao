"""号码球展示组件."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core.ball import Ball, BallColor


class BallWidget(QFrame):
    """单个球的图形化展示."""

    def __init__(self, ball: Ball, size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ball = ball
        self.size = size
        self.setFixedSize(size, size)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.ball.color == BallColor.RED:
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
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.ball.number:02d}"
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

        if show_index is not None:
            index_label = QLabel(f"{show_index:02d}.")
            index_label.setStyleSheet("color: #666; font-weight: bold;")
            row_layout.addWidget(index_label)

        for ball in ticket.red_balls:
            row_layout.addWidget(BallWidget(ball))

        separator = QLabel("+")
        separator.setStyleSheet("color: #999; font-size: 16px; margin: 0 4px;")
        row_layout.addWidget(separator)
        row_layout.addWidget(BallWidget(ticket.blue_ball))

        row_layout.addStretch()
        self.layout.addWidget(row)

        if ticket.basis:
            basis_label = QLabel(ticket.basis)
            basis_label.setWordWrap(True)
            basis_label.setStyleSheet("color: #888; font-size: 12px; margin-left: 28px;")
            self.layout.addWidget(basis_label)
