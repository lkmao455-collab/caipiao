"""参数组保存对话框.

在「一键找最优策略和参数」扫描完成后，让用户选择前 N 个结果保存为参数组.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, Optional
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
from ...persistence.optimal_param_store import OptimalParamStore
from ...persistence.parameter_group_store import ParameterGroupStore
from ..optimal_strategy_scan_thread import StrategyScanResult


def _aggregate_hit_distribution(res, profile_key: str) -> str:
    """从 BatchBacktestResult 中汇总中奖号码分布."""
    hit_counter: Counter = Counter()
    for tr in res.ticket_results:
        hits = tr.get("hits", {})
        if profile_key == "ssq":
            key = f"红{hits.get('red', 0)}蓝{hits.get('blue', 0)}"
        elif profile_key == "3d":
            key = f"中{hits.get('pos', 0)}位"
        else:
            parts = [f"{k}{v}" for k, v in sorted(hits.items())]
            key = " ".join(parts) if parts else "无"
        hit_counter[key] += 1

    if not hit_counter:
        return ""
    # 按出现次数降序排列，取前5
    top = hit_counter.most_common(5)
    return ", ".join(f"{k}:{v}次" for k, v in top)


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
        optimal_param_store: Optional[OptimalParamStore] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("保存为参数组")
        self.resize(520, 420)
        self._scan_result = scan_result
        self._profile_key = profile_key
        self._store = store
        self._optimal_param_store = optimal_param_store or OptimalParamStore()
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
        """返回有效结果，按盈亏（收益）降序排列."""
        results = [r for r in self._scan_result.all_results if not r[2].errors]
        results.sort(key=lambda r: r[2].total_fixed_prize - r[2].total_cost, reverse=True)
        return results

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
            profit = res.total_fixed_prize - res.total_cost
            profit_str = f"+{profit}" if profit >= 0 else str(profit)
            dist = _aggregate_hit_distribution(res, self._profile_key)
            dist_text = f"\n    中奖分布: {dist}" if dist else ""
            lines.append(
                f"第{rank}名 {name} ({strategy_id}){param_text}: "
                f"奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次, "
                f"盈亏 {profit_str}"
                f"{dist_text}"
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

        def _float_cv(cv: Any, key: str, default: float = 0.0) -> float:
            if isinstance(cv, dict):
                val = cv.get(key, default)
                if isinstance(val, (int, float)):
                    return float(val)
            return default

        items = []
        for strategy_id, value, res in results:
            hit_dist = _aggregate_hit_distribution(res, self._profile_key)
            cv = self._scan_result.cv_results.get(strategy_id, {})

            # 优先使用扫描线程按策略记录的代表性参数名
            param_name = self._scan_result.param_names.get(strategy_id)
            if param_name is None and value is not None:
                param_name = self._scan_result.param_name

            metrics = {
                "total_fixed_prize": res.total_fixed_prize,
                "hit_count": res.hit_count,
                "total_rounds": res.total_rounds,
                "first_ticket_hit_count": res.first_ticket_hit_count,
                "total_cost": res.total_cost,
                "hit_distribution": hit_dist,
                "stability_score": _float_cv(cv, "stability_score"),
                "cv_mean_prize": _float_cv(cv, "mean_fixed_prize"),
                "cv_std_prize": _float_cv(cv, "std_fixed_prize"),
            }
            items.append(
                StrategyParameterItem(
                    strategy_id=strategy_id,
                    strategy_name=self._strategy_name_map.get(
                        strategy_id, strategy_id
                    ),
                    param_name=param_name if value is not None else None,
                    param_value=value,
                    enabled=True,
                    metrics=metrics,
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

        # 同步锁定保存的参数：仅锁定综合排名第一（overall best）的策略参数，
        # 其余策略仍保存到参数组但不自动锁定。
        best_params_map = getattr(self._scan_result, "best_params", {}) or {}
        already_locked = {
            (item.strategy_id, p.param_name): p.param_value
            for item in items
            for p in self._optimal_param_store.load(self._profile_key).locked
            if p.strategy_id == item.strategy_id
        }
        overall_best_item = items[0] if items else None
        params_to_lock = {}
        if overall_best_item is not None:
            best_params = best_params_map.get(overall_best_item.strategy_id, {})
            params_to_lock = dict(best_params) if best_params else {}
            # 若扫描结果未保存完整参数，回退到旧的代表参数
            if (
                not params_to_lock
                and overall_best_item.param_name is not None
                and overall_best_item.param_value is not None
            ):
                params_to_lock = {
                    overall_best_item.param_name: overall_best_item.param_value
                }

        if params_to_lock:
            lock_lines = [
                f"{param_name} = {param_value}"
                for param_name, param_value in params_to_lock.items()
            ]
            reply = QMessageBox.question(
                self,
                "锁定最优参数",
                f"是否将排名第一的策略「{overall_best_item.strategy_name}」的以下参数锁定，"
                f"以保证后续生成结果稳定？\n\n" + "\n".join(lock_lines),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                for param_name, param_value in params_to_lock.items():
                    # 若用户已锁定到相同值，则保留原锁定记录（不覆盖 source/locked_at）
                    if (
                        already_locked.get(
                            (overall_best_item.strategy_id, param_name)
                        )
                        == param_value
                    ):
                        continue
                    self._optimal_param_store.lock(
                        profile_key=self._profile_key,
                        strategy_id=overall_best_item.strategy_id,
                        param_name=param_name,
                        param_value=param_value,
                        source="scan",
                        stability_score=overall_best_item.metrics.get(
                            "stability_score", 0.0
                        ),
                        cv_mean_prize=overall_best_item.metrics.get(
                            "cv_mean_prize", 0.0
                        ),
                        cv_std_prize=overall_best_item.metrics.get(
                            "cv_std_prize", 0.0
                        ),
                    )

        self.group_saved.emit(group)
        QMessageBox.information(self, "保存成功", f"参数组「{name}」已保存")
        self.accept()
