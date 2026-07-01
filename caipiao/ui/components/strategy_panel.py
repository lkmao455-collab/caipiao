"""策略选择与参数配置面板."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Signal
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
from ...utils.validators import parse_int_list


class StrategyPanel(QWidget):
    """策略选择面板，根据策略动态生成参数控件."""

    options_changed = Signal()

    def __init__(self, engine: GenerationEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._current_strategy: GenerationStrategy | None = None
        self._option_widgets: Dict[str, Any] = {}

        self._setup_ui()
        self._refresh_strategies()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 策略选择
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("生成策略:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.setToolTip("选择号码生成策略。不同策略基于不同的概率统计思想。")
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        selector_layout.addWidget(self.strategy_combo, 1)
        self.layout.addLayout(selector_layout)

        # 策略描述
        self.description_label = QLabel("请选择生成策略")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #666;")
        self.layout.addWidget(self.description_label)

        # 参数区域
        self.options_group = QGroupBox("策略参数")
        self.options_layout = QFormLayout(self.options_group)
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
        self.options_changed.emit()

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
                if tooltip:
                    label.setToolTip(tooltip)
                self.options_layout.addRow(label, widget)

    def _create_option_widget(self, key: str, meta: Dict[str, Any]):
        type_ = meta.get("type", "string")
        default = meta.get("default")

        if type_ == "int":
            spin = QSpinBox()
            spin.setRange(meta.get("min", -999999), meta.get("max", 999999))
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
