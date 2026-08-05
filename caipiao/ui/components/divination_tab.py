"""八卦占卜 UI 组件.

提供八卦占卜界面，支持时间起卦、随机起卦、手动起卦三种方式。
时间起卦支持按小时（24个复选框）或按时辰（12个复选框）选择，
每个选中的时间生成一卦。支持自动填入吉时功能。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...calendar.almanac import get_lucky_hours
from ...divination.bagua import Trigram
from ...divination.divination_engine import (
    DivinationResult,
    batch_time_divination,
    manual_divination,
    random_divination,
)

logger = logging.getLogger(__name__)

# 时辰定义：(地支, 起始小时, 结束小时)
SHICHEN_LIST = [
    ("子", 23, 1), ("丑", 1, 3), ("寅", 3, 5), ("卯", 5, 7),
    ("辰", 7, 9), ("巳", 9, 11), ("午", 11, 13), ("未", 13, 15),
    ("申", 15, 17), ("酉", 17, 19), ("戌", 19, 21), ("亥", 21, 23),
]

# 时辰对应的小时列表
SHICHEN_HOURS = {
    "子": [23, 0], "丑": [1, 2], "寅": [3, 4], "卯": [5, 6],
    "辰": [7, 8], "巳": [9, 10], "午": [11, 12], "未": [13, 14],
    "申": [15, 16], "酉": [17, 18], "戌": [19, 20], "亥": [21, 22],
}

# 地支列表
EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


class HexagramWidget(QWidget):
    """六爻卦象绘制组件."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._yao: tuple[int, ...] = ()
        self._upper: Trigram | None = None
        self._lower: Trigram | None = None
        self.setMinimumSize(200, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_hexagram(self, yao: tuple[int, ...], upper: Trigram, lower: Trigram) -> None:
        """设置卦象数据."""
        self._yao = yao
        self._upper = upper
        self._lower = lower
        self.update()

    def paintEvent(self, event) -> None:
        """绘制卦象."""
        if not self._yao or not self._upper or not self._lower:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        painter.fillRect(0, 0, width, height, QColor("#FAFAFA"))

        painter.setPen(QPen(QColor("#E0E0E0"), 2))
        painter.drawRect(1, 1, width - 2, height - 2)

        line_width = min(width * 0.6, 120)
        line_height = 12
        gap = 20
        start_y = (height - 6 * (line_height + gap)) / 2

        painter.setFont(QFont("SimSun", 14))

        for i in range(6):
            y = start_y + i * (line_height + gap)
            x_center = width / 2
            yao_value = self._yao[i]

            if yao_value in (2, 3):
                color = QColor("#FF5722")
                painter.setPen(QPen(color, 3))
            else:
                color = QColor("#333333")
                painter.setPen(QPen(color, 2))

            if yao_value in (1, 2):
                painter.drawLine(
                    int(x_center - line_width / 2), int(y),
                    int(x_center + line_width / 2), int(y)
                )
            else:
                gap_width = 15
                painter.drawLine(
                    int(x_center - line_width / 2), int(y),
                    int(x_center - gap_width / 2), int(y)
                )
                painter.drawLine(
                    int(x_center + gap_width / 2), int(y),
                    int(x_center + line_width / 2), int(y)
                )

            positions = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
            painter.setPen(QPen(QColor("#666666"), 1))
            painter.setFont(QFont("SimSun", 10))
            painter.drawText(
                int(x_center + line_width / 2 + 15), int(y + 5),
                positions[i]
            )

            painter.setPen(QPen(color, 2))
            painter.setFont(QFont("SimSun", 14))

        painter.setPen(QPen(QColor("#1976D2"), 1))
        painter.setFont(QFont("SimSun", 16))
        painter.drawText(
            int(width / 2 - 60), int(start_y - 30),
            f"{self._lower.name}下 · {self._upper.name}上"
        )

        painter.setPen(QPen(QColor("#E0E0E0"), 1))
        mid_y = start_y + 3 * (line_height + gap) - gap / 2
        painter.drawLine(50, int(mid_y), width - 50, int(mid_y))

        painter.end()


class DivinationTab(QWidget):
    """八卦占卜标签页."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results: list[DivinationResult] = []
        self._result: DivinationResult | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # 左侧：起卦控制
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)

        # 标题
        title = QLabel("八卦占卜")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #8B0000;")
        left_layout.addWidget(title)

        # 操作提示
        hint = QLabel(
            "选择起卦方式后点击「开始起卦」，即可获得卦象、卦辞。\n"
            "时间起卦可选择吉时或自动填入吉时，每个选中的时间生成一组。"
            "（结果由《易经》象数推演，仅供娱乐参考）。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 9pt;")
        left_layout.addWidget(hint)

        # 起卦方式选择
        method_group = QGroupBox("起卦方式")
        method_layout = QVBoxLayout(method_group)
        method_layout.setSpacing(8)
        method_layout.setContentsMargins(12, 16, 12, 12)

        self.time_radio = QRadioButton("时间起卦（梅花易数）")
        self.time_radio.setChecked(True)
        self.time_radio.setToolTip("以当前年、月、日、时依《梅花易数》推演成卦")
        method_layout.addWidget(self.time_radio)

        self.random_radio = QRadioButton("随机起卦")
        self.random_radio.setToolTip("系统随机掷出六爻，随心而占")
        method_layout.addWidget(self.random_radio)

        self.manual_radio = QRadioButton("手动输入")
        self.manual_radio.setToolTip("自行指定六爻阴阳（0=阴，1=阳）")
        method_layout.addWidget(self.manual_radio)

        left_layout.addWidget(method_group)

        # 时间选择模式（仅时间起卦时显示）
        self.time_mode_group = QGroupBox("时间选择模式")
        self.time_mode_layout = QVBoxLayout(self.time_mode_group)
        self.time_mode_layout.setSpacing(8)
        self.time_mode_layout.setContentsMargins(12, 16, 12, 12)

        self.hour_mode_radio = QRadioButton("按小时选择（24小时）")
        self.hour_mode_radio.setToolTip("显示24个复选框，每个对应一个小时")
        self.hour_mode_radio.setChecked(True)
        self.time_mode_layout.addWidget(self.hour_mode_radio)

        self.shichen_mode_radio = QRadioButton("按时辰选择（12时辰）")
        self.shichen_mode_radio.setToolTip("显示12个复选框，每个对应一个时辰")
        self.time_mode_layout.addWidget(self.shichen_mode_radio)

        left_layout.addWidget(self.time_mode_group)

        # 小时复选框面板（用滚动区域包裹）
        self.hour_scroll = QScrollArea()
        self.hour_scroll.setWidgetResizable(True)
        self.hour_scroll.setMaximumHeight(160)
        self.hour_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.hour_panel = QGroupBox("选择小时（0-23点）")
        self.hour_panel_layout = QGridLayout()
        self.hour_panel_layout.setSpacing(6)
        self.hour_panel_layout.setContentsMargins(12, 16, 12, 12)

        self.hour_checkboxes: list[QCheckBox] = []
        for i in range(24):
            cb = QCheckBox(f"{i:02d}时")
            cb.setToolTip(f"选择 {i}:00 - {i}:59 的小时")
            self.hour_checkboxes.append(cb)
            row = i // 6
            col = i % 6
            self.hour_panel_layout.addWidget(cb, row, col)

        self.hour_panel.setLayout(self.hour_panel_layout)
        self.hour_scroll.setWidget(self.hour_panel)
        left_layout.addWidget(self.hour_scroll)

        # 时辰复选框面板（用滚动区域包裹）
        self.shichen_scroll = QScrollArea()
        self.shichen_scroll.setWidgetResizable(True)
        self.shichen_scroll.setMaximumHeight(100)
        self.shichen_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.shichen_panel = QGroupBox("选择时辰")
        self.shichen_panel_layout = QGridLayout()
        self.shichen_panel_layout.setSpacing(6)
        self.shichen_panel_layout.setContentsMargins(12, 16, 12, 12)

        self.shichen_checkboxes: list[QCheckBox] = []
        for i, (name, start, end) in enumerate(SHICHEN_LIST):
            if name == "子":
                label = f"子时(23-{end}点)"
            else:
                label = f"{name}时({start}-{end}点)"
            cb = QCheckBox(label)
            cb.setToolTip(f"选择{name}时（{start}-{end}点），生成一卦")
            self.shichen_checkboxes.append(cb)
            row = i // 4
            col = i % 4
            self.shichen_panel_layout.addWidget(cb, row, col)

        self.shichen_panel.setLayout(self.shichen_panel_layout)
        self.shichen_scroll.setWidget(self.shichen_panel)
        left_layout.addWidget(self.shichen_scroll)

        # 选中时间显示编辑框
        self.selected_time_group = QGroupBox("选中的时间")
        self.selected_time_layout = QVBoxLayout(self.selected_time_group)
        self.selected_time_layout.setSpacing(8)
        self.selected_time_layout.setContentsMargins(12, 16, 12, 12)

        # 小时输入框
        hour_input_layout = QHBoxLayout()
        hour_input_layout.addWidget(QLabel("小时:"))
        self.hour_input = QLineEdit()
        self.hour_input.setPlaceholderText("如: 0,1,2,3 或 3,4,7,8")
        self.hour_input.setToolTip("输入小时（0-23），用逗号分隔")
        self.hour_input.textChanged.connect(self._on_hour_input_changed)
        hour_input_layout.addWidget(self.hour_input)
        self.selected_time_layout.addLayout(hour_input_layout)

        # 时辰输入框
        shichen_input_layout = QHBoxLayout()
        shichen_input_layout.addWidget(QLabel("时辰:"))
        self.shichen_input = QLineEdit()
        self.shichen_input.setPlaceholderText("如: 子,丑,寅 或 辰,巳,午")
        self.shichen_input.setToolTip("输入时辰地支（子丑寅卯辰巳午未申酉戌亥），用逗号分隔")
        self.shichen_input.textChanged.connect(self._on_shichen_input_changed)
        shichen_input_layout.addWidget(self.shichen_input)
        self.selected_time_layout.addLayout(shichen_input_layout)

        left_layout.addWidget(self.selected_time_group)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(self.select_all_btn)

        self.clear_all_btn = QPushButton("取消全选")
        self.clear_all_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.clear_all_btn)

        self.auto_lucky_btn = QPushButton("自动填入吉时")
        self.auto_lucky_btn.setToolTip("根据今日天干地支自动选择吉时")
        self.auto_lucky_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4CAF50, stop:0.5 #45a049, stop:1 #3d8b40);
                color: white;
                border: 1px solid #2E7D32;
                padding: 6px 12px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5CBF60, stop:0.5 #4CAF50, stop:1 #45a049);
            }
        """)
        self.auto_lucky_btn.clicked.connect(self._auto_fill_lucky_hours)
        btn_layout.addWidget(self.auto_lucky_btn)

        left_layout.addLayout(btn_layout)

        # 吉时信息显示
        self.lucky_info = QLabel()
        self.lucky_info.setWordWrap(True)
        self.lucky_info.setStyleSheet(
            "color: #2E7D32; font-size: 9pt; background: #E8F5E9; "
            "border: 1px solid #A5D6A7; border-radius: 4px; padding: 6px;"
        )
        self.lucky_info.setVisible(False)
        left_layout.addWidget(self.lucky_info)

        # 方式说明
        self.method_desc = QLabel()
        self.method_desc.setWordWrap(True)
        self.method_desc.setMinimumHeight(48)
        self.method_desc.setStyleSheet(
            "color: #555; font-size: 9pt; background: #FFF8E1; "
            "border: 1px solid #F0D9A8; border-radius: 6px; padding: 8px;"
        )
        left_layout.addWidget(self.method_desc)

        # 时间起卦所用的当前时间
        self.time_info = QLabel()
        self.time_info.setStyleSheet("color: #8B0000; font-size: 9pt;")
        left_layout.addWidget(self.time_info)

        # 手动输入面板
        self.manual_panel = QGroupBox("输入六爻（从初爻到上爻）")
        self.manual_panel.setVisible(False)
        manual_layout = QGridLayout()
        manual_layout.setSpacing(8)
        manual_layout.setContentsMargins(12, 16, 12, 12)

        self.yao_spins: list[QSpinBox] = []
        positions = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]

        for i, pos in enumerate(positions):
            row = i // 2
            col = (i % 2) * 2

            label = QLabel(f"{pos}:")
            manual_layout.addWidget(label, row, col)

            spin = QSpinBox()
            spin.setRange(0, 1)
            spin.setSpecialValueText("阴(0)")
            spin.setPrefix("爻值 ")
            spin.setToolTip("0=阴爻，1=阳爻")
            manual_layout.addWidget(spin, row, col + 1)

            self.yao_spins.append(spin)

        self.manual_panel.setLayout(manual_layout)
        left_layout.addWidget(self.manual_panel)

        # 起卦按钮
        self.divination_btn = QPushButton("开始起卦")
        self.divination_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E2231A, stop:0.5 #C41E3A, stop:1 #A01830);
                color: white;
                border: 2px solid #D4A017;
                padding: 12px 24px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F54030, stop:0.5 #E2231A, stop:1 #C41E3A);
                border: 2px solid #F5C518;
            }
            QPushButton:pressed {
                background: #A01830;
            }
        """)
        self.divination_btn.clicked.connect(self._do_divination)
        left_layout.addWidget(self.divination_btn)

        left_layout.addStretch()

        layout.addWidget(left_panel, 1)

        # 右侧：结果显示
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        # 卦象绘制
        self.hexagram_widget = HexagramWidget()
        right_layout.addWidget(self.hexagram_widget, 2)

        # 卦象信息
        info_group = QGroupBox("卦象信息")
        info_layout = QVBoxLayout()

        self.hexagram_name_label = QLabel()
        self.hexagram_name_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #8B0000;")
        info_layout.addWidget(self.hexagram_name_label)

        self.hexagram_detail = QTextEdit()
        self.hexagram_detail.setReadOnly(True)
        self.hexagram_detail.setMaximumHeight(200)
        self.hexagram_detail.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
                font-size: 11pt;
            }
        """)
        info_layout.addWidget(self.hexagram_detail)

        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)

        # 推荐号码
        self.numbers_group = QGroupBox("推荐号码")
        self.numbers_group.setVisible(False)
        numbers_layout = QVBoxLayout()

        self.numbers_label = QLabel()
        self.numbers_label.setStyleSheet("font-size: 14pt; color: #8B0000;")
        self.numbers_label.setWordWrap(True)
        numbers_layout.addWidget(self.numbers_label)

        self.numbers_group.setLayout(numbers_layout)
        right_layout.addWidget(self.numbers_group)

        layout.addWidget(right_panel, 2)

        # 连接信号
        self.time_radio.toggled.connect(self._on_method_changed)
        self.random_radio.toggled.connect(self._on_method_changed)
        self.manual_radio.toggled.connect(self._on_method_changed)
        self.hour_mode_radio.toggled.connect(self._on_time_mode_changed)
        self.shichen_mode_radio.toggled.connect(self._on_time_mode_changed)
        self._on_method_changed()

    def _select_all(self) -> None:
        """全选当前模式的所有时间复选框."""
        if self.time_radio.isChecked():
            if self.hour_mode_radio.isChecked():
                for cb in self.hour_checkboxes:
                    cb.setChecked(True)
                self._sync_checkboxes_to_input()
            else:
                for cb in self.shichen_checkboxes:
                    cb.setChecked(True)
                self._sync_checkboxes_to_input()

    def _clear_all(self) -> None:
        """取消全选当前模式的所有时间复选框."""
        if self.time_radio.isChecked():
            if self.hour_mode_radio.isChecked():
                for cb in self.hour_checkboxes:
                    cb.setChecked(False)
            else:
                for cb in self.shichen_checkboxes:
                    cb.setChecked(False)
            self._sync_checkboxes_to_input()

    def _auto_fill_lucky_hours(self) -> None:
        """自动填入今日吉时."""
        now = datetime.now(timezone.utc).astimezone()
        lucky_hours = get_lucky_hours(now.year, now.month, now.day, min_score=60)

        if not lucky_hours:
            QMessageBox.information(self, "提示", "今日暂无吉时数据")
            return

        if self.hour_mode_radio.isChecked():
            # 小时模式：先取消全选，然后选中吉时对应的小时
            for cb in self.hour_checkboxes:
                cb.setChecked(False)

            filled_hours = []
            for item in lucky_hours:
                for h in item["hours"]:
                    if 0 <= h <= 23:
                        self.hour_checkboxes[h].setChecked(True)
                        filled_hours.append(h)

            # 同步到编辑框
            self._sync_checkboxes_to_input()

            self.lucky_info.setText(
                f"已自动填入吉时（共{len(filled_hours)}个小时）：\n"
                + "、".join([f"{h:02d}时" for h in sorted(filled_hours)])
            )
        else:
            # 时辰模式：先取消全选，然后选中吉时对应的时辰
            for cb in self.shichen_checkboxes:
                cb.setChecked(False)

            filled_shichen = []
            for item in lucky_hours:
                branch = item["branch"]
                if branch in EARTHLY_BRANCHES:
                    idx = EARTHLY_BRANCHES.index(branch)
                    self.shichen_checkboxes[idx].setChecked(True)
                    filled_shichen.append(item["name"])

            # 同步到编辑框
            self._sync_checkboxes_to_input()

            self.lucky_info.setText(
                f"已自动填入吉时（共{len(filled_shichen)}个时辰）：\n"
                + "、".join(filled_shichen)
            )

        self.lucky_info.setVisible(True)

    def _sync_checkboxes_to_input(self) -> None:
        """将复选框状态同步到编辑框."""
        if self.hour_mode_radio.isChecked():
            selected = []
            for i, cb in enumerate(self.hour_checkboxes):
                if cb.isChecked():
                    selected.append(str(i))
            self.hour_input.setText(",".join(selected))
        else:
            selected = []
            for i, cb in enumerate(self.shichen_checkboxes):
                if cb.isChecked():
                    selected.append(SHICHEN_LIST[i][0])
            self.shichen_input.setText(",".join(selected))

    def _on_hour_input_changed(self, text: str) -> None:
        """小时输入框变化时，同步更新复选框."""
        try:
            # 解析输入的小时
            hours = set()
            for part in text.split(","):
                part = part.strip()
                if part:
                    h = int(part)
                    if 0 <= h <= 23:
                        hours.add(h)

            # 更新复选框
            for i, cb in enumerate(self.hour_checkboxes):
                cb.setChecked(i in hours)
        except ValueError:
            pass

    def _on_shichen_input_changed(self, text: str) -> None:
        """时辰输入框变化时，同步更新复选框."""
        # 解析输入的时辰
        selected_branches = set()
        for part in text.split(","):
            part = part.strip()
            if part and part in EARTHLY_BRANCHES:
                selected_branches.add(part)

        # 更新复选框
        for i, cb in enumerate(self.shichen_checkboxes):
            branch = SHICHEN_LIST[i][0]
            cb.setChecked(branch in selected_branches)

    def _on_method_changed(self) -> None:
        """起卦方式改变时，更新说明、当前时间与手动输入面板."""
        is_manual = self.manual_radio.isChecked()
        is_time = self.time_radio.isChecked()
        self.manual_panel.setVisible(is_manual)
        self.time_info.setVisible(is_time)
        self.time_mode_group.setVisible(is_time)
        self.selected_time_group.setVisible(is_time)
        self.select_all_btn.setVisible(is_time)
        self.clear_all_btn.setVisible(is_time)
        self.auto_lucky_btn.setVisible(is_time)
        self.hour_scroll.setVisible(is_time and self.hour_mode_radio.isChecked())
        self.shichen_scroll.setVisible(is_time and self.shichen_mode_radio.isChecked())

        if is_time:
            self._on_time_mode_changed()
            now = datetime.now(timezone.utc).astimezone()
            self.time_info.setText(
                f"当前时间：{now.year}年{now.month}月{now.day}日 {now.hour}时"
            )
        else:
            self.lucky_info.setVisible(False)

        if self.random_radio.isChecked():
            self.method_desc.setText(
                "随机起卦：由系统随机掷出六爻，随心而占，"
                "适合心无定见、随缘问卜之时。"
            )
        elif self.manual_radio.isChecked():
            self.method_desc.setText(
                "手动输入：自行指定六爻阴阳（0=阴爻，1=阳爻），"
                "从初爻到上爻依次填入，适合已有卦象或特定起法。"
            )

    def _on_time_mode_changed(self) -> None:
        """时间模式改变时，更新复选框面板显示和说明."""
        is_hour_mode = self.hour_mode_radio.isChecked()
        self.hour_scroll.setVisible(self.time_radio.isChecked() and is_hour_mode)
        self.shichen_scroll.setVisible(self.time_radio.isChecked() and not is_hour_mode)
        self.lucky_info.setVisible(False)

        # 清空编辑框
        self.hour_input.clear()
        self.shichen_input.clear()

        if self.time_radio.isChecked():
            if is_hour_mode:
                self.method_desc.setText(
                    "时间起卦（小时模式）：选择需要的小时，每个选中的小时生成一卦。\n"
                    "点击「自动填入吉时」可自动选择今日吉时。"
                )
            else:
                self.method_desc.setText(
                    "时间起卦（时辰模式）：选择需要的时辰，每个选中的时辰生成一卦。\n"
                    "点击「自动填入吉时」可自动选择今日吉时。"
                )

    def _get_selected_hours(self) -> list[int]:
        """获取选中的小时列表."""
        hours = []
        if self.hour_mode_radio.isChecked():
            for i, cb in enumerate(self.hour_checkboxes):
                if cb.isChecked():
                    hours.append(i)
        else:
            for i, cb in enumerate(self.shichen_checkboxes):
                if cb.isChecked():
                    branch_name = SHICHEN_LIST[i][0]
                    hours.extend(SHICHEN_HOURS[branch_name])
        return sorted(set(hours))

    def _do_divination(self) -> None:
        """执行起卦."""
        try:
            if self.time_radio.isChecked():
                selected_hours = self._get_selected_hours()
                if not selected_hours:
                    QMessageBox.warning(self, "提示", "请至少选择一个时间（小时或时辰）")
                    return

                self._results = batch_time_divination(hours=selected_hours)

                if len(self._results) == 1:
                    self._result = self._results[0]
                else:
                    self._result = self._results[0]

                self._update_result_batch()

            elif self.random_radio.isChecked():
                self._result = random_divination()
                self._results = [self._result]
                self._update_result()

            else:
                yao_values = [spin.value() for spin in self.yao_spins]
                self._result = manual_divination(yao_values)
                self._results = [self._result]
                self._update_result()

        except Exception as exc:  # noqa: BLE001
            logger.exception("起卦失败")
            QMessageBox.warning(self, "起卦错误", f"起卦失败：{exc!s}")

    def _update_result(self) -> None:
        """更新单个卦象结果."""
        if not self._result:
            return

        self.hexagram_widget.set_hexagram(
            self._result.yao,
            self._result.upper_trigram,
            self._result.lower_trigram,
        )

        name = self._result.hexagram.full_name
        if self._result.changed_hexagram:
            name += f" -> {self._result.changed_hexagram.full_name}"
        self.hexagram_name_label.setText(name)

        detail = self._result.summary()
        self.hexagram_detail.setText(detail)

        if self._result.recommended_numbers:
            nums = "、".join([f"{n:02d}" for n in self._result.recommended_numbers[:8]])
            self.numbers_label.setText(f"推荐号码：{nums}")
            self.numbers_group.setVisible(True)
        else:
            self.numbers_group.setVisible(False)

    def _update_result_batch(self) -> None:
        """更新批量卦象结果显示."""
        if not self._results:
            return

        first = self._results[0]
        self.hexagram_widget.set_hexagram(
            first.yao,
            first.upper_trigram,
            first.lower_trigram,
        )

        if len(self._results) == 1:
            name = first.hexagram.full_name
            if first.changed_hexagram:
                name += f" -> {first.changed_hexagram.full_name}"
            self.hexagram_name_label.setText(name)
            self.hexagram_detail.setText(first.summary())
        else:
            self.hexagram_name_label.setText(f"共 {len(self._results)} 组卦象")

            details = []
            for i, r in enumerate(self._results):
                hr = r.time_str.split(" ")[-1] if " " in r.time_str else ""
                changed = f" -> {r.changed_hexagram.full_name}" if r.changed_hexagram else ""
                details.append(f"[{i+1}] {r.hexagram.full_name}{changed}  {hr}")
                details.append(f"    {r.hexagram.description}")
                details.append("")

            self.hexagram_detail.setText("\n".join(details))

        if first.recommended_numbers:
            nums = "、".join([f"{n:02d}" for n in first.recommended_numbers[:8]])
            self.numbers_label.setText(f"推荐号码（第1组）：{nums}")
            self.numbers_group.setVisible(True)
        else:
            self.numbers_group.setVisible(False)

    def get_results(self) -> list[DivinationResult]:
        """获取所有卦象结果（供外部策略使用）."""
        return self._results
