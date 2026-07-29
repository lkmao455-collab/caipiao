"""八卦占卜 UI 组件.

提供八卦占卜界面，支持时间起卦、随机起卦、手动起卦三种方式。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)

from ...divination.bagua import BAGUA, Trigram
from ...divination.yijing import Hexagram, get_yao_positions
from ...divination.divination_engine import (
    DivinationResult,
    time_divination,
    random_divination,
    manual_divination,
)


class HexagramWidget(QWidget):
    """六爻卦象绘制组件."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._yao: tuple[int, ...] = ()
        self._upper: Optional[Trigram] = None
        self._lower: Optional[Trigram] = None
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

        # 背景色
        painter.fillRect(0, 0, width, height, QColor("#FAFAFA"))

        # 绘制边框
        painter.setPen(QPen(QColor("#E0E0E0"), 2))
        painter.drawRect(1, 1, width - 2, height - 2)

        # 计算爻的尺寸
        line_width = min(width * 0.6, 120)
        line_height = 12
        gap = 20
        start_y = (height - 6 * (line_height + gap)) / 2

        # 绘制六爻（从下到上）
        painter.setFont(QFont("SimSun", 14))

        for i in range(6):
            y = start_y + i * (line_height + gap)
            x_center = width / 2

            # 爻的值
            yao_value = self._yao[i]

            # 颜色：动爻（老阳/老阴）以橙红突出，静爻用墨色
            if yao_value in (2, 3):  # 动爻
                color = QColor("#FF5722")
                painter.setPen(QPen(color, 3))
            else:  # 静爻（少阳/少阴）
                color = QColor("#333333")
                painter.setPen(QPen(color, 2))

            # 绘制爻线
            if yao_value in (1, 2):  # 阳爻 ━━━━━
                painter.drawLine(
                    int(x_center - line_width / 2), int(y),
                    int(x_center + line_width / 2), int(y)
                )
            else:  # 阴爻 ━ ━
                gap_width = 15
                painter.drawLine(
                    int(x_center - line_width / 2), int(y),
                    int(x_center - gap_width / 2), int(y)
                )
                painter.drawLine(
                    int(x_center + gap_width / 2), int(y),
                    int(x_center + line_width / 2), int(y)
                )

            # 爻位标签
            positions = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
            painter.setPen(QPen(QColor("#666666"), 1))
            painter.setFont(QFont("SimSun", 10))
            painter.drawText(
                int(x_center + line_width / 2 + 15), int(y + 5),
                positions[i]
            )

            # 重新设置画笔
            painter.setPen(QPen(color, 2))
            painter.setFont(QFont("SimSun", 14))

        # 绘制卦名（下卦·上卦 传统记法）
        painter.setPen(QPen(QColor("#1976D2"), 1))
        painter.setFont(QFont("SimSun", 16))
        painter.drawText(
            int(width / 2 - 60), int(start_y - 30),
            f"{self._lower.name}下 · {self._upper.name}上"
        )

        # 绘制分隔线
        painter.setPen(QPen(QColor("#E0E0E0"), 1))
        mid_y = start_y + 3 * (line_height + gap) - gap / 2
        painter.drawLine(50, int(mid_y), width - 50, int(mid_y))

        painter.end()


class DivinationTab(QWidget):
    """八卦占卜标签页."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: Optional[DivinationResult] = None
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
            "选择起卦方式后点击「开始起卦」，即可获得卦象、卦辞与推荐号码"
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

        # 方式说明（随选择动态更新）
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

        self.yao_spins: List[QSpinBox] = []
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
        self._on_method_changed()

    def _on_method_changed(self) -> None:
        """起卦方式改变时，更新说明、当前时间与手动输入面板。"""
        is_manual = self.manual_radio.isChecked()
        self.manual_panel.setVisible(is_manual)
        self.time_info.setVisible(self.time_radio.isChecked())

        if self.time_radio.isChecked():
            self.method_desc.setText(
                "时间起卦：以当前年、月、日、时依《梅花易数》推演，"
                "随时间流转自然成卦，所谓“天人合一，感而遂通”。"
            )
            now = datetime.now()
            self.time_info.setText(
                f"起卦时间：{now.year}年{now.month}月{now.day}日 {now.hour}时"
            )
        elif self.random_radio.isChecked():
            self.method_desc.setText(
                "随机起卦：由系统随机掷出六爻，随心而占，"
                "适合心无定见、随缘问卜之时。"
            )
        else:
            self.method_desc.setText(
                "手动输入：自行指定六爻阴阳（0=阴爻，1=阳爻），"
                "从初爻到上爻依次填入，适合已有卦象或特定起法。"
            )

    def _do_divination(self) -> None:
        """执行起卦."""
        try:
            if self.time_radio.isChecked():
                self._result = time_divination()
            elif self.random_radio.isChecked():
                self._result = random_divination()
            else:
                # 手动输入
                yao_values = [spin.value() for spin in self.yao_spins]
                self._result = manual_divination(yao_values)

            self._update_result()

        except Exception as e:
            QMessageBox.warning(self, "起卦错误", f"起卦失败：{str(e)}")

    def _update_result(self) -> None:
        """更新结果显示."""
        if not self._result:
            return

        # 更新卦象绘制
        self.hexagram_widget.set_hexagram(
            self._result.yao,
            self._result.upper_trigram,
            self._result.lower_trigram,
        )

        # 更新卦象名称
        name = self._result.hexagram.full_name
        if self._result.changed_hexagram:
            name += f" → {self._result.changed_hexagram.full_name}"
        self.hexagram_name_label.setText(name)

        # 更新卦象详情
        detail = self._result.summary()
        self.hexagram_detail.setText(detail)

        # 更新推荐号码
        if self._result.recommended_numbers:
            nums = "、".join([f"{n:02d}" for n in self._result.recommended_numbers[:8]])
            self.numbers_label.setText(f"推荐号码：{nums}")
            self.numbers_group.setVisible(True)
        else:
            self.numbers_group.setVisible(False)
