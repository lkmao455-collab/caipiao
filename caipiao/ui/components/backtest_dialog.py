"""历史回测对话框.

选择一个已经开奖的历史日期，使用策略基于该日期之前的数据生成预测号码，
并与真实开奖结果对比。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDate, QThread
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.engine import GenerationEngine
from ...core.ticket import Ticket
from ...data.repository import DataRepository
from ..workers import GenerateTicketsThread
from .ball_display import TicketRowWidget
from .strategy_panel import StrategyPanel


class BacktestDialog(QDialog):
    """历史回测窗口."""

    def __init__(
        self,
        engine: GenerationEngine,
        data_repository: DataRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.data_repository = data_repository
        self._generate_thread: Optional[QThread] = None

        self.setWindowTitle("历史回测")
        self.resize(900, 700)
        self._setup_ui()
        self._refresh_date_range()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)

        # 说明
        info = QLabel(
            "选择一个已开奖日期，程序会使用该日期之前的全部历史数据生成预测，"
            "并与当天真实开奖结果进行对比。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        self.layout.addWidget(info)

        # 顶部控制区
        control_layout = QHBoxLayout()

        control_layout.addWidget(QLabel("回测日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        control_layout.addWidget(self.date_edit)

        control_layout.addWidget(QLabel("预测注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(5)
        control_layout.addWidget(self.count_spin)

        self.run_btn = QPushButton("开始回测")
        self.run_btn.setToolTip("使用选中日期之前的数据生成预测")
        self.run_btn.clicked.connect(self._run_backtest)
        control_layout.addWidget(self.run_btn)

        control_layout.addStretch()
        self.layout.addLayout(control_layout)

        # 策略面板
        self.strategy_panel = StrategyPanel(self.engine)
        self.layout.addWidget(self.strategy_panel)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        # 结果区分左右/上下
        self.result_group = QGroupBox("回测结果")
        result_layout = QVBoxLayout(self.result_group)

        # 真实开奖
        actual_layout = QHBoxLayout()
        self.actual_info_label = QLabel("真实开奖：")
        self.actual_info_label.setStyleSheet("font-weight: bold; color: #0A2540;")
        actual_layout.addWidget(self.actual_info_label)
        self.actual_container = QWidget()
        self.actual_layout = QHBoxLayout(self.actual_container)
        self.actual_layout.setContentsMargins(0, 0, 0, 0)
        actual_layout.addWidget(self.actual_container)
        actual_layout.addStretch()
        result_layout.addLayout(actual_layout)

        # 训练数据范围说明：明确展示预测所用数据的截止情况，说明不存在数据泄露
        self.data_scope_label = QLabel()
        self.data_scope_label.setWordWrap(True)
        self.data_scope_label.setStyleSheet(
            "color: #1B5E20; background: #E8F5E9; border: 1px solid #A5D6A7;"
            " border-radius: 4px; padding: 6px; font-size: 12px;"
        )
        self.data_scope_label.setVisible(False)
        result_layout.addWidget(self.data_scope_label)

        # 预测结果
        result_layout.addWidget(QLabel("预测号码（命中数 = 红球命中 + 蓝球命中）:"))
        self.predicted_scroll = QScrollArea()
        self.predicted_scroll.setWidgetResizable(True)
        self.predicted_container = QWidget()
        self.predicted_layout = QVBoxLayout(self.predicted_container)
        self.predicted_layout.setSpacing(8)
        self.predicted_layout.addStretch()
        self.predicted_scroll.setWidget(self.predicted_container)
        result_layout.addWidget(self.predicted_scroll)

        self.layout.addWidget(self.result_group)

    def _refresh_date_range(self) -> None:
        """根据本地数据设置可选日期范围."""
        start, end = self.data_repository.get_date_range()
        if start is None or end is None:
            self.date_edit.setEnabled(False)
            self.run_btn.setEnabled(False)
            return
        self.date_edit.setMinimumDate(QDate(start.year, start.month, start.day))
        self.date_edit.setMaximumDate(QDate(end.year, end.month, end.day))

        # 在日历上对已有开奖记录的日期加下划线提示
        calendar = self.date_edit.calendarWidget()
        highlight_format = QTextCharFormat()
        highlight_format.setFontUnderline(True)
        highlight_format.setForeground(QColor("#1976D2"))
        for record in self.data_repository.get_all():
            qdate = QDate(
                record.draw_date.year,
                record.draw_date.month,
                record.draw_date.day,
            )
            calendar.setDateTextFormat(qdate, highlight_format)

        # 默认选中倒数第二期，留出预测空间
        records = self.data_repository.get_all()
        if len(records) >= 2:
            default = records[-2].draw_date
        else:
            default = end
        self.date_edit.setDate(QDate(default.year, default.month, default.day))

    def _run_backtest(self) -> None:
        target_qdate = self.date_edit.date()
        target_date = datetime(target_qdate.year(), target_qdate.month(), target_qdate.day())

        actual = self.data_repository.get_record_by_date(target_date)
        if actual is None:
            QMessageBox.warning(self, "无开奖记录", "选中的日期没有官方开奖数据，请重新选择。")
            return

        history = self.data_repository.get_records_before(target_date)
        strategy_id = self.strategy_panel.current_strategy_id()
        if not strategy_id:
            QMessageBox.warning(self, "提示", "请选择一个生成策略")
            return

        try:
            options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        # 需要历史数据的策略自动注入该日期之前的数据
        history_dependent = {
            "hot_cold",
            "smart_hot_cold",
            "missing_number",
            "balanced",
            "xgboost",
            "lightgbm",
        }
        if strategy_id in history_dependent:
            if not history:
                QMessageBox.warning(self, "缺少数据", "该日期之前没有足够的历史开奖数据。")
                return
            options["history"] = history

        count = self.count_spin.value()

        # 显示真实开奖
        self._show_actual(actual)

        # 展示本次预测所用数据的截止情况，明确不存在数据泄露
        self._show_data_scope(strategy_id, history, target_date, strategy_id in history_dependent)

        self.run_btn.setEnabled(False)
        self.run_btn.setText("预测中...")
        self.progress.setVisible(True)

        self._generate_thread = GenerateTicketsThread(
            self.engine, strategy_id, count, options, self
        )
        self._generate_thread.result_ready.connect(
            lambda tickets, error: self._on_prediction_finished(tickets, error, actual)
        )
        self._generate_thread.start()

    def _show_actual(self, actual) -> None:
        """显示真实开奖结果."""
        # 清空旧内容
        while self.actual_layout.count():
            item = self.actual_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        date_str = actual.draw_date.strftime("%Y-%m-%d")
        self.actual_info_label.setText(f"真实开奖：第 {actual.issue} 期  {date_str}")
        self.result_group.setTitle(f"回测结果 - 第 {actual.issue} 期（{date_str}）")

        ticket = Ticket(
            red_balls=actual.red_balls,
            blue_ball=actual.blue_ball,
            strategy_name="官方开奖",
            basis=f"期号：{actual.issue}，开奖日期：{date_str}",
        )
        self.actual_layout.addWidget(TicketRowWidget(ticket))

    def _show_data_scope(
        self, strategy_id, history, target_date, uses_history: bool
    ) -> None:
        """展示本次预测所用训练数据的范围，明确不含预测日、无数据泄露."""
        target_str = target_date.strftime("%Y-%m-%d")
        if not uses_history:
            self.data_scope_label.setText(
                f"该策略不依赖历史开奖数据，预测与 {target_str} 当期结果无关，"
                "不存在数据泄露。"
            )
            self.data_scope_label.setVisible(True)
            return

        start = min(r.draw_date for r in history)
        end = max(r.draw_date for r in history)
        self.data_scope_label.setText(
            f"✔ 无数据泄露：本次预测仅使用 {target_str} 之前的数据。\n"
            f"训练数据共 {len(history)} 期，日期范围 "
            f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}"
            f"（均早于预测日 {target_str}，不含当天及以后）。"
        )
        self.data_scope_label.setVisible(True)

    def _on_prediction_finished(self, tickets, error, actual) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始回测")
        self.progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "预测失败", str(error))
            return

        # 清空旧预测结果
        while self.predicted_layout.count() > 1:
            item = self.predicted_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        actual_reds = set(actual.red_balls)
        actual_blue = actual.blue_ball

        for idx, ticket in enumerate(tickets, start=1):
            red_hits = len(actual_reds & {b.number for b in ticket.red_balls})
            blue_hit = 1 if ticket.blue_ball.number == actual_blue else 0
            hit_text = f"命中 {red_hits} 个红球"
            if blue_hit:
                hit_text += " + 蓝球"

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            row_layout.addWidget(TicketRowWidget(ticket, show_index=idx))
            hit_label = QLabel(f"{hit_text}")
            hit_label.setStyleSheet(
                "color: #D32F2F; font-weight: bold; font-size: 13px;"
            )
            row_layout.addWidget(hit_label)
            row_layout.addStretch()

            self.predicted_layout.insertWidget(idx - 1, row_widget)
