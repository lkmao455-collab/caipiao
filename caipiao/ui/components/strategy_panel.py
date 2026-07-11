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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.engine import GenerationEngine
from ...core.strategy import GenerationStrategy
from ...persistence.optimal_param_store import OptimalParamStore
from ...persistence.settings import AppSettings
from ...utils.validators import parse_int_list


class StrategyPanel(QWidget):
    """策略选择面板，根据策略动态生成参数控件."""

    options_changed = Signal()
    recommend_requested = Signal(str)

    def __init__(
        self,
        engine: GenerationEngine,
        profile_key: str = "3d",
        store: OptimalParamStore | None = None,
        locked_params: list | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self._profile_key = profile_key
        self._store = store or OptimalParamStore()
        self._locked_params = locked_params or []
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

        # 免责声明
        self.disclaimer_label = QLabel(
            "注意：所有策略均基于历史数据统计，不保证中奖。彩票开奖是独立随机事件。"
        )
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setStyleSheet(
            "color: #d32f2f; padding: 4px; background: #fff3e0; border-radius: 4px;"
        )
        self.layout.addWidget(self.disclaimer_label)

        # 福彩3D 经验策略过滤：默认关闭，可在下方「经验策略参数」中开启

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

        # 福彩3D 经验策略参数
        self.filter_fc3d_group = QGroupBox("经验策略参数")
        filter_fc3d_layout = QFormLayout(self.filter_fc3d_group)
        filter_fc3d_layout.setSpacing(8)

        self.fc3d_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.fc3d_filter_enable_check.setChecked(self._settings.fc3d_filter_enabled)
        self.fc3d_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖号码逐位比较；\n"
            "只要与任一期相同的号码数超过允许上限，就放弃该号码。"
        )
        self.fc3d_filter_enable_check.stateChanged.connect(self._on_filter_fc3d_changed)
        filter_fc3d_layout.addRow(self.fc3d_filter_enable_check)

        self.fc3d_compare_spin = QSpinBox()
        self.fc3d_compare_spin.setRange(0, 50)
        self.fc3d_compare_spin.setMinimumWidth(60)
        self.fc3d_compare_spin.setValue(self._settings.fc3d_filter_compare_periods)
        self.fc3d_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.fc3d_compare_spin.valueChanged.connect(self._on_filter_fc3d_changed)
        filter_fc3d_layout.addRow("对比期数:", self.fc3d_compare_spin)

        self.fc3d_max_overlap_spin = QSpinBox()
        self.fc3d_max_overlap_spin.setRange(0, 3)
        self.fc3d_max_overlap_spin.setMinimumWidth(60)
        self.fc3d_max_overlap_spin.setValue(self._settings.fc3d_filter_max_overlap)
        self.fc3d_max_overlap_spin.setToolTip(
            "允许与某期开奖号码相同的号码最大个数。\n"
            "若新生成号码与任一期相同号码数多于该值，则放弃该号码。"
        )
        self.fc3d_max_overlap_spin.valueChanged.connect(self._on_filter_fc3d_changed)
        filter_fc3d_layout.addRow("允许相同号码数:", self.fc3d_max_overlap_spin)

        self.layout.addWidget(self.filter_fc3d_group)
        self.filter_fc3d_group.setVisible(False)

        # 参数区域
        self.options_group = QGroupBox("策略参数")
        self.options_layout = QFormLayout(self.options_group)
        self.options_layout.setSpacing(10)
        self.options_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.options_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.options_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.options_scroll.setWidget(self.options_group)
        self.layout.addWidget(self.options_scroll)

        # 恢复默认参数
        self.reset_defaults_btn = QPushButton("恢复默认参数")
        self.reset_defaults_btn.setToolTip("清除该策略的所有锁定参数")
        self.reset_defaults_btn.clicked.connect(self._on_reset_defaults)
        self.layout.addWidget(self.reset_defaults_btn)

        self.layout.addStretch()

    def _on_reset_defaults(self) -> None:
        strategy_id = self.current_strategy_id()
        if not strategy_id:
            return
        locked = self._store.get_locked(self._profile_key, strategy_id)
        for param_name in list(locked.keys()):
            self._store.unlock(self._profile_key, strategy_id, param_name)
        # 同步失效内存中的锁定参数缓存
        if self._locked_params:
            self._locked_params = [
                p for p in self._locked_params if p.strategy_id != strategy_id
            ]
        self._rebuild_options(self._current_strategy)

    def _on_recommend_parameters(self) -> None:
        if not self._current_strategy or not hasattr(
            self._current_strategy, "recommend_parameters"
        ):
            return
        self.recommend_requested.emit(self.current_strategy_id())

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
        # 仅SSQ策略显示过滤设置
        is_ssq = bool(strategy_id and not strategy_id.endswith("_3d")
                       and not any(strategy_id.endswith(f"_{s}") for s in ["qlc", "kl8", "dlt", "pl3", "pl5", "qxc", "gd36x7"]))
        self.filter_ssq_group.setVisible(is_ssq)
        # 仅福彩3D策略显示经验策略参数
        is_3d = bool(strategy_id and strategy_id.endswith("_3d"))
        self.filter_fc3d_group.setVisible(is_3d)
        self.options_changed.emit()

    def _on_filter_ssq_changed(self, _=None) -> None:
        """SSQ过滤参数变化时保存到 QSettings."""
        self._settings.ssq_filter_compare_periods = self.ssq_compare_spin.value()
        self._settings.ssq_filter_max_red_overlap = self.ssq_max_red_spin.value()
        self._settings.ssq_filter_block_blue = self.ssq_block_blue_check.isChecked()
        self._settings.sync()

    def _on_filter_fc3d_changed(self, _=None) -> None:
        """3D经验策略过滤参数变化时保存到 QSettings."""
        self._settings.fc3d_filter_enabled = self.fc3d_filter_enable_check.isChecked()
        self._settings.fc3d_filter_compare_periods = self.fc3d_compare_spin.value()
        self._settings.fc3d_filter_max_overlap = self.fc3d_max_overlap_spin.value()
        self._settings.sync()

    def _get_locked_for_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """读取某策略的锁定参数；优先使用内存缓存，缺失时回退到持久化存储."""
        locked: Dict[str, Any] = {}
        if self._locked_params:
            locked = {
                p.param_name: p.param_value
                for p in self._locked_params
                if p.strategy_id == strategy_id
            }
        if not locked:
            locked = self._store.get_locked(self._profile_key, strategy_id)
        return locked

    def _rebuild_options(self, strategy: GenerationStrategy | None) -> None:
        # 移除旧推荐按钮（如果存在）
        if hasattr(self, "_recommend_btn"):
            self._recommend_btn.deleteLater()
            delattr(self, "_recommend_btn")

        # 清空旧控件
        while self.options_layout.rowCount() > 0:
            self.options_layout.removeRow(0)
        self._option_widgets.clear()

        if strategy is None:
            self.options_group.setVisible(False)
            self.reset_defaults_btn.setVisible(False)
            return

        schema = strategy.get_config_schema()
        if not schema:
            self.options_group.setVisible(False)
            self.reset_defaults_btn.setVisible(False)
            return

        locked = self._get_locked_for_strategy(strategy.metadata.id)
        self.options_group.setVisible(True)
        self.reset_defaults_btn.setVisible(True)

        if hasattr(strategy, "recommend_parameters"):
            self._recommend_btn = QPushButton("一键推荐参数")
            self._recommend_btn.setToolTip("基于当前历史数据统计特征自动推荐参数")
            self._recommend_btn.clicked.connect(self._on_recommend_parameters)
            self.layout.insertWidget(4, self._recommend_btn)
            self._recommend_btn.setVisible(True)

        for key, meta in schema.items():
            locked_value = locked.get(key)
            effective_meta = meta
            if locked_value is not None:
                effective_meta = dict(meta)
                effective_meta["default"] = locked_value
            widget = self._create_option_widget(key, effective_meta)
            if widget:
                tooltip = meta.get("tooltip") or meta.get("description") or ""
                if tooltip:
                    widget.setToolTip(tooltip)
                label = QLabel(meta.get("label", key))
                label.setWordWrap(True)
                if tooltip:
                    label.setToolTip(tooltip)
                if key in locked:
                    widget.setEnabled(False)
                    row = QHBoxLayout()
                    row.addWidget(widget, 1)
                    lock_label = QLabel("[锁定]")
                    lock_label.setToolTip(
                        f"参数已锁定为 {locked[key]}，在「一键找最优」中不会被调整"
                    )
                    row.addWidget(lock_label)
                    self.options_layout.addRow(label, row)
                else:
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

    def set_profile_key(
        self, profile_key: str, locked_params: list | None = None
    ) -> None:
        """切换彩种时更新 profile_key 与锁定参数列表."""
        self._profile_key = profile_key
        if locked_params is not None:
            self._locked_params = locked_params

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
