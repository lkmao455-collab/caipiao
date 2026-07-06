"""主窗口参数组面板.

展示已保存的参数组，允许用户启用/禁用组内策略并生成号码.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.parameter_group import ParameterGroup, StrategyParameterItem
from ...persistence.parameter_group_store import ParameterGroupStore


class ParameterGroupPanel(QWidget):
    """参数组管理面板."""

    request_generate = Signal(list)  # List[StrategyParameterItem]

    def __init__(
        self,
        store: ParameterGroupStore,
        profile_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._profile_key = profile_key
        self._groups: List[ParameterGroup] = []
        self._item_checkboxes: dict[str, QCheckBox] = {}

        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 顶部：选择参数组
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("已保存参数组:"))
        self.group_list = QListWidget()
        self.group_list.setMaximumHeight(120)
        self.group_list.currentItemChanged.connect(self._on_group_changed)
        top_layout.addWidget(self.group_list, 1)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("重新加载当前彩种的参数组列表")
        self.refresh_btn.clicked.connect(self.refresh)
        top_layout.addWidget(self.refresh_btn)

        self.rename_btn = QPushButton("重命名")
        self.rename_btn.setToolTip("重命名选中的参数组")
        self.rename_btn.clicked.connect(self._on_rename)
        top_layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("删除")
        self.delete_btn.setToolTip("删除选中的参数组")
        self.delete_btn.clicked.connect(self._on_delete)
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)

        # 详情区
        self.detail_group = QGroupBox("参数组详情")
        self.detail_layout = QVBoxLayout(self.detail_group)
        self.detail_layout.addWidget(QLabel("请选择一个参数组"))
        layout.addWidget(self.detail_group)

        # 生成数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("每组生成注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(5)
        self.count_spin.setSuffix(" 注")
        self.count_spin.setToolTip("参数组中每个启用的策略都将生成这么多注")
        count_layout.addWidget(self.count_spin)
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.clicked.connect(self._select_none)
        self.generate_btn = QPushButton("使用参数组生成号码")
        self.generate_btn.setToolTip("根据当前参数组中勾选的策略生成号码")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.select_none_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.generate_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def set_profile_key(self, profile_key: str) -> None:
        """切换当前彩种时重新加载."""
        self._profile_key = profile_key
        self.refresh()

    def refresh(self) -> None:
        """刷新参数组列表，按总中奖金额降序排列."""
        self.group_list.clear()
        self._groups = self._store.load_all(self._profile_key)

        # 按总中奖金额降序排列
        def _group_total_prize(g):
            return sum(item.metrics.get("total_fixed_prize", 0) for item in g.items)
        self._groups.sort(key=_group_total_prize, reverse=True)

        for idx, g in enumerate(self._groups):
            total_prize = _group_total_prize(g)
            total_cost = sum(item.metrics.get("total_cost", 0) for item in g.items)
            profit = total_prize - total_cost
            profit_str = f"+{profit}" if profit >= 0 else str(profit)
            item_text = f"{idx + 1}. {g.name}  奖金{total_prize}元 盈亏{profit_str}"
            item = QListWidgetItem(item_text)
            item.setData(1, g.id)  # role 1 存储 group id
            self.group_list.addItem(item)
        self._clear_detail()

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.detail_layout.addWidget(QLabel("请选择一个参数组"))
        self._item_checkboxes.clear()

    def _on_group_changed(
        self, current: QListWidgetItem | None, _previous=None
    ) -> None:
        self._clear_detail()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return

        self.detail_layout.addWidget(QLabel(f"名称: {group.name}"))
        self.detail_layout.addWidget(QLabel(f"创建时间: {group.created_at}"))
        self.detail_layout.addWidget(QLabel("策略列表（按盈亏排序，勾选以启用）："))

        # 按盈亏降序排列
        sorted_items = sorted(
            group.items,
            key=lambda it: it.metrics.get("total_fixed_prize", 0) - it.metrics.get("total_cost", 0),
            reverse=True,
        )

        for idx, item in enumerate(sorted_items, start=1):
            param_text = ""
            if item.param_name is not None and item.param_value is not None:
                param_text = f"  [{item.param_name}={item.param_value}]"
            metrics = item.metrics
            prize = metrics.get("total_fixed_prize", 0)
            cost = metrics.get("total_cost", 0)
            hits = metrics.get("hit_count", 0)
            profit = prize - cost
            profit_str = f"+{profit}" if profit >= 0 else str(profit)
            hit_dist = metrics.get("hit_distribution", "")
            dist_text = f"\n    中奖分布: {hit_dist}" if hit_dist else ""
            metric_text = (
                f"奖金 {prize} 元, 中奖 {hits} 次, "
                f"盈亏 {profit_str}"
                f"{dist_text}"
            )
            checkbox = QCheckBox(
                f"{idx}. {item.strategy_name}{param_text} — {metric_text}"
            )
            checkbox.setChecked(item.enabled)
            self.detail_layout.addWidget(checkbox)
            self._item_checkboxes[item.strategy_id] = checkbox

    def _select_all(self) -> None:
        for cb in self._item_checkboxes.values():
            cb.setChecked(True)

    def _select_none(self) -> None:
        for cb in self._item_checkboxes.values():
            cb.setChecked(False)

    def _enabled_items(self) -> List[StrategyParameterItem]:
        current = self.group_list.currentItem()
        if current is None:
            return []
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return []
        return [
            item
            for item in group.items
            if self._item_checkboxes.get(item.strategy_id, QCheckBox()).isChecked()
        ]

    def _on_generate(self) -> None:
        items = self._enabled_items()
        if not items:
            QMessageBox.warning(self, "提示", "请至少启用一个策略")
            return
        self.request_generate.emit(items)

    def _on_rename(self) -> None:
        current = self.group_list.currentItem()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", text=group.name
        )
        if ok and new_name.strip():
            if self._store.rename(
                self._profile_key, group_id, new_name.strip()
            ):
                self.refresh()

    def _on_delete(self) -> None:
        current = self.group_list.currentItem()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除参数组「{group.name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(self._profile_key, group_id)
            self.refresh()
