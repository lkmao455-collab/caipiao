"""万年历 UI 组件.

提供完整的日历视图，支持公历/农历显示、黄历宜忌、节气节日等。
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QBrush, QPainter
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QGridLayout,
    QSizePolicy,
)

from ...calendar.lunar_calendar import (
    solar_to_lunar,
    lunar_month_name,
    lunar_day_name,
    get_weekday_name,
    SolarDate,
    LunarDate,
)
from ...calendar.heavenly_earthly import (
    get_ganzhi,
    get_ganzhi_year,
    get_ganzhi_month,
    get_ganzhi_day,
    get_shengxiao,
    get_chongsha,
)
from ...calendar.almanac import (
    get_almanac,
    get_solar_term,
    get_current_solar_term,
    get_festivals,
    get_traditional_festivals,
)


class LunarCalendarWidget(QWidget):
    """万年历标签页."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_date = datetime.now()
        self._setup_ui()
        self._update_display()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # 左侧：日历
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)

        # 日历控件
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setMinimumSize(400, 300)
        self.calendar.clicked.connect(self._on_date_clicked)
        self.calendar.currentPageChanged.connect(self._on_month_changed)

        # 自定义日历渲染
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Monday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Tuesday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Wednesday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Thursday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Friday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, QTextCharFormat())
        self.calendar.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, QTextCharFormat())

        left_layout.addWidget(self.calendar)

        # 导航按钮
        nav_layout = QHBoxLayout()

        self.prev_month_btn = QPushButton("◀ 上月")
        self.prev_month_btn.clicked.connect(self._prev_month)
        nav_layout.addWidget(self.prev_month_btn)

        self.today_btn = QPushButton("今天")
        self.today_btn.clicked.connect(self._go_today)
        nav_layout.addWidget(self.today_btn)

        self.next_month_btn = QPushButton("下月 ▶")
        self.next_month_btn.clicked.connect(self._next_month)
        nav_layout.addWidget(self.next_month_btn)

        left_layout.addLayout(nav_layout)

        layout.addWidget(left_panel, 1)

        # 右侧：详情
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        # 当前日期标题
        self.date_title = QLabel()
        self.date_title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #8B0000;")
        right_layout.addWidget(self.date_title)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        right_layout.addWidget(line)

        # 详细信息区
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setStyleSheet("""
            QTextEdit {
                background-color: #FFFEF9;
                border: 2px solid #D4A017;
                border-radius: 6px;
                padding: 12px;
                font-size: 11pt;
                color: #2D2D2D;
            }
        """)
        right_layout.addWidget(self.detail_text, 1)

        # 节气信息
        self.solar_term_label = QLabel()
        self.solar_term_label.setStyleSheet("""
            QLabel {
                background-color: rgba(46, 139, 87, 0.1);
                border: 2px solid #2E8B57;
                border-radius: 6px;
                padding: 8px;
                font-size: 11pt;
                color: #2D2D2D;
            }
        """)
        self.solar_term_label.setWordWrap(True)
        right_layout.addWidget(self.solar_term_label)

        # 节日信息
        self.festival_label = QLabel()
        self.festival_label.setStyleSheet("""
            QLabel {
                background-color: rgba(212, 160, 23, 0.1);
                border: 2px solid #D4A017;
                border-radius: 6px;
                padding: 8px;
                font-size: 11pt;
                color: #2D2D2D;
            }
        """)
        self.festival_label.setWordWrap(True)
        right_layout.addWidget(self.festival_label)

        layout.addWidget(right_panel, 1)

    def _on_date_clicked(self, qdate: QDate) -> None:
        """点击日期."""
        self._current_date = datetime(qdate.year(), qdate.month(), qdate.day())
        self._update_display()

    def _on_month_changed(self) -> None:
        """月份切换."""
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        self._current_date = datetime(year, month, 1)
        self._update_display()

    def _prev_month(self) -> None:
        """上一月."""
        self.calendar.showPreviousMonth()

    def _next_month(self) -> None:
        """下一月."""
        self.calendar.showNextMonth()

    def _go_today(self) -> None:
        """回到今天."""
        self._current_date = datetime.now()
        self.calendar.setSelectedDate(QDate.currentDate())
        self._update_display()

    def _update_display(self) -> None:
        """更新显示."""
        year = self._current_date.year
        month = self._current_date.month
        day = self._current_date.day

        # 农历
        lunar = solar_to_lunar(year, month, day)
        lunar_month_str = lunar_month_name(lunar.month, lunar.is_leap)
        lunar_day_str = lunar_day_name(lunar.day)

        # 星期
        weekday = get_weekday_name(year, month, day)

        # 天干地支
        ganzhi = get_ganzhi(year, month, day)
        year_gz = ganzhi["year_ganzhi"]
        month_gz = ganzhi["month_ganzhi"]
        day_gz = ganzhi["day_ganzhi"]
        shengxiao = ganzhi["shengxiao"]

        # 更新标题
        self.date_title.setText(f"{year}年{month}月{day}日 {weekday}")

        # 更新详情
        detail_lines = [
            f"【公历】{year}年{month}月{day}日 {weekday}",
            f"【农历】{year_gz}年（{shengxiao}年）{lunar_month_str}{lunar_day_str}",
            f"【干支】{year_gz}年 {month_gz}月 {day_gz}日",
            f"【生肖】{shengxiao}",
            "",
            "━━━━━━━━━━━━━━━━━━",
        ]

        # 黄历
        almanac = get_almanac(year, month, day)
        detail_lines.append(f"【宜】{' / '.join(almanac['yi'])}")
        detail_lines.append(f"【忌】{' / '.join(almanac['ji'])}")
        detail_lines.append(f"【冲煞】{almanac['chongsha']} {almanac['shengsha']}")

        self.detail_text.setText("\n".join(detail_lines))

        # 节气
        solar_term = get_current_solar_term(year, month, day)
        if solar_term:
            self.solar_term_label.setText(f"节气：{solar_term}")
            self.solar_term_label.setVisible(True)
        else:
            # 显示本月节气
            terms = get_solar_term(year, month)
            if terms:
                term_str = "、".join([f"{name}({day})" for name, _, day in terms])
                self.solar_term_label.setText(f"本月节气：{term_str}")
                self.solar_term_label.setVisible(True)
            else:
                self.solar_term_label.setVisible(False)

        # 节日
        festivals = []
        solar_festivals = get_festivals(month, day)
        traditional_festivals = get_traditional_festivals(lunar.month, lunar.day)

        if solar_festivals:
            festivals.extend(solar_festivals)
        if traditional_festivals:
            festivals.extend(traditional_festivals)

        if festivals:
            self.festival_label.setText(f"节日：{' / '.join(festivals)}")
            self.festival_label.setVisible(True)
        else:
            self.festival_label.setVisible(False)
