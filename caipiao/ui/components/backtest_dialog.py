"""历史回测对话框.

选择一个已经开奖的历史日期，使用策略基于该日期之前的数据生成预测号码，
并与真实开奖结果对比。
"""

from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt, QDate, QThread
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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...persistence.backtest_db import BacktestDatabase
from ...persistence.settings import AppSettings
from ...core.profile import LotteryProfile
from ...core.prize import calculate_prize
from ...core.strategies import needs_history
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
        self.resize(1200, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self._setup_ui()
        self._refresh_date_range()
        self._restore_last_settings()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        # 顶部控制栏（保留原有控件）
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

        control_layout.addSpacing(20)
        control_layout.addWidget(QLabel("过滤回测:"))
        control_layout.addWidget(QLabel("重合上限:"))
        self.filter_threshold_spin = QSpinBox()
        self.filter_threshold_spin.setRange(0, 10)
        self.filter_threshold_spin.setValue(2)
        self.filter_threshold_spin.setToolTip("号码重合数超过此阈值则被过滤")
        control_layout.addWidget(self.filter_threshold_spin)

        control_layout.addWidget(QLabel("比较期数:"))
        self.filter_periods_spin = QSpinBox()
        self.filter_periods_spin.setRange(1, 50)
        self.filter_periods_spin.setValue(7)
        self.filter_periods_spin.setToolTip("与最近N期开奖记录比较")
        control_layout.addWidget(self.filter_periods_spin)

        self.filter_backtest_btn = QPushButton("过滤回测")
        self.filter_backtest_btn.setToolTip("测试多期历史数据：用过滤规则筛选号码，检查是否能中奖")
        self.filter_backtest_btn.clicked.connect(self._run_filter_backtest)
        self.filter_backtest_btn.setAutoDefault(False)
        control_layout.addWidget(self.filter_backtest_btn)

        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # 中间 splitter：左侧策略面板 + 右侧回测结果
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)

        # 左侧：策略面板
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("策略选择"))
        self.strategy_panel = StrategyPanel(self.context.engine)
        left_layout.addWidget(self.strategy_panel)
        splitter.addWidget(left_widget)

        # 右侧：进度 + 回测结果
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        right_layout.addWidget(self.progress)

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

        right_layout.addWidget(self.result_group, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 900])  # 左侧300，右侧900

        main_layout.addWidget(splitter, 1)

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

    def _run_filter_backtest(self) -> None:
        """过滤回测：用过滤规则筛选号码，购买所有有效号码，检查是否中奖."""
        from math import comb

        threshold = self.filter_threshold_spin.value()
        compare_periods = self.filter_periods_spin.value()

        # 获取选中的回测日期
        target_qdate = self.date_edit.date()
        target_date = datetime(target_qdate.year(), target_qdate.month(), target_qdate.day())
        actual = self.data_repository.get_record_by_date(target_date)
        if actual is None:
            QMessageBox.warning(self, "无开奖记录", "选中的日期没有官方开奖数据，请重新选择。")
            return

        # 获取目标日期之前的历史记录
        history = self.data_repository.get_records_before(target_date)
        if len(history) < compare_periods:
            QMessageBox.warning(self, "数据不足", f"该日期之前只有 {len(history)} 期数据，需要至少 {compare_periods} 期")
            return

        self.filter_backtest_btn.setEnabled(False)
        self.filter_backtest_btn.setText("计算中...")
        self.progress.setVisible(True)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        profile = self.profile
        recent = history[-compare_periods:]  # 最近N期作为过滤参考

        if profile.key in ("3d", "pl3"):
            # 福彩3D/排列3
            # 生成所有220种组合
            all_combos = set()
            for a in range(10):
                for b in range(a+1, 10):
                    for c in range(b+1, 10):
                        all_combos.add((a, b, c))
            for a in range(10):
                for b in range(10):
                    if a != b:
                        all_combos.add((a, a, b))
            for a in range(10):
                all_combos.add((a, a, a))

            # 生成所有1000个数字
            all_numbers = set()
            for a in range(10):
                for b in range(10):
                    for c in range(10):
                        all_numbers.add((a, b, c))

            # 过滤：与最近N期比较，同位相同数 > threshold 则过滤
            filtered_numbers = set()
            for num in all_numbers:
                for record in recent:
                    hist_nums = record.groups.get("pos", [])
                    if len(hist_nums) == 3:
                        same_count = sum(1 for x, y in zip(num, hist_nums) if x == y)
                        if same_count > threshold:
                            filtered_numbers.add(num)
                            break

            # 转换为组合（被过滤的）
            filtered_combos = set()
            for num in filtered_numbers:
                sorted_num = tuple(sorted(num))
                filtered_combos.add(sorted_num)

            # 有效组合 = 总组合220 - 被过滤的组合
            total_combos = 220
            valid_count = total_combos - len(filtered_combos)
            total_cost = valid_count * 2  # 每注2元

            # 检查开奖号码是否在有效组合中（即没有被过滤）
            target_nums = actual.groups.get("pos", [])
            target_sorted = tuple(sorted(target_nums))
            is_win = target_sorted not in filtered_combos  # 不在过滤列表中就是有效

            # 计算奖金（如果中奖）
            prize = 0
            prize_name = "未中奖"
            if is_win:
                # 福彩3D中奖规则
                if target_nums[0] == target_nums[1] == target_nums[2]:
                    # 豹子号
                    prize = 1000
                    prize_name = "豹子号"
                elif target_nums[0] == target_nums[1] or target_nums[1] == target_nums[2] or target_nums[0] == target_nums[2]:
                    # 组选3
                    prize = 346
                    prize_name = "组选3"
                else:
                    # 组选6
                    prize = 173
                    prize_name = "组选6"

            profit = prize - total_cost if is_win else -total_cost

            # 生成报告
            lines = []
            lines.append("═" * 60)
            lines.append("  过滤回测结果")
            lines.append("═" * 60)
            lines.append("")
            lines.append(f"  回测日期: {actual.issue} ({target_date.strftime('%Y-%m-%d')})")
            lines.append(f"  开奖号码: {target_nums}")
            lines.append("")
            lines.append(f"  过滤参数: 重合上限={threshold}, 比较期数={compare_periods}")
            lines.append(f"  参考期数: {len(recent)} 期 ({recent[0].issue} ~ {recent[-1].issue})")
            lines.append("")
            lines.append(f"  过滤后有效号码: {valid_count} 个")
            lines.append(f"  购买花费: {total_cost} 元 (每注2元)")
            lines.append("")
            if is_win:
                lines.append(f"  中奖结果: ✓ 中奖!")
                lines.append(f"  中奖类型: {prize_name}")
                lines.append(f"  中奖奖金: {prize} 元")
                lines.append(f"  净收益: {profit:+d} 元")
            else:
                lines.append(f"  中奖结果: ✗ 未中奖")
                lines.append(f"  净亏损: {profit} 元")
            lines.append("")
            lines.append("═" * 60)

            # 显示被过滤的号码（每行8个，逗号分隔）
            lines.append("")
            lines.append("  被过滤的号码 (%d个):" % len(filtered_combos))
            filtered_list = sorted(filtered_combos)
            for i in range(0, len(filtered_list), 8):
                chunk = filtered_list[i:i+8]
                nums_str = ", ".join("%d%d%d" % n for n in chunk)
                lines.append("    " + nums_str)

        elif profile.key == "ssq":
            # 双色球（简化版）
            target_reds = set(actual.groups.get("red", []))
            target_blue = next(iter(actual.groups.get("blue", [])), None)

            # 估算有效号码比例
            filtered_pairs = 0
            total_pairs = 0
            for j in range(len(recent)):
                for k in range(j):
                    base_reds = set(recent[k].groups.get("red", []))
                    curr_reds = set(recent[j].groups.get("red", []))
                    overlap = len(base_reds & curr_reds)
                    total_pairs += 1
                    if overlap > threshold:
                        filtered_pairs += 1

            filter_pct = filtered_pairs / max(total_pairs, 1)
            total_ssq = comb(33, 6) * 16
            valid_count = int(total_ssq * (1 - filter_pct))
            total_cost = min(valid_count, 10000) * 2

            # 检查目标红球是否与历史有太多重合
            is_filtered = False
            for record in recent:
                hist_reds = set(record.groups.get("red", []))
                overlap = len(target_reds & hist_reds)
                if overlap > threshold:
                    is_filtered = True
                    break

            is_win = not is_filtered
            profit = 0
            if is_win:
                # 简化：假设中了三等奖
                profit = 3000 - total_cost

            lines = []
            lines.append("═" * 60)
            lines.append("  过滤回测结果")
            lines.append("═" * 60)
            lines.append("")
            lines.append(f"  回测日期: {actual.issue} ({target_date.strftime('%Y-%m-%d')})")
            lines.append(f"  开奖号码: 红{sorted(target_reds)} 蓝{target_blue}")
            lines.append("")
            lines.append(f"  过滤参数: 重合上限={threshold}, 比较期数={compare_periods}")
            lines.append(f"  参考期数: {len(recent)} 期")
            lines.append("")
            lines.append(f"  过滤后有效号码: 约 {valid_count:,} 个")
            lines.append(f"  购买花费: {total_cost:,} 元 (每注2元)")
            lines.append("")
            if is_win:
                lines.append(f"  中奖结果: ✓ 号码在有效范围内!")
            else:
                lines.append(f"  中奖结果: ✗ 号码被过滤掉了")
            lines.append("")
            lines.append("═" * 60)

        elif profile.key == "kl8":
            # 快乐8：从1-80选20个号码
            # 优化过滤：降低阈值 + 高频过滤
            target_nums = set(actual.groups.get("main", []))

            # 1. 统计每个号码在近期出现的频率
            num_freq = {}
            for record in recent:
                for num in record.groups.get("main", []):
                    num_freq[num] = num_freq.get(num, 0) + 1

            # 高频号码：在超过50%的近期出现（快乐8号码分散，用50%更实用）
            hot_threshold = len(recent) * 0.5
            hot_numbers = set(num for num, freq in num_freq.items() if freq >= hot_threshold)

            # 2. 计算重合过滤比例
            filtered_pairs = 0
            total_pairs = 0
            for j in range(len(recent)):
                for k in range(j):
                    base_nums = set(recent[k].groups.get("main", []))
                    curr_nums = set(recent[j].groups.get("main", []))
                    overlap = len(base_nums & curr_nums)
                    total_pairs += 1
                    if overlap > threshold:
                        filtered_pairs += 1

            overlap_filter_pct = filtered_pairs / max(total_pairs, 1)

            # 3. 高频过滤比例：假设选中高频号码的概率
            # 如果有N个高频号码，选20个号包含至少1个高频号的概率
            hot_count = len(hot_numbers)
            if hot_count > 0:
                # P(不含高频号) = C(80-hot_count, 20) / C(80, 20)
                from math import comb
                if hot_count <= 60:  # 避免计算溢出
                    p_no_hot = comb(80 - hot_count, 20) / comb(80, 20)
                    hot_filter_pct = 1 - p_no_hot
                else:
                    hot_filter_pct = 0.99  # 极端情况
            else:
                hot_filter_pct = 0.0

            # 综合过滤比例（取较大值）
            filter_pct = max(overlap_filter_pct, hot_filter_pct)

            from math import comb
            total_kl8 = comb(80, 20)
            valid_count = int(total_kl8 * (1 - filter_pct))
            total_cost = min(valid_count, 50000) * 2

            # 检查目标号码是否被过滤
            is_filtered = False
            # 检查重合过滤
            for record in recent:
                hist_nums = set(record.groups.get("main", []))
                overlap = len(target_nums & hist_nums)
                if overlap > threshold:
                    is_filtered = True
                    break
            # 检查高频过滤
            if not is_filtered and hot_numbers:
                target_hot = target_nums & hot_numbers
                if len(target_hot) >= 2:  # 包含2个以上高频号则过滤
                    is_filtered = True

            is_win = not is_filtered
            profit = 0
            if is_win:
                profit = 100 - total_cost

            lines = []
            lines.append("═" * 60)
            lines.append("  过滤回测结果")
            lines.append("═" * 60)
            lines.append("")
            lines.append(f"  回测日期: {actual.issue} ({target_date.strftime('%Y-%m-%d')})")
            lines.append(f"  开奖号码: {sorted(target_nums)}")
            lines.append("")
            lines.append(f"  过滤参数: 重合上限={threshold}, 比较期数={compare_periods}")
            lines.append(f"  参考期数: {len(recent)} 期")
            lines.append("")
            lines.append(f"  高频号码: {sorted(hot_numbers) if hot_numbers else '无'}")
            lines.append(f"  重合过滤比例: {overlap_filter_pct*100:.1f}%")
            lines.append(f"  高频过滤比例: {hot_filter_pct*100:.1f}%")
            lines.append(f"  综合过滤比例: {filter_pct*100:.1f}%")
            lines.append("")
            lines.append(f"  过滤后有效号码: 约 {valid_count:,} 个")
            lines.append(f"  购买花费: {total_cost:,} 元 (每注2元)")
            lines.append("")
            if is_win:
                lines.append(f"  中奖结果: ✓ 号码在有效范围内!")
            else:
                lines.append(f"  中奖结果: ✗ 号码被过滤掉了")
            lines.append("")
            lines.append("═" * 60)

        else:
            QMessageBox.information(self, "提示", "暂不支持该彩种的过滤回测")
            self.filter_backtest_btn.setEnabled(True)
            self.filter_backtest_btn.setText("过滤回测")
            self.progress.setVisible(False)
            return

        self.filter_backtest_btn.setEnabled(True)
        self.filter_backtest_btn.setText("过滤回测")
        self.progress.setVisible(False)

        # 显示结果
        while self.predicted_layout.count() > 1:
            item = self.predicted_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        result_text = QLabel("\n".join(lines))
        result_text.setStyleSheet(
            "QLabel { color: #0A2540; background-color: #E8F5E9; "
            "border-radius: 4px; padding: 10px; font-size: 10pt; }"
        )
        result_text.setWordWrap(True)
        self.predicted_layout.insertWidget(0, result_text)

        self.summary_label.setText(
            f"过滤回测: 有效号码{valid_count}个, 花费{total_cost}元, "
            f"{'中奖!' if is_win else '未中奖'}"
        )
        self.summary_label.setVisible(True)

        # 显示真实开奖号码
        self._show_actual(actual)

        # 显示在结果区域
        while self.predicted_layout.count() > 1:
            item = self.predicted_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        result_text = QLabel("\n".join(lines))
        result_text.setStyleSheet(
            "QLabel { color: #0A2540; background-color: #E8F5E9; "
            "border-radius: 4px; padding: 10px; font-size: 10pt; }"
        )
        result_text.setWordWrap(True)
        self.predicted_layout.insertWidget(0, result_text)

        self.summary_label.setText(
            f"过滤回测: 有效号码{valid_count}个, 花费{total_cost}元, "
            f"{'中奖! 奖金%d元' % prize if is_win else '未中奖, 亏损%d元' % total_cost}"
        )
        self.summary_label.setVisible(True)
