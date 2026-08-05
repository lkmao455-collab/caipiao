"""回测记录查询对话框.

用于调阅已持久化到 SQLite 的单期回测与批量回测结果。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.profile import get_profile
from ...persistence.backtest_db import BacktestDatabase


class BacktestHistoryDialog(QDialog):
    """回测历史记录查询窗口."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("回测记录")
        self.resize(1100, 750)
        self._db = BacktestDatabase()

        self._setup_ui()
        self._refresh_all()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "这里展示所有已保存的历史回测结果。\n"
            "选中表格中的某一行，可在下方查看该次回测的详细数据。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # 单期回测标签页
        self.single_tab = self._build_single_tab()
        self.tabs.addTab(self.single_tab, "单期回测")

        # 批量回测标签页
        self.batch_tab = self._build_batch_tab()
        self.tabs.addTab(self.batch_tab, "批量回测")

        # 底部详情
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("在上方表格中选择一行以查看详情...")
        layout.addWidget(self.detail_text, 1)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_all)
        btn_layout.addWidget(refresh_btn)

        delete_btn = QPushButton("删除选中")
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _build_single_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.single_table = QTableWidget()
        self.single_table.setColumnCount(10)
        self.single_table.setHorizontalHeaderLabels(
            ["ID", "时间", "彩种", "策略", "目标日期", "期号", "注数", "花费", "固定奖", "盈亏"]
        )
        self.single_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.single_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.single_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.single_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.single_table.setColumnWidth(0, 60)
        self.single_table.itemSelectionChanged.connect(self._on_single_selected)
        layout.addWidget(self.single_table)
        return widget

    def _build_batch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(11)
        self.batch_table.setHorizontalHeaderLabels(
            ["ID", "时间", "彩种", "策略", "起始日期", "结束日期", "期数", "花费", "固定奖", "中奖", "盈亏"]
        )
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.batch_table.setColumnWidth(0, 60)
        self.batch_table.itemSelectionChanged.connect(self._on_batch_selected)
        layout.addWidget(self.batch_table)
        return widget

    def _refresh_all(self) -> None:
        self._refresh_single()
        self._refresh_batch()
        self.detail_text.clear()

    def _refresh_single(self) -> None:
        records = self._db.list_single(limit=500)
        self.single_table.setRowCount(len(records))
        for row, r in enumerate(records):
            items = [
                QTableWidgetItem(str(r.id)),
                QTableWidgetItem(r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""),
                QTableWidgetItem(get_profile(r.profile_key).name),
                QTableWidgetItem(r.strategy_id),
                QTableWidgetItem(r.target_date),
                QTableWidgetItem(r.issue),
                QTableWidgetItem(str(r.tickets_count)),
                QTableWidgetItem(str(r.total_cost)),
                QTableWidgetItem(str(r.total_fixed_prize)),
                QTableWidgetItem(f"{r.profit:+d}"),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.single_table.setItem(row, col, item)

    def _refresh_batch(self) -> None:
        records = self._db.list_batch(limit=500)
        self.batch_table.setRowCount(len(records))
        for row, r in enumerate(records):
            items = [
                QTableWidgetItem(str(r.id)),
                QTableWidgetItem(r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""),
                QTableWidgetItem(get_profile(r.profile_key).name),
                QTableWidgetItem(r.strategy_id),
                QTableWidgetItem(r.start_date),
                QTableWidgetItem(r.end_date),
                QTableWidgetItem(str(r.total_rounds)),
                QTableWidgetItem(str(r.total_cost)),
                QTableWidgetItem(str(r.total_fixed_prize)),
                QTableWidgetItem(str(r.hit_count)),
                QTableWidgetItem(f"{r.profit:+d}"),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.batch_table.setItem(row, col, item)

    def _on_single_selected(self) -> None:
        row = self.single_table.currentRow()
        if row < 0:
            return
        item = self.single_table.item(row, 0)
        if item is None:
            return
        backtest_id = int(item.text())
        record = self._db.get_single(backtest_id)
        if record is None:
            return
        lines: list[str] = [
            f"ID: {record.id}",
            f"时间: {record.created_at}",
            f"彩种: {get_profile(record.profile_key).name} ({record.profile_key})",
            f"策略: {record.strategy_id}",
            f"目标日期: {record.target_date}  期号: {record.issue}",
            f"参数: {record.options}",
            f"真实开奖: {record.actual_groups}",
            (f"注数: {record.tickets_count}  花费: {record.total_cost}  固定奖: {record.total_fixed_prize}"
            f"  浮动奖: {record.float_prize_count}  中奖: {record.hit_count}  盈亏: {record.profit:+d}"),
            "",
            "投注明细:",
        ]
        for t in record.tickets:
            groups = json.loads(t["groups"])
            hits = json.loads(t["hits"])
            prize = t["prize_amount"]
            prize_text = f"{t['prize_name']}（浮动）" if prize is None else f"{t['prize_name']} {prize} 元"
            prefix = "【首注】" if t["is_first"] else ""
            lines.append(
                f"{prefix}第 {t['ticket_index'] + 1} 注: {groups}  命中: {hits}  -> {prize_text}"
            )
        self.detail_text.setPlainText("\n".join(lines))

    def _on_batch_selected(self) -> None:
        row = self.batch_table.currentRow()
        if row < 0:
            return
        item = self.batch_table.item(row, 0)
        if item is None:
            return
        backtest_id = int(item.text())
        record = self._db.get_batch(backtest_id)
        if record is None:
            return
        hit_lines = [
            f"第 {idx + 1} 注: {count} 次"
            for idx, count in sorted(record.ticket_index_hits.items())
        ]
        lines: list[str] = [
            f"ID: {record.id}",
            f"时间: {record.created_at}",
            f"彩种: {get_profile(record.profile_key).name} ({record.profile_key})",
            f"策略: {record.strategy_id}",
            f"日期区间: {record.start_date} ~ {record.end_date}",
            f"每期注数: {record.tickets_per_round}",
            f"参数: {record.options}",
            (f"总期数: {record.total_rounds}  总花费: {record.total_cost}"
            f"  固定奖: {record.total_fixed_prize}  浮动奖: {record.float_prize_count}"
            f"  中奖: {record.hit_count}  首注中奖: {record.first_ticket_hit_count}"),
            f"盈亏: {record.profit:+d} 元",
            "",
            "各注中奖次数:",
        ]
        lines.extend(hit_lines)
        self.detail_text.setPlainText("\n".join(lines))

    def _delete_selected(self) -> None:
        current_tab = self.tabs.currentWidget()
        if current_tab == self.single_tab:
            table = self.single_table
            delete_fn = self._db.delete_single
        else:
            table = self.batch_table
            delete_fn = self._db.delete_batch

        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条记录")
            return
        item = table.item(row, 0)
        if item is None:
            return
        backtest_id = int(item.text())
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除选中的回测记录（ID={backtest_id}）吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_fn(backtest_id)
            self._refresh_all()


import json
