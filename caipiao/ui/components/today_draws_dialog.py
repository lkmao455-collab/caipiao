"""今日开奖彩种提示小窗口."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.profile import (
    LOTTERY_CATEGORY_SPORTS,
    LotteryProfile,
    list_profiles,
)


class LotteryItem(QFrame):
    """单个彩种条目."""

    def __init__(self, profile: LotteryProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self._setup_ui()

    def _setup_ui(self) -> None:
        is_sports = self.profile.category == LOTTERY_CATEGORY_SPORTS
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {"#E3F2FD" if is_sports else "#FFF3E0"};
                border: 1px solid {"#90CAF9" if is_sports else "#FFCC80"};
                border-radius: 4px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # 彩种名称
        name_label = QLabel(self.profile.name)
        name_label.setStyleSheet(
            f"""
            QLabel {{
                color: {"#1565C0" if is_sports else "#E65100"};
                font-weight: bold;
                font-size: 11pt;
            }}
            """
        )
        layout.addWidget(name_label)

        layout.addStretch()

        # 开奖时间
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        if self.profile.is_daily:
            schedule_text = "每日开奖"
        else:
            days = "/".join(weekday_names[d] for d in self.profile.draw_weekdays)
            schedule_text = f"周{days}开奖"

        schedule_label = QLabel(schedule_text)
        schedule_label.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(schedule_label)


class TodayDrawsDialog(QDialog):
    """今日开奖彩种提示对话框（不可自动关闭，需手动点击关闭）."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("今日开奖彩种")
        # 禁用关闭按钮（X），只能通过点击"关闭"按钮关闭
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(320)
        self.setMaximumWidth(450)

        self._today_profiles = self._get_today_profiles()
        self._setup_ui()

    def _get_today_profiles(self) -> list[LotteryProfile]:
        """获取今日开奖的彩种列表."""
        today_weekday = datetime.now(timezone.utc).astimezone().weekday()  # 0=周一, 6=周日
        result = []
        for p in list_profiles():
            if p.is_daily or today_weekday in p.draw_weekdays:
                result.append(p)
        return result

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 标题
        today_str = datetime.now(timezone.utc).astimezone().strftime("%Y年%m月%d日")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        today_weekday = weekday_names[datetime.now(timezone.utc).astimezone().weekday()]

        title = QLabel(f"今日 ({today_str} {today_weekday}) 开奖彩种")
        title.setStyleSheet(
            """
            QLabel {
                font-size: 13pt;
                font-weight: bold;
                color: #1a1a1a;
                background-color: #E8F5E9;
                border: 1px solid #A5D6A7;
                border-radius: 4px;
                padding: 6px 12px;
            }
            """
        )
        layout.addWidget(title)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        if not self._today_profiles:
            no_draw_label = QLabel("今日无彩种开奖")
            no_draw_label.setStyleSheet("color: #999; font-size: 10pt;")
            no_draw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_draw_label)
        else:
            # 彩种列表（垂直排列）
            for profile in self._today_profiles:
                item = LotteryItem(profile)
                layout.addWidget(item)

            # 提示信息
            count = len(self._today_profiles)
            hint = QLabel(f"共 {count} 个彩种即将开奖，祝您好运！")
            hint.setStyleSheet("color: #888; font-size: 9pt;")
            layout.addWidget(hint)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
