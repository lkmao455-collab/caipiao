"""开奖记录相邻期统计分析对话框.

支持彩种：
- 双色球：相邻期红球/蓝球重合统计
- 福彩3D：相邻期按位数字相同个数统计
- 七乐彩：相邻期基本号/特别号重合统计
- 快乐8：相邻期主号码重合个数统计

每种彩种根据自身的 NumberGroup 结构计算相邻期号码重叠情况。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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

from ...core.profile import LotteryProfile, NumberGroup
from ...data.models import DrawRecord
from ...data.repository import DrawRepository


# --------------------------------------------------------------------------- #
# 统计抽象
# --------------------------------------------------------------------------- #
@dataclass
class GroupOverlapStats:
    """单个号码组的相邻期统计结果."""

    group_name: str = ""
    total_pairs: int = 0
    # 相同个数 -> 次数
    same_counts: Dict[int, int] = field(default_factory=dict)

    def same_ratio(self, n: int) -> float:
        return self.same_counts.get(n, 0) / max(self.total_pairs, 1) * 100


@dataclass
class AdjacentStats:
    """相邻开奖记录统计结果.

    Attributes:
        total_pairs: 相邻期对数
        group_stats: 每个分析号码组的统计（按组 key）
    """

    total_pairs: int = 0
    group_stats: Dict[str, GroupOverlapStats] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 分析器
# --------------------------------------------------------------------------- #
def _analyze_adjacent_ssq(records: List[DrawRecord]) -> Tuple[AdjacentStats, List[Dict[str, Any]]]:
    """双色球：红球 0-6 个相同，蓝球是否相同。"""
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    stats.group_stats["red"] = GroupOverlapStats(group_name="红球", total_pairs=stats.total_pairs,
                                                  same_counts={i: 0 for i in range(0, 7)})
    stats.group_stats["blue"] = GroupOverlapStats(group_name="蓝球", total_pairs=stats.total_pairs)
    blue_same_count = 0

    details: List[Dict[str, Any]] = []
    if not records:
        return stats, details

    records = sorted(records, key=lambda r: r.draw_date)
    details.append({"red": None, "blue": None})

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        prev_reds = set(prev.groups.get("red", []))
        curr_reds = set(curr.groups.get("red", []))
        red_overlap = len(prev_reds & curr_reds)
        stats.group_stats["red"].same_counts[red_overlap] += 1

        prev_blue = next(iter(prev.groups.get("blue", [])), None)
        curr_blue = next(iter(curr.groups.get("blue", [])), None)
        blue_same = prev_blue is not None and curr_blue is not None and prev_blue == curr_blue
        if blue_same:
            blue_same_count += 1

        details.append({"red": red_overlap, "blue": blue_same})

    stats.group_stats["blue"].same_counts[1] = blue_same_count
    stats.group_stats["blue"].same_counts[0] = stats.total_pairs - blue_same_count
    return stats, details


def _analyze_adjacent_positional(records: List[DrawRecord], group: NumberGroup) -> Tuple[AdjacentStats, List[Dict[str, Any]]]:
    """按位数字彩种（福彩3D/排列3/排列5/7星彩）：统计每位相同个数。"""
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    stats.group_stats[group.key] = GroupOverlapStats(
        group_name=group.name,
        total_pairs=stats.total_pairs,
        same_counts={i: 0 for i in range(0, group.count + 1)},
    )
    details: List[Dict[str, Any]] = []
    if not records:
        return stats, details

    records = sorted(records, key=lambda r: r.draw_date)
    details.append({group.key: None})

    for i in range(1, len(records)):
        prev = records[i - 1].groups.get(group.key, [])
        curr = records[i].groups.get(group.key, [])
        same = sum(1 for a, b in zip(prev, curr) if a == b)
        stats.group_stats[group.key].same_counts[same] += 1
        details.append({group.key: same})

    return stats, details


def _analyze_adjacent_basic_special(records: List[DrawRecord], basic_group: NumberGroup,
                                    special_group: NumberGroup) -> Tuple[AdjacentStats, List[Dict[str, Any]]]:
    """基本号+特别号彩种（七乐彩/广东36选7）：基本号 0-N 个相同，特别号是否相同。"""
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    stats.group_stats["basic"] = GroupOverlapStats(
        group_name=basic_group.name,
        total_pairs=stats.total_pairs,
        same_counts={i: 0 for i in range(0, basic_group.count + 1)},
    )
    stats.group_stats["special"] = GroupOverlapStats(
        group_name=special_group.name,
        total_pairs=stats.total_pairs,
    )
    special_same_count = 0

    details: List[Dict[str, Any]] = []
    if not records:
        return stats, details

    records = sorted(records, key=lambda r: r.draw_date)
    details.append({"basic": None, "special": None})

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        prev_basic = set(prev.groups.get(basic_group.key, []))
        curr_basic = set(curr.groups.get(basic_group.key, []))
        basic_overlap = len(prev_basic & curr_basic)
        stats.group_stats["basic"].same_counts[basic_overlap] += 1

        prev_special = next(iter(prev.groups.get(special_group.key, [])), None)
        curr_special = next(iter(curr.groups.get(special_group.key, [])), None)
        special_same = (
            prev_special is not None
            and curr_special is not None
            and prev_special == curr_special
        )
        if special_same:
            special_same_count += 1

        details.append({"basic": basic_overlap, "special": special_same})

    stats.group_stats["special"].same_counts[1] = special_same_count
    stats.group_stats["special"].same_counts[0] = stats.total_pairs - special_same_count
    return stats, details


def _analyze_adjacent_main(records: List[DrawRecord], group: NumberGroup) -> Tuple[AdjacentStats, List[Dict[str, Any]]]:
    """快乐8：开奖 20 个号码，统计相邻期相同号码个数分布。"""
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    # 主号码相邻期重复个数的统计桶：0-20
    stats.group_stats[group.key] = GroupOverlapStats(
        group_name=group.name,
        total_pairs=stats.total_pairs,
        same_counts={i: 0 for i in range(0, group.count + 1)},
    )
    details: List[Dict[str, Any]] = []
    if not records:
        return stats, details

    records = sorted(records, key=lambda r: r.draw_date)
    details.append({group.key: None})

    for i in range(1, len(records)):
        prev = set(records[i - 1].groups.get(group.key, []))
        curr = set(records[i].groups.get(group.key, []))
        overlap = len(prev & curr)
        stats.group_stats[group.key].same_counts[overlap] += 1
        details.append({group.key: overlap})

    return stats, details


def _analyze_adjacent(records: List[DrawRecord], profile: LotteryProfile) -> Tuple[AdjacentStats, List[Dict[str, Any]]]:
    """根据彩种档案选择对应的相邻期分析器."""
    if profile.key == "ssq":
        return _analyze_adjacent_ssq(records)

    if profile.key in ("3d", "pl3", "pl5", "qxc"):
        group = profile.primary_group
        return _analyze_adjacent_positional(records, group)

    if profile.key in ("qlc", "gd36x7"):
        basic = profile.group("basic")
        special = profile.group("special")
        return _analyze_adjacent_basic_special(records, basic, special)

    if profile.key == "kl8":
        group = profile.primary_group
        return _analyze_adjacent_main(records, group)

    # 未知彩种退化为通用：分析所有 pick_groups
    stats = AdjacentStats(total_pairs=max(0, len(records) - 1))
    details: List[Dict[str, Any]] = []
    if not records:
        return stats, details

    records = sorted(records, key=lambda r: r.draw_date)
    for idx, g in enumerate(profile.pick_groups):
        stats.group_stats[g.key] = GroupOverlapStats(
            group_name=g.name,
            total_pairs=stats.total_pairs,
            same_counts={i: 0 for i in range(0, g.count + 1)},
        )
    details.append({g.key: None for g in profile.pick_groups})

    for i in range(1, len(records)):
        detail: Dict[str, Any] = {}
        for g in profile.pick_groups:
            if g.positional:
                prev = records[i - 1].groups.get(g.key, [])
                curr = records[i].groups.get(g.key, [])
                overlap = sum(1 for a, b in zip(prev, curr) if a == b)
            else:
                prev = set(records[i - 1].groups.get(g.key, []))
                curr = set(records[i].groups.get(g.key, []))
                overlap = len(prev & curr)
            stats.group_stats[g.key].same_counts[overlap] += 1
            detail[g.key] = overlap
        details.append(detail)

    return stats, details


# --------------------------------------------------------------------------- #
# 分组工具
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
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
        # 列：期号、日期、各号码组显示列、各组与上期重叠列
        self._build_table_columns()
        table_layout.addWidget(self.record_table)
        right_layout.addWidget(table_box, 2)

        stats_box = QGroupBox("相邻期统计")
        stats_layout = QVBoxLayout(stats_box)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet(
            "QTextEdit { color: #0A2540; background-color: #E8F5E9; "
            "border-radius: 4px; padding: 6px; font-size: 10pt; }"
        )
        stats_layout.addWidget(self.stats_text)
        right_layout.addWidget(stats_box, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([250, 950])
        layout.addWidget(splitter, 1)

    # ----------------------------------------------------------------------- #
    # 按彩种定制的列配置
    # ----------------------------------------------------------------------- #
    def _build_table_columns(self) -> None:
        """根据当前彩种构建表格列标题与列伸缩策略."""
        headers = ["期号", "开奖日期"]
        stretch_cols: List[int] = []

        if self.profile.key == "ssq":
            headers.extend(["红球", "蓝球", "与上期红球重复", "与上期蓝球相同"])
            stretch_cols = [2]
        elif self.profile.key in ("3d", "pl3", "pl5", "qxc"):
            group = self.profile.primary_group
            headers.append(group.name)
            headers.append(f"与上期{group.name}同位相同")
            stretch_cols = [2]
        elif self.profile.key in ("qlc", "gd36x7"):
            headers.extend(["基本号", "特别号", "与上期基本号重复", "与上期特别号相同"])
            stretch_cols = [2]
        elif self.profile.key == "kl8":
            group = self.profile.primary_group
            headers.extend([group.name, f"与上期{group.name}重复"])
            stretch_cols = [2]
        else:
            for g in self.profile.pick_groups:
                headers.append(g.name)
                headers.append(f"与上期{g.name}重复")
            stretch_cols = list(range(2, 2 + len(self.profile.pick_groups) * 2, 2))

        self.record_table.setColumnCount(len(headers))
        self.record_table.setHorizontalHeaderLabels(headers)
        for c in range(len(headers)):
            if c in stretch_cols:
                self.record_table.horizontalHeader().setSectionResizeMode(
                    c, QHeaderView.ResizeMode.Stretch
                )
            else:
                self.record_table.horizontalHeader().setSectionResizeMode(
                    c, QHeaderView.ResizeMode.ResizeToContents
                )

    def _format_group(self, record: DrawRecord, group: NumberGroup) -> str:
        """格式化一组号码用于表格显示."""
        nums = record.groups.get(group.key, [])
        if group.positional:
            return " ".join(f"{n:0{group.pad}d}" for n in nums)
        return " ".join(f"{n:0{group.pad}d}" for n in sorted(nums))

    def _refresh_data(self) -> None:
        self._records = self.data_repository.get_all()
        if not self._records:
            QMessageBox.information(self, "缺少数据", "当前没有开奖记录可供分析。")
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

    # ----------------------------------------------------------------------- #
    # 按彩种定制的数据显示
    # ----------------------------------------------------------------------- #
    def _show_records(self, records: List[DrawRecord]) -> None:
        stats, details = _analyze_adjacent(records, self.profile)

        self.record_table.setRowCount(len(records))
        for idx, record in enumerate(records):
            self.record_table.setItem(idx, 0, QTableWidgetItem(record.issue))
            date_item = QTableWidgetItem(record.draw_date.strftime("%Y-%m-%d"))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, 1, date_item)

            detail = details[idx] if idx < len(details) else {}

            if self.profile.key == "ssq":
                self._fill_ssq_row(idx, record, detail)
            elif self.profile.key in ("3d", "pl3", "pl5", "qxc"):
                self._fill_positional_row(idx, record, detail)
            elif self.profile.key in ("qlc", "gd36x7"):
                self._fill_basic_special_row(idx, record, detail)
            elif self.profile.key == "kl8":
                self._fill_kl8_row(idx, record, detail)
            else:
                self._fill_generic_row(idx, record, detail)

        self._show_stats(stats)

    def _fill_ssq_row(self, idx: int, record: DrawRecord, detail: Dict[str, Any]) -> None:
        reds = record.groups.get("red", [])
        blue = next(iter(record.groups.get("blue", [])), None)

        red_item = QTableWidgetItem(" ".join(f"{r:02d}" for r in sorted(reds)))
        red_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 2, red_item)

        blue_item = QTableWidgetItem(f"{blue:02d}" if blue is not None else "-")
        blue_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 3, blue_item)

        red_overlap = detail.get("red")
        overlap_text = str(red_overlap) if red_overlap is not None else "-"
        overlap_item = QTableWidgetItem(overlap_text)
        overlap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 4, overlap_item)

        blue_same = detail.get("blue")
        blue_same_text = "是" if blue_same else ("否" if blue_same is False else "-")
        blue_same_item = QTableWidgetItem(blue_same_text)
        blue_same_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 5, blue_same_item)

    def _fill_positional_row(self, idx: int, record: DrawRecord, detail: Dict[str, Any]) -> None:
        group = self.profile.primary_group
        nums_item = QTableWidgetItem(self._format_group(record, group))
        nums_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 2, nums_item)

        same = detail.get(group.key)
        same_text = str(same) if same is not None else "-"
        same_item = QTableWidgetItem(same_text)
        same_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 3, same_item)

    def _fill_basic_special_row(self, idx: int, record: DrawRecord, detail: Dict[str, Any]) -> None:
        basic = self.profile.group("basic")
        special = self.profile.group("special")

        basic_item = QTableWidgetItem(self._format_group(record, basic))
        basic_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 2, basic_item)

        special_num = next(iter(record.groups.get(special.key, [])), None)
        special_item = QTableWidgetItem(
            f"{special_num:02d}" if special_num is not None else "-"
        )
        special_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 3, special_item)

        basic_overlap = detail.get("basic")
        basic_text = str(basic_overlap) if basic_overlap is not None else "-"
        basic_overlap_item = QTableWidgetItem(basic_text)
        basic_overlap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 4, basic_overlap_item)

        special_same = detail.get("special")
        special_text = "是" if special_same else ("否" if special_same is False else "-")
        special_same_item = QTableWidgetItem(special_text)
        special_same_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 5, special_same_item)

    def _fill_kl8_row(self, idx: int, record: DrawRecord, detail: Dict[str, Any]) -> None:
        group = self.profile.primary_group

        nums_item = QTableWidgetItem(self._format_group(record, group))
        nums_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 2, nums_item)

        overlap = detail.get(group.key)
        overlap_text = str(overlap) if overlap is not None else "-"
        overlap_item = QTableWidgetItem(overlap_text)
        overlap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_table.setItem(idx, 3, overlap_item)

    def _fill_generic_row(self, idx: int, record: DrawRecord, detail: Dict[str, Any]) -> None:
        col = 2
        for g in self.profile.pick_groups:
            nums_item = QTableWidgetItem(self._format_group(record, g))
            nums_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, col, nums_item)
            col += 1

            overlap = detail.get(g.key)
            overlap_text = str(overlap) if overlap is not None else "-"
            overlap_item = QTableWidgetItem(overlap_text)
            overlap_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.record_table.setItem(idx, col, overlap_item)
            col += 1

    def _show_stats(self, stats: AdjacentStats) -> None:
        lines = [f"相邻期对数：{stats.total_pairs}"]
        for key in stats.group_stats:
            gstat = stats.group_stats[key]
            lines.append("")
            lines.append(f"【{gstat.group_name}相同统计】")
            if self.profile.key in ("ssq", "qlc", "gd36x7") and key in ("blue", "special"):
                # 二值统计
                same = gstat.same_counts.get(1, 0)
                diff = gstat.same_counts.get(0, 0)
                lines.append(f"  相同：{same} 次（{gstat.same_ratio(1):.2f}%）")
                lines.append(f"  不同：{diff} 次（{gstat.same_ratio(0):.2f}%）")
            else:
                max_n = max(gstat.same_counts.keys()) if gstat.same_counts else 0
                for n in range(0, max_n + 1):
                    count = gstat.same_counts.get(n, 0)
                    ratio = gstat.same_ratio(n)
                    lines.append(f"  {n} 个相同：{count} 次（{ratio:.2f}%）")

        self.stats_text.setText("\n".join(lines))
