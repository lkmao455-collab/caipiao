"""历史回测对话框.

选择一个已经开奖的历史日期，使用策略基于该日期之前的数据生成预测号码，
并与真实开奖结果对比。
"""

from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Optional

from PySide6.QtCore import QDate, QThread
from PySide6.QtGui import QColor, QFont, QTextCharFormat
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

from ...persistence.backtest_db import BacktestDatabase
from ...persistence.settings import AppSettings
from ...core.profile import LotteryProfile
from ...core.prize import calculate_prize
from ...core.strategies.generic import needs_history
from ...core.ticket import Ticket
from ..workers import GenerateTicketsThread
from .ball_display import TicketRowWidget
from .strategy_panel import StrategyPanel


class BacktestDialog(QDialog):
    """历史回测窗口."""

    def __init__(
        self,
        context,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.profile: LotteryProfile = context.profile
        self.data_repository = context.data_repository
        self.settings = AppSettings()
        self._db = BacktestDatabase()
        self._generate_thread: Optional[QThread] = None
        self._last_ticket_results: List[Dict[str, Any]] = []

        self.setWindowTitle(f"{self.profile.name}历史回测")
        self.resize(900, 700)
        self._setup_ui()
        self._refresh_date_range()
        self._restore_last_settings()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)

        info = QLabel(
            "选择一个已开奖日期，程序会使用该日期之前的全部历史数据生成预测，"
            "并与当天真实开奖结果进行对比。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        self.layout.addWidget(info)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("回测日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        control_layout.addWidget(self.date_edit)

        control_layout.addWidget(QLabel("预测注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(5)
        control_layout.addWidget(self.count_spin)

        self.run_btn = QPushButton("开始回测")
        self.run_btn.setToolTip("使用选中日期之前的数据生成预测")
        self.run_btn.clicked.connect(self._run_backtest)
        control_layout.addWidget(self.run_btn)

        control_layout.addStretch()
        self.layout.addLayout(control_layout)

        self.strategy_panel = StrategyPanel(self.context.engine)
        self.layout.addWidget(self.strategy_panel)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        self.result_group = QGroupBox("回测结果")
        result_layout = QVBoxLayout(self.result_group)

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

        self.data_scope_label = QLabel()
        self.data_scope_label.setWordWrap(True)
        self.data_scope_label.setStyleSheet(
            "color: #1B5E20; background: #E8F5E9; border: 1px solid #A5D6A7;"
            " border-radius: 4px; padding: 6px; font-size: 9pt;"
        )
        self.data_scope_label.setVisible(False)
        result_layout.addWidget(self.data_scope_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "QLabel { color: #0A2540; background-color: #E3F2FD; "
            "border-radius: 4px; padding: 6px; font-size: 10pt; font-weight: bold; }"
        )
        self.summary_label.setVisible(False)
        result_layout.addWidget(self.summary_label)

        result_layout.addWidget(QLabel("预测号码（命中数按各号码组分别统计）:"))
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
        start, end = self.data_repository.get_date_range()
        if start is None or end is None:
            self.date_edit.setEnabled(False)
            self.run_btn.setEnabled(False)
            return
        self.date_edit.setMinimumDate(QDate(start.year, start.month, start.day))
        self.date_edit.setMaximumDate(QDate(end.year, end.month, end.day))

        calendar = self.date_edit.calendarWidget()
        highlight_format = QTextCharFormat()
        highlight_format.setFontUnderline(True)
        highlight_format.setFontWeight(QFont.Weight.Bold)
        highlight_format.setForeground(QColor("#1976D2"))
        for record in self.data_repository.get_all():
            qdate = QDate(
                record.draw_date.year,
                record.draw_date.month,
                record.draw_date.day,
            )
            calendar.setDateTextFormat(qdate, highlight_format)

        records = self.data_repository.get_all()
        if len(records) >= 2:
            default = records[-2].draw_date
        else:
            default = end
        self.date_edit.setDate(QDate(default.year, default.month, default.day))

    def _restore_last_settings(self) -> None:
        """恢复上次使用的回测参数."""
        last_date_str = self.settings.last_backtest_date
        if last_date_str:
            try:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                qdate = QDate(last_date.year, last_date.month, last_date.day)
                if qdate >= self.date_edit.minimumDate() and qdate <= self.date_edit.maximumDate():
                    self.date_edit.setDate(qdate)
            except ValueError:
                pass

        self.count_spin.setValue(self.settings.last_backtest_count)

        saved_options = self.settings.last_backtest_options
        if saved_options:
            self.strategy_panel.set_options(saved_options)

    def _save_current_settings(self) -> None:
        """保存当前回测参数."""
        self.settings.last_backtest_date = self.date_edit.date().toString("yyyy-MM-dd")
        self.settings.last_backtest_count = self.count_spin.value()
        try:
            options = self.strategy_panel.current_options()
            user_options = {k: v for k, v in options.items() if k != "history"}
            self.settings.last_backtest_options = user_options
        except ValueError:
            pass
        self.settings.sync()

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

        uses_history = needs_history(strategy_id)
        if uses_history:
            if not history:
                QMessageBox.warning(self, "缺少数据", "该日期之前没有足够的历史开奖数据。")
                return
            options["history"] = history

        count = self.count_spin.value()

        # 保存当前参数供下次启动恢复
        self._save_current_settings()

        self._show_actual(actual)
        self._show_data_scope(strategy_id, history, target_date, uses_history)

        self.run_btn.setEnabled(False)
        self.run_btn.setText("预测中...")
        self.progress.setVisible(True)

        self._generate_thread = GenerateTicketsThread(
            self.context.engine, strategy_id, count, options, self
        )
        self._generate_thread.result_ready.connect(
            lambda tickets, error: self._on_prediction_finished(tickets, error, actual)
        )
        self._generate_thread.finished.connect(
            partial(self._cleanup_generate_thread)
        )
        self._generate_thread.start()

    def _cleanup_generate_thread(self) -> None:
        """生成线程 finished 后的清理."""
        thread = self.sender()
        if thread is None:
            return
        if thread is self._generate_thread:
            self._generate_thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    def _show_actual(self, actual) -> None:
        while self.actual_layout.count():
            item = self.actual_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        date_str = actual.draw_date.strftime("%Y-%m-%d")
        self.actual_info_label.setText(f"真实开奖：第 {actual.issue} 期  {date_str}")
        self.result_group.setTitle(f"回测结果 - 第 {actual.issue} 期（{date_str}）")

        # 使用完整 groups 展示真实开奖（包括 draw_only 组），但用 pick_groups 验证
        groups = {g.key: actual.groups.get(g.key, []) for g in self.profile.groups}
        ticket = Ticket(
            profile=self.profile,
            groups=groups,
            strategy_name="官方开奖",
            basis=f"期号：{actual.issue}，开奖日期：{date_str}",
            validate=False,
        )
        self.actual_layout.addWidget(TicketRowWidget(ticket))

    def _show_data_scope(
        self, strategy_id, history, target_date, uses_history: bool
    ) -> None:
        target_str = target_date.strftime("%Y-%m-%d")
        if not uses_history:
            self.data_scope_label.setText(
                f"该策略不依赖历史开奖数据，预测与 {target_str} 当期结果无关，"
                "不存在数据泄露。"
            )
            self.data_scope_label.setVisible(True)
            return

        if not history:
            self.data_scope_label.setText(
                f"⚠ 该策略需要历史数据，但 {target_str} 之前没有可用记录。"
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

        while self.predicted_layout.count() > 1:
            item = self.predicted_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total_cost = len(tickets) * 2
        total_fixed_prize = 0
        float_prize_count = 0
        hit_count = 0
        ticket_results: List[Dict[str, Any]] = []

        for idx, ticket in enumerate(tickets, start=1):
            hits: Dict[str, int] = {}
            hit_parts = []
            for g in self.profile.groups:
                actual_nums = actual.groups.get(g.key, [])
                predicted_nums = ticket.groups.get(g.key, [])
                if g.positional:
                    h = sum(1 for a, p in zip(actual_nums, predicted_nums) if a == p)
                elif g.draw_only:
                    ticket_numbers: set[int] = set()
                    for pg in self.profile.pick_groups:
                        ticket_numbers.update(ticket.groups.get(pg.key, []))
                    h = len(set(actual_nums) & ticket_numbers)
                else:
                    h = len(set(actual_nums) & set(predicted_nums))
                hits[g.key] = h
                if not g.draw_only:
                    hit_parts.append(f"{g.name}{h}")
            hit_text = "，".join(hit_parts)

            prize_name, prize_amount = calculate_prize(
                self.profile.key, hits, ticket.groups, actual.groups
            )
            if prize_amount is None:
                prize_text = f"{prize_name}（浮动奖金）"
                float_prize_count += 1
                hit_count += 1
            elif prize_amount > 0:
                prize_text = f"{prize_name} · 奖金 {prize_amount} 元"
                total_fixed_prize += prize_amount
                hit_count += 1
            else:
                prize_text = "未中奖"

            ticket_results.append({
                "ticket": ticket,
                "hits": hits,
                "prize_name": prize_name,
                "prize_amount": prize_amount,
            })

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            row_layout.addWidget(TicketRowWidget(ticket, show_index=idx))
            hit_label = QLabel(f"命中：{hit_text}\n{prize_text}")
            hit_label.setStyleSheet(
                "QLabel { color: #B71C1C; background-color: #FFEBEE; "
                "border-radius: 4px; padding: 4px; font-weight: bold; font-size: 10pt; }"
            )
            hit_label.setWordWrap(True)
            row_layout.addWidget(hit_label)
            row_layout.addStretch()

            self.predicted_layout.insertWidget(idx - 1, row_widget)

        profit = total_fixed_prize - total_cost
        self.summary_label.setText(
            f"本期共 {len(tickets)} 注，总花费 {total_cost} 元 | "
            f"固定奖金合计 {total_fixed_prize} 元 | "
            f"浮动奖 {float_prize_count} 次 | "
            f"中奖 {hit_count} 次 | 盈亏 {profit:+d} 元"
        )
        self.summary_label.setVisible(True)

        # 持久化到 SQLite
        self._last_ticket_results = ticket_results
        self._save_single_backtest(
            actual, tickets_count=len(tickets), total_cost=total_cost,
            total_fixed_prize=total_fixed_prize, float_prize_count=float_prize_count,
            hit_count=hit_count, tickets=ticket_results,
        )

    def _save_single_backtest(
        self,
        actual,
        tickets_count: int,
        total_cost: int,
        total_fixed_prize: int,
        float_prize_count: int,
        hit_count: int,
        tickets: List[Dict[str, Any]],
    ) -> None:
        """保存本次单期回测结果到数据库."""
        try:
            options = self.strategy_panel.current_options()
            user_options = {k: v for k, v in options.items() if k != "history"}
            self._db.save_single(
                profile_key=self.profile.key,
                strategy_id=self.strategy_panel.current_strategy_id(),
                target_date=actual.draw_date.strftime("%Y-%m-%d"),
                issue=actual.issue or "",
                tickets_count=tickets_count,
                options=user_options,
                actual_groups={g.key: list(actual.groups.get(g.key, [])) for g in self.profile.groups},
                total_cost=total_cost,
                total_fixed_prize=total_fixed_prize,
                float_prize_count=float_prize_count,
                hit_count=hit_count,
                tickets=tickets,
            )
        except Exception as exc:  # noqa: BLE001
            # 保存失败不应影响主流程，仅记录日志
            import logging
            logging.getLogger(__name__).warning("保存单期回测结果失败: %s", exc)
