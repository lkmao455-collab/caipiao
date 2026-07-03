"""开奖记录相邻期统计分析对话框.

功能：展示指定时间范围内的所有开奖记录，并按相邻两期统计：
- 红球相同个数（1-6 个）的次数与比例（互斥统计）
- 蓝球两期相同的次数与比例

当前仅支持双色球（红球 + 蓝球结构）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.profile import LotteryProfile
from ...data.models import DrawRecord
from ...data.repository import DrawRepository


@dataclass
class AdjacentStats:
    """相邻开奖记录统计结果."""

    total_pairs: int = 0
    red_same_counts: Dict[int, int] = field(default_factory=lambda: {i: 0 for i in range(0, 7)})
    blue_same_count: int = 0

    def red_same_ratio(self, n: int) -> float:
        return self.red_same_counts.get(n, 0) / max(self.total_pairs, 1) * 100

    def blue_same_ratio(self) -> float:
        return self.blue_same_count / max(self.total_pairs, 1) * 100


def _analyze_adjacent(records: List[DrawRecord]) -> Tuple[AdjacentStats, List[Optional[int]]]:
    """分析相邻记录的红球/蓝球重合情况.

    Returns:
        stats: 统计结果
        red_overlaps: 每条记录与上一期的红球交集数；第一条为 None
    """
    records = sorted(records, key=lambda r: r.draw_date)
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    red_overlaps: List[Optional[int]] = [None]
    blue_sames: List[Optional[bool]] = [None]

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        prev_reds = set(prev.groups.get("red", []))
        curr_reds = set(curr.groups.get("red", []))
        overlap = len(prev_reds & curr_reds)
        red_overlaps.append(overlap)
        if 0 <= overlap <= 6:
            stats.red_same_counts[overlap] += 1

        prev_blue = next(iter(prev.groups.get("blue", [])), None)
        curr_blue = next(iter(curr.groups.get("blue", [])), None)
        blue_same = prev_blue is not None and curr_blue is not None and prev_blue == curr_blue
        blue_sames.append(blue_same)
        if blue_same:
            stats.blue_same_count += 1

    return stats, red_overlaps, blue_sames


def _group_key(record: DrawRecord, mode: str) -> str:
    """根据分组模式返回该记录所属分组的 key."""
    d = record.draw_date
    if mode == "year":
        return f"{d.year}年"
    if mode == "quarter":
        quarter = (d.month - 1) // 3 + 1
        return f"{d.year}年第{quarter}季度"
    if mode == "month":
        return d.strftime("%Y年%m月")
    if mode == "week":
        return f"{d.year}年第{d.isocalendar()[1]:02d}周"
    return "全部"


class DrawAnalysisDialog(QDialog):
    """开奖记录相邻期统计分析窗口."""

    def __init__(
        self,
        context,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.profile: LotteryProfile = context.profile
        self.data_repository: DrawRepository = context.data_repository

        self.setWindowTitle(f"{self.profile.name}开奖记录分析")
        self.resize(1200, 800)
        self._setup_ui()
        self._refresh_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 顶部控制栏
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("分组方式:"))
        self.group_combo = QComboBox()
        self.group_combo.addItem("全部", "all")
        self.group_combo.addItem("按年", "year")
        self.group_combo.addItem("按季度", "quarter")
        self.group_combo.addItem("按月", "month")
        self.group_combo.addItem("按周", "week")
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        control_layout.addWidget(self.group_combo)

        control_layout.addWidget(QLabel("当前分组:"))
        self.current_group_label = QLabel("全部")
        self.current_group_label.setStyleSheet("font-weight: bold; color: #0A2540;")
        control_layout.addWidget(self.current_group_label)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        # 中间 splitter：左侧分组列表 + 右侧表格和统计
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧分组列表
        group_box = QGroupBox("分组")
        group_layout = QVBoxLayout(group_box)
        self.group_list = QTableWidget()
        self.group_list.setColumnCount(2)
        self.group_list.setHorizontalHeaderLabels(["分组", "期数"])
        self.group_list.horizontalHeader().setStretchLastSection(True)
        self.group_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_list.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_list.itemSelectionChanged.connect(self._on_group_selected)
        group_layout.addWidget(self.group_list)
        splitter.addWidget(group_box)

        # 右侧：表格 + 统计
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        table_box = QGroupBox("开奖记录")
        table_layout = QVBoxLayout(table_box)
        self.record_table = QTableWidget()
        self.record_table.setColumnCount(6)
        self.record_table.setHorizontalHeaderLabels(
            ["期号", "开奖日期", "红球", "蓝球", "与上期红球重复", "与上期蓝球相同"]
        )
        self.record_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.record_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.record_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.record_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.record_table)
        right_layout.addWidget(table_box, 2)

        stats_box = QGroupBox("相邻期统计")
        stats_layout = QVBoxLayout(stats_box)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet(
            "QLabel { color: #0A2540; background-color: #E8F5E9; "
            "border-radius: 4px; padding: 6px; font-size: 13px; }"
        )
        stats_layout.addWidget(self.stats_text)
        right_layout.addWidget(stats_box, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([250, 950])
        layout.addWidget(splitter, 1)

    def _refresh_data(self) -> None:
        self._records = self.data_repository.get_all()
        if not self._records:
            QMessageBox.information(self, "缺少数据", "当前没有开奖记录可供分析。")
            return

        if self.profile.key != "ssq":
            QMessageBox.information(
                self,
                "不支持",
                "相邻期红球/蓝球统计功能当前仅支持双色球。",
            )
            self.group_combo.setEnabled(False)
            self.record_table.setRowCount(0)
            self.stats_text.setText("该功能当前仅支持双色球。")
            return

        self._records.sort(key=lambda r: r.draw_date)
        self._rebuild_group_list()

    def _rebuild_group_list(self) -> None:
        mode = self.group_combo.currentData()
        groups: Dict[str, List[DrawRecord]] = {}
        for r in self._records:
            key = _group_key(r, mode)
            groups.setdefault(key, []).append(r)

        self._groups = dict(sorted(groups.items(), key=lambda x: x[0]))
        self.group_list.setRowCount(len(self._groups))
        for idx, (key, records) in enumerate(self._groups.items()):
            self.group_list.setItem(idx, 0, QTableWidgetItem(key))
            item = QTableWidgetItem(str(len(records)))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.group_list.setItem(idx, 1, item)

        if self.group_list.rowCount() > 0:
            self.group_list.selectRow(0)

    def _on_group_changed(self) -> None:
        self._rebuild_group_list()

    def _on_group_selected(self) -> None:
        selected = self.group_list.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        group_key = self.group_list.item(row, 0).text()
        self.current_group_label.setText(group_key)
        records = self._groups.get(group_key, [])
        self._show_records(records)

    def _show_records(self, records: List[DrawRecord]) -> None:
        stats, red_overlaps, blue_sames = _analyze_adjacent(records)

        self.record_table.setRowCount(len(records))
        for idx, record in enumerate(records):
            reds = record.groups.get("red", [])
            blue = next(iter(record.groups.get("blue", [])), None)

            self.record_table.setItem(idx, 0, QTableWidgetItem(record.issue))
            date_item = QTableWidgetItem(record.draw_date.strftime("%Y-%m-%d"))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 1, date_item)

            red_item = QTableWidgetItem(" ".join(f"{r:02d}" for r in sorted(reds)))
            red_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 2, red_item)

            blue_item = QTableWidgetItem(f"{blue:02d}" if blue is not None else "-")
            blue_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 3, blue_item)

            overlap = red_overlaps[idx]
            overlap_text = str(overlap) if overlap is not None else "-"
            overlap_item = QTableWidgetItem(overlap_text)
            overlap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 4, overlap_item)

            blue_same = blue_sames[idx]
            blue_same_text = "是" if blue_same else ("否" if blue_same is False else "-")
            blue_same_item = QTableWidgetItem(blue_same_text)
            blue_same_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 5, blue_same_item)

        self._show_stats(stats)

    def _show_stats(self, stats: AdjacentStats) -> None:
        lines = [
            f"相邻期对数：{stats.total_pairs}",
            "",
            "【红球相同个数统计】",
        ]
        for n in range(0, 7):
            count = stats.red_same_counts[n]
            ratio = stats.red_same_ratio(n)
            lines.append(f"  {n} 个相同：{count} 次（{ratio:.2f}%）")

        lines.append("")
        lines.append("【蓝球相同统计】")
        lines.append(
            f"  蓝球相同：{stats.blue_same_count} 次（{stats.blue_same_ratio():.2f}%）"
        )
        lines.append(
            f"  蓝球不同：{stats.total_pairs - stats.blue_same_count} 次"
            f"（{(stats.total_pairs - stats.blue_same_count) / max(stats.total_pairs, 1) * 100:.2f}%）"
        )

        self.stats_text.setText("\n".join(lines))
