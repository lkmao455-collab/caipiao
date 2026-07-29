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

        self.fc3d_min_sum_spin = QSpinBox()
        self.fc3d_min_sum_spin.setRange(0, 27)
        self.fc3d_min_sum_spin.setMinimumWidth(60)
        self.fc3d_min_sum_spin.setValue(self._settings.fc3d_filter_min_sum)
        self.fc3d_min_sum_spin.setToolTip(
            "三位数字之和的下限，小于该值的号码将被过滤（0=不限制）。"
        )
        self.fc3d_min_sum_spin.valueChanged.connect(self._on_filter_fc3d_changed)
        filter_fc3d_layout.addRow("最小和值:", self.fc3d_min_sum_spin)

        self.fc3d_max_sum_spin = QSpinBox()
        self.fc3d_max_sum_spin.setRange(0, 27)
        self.fc3d_max_sum_spin.setMinimumWidth(60)
        self.fc3d_max_sum_spin.setValue(self._settings.fc3d_filter_max_sum)
        self.fc3d_max_sum_spin.setToolTip(
            "三位数字之和的上限，大于该值的号码将被过滤（27=不限制）。"
        )
        self.fc3d_max_sum_spin.valueChanged.connect(self._on_filter_fc3d_changed)
        filter_fc3d_layout.addRow("最大和值:", self.fc3d_max_sum_spin)

        self.layout.addWidget(self.filter_fc3d_group)
        self.filter_fc3d_group.setVisible(False)

        # 七乐彩 经验策略参数（参照福彩3D）
        self.filter_qlc_group = QGroupBox("经验策略参数")
        filter_qlc_layout = QFormLayout(self.filter_qlc_group)
        filter_qlc_layout.setSpacing(8)

        self.qlc_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.qlc_filter_enable_check.setChecked(self._settings.qlc_filter_enabled)
        self.qlc_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖基本号比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.qlc_filter_enable_check.stateChanged.connect(self._on_filter_qlc_changed)
        filter_qlc_layout.addRow(self.qlc_filter_enable_check)

        self.qlc_compare_spin = QSpinBox()
        self.qlc_compare_spin.setRange(0, 50)
        self.qlc_compare_spin.setMinimumWidth(60)
        self.qlc_compare_spin.setValue(self._settings.qlc_filter_compare_periods)
        self.qlc_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.qlc_compare_spin.valueChanged.connect(self._on_filter_qlc_changed)
        filter_qlc_layout.addRow("对比期数:", self.qlc_compare_spin)

        self.qlc_max_overlap_spin = QSpinBox()
        self.qlc_max_overlap_spin.setRange(0, 7)
        self.qlc_max_overlap_spin.setMinimumWidth(60)
        self.qlc_max_overlap_spin.setValue(self._settings.qlc_filter_max_overlap)
        self.qlc_max_overlap_spin.setToolTip(
            "允许与某期开奖基本号重合的号码最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。"
        )
        self.qlc_max_overlap_spin.valueChanged.connect(self._on_filter_qlc_changed)
        filter_qlc_layout.addRow("允许重合号码数:", self.qlc_max_overlap_spin)

        self.qlc_min_sum_spin = QSpinBox()
        self.qlc_min_sum_spin.setRange(0, 210)
        self.qlc_min_sum_spin.setMinimumWidth(60)
        self.qlc_min_sum_spin.setValue(self._settings.qlc_filter_min_sum)
        self.qlc_min_sum_spin.setToolTip(
            "7 个基本号之和的下限，小于该值的号码将被过滤（0=不限制）。\n"
            "理论最小和值为 28（1+2+...+7）。"
        )
        self.qlc_min_sum_spin.valueChanged.connect(self._on_filter_qlc_changed)
        filter_qlc_layout.addRow("最小和值:", self.qlc_min_sum_spin)

        self.qlc_max_sum_spin = QSpinBox()
        self.qlc_max_sum_spin.setRange(0, 210)
        self.qlc_max_sum_spin.setMinimumWidth(60)
        self.qlc_max_sum_spin.setValue(self._settings.qlc_filter_max_sum)
        self.qlc_max_sum_spin.setToolTip(
            "7 个基本号之和的上限，大于该值的号码将被过滤（210=不限制）。\n"
            "理论最大和值为 189（24+25+...+30）。"
        )
        self.qlc_max_sum_spin.valueChanged.connect(self._on_filter_qlc_changed)
        filter_qlc_layout.addRow("最大和值:", self.qlc_max_sum_spin)

        self.layout.addWidget(self.filter_qlc_group)
        self.filter_qlc_group.setVisible(False)

        # 大乐透 经验策略参数（参照七乐彩）
        self.filter_dlt_group = QGroupBox("经验策略参数")
        filter_dlt_layout = QFormLayout(self.filter_dlt_group)
        filter_dlt_layout.setSpacing(8)

        self.dlt_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.dlt_filter_enable_check.setChecked(self._settings.dlt_filter_enabled)
        self.dlt_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖前区号码比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.dlt_filter_enable_check.stateChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow(self.dlt_filter_enable_check)

        self.dlt_compare_spin = QSpinBox()
        self.dlt_compare_spin.setRange(0, 50)
        self.dlt_compare_spin.setMinimumWidth(60)
        self.dlt_compare_spin.setValue(self._settings.dlt_filter_compare_periods)
        self.dlt_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.dlt_compare_spin.valueChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow("对比期数:", self.dlt_compare_spin)

        self.dlt_max_front_overlap_spin = QSpinBox()
        self.dlt_max_front_overlap_spin.setRange(0, 5)
        self.dlt_max_front_overlap_spin.setMinimumWidth(60)
        self.dlt_max_front_overlap_spin.setValue(self._settings.dlt_filter_max_front_overlap)
        self.dlt_max_front_overlap_spin.setToolTip(
            "允许与某期开奖前区号码重合的最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。"
        )
        self.dlt_max_front_overlap_spin.valueChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow("前区重合上限:", self.dlt_max_front_overlap_spin)

        self.dlt_block_back_check = QCheckBox("禁止后区与历史相同")
        self.dlt_block_back_check.setChecked(self._settings.dlt_filter_block_back)
        self.dlt_block_back_check.setToolTip("开启后，后区号码与最近历史后区号码相同则淘汰。")
        self.dlt_block_back_check.stateChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow(self.dlt_block_back_check)

        self.dlt_back_compare_spin = QSpinBox()
        self.dlt_back_compare_spin.setRange(0, 50)
        self.dlt_back_compare_spin.setMinimumWidth(60)
        self.dlt_back_compare_spin.setValue(self._settings.dlt_filter_back_compare_periods)
        self.dlt_back_compare_spin.setToolTip("禁止后区重复的对比期数（仅在勾选上方复选框时生效）")
        self.dlt_back_compare_spin.valueChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow("后区对比期数:", self.dlt_back_compare_spin)

        self.dlt_min_front_sum_spin = QSpinBox()
        self.dlt_min_front_sum_spin.setRange(0, 165)
        self.dlt_min_front_sum_spin.setMinimumWidth(60)
        self.dlt_min_front_sum_spin.setValue(self._settings.dlt_filter_min_front_sum)
        self.dlt_min_front_sum_spin.setToolTip(
            "5 个前区号码之和的下限，小于该值的号码将被过滤（0=不限制）。\n"
            "理论最小和值为 15（1+2+3+4+5）。"
        )
        self.dlt_min_front_sum_spin.valueChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow("前区最小和值:", self.dlt_min_front_sum_spin)

        self.dlt_max_front_sum_spin = QSpinBox()
        self.dlt_max_front_sum_spin.setRange(0, 165)
        self.dlt_max_front_sum_spin.setMinimumWidth(60)
        self.dlt_max_front_sum_spin.setValue(self._settings.dlt_filter_max_front_sum)
        self.dlt_max_front_sum_spin.setToolTip(
            "5 个前区号码之和的上限，大于该值的号码将被过滤（165=不限制）。\n"
            "理论最大和值为 165（31+32+33+34+35）。"
        )
        self.dlt_max_front_sum_spin.valueChanged.connect(self._on_filter_dlt_changed)
        filter_dlt_layout.addRow("前区最大和值:", self.dlt_max_front_sum_spin)

        self.layout.addWidget(self.filter_dlt_group)
        self.filter_dlt_group.setVisible(False)

        # 排列3 经验策略参数（参照福彩3D）
        self.filter_pl3_group = QGroupBox("经验策略参数")
        filter_pl3_layout = QFormLayout(self.filter_pl3_group)
        filter_pl3_layout.setSpacing(8)

        self.pl3_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.pl3_filter_enable_check.setChecked(self._settings.pl3_filter_enabled)
        self.pl3_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖号码比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.pl3_filter_enable_check.stateChanged.connect(self._on_filter_pl3_changed)
        filter_pl3_layout.addRow(self.pl3_filter_enable_check)

        self.pl3_compare_spin = QSpinBox()
        self.pl3_compare_spin.setRange(0, 50)
        self.pl3_compare_spin.setMinimumWidth(60)
        self.pl3_compare_spin.setValue(self._settings.pl3_filter_compare_periods)
        self.pl3_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.pl3_compare_spin.valueChanged.connect(self._on_filter_pl3_changed)
        filter_pl3_layout.addRow("对比期数:", self.pl3_compare_spin)

        self.pl3_max_overlap_spin = QSpinBox()
        self.pl3_max_overlap_spin.setRange(0, 3)
        self.pl3_max_overlap_spin.setMinimumWidth(60)
        self.pl3_max_overlap_spin.setValue(self._settings.pl3_filter_max_overlap)
        self.pl3_max_overlap_spin.setToolTip(
            "允许与某期开奖号码重合的最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。"
        )
        self.pl3_max_overlap_spin.valueChanged.connect(self._on_filter_pl3_changed)
        filter_pl3_layout.addRow("允许相同号码数:", self.pl3_max_overlap_spin)

        self.pl3_min_sum_spin = QSpinBox()
        self.pl3_min_sum_spin.setRange(0, 27)
        self.pl3_min_sum_spin.setMinimumWidth(60)
        self.pl3_min_sum_spin.setValue(self._settings.pl3_filter_min_sum)
        self.pl3_min_sum_spin.setToolTip(
            "三位数字之和的下限，小于该值的号码将被过滤（0=不限制）。"
        )
        self.pl3_min_sum_spin.valueChanged.connect(self._on_filter_pl3_changed)
        filter_pl3_layout.addRow("最小和值:", self.pl3_min_sum_spin)

        self.pl3_max_sum_spin = QSpinBox()
        self.pl3_max_sum_spin.setRange(0, 27)
        self.pl3_max_sum_spin.setMinimumWidth(60)
        self.pl3_max_sum_spin.setValue(self._settings.pl3_filter_max_sum)
        self.pl3_max_sum_spin.setToolTip(
            "三位数字之和的上限，大于该值的号码将被过滤（27=不限制）。"
        )
        self.pl3_max_sum_spin.valueChanged.connect(self._on_filter_pl3_changed)
        filter_pl3_layout.addRow("最大和值:", self.pl3_max_sum_spin)

        self.layout.addWidget(self.filter_pl3_group)
        self.filter_pl3_group.setVisible(False)

        # 排列5 经验策略参数（参照排列3）
        self.filter_pl5_group = QGroupBox("经验策略参数")
        filter_pl5_layout = QFormLayout(self.filter_pl5_group)
        filter_pl5_layout.setSpacing(8)

        self.pl5_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.pl5_filter_enable_check.setChecked(self._settings.pl5_filter_enabled)
        self.pl5_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖号码比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.pl5_filter_enable_check.stateChanged.connect(self._on_filter_pl5_changed)
        filter_pl5_layout.addRow(self.pl5_filter_enable_check)

        self.pl5_compare_spin = QSpinBox()
        self.pl5_compare_spin.setRange(0, 50)
        self.pl5_compare_spin.setMinimumWidth(60)
        self.pl5_compare_spin.setValue(self._settings.pl5_filter_compare_periods)
        self.pl5_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.pl5_compare_spin.valueChanged.connect(self._on_filter_pl5_changed)
        filter_pl5_layout.addRow("对比期数:", self.pl5_compare_spin)

        self.pl5_max_overlap_spin = QSpinBox()
        self.pl5_max_overlap_spin.setRange(0, 5)
        self.pl5_max_overlap_spin.setMinimumWidth(60)
        self.pl5_max_overlap_spin.setValue(self._settings.pl5_filter_max_overlap)
        self.pl5_max_overlap_spin.setToolTip(
            "允许与某期开奖号码重合的最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。"
        )
        self.pl5_max_overlap_spin.valueChanged.connect(self._on_filter_pl5_changed)
        filter_pl5_layout.addRow("允许相同号码数:", self.pl5_max_overlap_spin)

        self.pl5_min_sum_spin = QSpinBox()
        self.pl5_min_sum_spin.setRange(0, 45)
        self.pl5_min_sum_spin.setMinimumWidth(60)
        self.pl5_min_sum_spin.setValue(self._settings.pl5_filter_min_sum)
        self.pl5_min_sum_spin.setToolTip(
            "五位数字之和的下限，小于该值的号码将被过滤（0=不限制）。"
        )
        self.pl5_min_sum_spin.valueChanged.connect(self._on_filter_pl5_changed)
        filter_pl5_layout.addRow("最小和值:", self.pl5_min_sum_spin)

        self.pl5_max_sum_spin = QSpinBox()
        self.pl5_max_sum_spin.setRange(0, 45)
        self.pl5_max_sum_spin.setMinimumWidth(60)
        self.pl5_max_sum_spin.setValue(self._settings.pl5_filter_max_sum)
        self.pl5_max_sum_spin.setToolTip(
            "五位数字之和的上限，大于该值的号码将被过滤（45=不限制）。"
        )
        self.pl5_max_sum_spin.valueChanged.connect(self._on_filter_pl5_changed)
        filter_pl5_layout.addRow("最大和值:", self.pl5_max_sum_spin)

        self.layout.addWidget(self.filter_pl5_group)
        self.filter_pl5_group.setVisible(False)

        # 7星彩 经验策略参数（参照排列5）
        self.filter_qxc_group = QGroupBox("经验策略参数")
        filter_qxc_layout = QFormLayout(self.filter_qxc_group)
        filter_qxc_layout.setSpacing(8)

        self.qxc_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.qxc_filter_enable_check.setChecked(self._settings.qxc_filter_enabled)
        self.qxc_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖号码比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.qxc_filter_enable_check.stateChanged.connect(self._on_filter_qxc_changed)
        filter_qxc_layout.addRow(self.qxc_filter_enable_check)

        self.qxc_compare_spin = QSpinBox()
        self.qxc_compare_spin.setRange(0, 50)
        self.qxc_compare_spin.setMinimumWidth(60)
        self.qxc_compare_spin.setValue(self._settings.qxc_filter_compare_periods)
        self.qxc_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.qxc_compare_spin.valueChanged.connect(self._on_filter_qxc_changed)
        filter_qxc_layout.addRow("对比期数:", self.qxc_compare_spin)

        self.qxc_max_overlap_spin = QSpinBox()
        self.qxc_max_overlap_spin.setRange(0, 7)
        self.qxc_max_overlap_spin.setMinimumWidth(60)
        self.qxc_max_overlap_spin.setValue(self._settings.qxc_filter_max_overlap)
        self.qxc_max_overlap_spin.setToolTip(
            "允许与某期开奖号码重合的最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。"
        )
        self.qxc_max_overlap_spin.valueChanged.connect(self._on_filter_qxc_changed)
        filter_qxc_layout.addRow("允许相同号码数:", self.qxc_max_overlap_spin)

        self.qxc_min_sum_spin = QSpinBox()
        self.qxc_min_sum_spin.setRange(0, 63)
        self.qxc_min_sum_spin.setMinimumWidth(60)
        self.qxc_min_sum_spin.setValue(self._settings.qxc_filter_min_sum)
        self.qxc_min_sum_spin.setToolTip(
            "七位数字之和的下限，小于该值的号码将被过滤（0=不限制）。"
        )
        self.qxc_min_sum_spin.valueChanged.connect(self._on_filter_qxc_changed)
        filter_qxc_layout.addRow("最小和值:", self.qxc_min_sum_spin)

        self.qxc_max_sum_spin = QSpinBox()
        self.qxc_max_sum_spin.setRange(0, 63)
        self.qxc_max_sum_spin.setMinimumWidth(60)
        self.qxc_max_sum_spin.setValue(self._settings.qxc_filter_max_sum)
        self.qxc_max_sum_spin.setToolTip(
            "七位数字之和的上限，大于该值的号码将被过滤（63=不限制）。"
        )
        self.qxc_max_sum_spin.valueChanged.connect(self._on_filter_qxc_changed)
        filter_qxc_layout.addRow("最大和值:", self.qxc_max_sum_spin)

        self.layout.addWidget(self.filter_qxc_group)
        self.filter_qxc_group.setVisible(False)

        # 快乐8 经验策略参数（参照七乐彩）
        self.filter_kl8_group = QGroupBox("经验策略参数")
        filter_kl8_layout = QFormLayout(self.filter_kl8_group)
        filter_kl8_layout.setSpacing(8)

        self.kl8_filter_enable_check = QCheckBox("启用经验策略过滤")
        self.kl8_filter_enable_check.setChecked(self._settings.kl8_filter_enabled)
        self.kl8_filter_enable_check.setToolTip(
            "开启后将新生成的号码与最近若干期开奖号码比较；\n"
            "只要与任一期重合的号码数超过允许上限，就放弃该号码。"
        )
        self.kl8_filter_enable_check.stateChanged.connect(self._on_filter_kl8_changed)
        filter_kl8_layout.addRow(self.kl8_filter_enable_check)

        self.kl8_compare_spin = QSpinBox()
        self.kl8_compare_spin.setRange(0, 50)
        self.kl8_compare_spin.setMinimumWidth(60)
        self.kl8_compare_spin.setValue(self._settings.kl8_filter_compare_periods)
        self.kl8_compare_spin.setToolTip(
            "向前比较的历史开奖期数。例如 2 表示分别与前一期、前两期比较。"
        )
        self.kl8_compare_spin.valueChanged.connect(self._on_filter_kl8_changed)
        filter_kl8_layout.addRow("对比期数:", self.kl8_compare_spin)

        self.kl8_max_overlap_spin = QSpinBox()
        self.kl8_max_overlap_spin.setRange(0, 20)
        self.kl8_max_overlap_spin.setMinimumWidth(60)
        self.kl8_max_overlap_spin.setValue(self._settings.kl8_filter_max_overlap)
        self.kl8_max_overlap_spin.setToolTip(
            "允许与某期开奖号码重合的最大个数。\n"
            "若新生成号码与任一期重合数多于该值，则放弃该号码。\n"
            "快乐8开奖20个号，默认允许重合5个。"
        )
        self.kl8_max_overlap_spin.valueChanged.connect(self._on_filter_kl8_changed)
        filter_kl8_layout.addRow("允许重合号码数:", self.kl8_max_overlap_spin)

        self.kl8_min_sum_spin = QSpinBox()
        self.kl8_min_sum_spin.setRange(0, 800)
        self.kl8_min_sum_spin.setMinimumWidth(60)
        self.kl8_min_sum_spin.setValue(self._settings.kl8_filter_min_sum)
        self.kl8_min_sum_spin.setToolTip(
            "选中号码之和的下限，小于该值的号码将被过滤（0=不限制）。"
        )
        self.kl8_min_sum_spin.valueChanged.connect(self._on_filter_kl8_changed)
        filter_kl8_layout.addRow("最小和值:", self.kl8_min_sum_spin)

        self.kl8_max_sum_spin = QSpinBox()
        self.kl8_max_sum_spin.setRange(0, 800)
        self.kl8_max_sum_spin.setMinimumWidth(60)
        self.kl8_max_sum_spin.setValue(self._settings.kl8_filter_max_sum)
        self.kl8_max_sum_spin.setToolTip(
            "选中号码之和的上限，大于该值的号码将被过滤（800=不限制）。"
        )
        self.kl8_max_sum_spin.valueChanged.connect(self._on_filter_kl8_changed)
        filter_kl8_layout.addRow("最大和值:", self.kl8_max_sum_spin)

        self.layout.addWidget(self.filter_kl8_group)
        self.filter_kl8_group.setVisible(False)

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
        self.layout.addWidget(self.options_scroll, 1)  # stretch=1 占满剩余空间

        # 恢复默认参数
        self.reset_defaults_btn = QPushButton("恢复默认参数")
        self.reset_defaults_btn.setToolTip("清除该策略的所有锁定参数")
        self.reset_defaults_btn.clicked.connect(self._on_reset_defaults)
        self.layout.addWidget(self.reset_defaults_btn)

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

    # 快乐8保留智能冷热号、历史均衡和XGBoost策略
    _KL8_ALLOWED_STRATEGIES = {"smart_hot_cold_kl8", "balanced_kl8", "xgboost_kl8"}

    def _refresh_strategies(self) -> None:
        self.strategy_combo.clear()
        for strategy in self.engine.list_strategies():
            sid = strategy.metadata.id
            if sid.endswith("_kl8") and sid not in self._KL8_ALLOWED_STRATEGIES:
                continue
            self.strategy_combo.addItem(strategy.metadata.name, sid)
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
        # 过滤参数按“目标彩种”显示：
        # - 分彩种专属策略以其对应彩种为准（策略id后缀对应彩种）；
        # - 通用策略（如八卦占卜 bagua）不绑定特定彩种，按当前所选彩种
        #   self._profile_key 为准，确保针对双色球/大乐透/快乐8等不同彩种
        #   显示对应的过滤设置，而不是永远显示双色球过滤。
        _LOTTERY_SUFFIXES = {
            "_3d": "3d", "_qlc": "qlc", "_kl8": "kl8", "_dlt": "dlt",
            "_pl3": "pl3", "_pl5": "pl5", "_qxc": "qxc", "_gd36x7": "gd36x7",
        }
        filter_pk = self._profile_key  # 通用策略（含八卦占卜）按当前彩种
        for suf, pk in _LOTTERY_SUFFIXES.items():
            if strategy_id and strategy_id.endswith(suf):
                filter_pk = pk
                break
        self.filter_ssq_group.setVisible(filter_pk == "ssq")
        self.filter_fc3d_group.setVisible(filter_pk == "3d")
        self.filter_qlc_group.setVisible(filter_pk == "qlc")
        self.filter_dlt_group.setVisible(filter_pk == "dlt")
        self.filter_pl3_group.setVisible(filter_pk == "pl3")
        self.filter_pl5_group.setVisible(filter_pk == "pl5")
        self.filter_qxc_group.setVisible(filter_pk == "qxc")
        self.filter_kl8_group.setVisible(filter_pk == "kl8")
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
        self._settings.fc3d_filter_min_sum = self.fc3d_min_sum_spin.value()
        self._settings.fc3d_filter_max_sum = self.fc3d_max_sum_spin.value()
        self._settings.sync()

    def _on_filter_qlc_changed(self, _=None) -> None:
        """七乐彩经验策略过滤参数变化时保存到 QSettings."""
        self._settings.qlc_filter_enabled = self.qlc_filter_enable_check.isChecked()
        self._settings.qlc_filter_compare_periods = self.qlc_compare_spin.value()
        self._settings.qlc_filter_max_overlap = self.qlc_max_overlap_spin.value()
        self._settings.qlc_filter_min_sum = self.qlc_min_sum_spin.value()
        self._settings.qlc_filter_max_sum = self.qlc_max_sum_spin.value()
        self._settings.sync()

    def _on_filter_dlt_changed(self, _=None) -> None:
        """大乐透经验策略过滤参数变化时保存到 QSettings."""
        self._settings.dlt_filter_enabled = self.dlt_filter_enable_check.isChecked()
        self._settings.dlt_filter_compare_periods = self.dlt_compare_spin.value()
        self._settings.dlt_filter_max_front_overlap = self.dlt_max_front_overlap_spin.value()
        self._settings.dlt_filter_block_back = self.dlt_block_back_check.isChecked()
        self._settings.dlt_filter_back_compare_periods = self.dlt_back_compare_spin.value()
        self._settings.dlt_filter_min_front_sum = self.dlt_min_front_sum_spin.value()
        self._settings.dlt_filter_max_front_sum = self.dlt_max_front_sum_spin.value()
        self._settings.sync()

    def _on_filter_pl3_changed(self, _=None) -> None:
        """排列3经验策略过滤参数变化时保存到 QSettings."""
        self._settings.pl3_filter_enabled = self.pl3_filter_enable_check.isChecked()
        self._settings.pl3_filter_compare_periods = self.pl3_compare_spin.value()
        self._settings.pl3_filter_max_overlap = self.pl3_max_overlap_spin.value()
        self._settings.pl3_filter_min_sum = self.pl3_min_sum_spin.value()
        self._settings.pl3_filter_max_sum = self.pl3_max_sum_spin.value()
        self._settings.sync()

    def _on_filter_pl5_changed(self, _=None) -> None:
        """排列5经验策略过滤参数变化时保存到 QSettings."""
        self._settings.pl5_filter_enabled = self.pl5_filter_enable_check.isChecked()
        self._settings.pl5_filter_compare_periods = self.pl5_compare_spin.value()
        self._settings.pl5_filter_max_overlap = self.pl5_max_overlap_spin.value()
        self._settings.pl5_filter_min_sum = self.pl5_min_sum_spin.value()
        self._settings.pl5_filter_max_sum = self.pl5_max_sum_spin.value()
        self._settings.sync()

    def _on_filter_qxc_changed(self, _=None) -> None:
        """7星彩经验策略过滤参数变化时保存到 QSettings."""
        self._settings.qxc_filter_enabled = self.qxc_filter_enable_check.isChecked()
        self._settings.qxc_filter_compare_periods = self.qxc_compare_spin.value()
        self._settings.qxc_filter_max_overlap = self.qxc_max_overlap_spin.value()
        self._settings.qxc_filter_min_sum = self.qxc_min_sum_spin.value()
        self._settings.qxc_filter_max_sum = self.qxc_max_sum_spin.value()
        self._settings.sync()

    def _on_filter_kl8_changed(self, _=None) -> None:
        """快乐8经验策略过滤参数变化时保存到 QSettings."""
        self._settings.kl8_filter_enabled = self.kl8_filter_enable_check.isChecked()
        self._settings.kl8_filter_compare_periods = self.kl8_compare_spin.value()
        self._settings.kl8_filter_max_overlap = self.kl8_max_overlap_spin.value()
        self._settings.kl8_filter_min_sum = self.kl8_min_sum_spin.value()
        self._settings.kl8_filter_max_sum = self.kl8_max_sum_spin.value()
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
                if isinstance(choice, (tuple, list)) and len(choice) == 2:
                    value, label = choice
                else:
                    value, label = choice, str(choice)
                combo.addItem(str(label), value)
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
