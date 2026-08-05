"""最近开奖结果显示对话框."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.profile import LotteryProfile, list_profiles
from ...data.models import DrawRecord

logger = logging.getLogger(__name__)


class DrawResultCard(QFrame):
    """单个彩种开奖结果卡片."""

    def __init__(
        self,
        profile: LotteryProfile,
        record: DrawRecord | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.record = record
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame {
                background-color: #FFFBF0;
                border: 2px solid #FFD700;
                border-radius: 8px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 第一行：彩种名称 + 期号日期
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(self.profile.name)
        name_label.setStyleSheet(
            """
            QLabel {
                color: #B71C1C;
                font-weight: bold;
                font-size: 12pt;
                background: transparent;
                border: none;
            }
            """
        )
        top_layout.addWidget(name_label)

        top_layout.addStretch()

        if self.record:
            info_text = f"第{self.record.issue}期"
            if self.record.draw_date:
                info_text += f" | {self.record.draw_date}"
        else:
            info_text = "暂无数据"

        info_label = QLabel(info_text)
        info_label.setStyleSheet("color: #666; font-size: 9pt; background: transparent; border: none;")
        top_layout.addWidget(info_label)

        layout.addLayout(top_layout)

        # 第二行：开奖号码（靠左显示）
        if self.record:
            groups = self._get_display_groups()

            for i, (group_name, numbers, color) in enumerate(groups):
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(5)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

                # 组名标签
                if len(groups) > 1:
                    group_label = QLabel(f"{group_name}:")
                    group_label.setStyleSheet(
                        f"color: {color}; font-weight: bold; font-size: 10pt; "
                        "background: transparent; border: none;"
                    )
                    row_layout.addWidget(group_label)

                # 号码球
                for num in numbers:
                    ball = QLabel(f"{num:02d}")
                    ball.setFixedSize(28, 28)
                    ball.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    ball.setStyleSheet(
                        f"""
                        QLabel {{
                            background-color: {color};
                            color: white;
                            font-weight: bold;
                            font-size: 10pt;
                            border-radius: 14px;
                            border: none;
                        }}
                        """
                    )
                    row_layout.addWidget(ball)

                row_layout.addStretch()
                layout.addLayout(row_layout)
        else:
            no_data = QLabel("暂无开奖数据")
            no_data.setStyleSheet("color: #999; font-size: 10pt; background: transparent; border: none;")
            layout.addWidget(no_data)

    def _get_display_groups(self) -> list[tuple]:
        """获取用于显示的号码组信息."""
        if not self.record:
            return []

        result = []
        numbers = self.record.groups

        if self.profile.key == "ssq":
            # 双色球：6红 + 1蓝
            red = numbers.get("red", [])
            blue = numbers.get("blue", [])
            result.append(("红球", red, "#D32F2F"))
            result.append(("蓝球", blue, "#1976D2"))
        elif self.profile.key == "dlt":
            # 大乐透：5前区 + 2后区
            front = numbers.get("front", [])
            back = numbers.get("back", [])
            result.append(("前区", front, "#D32F2F"))
            result.append(("后区", back, "#1976D2"))
        elif self.profile.key == "kl8":
            # 快乐8：20个号码，分两行显示（每行10个）
            main = numbers.get("main", [])
            row1 = main[:10]
            row2 = main[10:]
            if row1:
                result.append(("号码", row1, "#7B1FA2"))
            if row2:
                result.append(("", row2, "#7B1FA2"))
        elif self.profile.key == "3d" or self.profile.key == "pl3":
            pos = numbers.get("pos", [])
            result.append(("号码", pos, "#F57C00"))
        elif self.profile.key == "pl5":
            pos = numbers.get("pos", [])
            result.append(("号码", pos, "#388E3C"))
        elif self.profile.key == "qxc":
            pos = numbers.get("pos", [])
            result.append(("号码", pos, "#00ACC1"))
        else:
            for key, nums in numbers.items():
                result.append((key, nums, "#D32F2F"))

        return result


class LatestResultsDialog(QDialog):
    """所有彩种最近一次开奖结果对话框."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("最近开奖结果")
        self.setMinimumSize(600, 500)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # 标题
        title = QLabel("各彩种最近一次开奖结果")
        title.setStyleSheet(
            """
            QLabel {
                font-size: 14pt;
                font-weight: bold;
                color: #B71C1C;
                padding: 8px;
            }
            """
        )
        layout.addWidget(title)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #FFD700;")
        layout.addWidget(line)

        # 滚动区域（仅垂直滚动，禁止水平滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        # 加载所有彩种的最近开奖结果
        self._load_results(scroll_layout)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_results(self, layout: QVBoxLayout) -> None:
        """加载所有彩种的最近开奖结果."""
        import json

        from ...utils import app_data_dir

        data_dir = app_data_dir()

        for profile in list_profiles():
            record = None
            storage_path = data_dir / profile.storage_file

            if storage_path.exists():
                try:
                    with open(storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    if data:
                        item = data[-1]
                        record = DrawRecord.from_dict(item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("读取开奖记录失败: %s", exc)
                    record = None

            card = DrawResultCard(profile, record)
            layout.addWidget(card)
