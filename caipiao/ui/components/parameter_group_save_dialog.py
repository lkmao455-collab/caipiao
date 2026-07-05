"""参数组保存对话框.

在「一键找最优策略和参数」扫描完成后，让用户选择前 N 个结果保存为参数组.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from ...core.parameter_group import ParameterGroup, StrategyParameterItem
from ...persistence.parameter_group_store import ParameterGroupStore
from ..optimal_strategy_scan_thread import StrategyScanResult


class ParameterGroupSaveDialog(QDialog):
    """保存扫描结果为参数组的对话框."""

    group_saved = Signal(object)  # ParameterGroup

    def __init__(
        self,
        scan_result: StrategyScanResult,
        profile_key: str,
        store: ParameterGroupStore,
        strategy_name_map: Optional[Dict[str, str]] = None,
        start_date: str = "",
        end_date: str = "",
        tickets_per_round: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("保存为参数组")
        self.resize(520, 420)
        self._scan_result = scan_result
        self._profile_key = profile_key
        self._store = store
        self._strategy_name_map = strategy_name_map or {}
        self._start_date = start_date
        self._end_date = end_date
        self._tickets_per_round = tickets_per_round

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "将「一键找最优策略和参数」的排名结果保存为参数组，"
            "方便日后在主窗口「参数组」标签页中快速生成号码。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setText(self._auto_name())
        form.addRow("参数组名称:", self.name_edit)

        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 10)
        eligible = self._eligible_results()
        self.top_n_spin.setValue(min(3, len(eligible)) if eligible else 1)
        self.top_n_spin.valueChanged.connect(self._update_preview)
        form.addRow("取前几名:", self.top_n_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("即将保存的策略:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)
        layout.addWidget(self.preview_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _eligible_results(self):
        return [r for r in self._scan_result.all_results if not r[2].errors]

    def _auto_name(self) -> str:
        count = len(self._eligible_results())
        return f"最优组_{datetime.now().strftime('%Y-%m-%d')}_前{count}策略"

    def _update_preview(self) -> None:
        top_n = self.top_n_spin.value()
        results = self._eligible_results()[:top_n]
        lines = []
        for rank, (strategy_id, value, res) in enumerate(results, start=1):
            name = self._strategy_name_map.get(strategy_id, strategy_id)
            param_text = f" 参数={value}" if value is not None else ""
            lines.append(
                f"{rank}. {name} ({strategy_id}){param_text}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次"
            )
        self.preview_text.setText("\n".join(lines))

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "名称错误", "请输入参数组名称")
            return

        top_n = self.top_n_spin.value()
        results = self._eligible_results()[:top_n]
        if not results:
            QMessageBox.warning(self, "无可用结果", "没有可保存的非失败策略")
            return

        items = []
        for strategy_id, value, res in results:
            items.append(
                StrategyParameterItem(
                    strategy_id=strategy_id,
                    strategy_name=self._strategy_name_map.get(
                        strategy_id, strategy_id
                    ),
                    param_name=self._scan_result.param_name
                    if value is not None
                    else None,
                    param_value=value,
                    enabled=True,
                    metrics={
                        "total_fixed_prize": res.total_fixed_prize,
                        "hit_count": res.hit_count,
                        "total_rounds": res.total_rounds,
                        "first_ticket_hit_count": res.first_ticket_hit_count,
                        "total_cost": res.total_cost,
                    },
                )
            )

        group = ParameterGroup(
            id=str(uuid4()),
            name=name,
            profile_key=self._profile_key,
            created_at=datetime.now().isoformat(),
            scan_context={
                "start_date": self._start_date,
                "end_date": self._end_date,
                "tickets_per_round": self._tickets_per_round,
                "generated_from_scan": True,
            },
            items=items,
        )

        self._store.save(group)
        self.group_saved.emit(group)
        QMessageBox.information(self, "保存成功", f"参数组「{name}」已保存")
        self.accept()
