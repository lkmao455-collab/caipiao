"""批量历史回测对话框."""

from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, Qt
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
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...persistence.backtest_db import BacktestDatabase
from ...core.profile import LotteryProfile
from ...core.strategies.generic import needs_history
from ..batch_backtest_thread import BatchBacktestThread
from ..optimal_period_scan_thread import OptimalPeriodScanThread
from ..optimal_strategy_scan_thread import OptimalStrategyScanThread
from .strategy_panel import StrategyPanel


class BatchBacktestDialog(QDialog):
    """批量历史回测窗口."""

    def __init__(
        self,
        context,
        plugin_dir: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.profile: LotteryProfile = context.profile
        self.data_repository = context.data_repository
        self.plugin_dir = plugin_dir
        self._db = BacktestDatabase()
        self._thread: Optional[BatchBacktestThread] = None

        self.setWindowTitle(f"{self.profile.name}批量历史回测")
        self.resize(1100, 800)
        # 允许最大化，方便查看更多信息
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint
        )

        self._setup_ui()
        self._refresh_date_range()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "选择起始与结束日期，程序会对区间内每一期开奖，"
            "使用该日期之前的历史数据生成预测并统计中奖情况。"
            "ML 策略会自动为每个日期重新训练模型。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("起始日期:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        control_layout.addWidget(self.start_date_edit)

        control_layout.addWidget(QLabel("结束日期:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        control_layout.addWidget(self.end_date_edit)

        control_layout.addWidget(QLabel("每期注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(5)
        control_layout.addWidget(self.count_spin)

        self.run_btn = QPushButton("开始批量回测")
        self.run_btn.setToolTip("对日期区间逐期回测")
        self.run_btn.clicked.connect(self._run_batch_backtest)
        control_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("停止回测")
        self.stop_btn.setToolTip("停止当前正在进行的批量回测")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_batch_backtest)
        control_layout.addWidget(self.stop_btn)

        self.optimal_btn = QPushButton("一键找最优期数")
        self.optimal_btn.setToolTip(
            "自动扫描当前策略的“统计期数”或“使用历史记录期数”，"
            "找出固定奖金合计最高的参数值并应用"
        )
        self.optimal_btn.clicked.connect(self._run_optimal_period_scan)
        control_layout.addWidget(self.optimal_btn)

        self.strategy_scan_btn = QPushButton("一键找最优策略和参数")
        self.strategy_scan_btn.setToolTip(
            "自动扫描所有使用历史数据的策略及其期数参数，"
            "找出固定奖金合计最高的策略和参数并应用"
        )
        self.strategy_scan_btn.clicked.connect(self._run_optimal_strategy_scan)
        control_layout.addWidget(self.strategy_scan_btn)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        self.strategy_panel = StrategyPanel(self.context.engine)
        layout.addWidget(self.strategy_panel)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 中间状态与结果用 splitter 分隔，可自由调整高度
        splitter = QSplitter(Qt.Orientation.Vertical)

        status_group = QGroupBox("运行日志")
        status_layout = QVBoxLayout(status_group)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setPlaceholderText("点击“开始批量回测”后，此处会显示每期的处理过程...")
        status_layout.addWidget(self.status_text)
        splitter.addWidget(status_group)

        result_group = QGroupBox("回测汇总")
        result_layout = QVBoxLayout(result_group)

        self.summary_label = QLabel("尚未开始批量回测。")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "QLabel { color: #0A2540; background-color: #E3F2FD; "
            "border-radius: 4px; padding: 6px; font-size: 11pt; font-weight: bold; }"
        )
        result_layout.addWidget(self.summary_label)

        result_layout.addWidget(QLabel("详细结果（中奖记录，按日期追加）:"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        result_layout.addWidget(self.detail_text, 1)

        splitter.addWidget(result_group)
        splitter.setSizes([350, 450])
        layout.addWidget(splitter, 1)

    def _refresh_date_range(self) -> None:
        start, end = self.data_repository.get_date_range()
        if start is None or end is None:
            self.start_date_edit.setEnabled(False)
            self.end_date_edit.setEnabled(False)
            self.run_btn.setEnabled(False)
            return

        qstart = QDate(start.year, start.month, start.day)
        qend = QDate(end.year, end.month, end.day)
        for edit in (self.start_date_edit, self.end_date_edit):
            edit.setMinimumDate(qstart)
            edit.setMaximumDate(qend)

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
            for edit in (self.start_date_edit, self.end_date_edit):
                calendar = edit.calendarWidget()
                calendar.setDateTextFormat(qdate, highlight_format)

        records = self.data_repository.get_all()
        if len(records) >= 30:
            default_start = records[-30].draw_date
        else:
            default_start = start
        self.start_date_edit.setDate(
            QDate(default_start.year, default_start.month, default_start.day)
        )
        self.end_date_edit.setDate(qend)

    def _run_batch_backtest(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期")
            return

        start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day())

        strategy_id = self.strategy_panel.current_strategy_id()
        if not strategy_id:
            QMessageBox.warning(self, "提示", "请选择一个生成策略")
            return

        try:
            options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        if needs_history(strategy_id):
            records = self.data_repository.get_all()
            if len(records) < 100:
                QMessageBox.warning(
                    self, "数据不足", "ML/历史策略需要至少 100 期历史数据"
                )
                return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("批量回测中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.detail_text.clear()
        self.status_text.clear()
        self.summary_label.setText("正在批量回测，请稍候...")
        self._detail_lines: List[str] = []
        self._running_cost = 0
        self._running_fixed_prize = 0
        self._running_float_count = 0
        self._running_hit_count = 0
        self._running_first_hit_count = 0
        self._running_rounds = 0
        self._running_ticket_index_hits: Dict[int, int] = {}

        self._thread = BatchBacktestThread(
            engine=self.context.engine,
            strategy_id=strategy_id,
            profile=self.profile,
            data_repository=self.data_repository,
            start_date=start_date,
            end_date=end_date,
            tickets_per_round=self.count_spin.value(),
            options=options,
            plugin_dir=self.plugin_dir,
            parent=self,
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.status_message.connect(self._on_status_message)
        self._thread.round_ready.connect(self._on_round_ready)
        self._thread.result_ready.connect(
            self._on_finished, Qt.ConnectionType.QueuedConnection
        )
        self._thread.finished.connect(self._cleanup_finished_thread)
        self._thread.start()

    def _stop_batch_backtest(self) -> None:
        """请求停止批量回测线程."""
        if self._thread and self._thread.isRunning():
            self.status_text.append("用户请求停止批量回测，等待当前期处理完成...")
            self._thread.requestInterruption()
            self.stop_btn.setEnabled(False)
        if getattr(self, "_scan_thread", None) and self._scan_thread.isRunning():
            self.status_text.append("用户请求停止参数扫描...")
            self._scan_thread.requestInterruption()
            self.stop_btn.setEnabled(False)
        if getattr(self, "_strategy_scan_thread", None) and self._strategy_scan_thread.isRunning():
            self.status_text.append("用户请求停止策略扫描...")
            self._strategy_scan_thread.requestInterruption()
            self.stop_btn.setEnabled(False)

    def _run_optimal_period_scan(self) -> None:
        """启动一键找最优期数扫描."""
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期")
            return

        start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day())

        strategy_id = self.strategy_panel.current_strategy_id()
        if not strategy_id:
            QMessageBox.warning(self, "提示", "请选择一个生成策略")
            return

        from ...ui.optimal_period_config import resolve_optimal_param

        resolved = resolve_optimal_param(strategy_id)
        if resolved is None:
            QMessageBox.information(
                self,
                "不支持",
                "当前策略没有可一键优化的“使用期数”参数。",
            )
            return

        try:
            base_options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("扫描中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.detail_text.clear()
        self.status_text.clear()
        self.summary_label.setText("正在扫描最优参数，请稍候...")

        self._scan_thread = OptimalPeriodScanThread(
            engine=self.context.engine,
            strategy_id=strategy_id,
            profile=self.profile,
            data_repository=self.data_repository,
            start_date=start_date,
            end_date=end_date,
            tickets_per_round=self.count_spin.value(),
            base_options=base_options,
            plugin_dir=self.plugin_dir,
            parent=self,
        )
        self._scan_thread.progress.connect(self._on_progress)
        self._scan_thread.status_message.connect(self._on_status_message)
        self._scan_thread.result_ready.connect(
            self._on_optimal_finished, Qt.ConnectionType.QueuedConnection
        )
        self._scan_thread.finished.connect(self._cleanup_finished_scan_thread)
        self._scan_thread.start()

    def _cleanup_finished_scan_thread(self) -> None:
        """扫描线程 finished 信号的统一清理：清空引用并安全 deleteLater."""
        thread = self.sender()
        if thread is None:
            return
        if getattr(self, "_scan_thread", None) is thread:
            self._scan_thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    def _run_optimal_strategy_scan(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            QMessageBox.warning(self, "日期错误", "起始日期不能晚于结束日期")
            return

        start_date = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day())

        records = self.data_repository.get_all()
        if len(records) < 100:
            QMessageBox.warning(self, "数据不足", "候选策略需要至少 100 期历史数据")
            return

        try:
            base_options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self.run_btn.setEnabled(False)
        self.run_btn.setText("扫描中...")
        self.stop_btn.setEnabled(True)
        self.optimal_btn.setEnabled(False)
        self.strategy_scan_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.detail_text.clear()
        self.status_text.clear()
        self.summary_label.setText("正在扫描最优策略和参数，请稍候...")

        self._strategy_scan_thread = OptimalStrategyScanThread(
            engine=self.context.engine,
            profile=self.profile,
            data_repository=self.data_repository,
            start_date=start_date,
            end_date=end_date,
            tickets_per_round=self.count_spin.value(),
            base_options=base_options,
            plugin_dir=self.plugin_dir,
            parent=self,
        )
        self._strategy_scan_thread.progress.connect(self._on_progress)
        self._strategy_scan_thread.status_message.connect(self._on_status_message)
        self._strategy_scan_thread.result_ready.connect(
            self._on_strategy_scan_finished, Qt.ConnectionType.QueuedConnection
        )
        self._strategy_scan_thread.finished.connect(self._cleanup_finished_strategy_scan_thread)
        self._strategy_scan_thread.start()

    def _cleanup_finished_strategy_scan_thread(self) -> None:
        thread = self.sender()
        if thread is None:
            return
        if getattr(self, "_strategy_scan_thread", None) is thread:
            self._strategy_scan_thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    def _on_strategy_scan_finished(self, result, error) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始批量回测")
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
        self.progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "扫描失败", str(error))
            self.summary_label.setText("一键找最优策略和参数失败。")
            return

        if result is None:
            self.summary_label.setText(
                self.summary_label.text() + "\n（已停止）"
            )
            return

        # 自动将最优策略和参数写回策略面板
        self.strategy_panel.set_strategy_id(result.optimal_strategy_id)
        if result.param_name is not None and result.optimal_value is not None:
            self.strategy_panel.set_options({result.param_name: result.optimal_value})

        summary_lines = [
            f"最优策略：{result.optimal_strategy_name} ({result.optimal_strategy_id})",
        ]
        if result.param_name is not None:
            summary_lines.append(f"最优参数：{result.param_name} = {result.optimal_value}")
        summary_lines.extend([
            f"回测期数：{result.optimal_result.total_rounds} 期",
            f"总花费：{result.optimal_result.total_cost} 元",
            f"固定奖金合计：{result.optimal_result.total_fixed_prize} 元",
            f"中奖次数：{result.optimal_result.hit_count} 次",
            f"首注中奖次数：{result.optimal_result.first_ticket_hit_count} 次",
        ])
        if result.interrupted:
            summary_lines.append("（已中断，结果为部分扫描）")
        self.summary_label.setText("\n".join(summary_lines))

        # 排名规则与 OptimalStrategyScanThread._pick_best_strategy 保持一致：
        # 固定奖金降序 -> 中奖次数降序 -> 策略 id 升序
        ranked = sorted(
            result.all_results,
            key=lambda item: (
                -item[2].total_fixed_prize,
                -item[2].hit_count,
                item[0],
            ),
        )
        self.status_text.append("=" * 40)
        self.status_text.append("一键找最优策略和参数扫描结果：")
        for rank, (strategy_id, value, res) in enumerate(ranked, start=1):
            strategy = self.context.engine.get(strategy_id)
            name = strategy.metadata.name if strategy is not None else strategy_id
            failed_mark = "（失败）" if res.errors else ""
            param_text = f" 参数={value}" if value is not None else ""
            self.status_text.append(
                f"{rank}. {name} ({strategy_id}){param_text}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次, "
                f"首注 {res.first_ticket_hit_count} 次"
                f"{failed_mark}"
            )
        self.status_text.append("=" * 40)

    def _cleanup_finished_thread(self) -> None:
        """线程 finished 信号的统一清理：清空引用并安全 deleteLater."""
        thread = self.sender()
        if thread is None:
            return
        if thread is self._thread:
            self._thread = None
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)

    def _on_status_message(self, message: str) -> None:
        self.status_text.append(message)
        # 自动滚动到底部
        scrollbar = self.status_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _on_round_ready(
        self, current: int, total: int, winners: List[Dict[str, Any]]
    ) -> None:
        """每期结束后追加中奖详情，并更新实时汇总."""
        self._running_rounds += 1
        # 本期的花费在生成时已经确定：每期固定生成 tickets_per_round 注
        # 但 winners 只包含中奖注，所以成本要按整期累加
        self._running_cost += self.count_spin.value() * 2

        first_winner = next((w for w in winners if w.get("is_first")), None)
        if first_winner:
            self._running_first_hit_count += 1

        for item in winners:
            t_idx = item.get("ticket_index", 0)
            self._running_ticket_index_hits[t_idx] = self._running_ticket_index_hits.get(t_idx, 0) + 1

            date = item["date"]
            issue = item["issue"]
            ticket = item["ticket"]
            prize_name = item["prize_name"]
            prize_amount = item["prize_amount"]
            prize_text = (
                f"{prize_name}（浮动奖金）"
                if prize_amount is None
                else f"{prize_name} {prize_amount} 元"
            )
            prefix = "【首注】" if item.get("is_first") else ""
            line = f"{prefix}{date} 第 {issue} 期：{ticket.format_compact()} -> {prize_text}"
            self._detail_lines.append(line)
            self.detail_text.append(line)

            if prize_amount is None:
                self._running_float_count += 1
                self._running_hit_count += 1
            else:
                self._running_fixed_prize += prize_amount
                if prize_amount > 0:
                    self._running_hit_count += 1

        self._update_running_summary(current, total)

    def _update_running_summary(self, current: int, total: int) -> None:
        profit = self._running_fixed_prize - self._running_cost
        rounds = max(self._running_rounds, 1)
        first_hit_rate = self._running_first_hit_count / rounds * 100
        per_ticket_lines = []
        for i in range(self.count_spin.value()):
            count = self._running_ticket_index_hits.get(i, 0)
            rate = count / rounds * 100
            per_ticket_lines.append(f"第 {i + 1} 注：{count} 次（{rate:.1f}%）")

        self.summary_label.setText(
            f"正在回测：{current}/{total} 期\n"
            f"已花费：{self._running_cost} 元 | "
            f"固定奖金：{self._running_fixed_prize} 元 | "
            f"浮动奖：{self._running_float_count} 次 | "
            f"中奖：{self._running_hit_count} 次 | "
            f"首注中奖：{self._running_first_hit_count} 次（{first_hit_rate:.1f}%）\n"
            + " | ".join(per_ticket_lines)
            + f"\n盈亏：{profit:+d} 元"
        )

    def _on_finished(self, result, error) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始批量回测")
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
        self.progress.setVisible(False)

        # 线程清理由 finished 信号统一处理，这里不操作线程对象

        if error:
            QMessageBox.critical(self, "批量回测失败", str(error))
            self.summary_label.setText("批量回测失败。")
            return

        if result is None:
            # 用户手动停止，保留已回测的汇总结果
            self.summary_label.setText(
                self.summary_label.text() + "\n（已停止）"
            )
            return

        # 持久化批量回测汇总
        self._save_batch_backtest(result)

        profit = result.total_fixed_prize - result.total_cost
        first_rate = (
            result.first_ticket_hit_count / max(result.total_rounds, 1) * 100
        )
        per_ticket_lines = []
        for i in range(self.count_spin.value()):
            count = result.ticket_index_hits.get(i, 0)
            rate = count / max(result.total_rounds, 1) * 100
            per_ticket_lines.append(f"第 {i + 1} 注：{count} 次（{rate:.1f}%）")

        summary_lines = [
            f"回测期数：{result.total_rounds} 期",
            f"每期注数：{self.count_spin.value()} 注",
            f"总花费：{result.total_cost} 元",
            f"固定奖金合计：{result.total_fixed_prize} 元",
            f"中浮动奖次数：{result.float_prize_count} 次",
            f"总中奖次数：{result.hit_count} 次",
            f"首注中奖次数：{result.first_ticket_hit_count} 次（{first_rate:.1f}%）",
            "各注中奖次数：" + " | ".join(per_ticket_lines),
            f"盈亏：{profit:+d} 元",
        ]
        self.summary_label.setText("\n".join(summary_lines))

        if not self._detail_lines:
            self.detail_text.setText("没有中奖记录。")

    def _on_optimal_finished(self, result, error) -> None:
        """处理一键找最优期数扫描结果."""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始批量回测")
        self.stop_btn.setEnabled(False)
        self.optimal_btn.setEnabled(True)
        self.strategy_scan_btn.setEnabled(True)
        self.progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "扫描失败", str(error))
            self.summary_label.setText("一键找最优期数失败。")
            return

        if result is None:
            self.summary_label.setText(
                self.summary_label.text() + "\n（已停止）"
            )
            return

        # 自动将最优参数写回策略面板
        self.strategy_panel.set_options({result.param_name: result.optimal_value})

        summary_lines = [
            f"最优参数：{result.param_name} = {result.optimal_value}",
            f"回测期数：{result.optimal_result.total_rounds} 期",
            f"总花费：{result.optimal_result.total_cost} 元",
            f"固定奖金合计：{result.optimal_result.total_fixed_prize} 元",
            f"中奖次数：{result.optimal_result.hit_count} 次",
            f"首注中奖次数：{result.optimal_result.first_ticket_hit_count} 次",
        ]
        if result.interrupted:
            summary_lines.append("（已中断，结果为部分扫描）")
        self.summary_label.setText("\n".join(summary_lines))

        # 在日志区打印所有结果排名
        ranked = sorted(
            result.all_results,
            key=lambda item: (
                item[1].total_fixed_prize,
                item[1].hit_count,
                -item[0],
            ),
            reverse=True,
        )
        self.status_text.append("=" * 40)
        self.status_text.append("一键找最优期数扫描结果：")
        for rank, (value, res) in enumerate(ranked, start=1):
            failed_mark = "（失败）" if res.errors else ""
            self.status_text.append(
                f"{rank}. {result.param_name}={value}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次, "
                f"首注 {res.first_ticket_hit_count} 次"
                f"{failed_mark}"
            )
        self.status_text.append("=" * 40)

    def _save_batch_backtest(self, result) -> None:
        """保存批量回测汇总结果到数据库."""
        try:
            options = self.strategy_panel.current_options()
            user_options = {k: v for k, v in options.items() if k != "history"}
            self._db.save_batch(
                profile_key=self.profile.key,
                strategy_id=self.strategy_panel.current_strategy_id(),
                start_date=self.start_date_edit.date().toString("yyyy-MM-dd"),
                end_date=self.end_date_edit.date().toString("yyyy-MM-dd"),
                tickets_per_round=self.count_spin.value(),
                options=user_options,
                total_cost=result.total_cost,
                total_fixed_prize=result.total_fixed_prize,
                float_prize_count=result.float_prize_count,
                hit_count=result.hit_count,
                total_rounds=result.total_rounds,
                first_ticket_hit_count=result.first_ticket_hit_count,
                ticket_index_hits=result.ticket_index_hits,
            )
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("保存批量回测结果失败: %s", exc)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            if not self._thread.wait(5000):
                self._thread.terminate()
                self._thread.wait(1000)
        if getattr(self, "_scan_thread", None) and self._scan_thread.isRunning():
            self._scan_thread.requestInterruption()
            if not self._scan_thread.wait(5000):
                self._scan_thread.terminate()
                self._scan_thread.wait(1000)
        if getattr(self, "_strategy_scan_thread", None) and self._strategy_scan_thread.isRunning():
            self._strategy_scan_thread.requestInterruption()
            if not self._strategy_scan_thread.wait(5000):
                self._strategy_scan_thread.terminate()
                self._strategy_scan_thread.wait(1000)
        super().closeEvent(event)
