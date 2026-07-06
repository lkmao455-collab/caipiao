"""策略选择与参数配置面板."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.engine import GenerationEngine
from ...core.strategy import GenerationStrategy
from ...persistence.settings import AppSettings
from ...utils.validators import parse_int_list


class StrategyPanel(QWidget):
    """策略选择面板，根据策略动态生成参数控件."""

    options_changed = Signal()

    def __init__(self, engine: GenerationEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._settings = AppSettings()
        self._current_strategy: GenerationStrategy | None = None
        self._option_widgets: Dict[str, Any] = {}

        self._setup_ui()
        self._refresh_strategies()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)

        # 策略选择
        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(8)
        selector_layout.addWidget(QLabel("生成策略:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.setToolTip("选择号码生成策略。不同策略基于不同的概率统计思想。")
        self.strategy_combo.setMinimumWidth(160)
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        selector_layout.addWidget(self.strategy_combo, 1)
        self.layout.addLayout(selector_layout)

        # 策略描述
        self.description_label = QLabel("请选择生成策略")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(
            "color: #666; padding: 4px; background: #f9f9f9; border-radius: 4px;"
        )
        self.layout.addWidget(self.description_label)

        # 福彩3D 过滤参数
        self.filter_3d_group = QGroupBox("福彩3D 过滤")
        filter_3d_layout = QFormLayout(self.filter_3d_group)
        filter_3d_layout.setSpacing(8)

        self.compare_periods_spin = QSpinBox()
        self.compare_periods_spin.setRange(0, 50)
        self.compare_periods_spin.setMinimumWidth(60)
        self.compare_periods_spin.setValue(self._settings.fc3d_filter_compare_periods)
        self.compare_periods_spin.setToolTip("向前比较的历史开奖期数（0=不过滤）")
        self.compare_periods_spin.valueChanged.connect(self._on_filter_3d_changed)
        filter_3d_layout.addRow("对比期数:", self.compare_periods_spin)

        self.max_matches_spin = QSpinBox()
        self.max_matches_spin.setRange(0, 3)
        self.max_matches_spin.setMinimumWidth(60)
        self.max_matches_spin.setValue(self._settings.fc3d_filter_max_matches)
        self.max_matches_spin.setToolTip("允许与历史开奖号码相同的数字个数（含重复，如717与677有两个7相同则为2）")
        self.max_matches_spin.valueChanged.connect(self._on_filter_3d_changed)
        filter_3d_layout.addRow("允许相同位数:", self.max_matches_spin)

        self.layout.addWidget(self.filter_3d_group)
        self.filter_3d_group.setVisible(False)

        # 双色球过滤参数
        self.filter_ssq_group = QGroupBox("双色球 过滤")
        filter_ssq_layout = QFormLayout(self.filter_ssq_group)
        filter_ssq_layout.setSpacing(8)

        self.ssq_compare_spin = QSpinBox()
        self.ssq_compare_spin.setRange(0, 50)
        self.ssq_compare_spin.setMinimumWidth(60)
        self.ssq_compare_spin.setValue(self._settings.ssq_filter_compare_periods)
        self.ssq_compare_spin.setToolTip("向前比较的历史开奖期数（0=不过滤）")
        self.ssq_compare_spin.valueChanged.connect(self._on_filter_ssq_changed)
        filter_ssq_layout.addRow("对比期数:", self.ssq_compare_spin)

        self.ssq_max_red_spin = QSpinBox()
        self.ssq_max_red_spin.setRange(0, 6)
        self.ssq_max_red_spin.setMinimumWidth(60)
        self.ssq_max_red_spin.setValue(self._settings.ssq_filter_max_red_overlap)
        self.ssq_max_red_spin.setToolTip("允许与历史开奖号码重合的红球最大个数（0=完全不允许重合）")
        self.ssq_max_red_spin.valueChanged.connect(self._on_filter_ssq_changed)
        filter_ssq_layout.addRow("红球重合上限:", self.ssq_max_red_spin)

        self.ssq_block_blue_check = QCheckBox("禁止蓝球与历史相同")
        self.ssq_block_blue_check.setChecked(self._settings.ssq_filter_block_blue)
        self.ssq_block_blue_check.stateChanged.connect(self._on_filter_ssq_changed)
        filter_ssq_layout.addRow(self.ssq_block_blue_check)

        self.ssq_blue_periods_spin = QSpinBox()
        self.ssq_blue_periods_spin.setRange(1, 50)
        self.ssq_blue_periods_spin.setMinimumWidth(60)
        self.ssq_blue_periods_spin.setValue(self._settings.ssq_filter_compare_periods)
        self.ssq_blue_periods_spin.setToolTip("禁止蓝球重复的对比期数（仅在勾选上方复选框时生效）")
        self.ssq_blue_periods_spin.valueChanged.connect(self._on_filter_ssq_changed)
        filter_ssq_layout.addRow("蓝球对比期数:", self.ssq_blue_periods_spin)

        self.layout.addWidget(self.filter_ssq_group)
        self.filter_ssq_group.setVisible(False)

        # 参数区域
        self.options_group = QGroupBox("策略参数")
        self.options_layout = QFormLayout(self.options_group)
        self.options_layout.setSpacing(10)
        self.options_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.options_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.options_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.layout.addWidget(self.options_group)

        self.layout.addStretch()

    def _refresh_strategies(self) -> None:
        self.strategy_combo.clear()
        for strategy in self.engine.list_strategies():
            self.strategy_combo.addItem(strategy.metadata.name, strategy.metadata.id)
        if self.strategy_combo.count() > 0:
            self._on_strategy_changed(0)

    def _on_strategy_changed(self, index: int) -> None:
        strategy_id = self.strategy_combo.itemData(index)
        strategy = self.engine.get(strategy_id) if strategy_id else None
        self._current_strategy = strategy
        self._rebuild_options(strategy)
        if strategy:
            self.description_label.setText(
                f"{strategy.metadata.description}\n版本: {strategy.metadata.version}"
            )
        else:
            self.description_label.setText("请选择生成策略")
        # 仅3D策略显示过滤设置
        is_3d = bool(strategy_id and strategy_id.endswith("_3d"))
        self.filter_3d_group.setVisible(is_3d)
        # 仅SSQ策略显示过滤设置
        is_ssq = bool(strategy_id and not strategy_id.endswith("_3d")
                       and not any(strategy_id.endswith(f"_{s}") for s in ["qlc", "kl8", "dlt", "pl3", "pl5", "qxc", "gd36x7"]))
        self.filter_ssq_group.setVisible(is_ssq)
        self.options_changed.emit()

    def _on_filter_3d_changed(self, _=None) -> None:
        """3D过滤参数变化时保存到 QSettings."""
        self._settings.fc3d_filter_compare_periods = self.compare_periods_spin.value()
        self._settings.fc3d_filter_max_matches = self.max_matches_spin.value()
        self._settings.sync()

    def _on_filter_ssq_changed(self, _=None) -> None:
        """SSQ过滤参数变化时保存到 QSettings."""
        self._settings.ssq_filter_compare_periods = self.ssq_compare_spin.value()
        self._settings.ssq_filter_max_red_overlap = self.ssq_max_red_spin.value()
        self._settings.ssq_filter_block_blue = self.ssq_block_blue_check.isChecked()
        self._settings.sync()

    def _rebuild_options(self, strategy: GenerationStrategy | None) -> None:
        # 清空旧控件
        while self.options_layout.rowCount() > 0:
            self.options_layout.removeRow(0)
        self._option_widgets.clear()

        if strategy is None:
            self.options_group.setVisible(False)
            return

        schema = strategy.get_config_schema()
        if not schema:
            self.options_group.setVisible(False)
            return

        self.options_group.setVisible(True)
        for key, meta in schema.items():
            widget = self._create_option_widget(key, meta)
            if widget:
                tooltip = meta.get("tooltip") or meta.get("description") or ""
                if tooltip:
                    widget.setToolTip(tooltip)
                label = QLabel(meta.get("label", key))
                label.setWordWrap(True)
                if tooltip:
                    label.setToolTip(tooltip)
                self.options_layout.addRow(label, widget)

    def _create_option_widget(self, key: str, meta: Dict[str, Any]):
        type_ = meta.get("type", "string")
        default = meta.get("default")

        if type_ == "int":
            spin = QSpinBox()
            spin.setRange(meta.get("min", -999999), meta.get("max", 999999))
            spin.setMinimumWidth(80)
            if default is not None:
                spin.setValue(int(default))
            else:
                spin.setSpecialValueText("随机")
                spin.setValue(spin.minimum())
            spin.valueChanged.connect(self._on_option_changed)
            self._option_widgets[key] = spin
            return spin

        if type_ == "choice":
            combo = QComboBox()
            combo.setMinimumWidth(120)
            for choice in meta.get("choices", []):
                combo.addItem(str(choice), choice)
            if default is not None:
                idx = combo.findData(default)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(self._on_option_changed)
            self._option_widgets[key] = combo
            return combo

        if type_ in ("list_int", "history"):
            edit = QLineEdit()
            edit.setMinimumWidth(120)
            if isinstance(default, list):
                edit.setText(", ".join(str(v) for v in default))
            edit.textChanged.connect(self._on_option_changed)
            self._option_widgets[key] = edit
            return edit

        if type_ == "bool":
            check = QCheckBox()
            check.setChecked(bool(default))
            check.stateChanged.connect(self._on_option_changed)
            self._option_widgets[key] = check
            return check

        # 默认字符串
        edit = QLineEdit()
        edit.setMinimumWidth(120)
        if default is not None:
            edit.setText(str(default))
        edit.textChanged.connect(self._on_option_changed)
        self._option_widgets[key] = edit
        return edit

    def _on_option_changed(self, _=None) -> None:
        """参数变化时发射无参信号。"""
        self.options_changed.emit()

    def current_strategy_id(self) -> str:
        return self.strategy_combo.currentData() or ""

    def set_strategy_id(self, strategy_id: str) -> None:
        idx = self.strategy_combo.findData(strategy_id)
        if idx >= 0:
            self.strategy_combo.setCurrentIndex(idx)

    def set_options(self, options: Dict[str, Any]) -> None:
        """根据当前策略的 schema 恢复参数值."""
        if not self._current_strategy or not options:
            return
        schema = self._current_strategy.get_config_schema()
        for key, value in options.items():
            if key not in schema:
                continue
            widget = self._option_widgets.get(key)
            if widget is None:
                continue
            meta = schema[key]
            type_ = meta.get("type", "string")
            try:
                if type_ == "int":
                    if value is None:
                        widget.setValue(widget.minimum())
                    else:
                        widget.setValue(int(value))
                elif type_ == "choice":
                    idx = widget.findData(value)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                elif type_ == "bool":
                    widget.setChecked(bool(value))
                elif type_ in ("list_int", "history"):
                    if isinstance(value, list):
                        widget.setText(", ".join(str(v) for v in value))
                    else:
                        widget.setText(str(value) if value is not None else "")
                else:
                    widget.setText(str(value) if value is not None else "")
            except Exception:  # noqa: BLE001
                continue

    def current_options(self) -> Dict[str, Any]:
        """读取当前参数值."""
        options: Dict[str, Any] = {}
        schema = (
            self._current_strategy.get_config_schema()
            if self._current_strategy
            else {}
        )
        for key, meta in (schema or {}).items():
            widget = self._option_widgets.get(key)
            if widget is None:
                continue
            type_ = meta.get("type", "string")
            if type_ == "int":
                value = widget.value()
                if value == widget.minimum() and meta.get("default") is None:
                    value = None
                options[key] = value
            elif type_ == "choice":
                options[key] = widget.currentData()
            elif type_ == "bool":
                options[key] = widget.isChecked()
            elif type_ in ("list_int", "history"):
                text = widget.text()
                min_val = meta.get("min", 1)
                max_val = meta.get("max", 99)
                try:
                    options[key] = parse_int_list(text, min_val, max_val)
                except ValueError as exc:
                    raise ValueError(f"{meta.get('label', key)} 格式错误: {exc}") from exc
            else:
                options[key] = widget.text()
        return options
