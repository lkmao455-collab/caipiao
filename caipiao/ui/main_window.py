"""主窗口."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
from itertools import permutations
from pathlib import Path
import logging

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QClipboard, QKeySequence
from PySide6.QtGui import QIcon, QPageSize, QPdfWriter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.profile import (
    NAV_HIDDEN_PROFILE_KEYS,
    category_label,
    list_profiles,
    list_profiles_by_category,
    profile_keys,
)
from ..core.prize import fc3d_bet_type
from ..core.strategies import is_ml_strategy, needs_history
from ..data.models import DrawRecord
from ..data.repository import DrawRepository
from ..ml.catboost_model import LotteryCatBoostModel
from ..ml.common.model_store import compute_lookback, is_model_current, new_model_path
from ..ml.lgbm_model import LotteryLightGBMModel
from ..ml.model import LotteryXGBoostModel
from ..persistence.history import HistoryManager
from ..persistence.optimal_param_store import OptimalParamStore
from ..persistence.parameter_group_store import ParameterGroupStore
from ..persistence.settings import AppSettings
from ..plugins.plugin_manager import PluginManager
from ..utils import app_data_dir
from .chart_utils import (
    ProbabilityChartDialog,
    build_group_probability_charts_html,
    build_probability_charts_html,
)
from .components.backtest_dialog import BacktestDialog
from .components.ball_display import TicketRowWidget
from .components.batch_backtest_dialog import BatchBacktestDialog
from .components.draw_analysis_dialog import DrawAnalysisDialog
from .components.history_panel import HistoryPanel
from .components.hotkey_edit import HotkeyEdit, validate_hotkey_dialog
from .components.parameter_group_panel import ParameterGroupPanel
from .components.strategy_panel import StrategyPanel
from .components.auto_update_dialog import AutoUpdateDialog
from .components.today_draws_dialog import TodayDrawsDialog
from .components.latest_results_dialog import LatestResultsDialog
from .components.training_progress_dialog import TrainingProgressDialog
from .components.lunar_calendar_widget import LunarCalendarWidget
from .components.divination_tab import DivinationTab
from .lottery_context import ContextManager, LotteryContext
from .markdown_view import MarkdownDialog
from .workers import (
    FetchAllDataThread,
    FetchLatestDataThread,
    GenerateTicketsThread,
    TrainModelThread,
)

# 双色球 ML 策略的模型新鲜度检测与自动重训配置：strategy_id -> (模型类, 模型文件前缀)。
ML_MODEL_STRATEGIES = {
    "xgboost": (LotteryXGBoostModel, "xgboost"),
    "lightgbm": (LotteryLightGBMModel, "lightgbm"),
    "catboost": (LotteryCatBoostModel, "catboost"),
    "ml_xgboost": (LotteryXGBoostModel, "xgboost"),
    "ml_lightgbm": (LotteryLightGBMModel, "lightgbm"),
    "ml_catboost": (LotteryCatBoostModel, "catboost"),
}

logger = logging.getLogger(__name__)

# 周几中文，用于展示开奖日期（weekday(): 周一=0 ... 周日=6）
_WEEKDAY_CN = "一二三四五六日"


class MainWindow(QMainWindow):
    """彩票号码生成器主窗口。

    支持彩种：
    - 福利彩票：双色球、福彩3D、七乐彩、快乐8
    - 体育彩票：超级大乐透、排列3、排列5、7星彩、广东36选7
    """

    def __init__(self, optimal_param_store: OptimalParamStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle("彩票号码生成器")
        self.setMinimumSize(950, 720)

        # 设置窗口图标
        icon_path = Path(__file__).resolve().parent / "resources" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # 数据目录（应用目录下的 .caipiao）
        self.data_dir = app_data_dir()
        self.data_dir.mkdir(exist_ok=True)

        # 设置
        self.settings = AppSettings()

        # 历史（所有彩种共用一份历史记录文件）
        self.history_manager = HistoryManager(self.data_dir / "history.json")

        # 参数组持久化
        self._param_group_store = ParameterGroupStore(self.data_dir)

        # 最优参数锁定持久化
        self._optimal_param_store = optimal_param_store or OptimalParamStore()

        # 彩种上下文管理器
        self.context_manager = ContextManager(self.data_dir, self.history_manager)
        self.current_key = self._validated_current_key(
            self.settings.get("current_lottery", "ssq")
        )
        self.settings.set("current_lottery", self.current_key)
        self.settings.sync()
        self.current = self.context_manager.get(self.current_key)

        # 启动时加载当前彩种的锁定参数
        self._locked_params = self._optimal_param_store.load(self.current_key).locked

        # 插件（每个彩种上下文独立加载，策略 id 互不冲突）
        self.plugin_managers: dict[str, PluginManager] = {}
        _default_plugin_dir = Path.cwd() / "plugins"
        plugin_dir = Path(self.settings.plugin_dir) if self.settings.plugin_dir else _default_plugin_dir
        if not plugin_dir.is_dir():
            plugin_dir = _default_plugin_dir
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for ctx in self.context_manager.all_contexts():
            pm = PluginManager(ctx.engine, plugin_dir)
            pm.load_all()
            self.plugin_managers[ctx.profile.key] = pm

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._apply_theme()
        self._register_boss_key()

        # 启动时自动检查更新（离线时静默失败，不影响使用）
        self._perform_auto_update()

    @staticmethod
    def _validated_current_key(key: str) -> str:
        """校验并规范化当前彩种 key，非法或已从导航隐藏时回退到双色球。"""
        if key in profile_keys() and key not in NAV_HIDDEN_PROFILE_KEYS:
            return key
        return "ssq"

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:
        """关闭窗口时请求后台线程结束并等待；超时后强制终止。"""
        pending = []
        for attr in (
            "_fetch_thread",
            "_latest_update_thread",
            "_pretrain_fetch_thread",
            "_xgboost_thread",
            "_generate_thread",
        ):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                thread.requestInterruption()
                pending.append((attr, thread))

        # 批量回测对话框可能是独立窗口，关闭主窗口时也要中断它
        for dialog in self.findChildren(QDialog):
            if hasattr(dialog, "_thread"):
                thread = getattr(dialog, "_thread", None)
                if thread and thread.isRunning():
                    thread.requestInterruption()
                    pending.append(("batch_backtest_thread", thread))

        for attr, thread in pending:
            if not thread.wait(3000):
                logger.warning("%s 未在 3 秒内结束，强制终止", attr)
                thread.terminate()
                thread.wait(1000)
            # 断开 finished 等信号，避免关闭期间触发回调操作已销毁对象
            try:
                thread.finished.disconnect()
            except RuntimeError:
                pass
            try:
                thread.result_ready.disconnect()
            except RuntimeError:
                pass
            try:
                thread.deleteLater()
            except RuntimeError:
                # 对象可能已被 C++ 侧销毁
                pass
            if isinstance(attr, str) and hasattr(self, attr):
                setattr(self, attr, None)

        event.accept()

    def _cleanup_finished_thread(self, attr_name: str) -> None:
        """线程 finished 信号的统一清理：清空引用并安全 deleteLater."""
        thread = self.sender()
        if thread is None:
            return
        current = getattr(self, attr_name, None)
        if thread is current:
            setattr(self, attr_name, None)
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 顶部彩种选择栏
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("当前彩种:"))
        self.lottery_combo = QComboBox()
        self._populate_lottery_combo()
        idx = self.lottery_combo.findData(self.current_key)
        if idx >= 0:
            self.lottery_combo.setCurrentIndex(idx)
        self.lottery_combo.currentIndexChanged.connect(self._on_lottery_changed)
        top_bar.addWidget(self.lottery_combo, 1)

        self.category_label = QLabel(self._category_text())
        self.category_label.setStyleSheet("color: #666; font-size: 10pt;")
        self.category_label.setToolTip("当前彩种所属大类：福利彩票或体育彩票。")
        top_bar.addWidget(self.category_label)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # 标题
        self.title_label = QLabel(self._title_text())
        self.title_label.setObjectName("app_title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        # 标签页
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # 生成页
        self.generate_tab = self._build_generate_tab()
        self.tabs.addTab(self.generate_tab, "生成号码")

        # 历史页
        self.history_panel = HistoryPanel(self.history_manager)
        self.history_panel.history_changed.connect(self._on_history_changed)
        self.tabs.addTab(self.history_panel, "历史记录")

        # 数据页
        self.data_tab = self._build_data_tab()
        self.tabs.addTab(self.data_tab, "开奖数据")

        # 万年历页
        self.calendar_tab = LunarCalendarWidget()
        self.tabs.addTab(self.calendar_tab, "万年历")

        # 八卦占卜页
        self.divination_tab = DivinationTab()
        self.tabs.addTab(self.divination_tab, "八卦占卜")

        # 插件页
        self.plugins_tab = self._build_plugins_tab()
        self.tabs.addTab(self.plugins_tab, "插件管理")

        # 设置页
        self.settings_tab = self._build_settings_tab()
        self.tabs.addTab(self.settings_tab, "设置")

        # 参数组页
        self.parameter_group_tab = self._build_parameter_group_tab()
        self.tabs.addTab(self.parameter_group_tab, "参数组")

        self._refresh_for_current_context()

    def _populate_lottery_combo(self) -> None:
        """按福利彩票/体育彩票分组填充彩种下拉框。"""
        self.lottery_combo.clear()
        first = True
        for category, profiles in list_profiles_by_category().items():
            visible = [p for p in profiles if p.key not in NAV_HIDDEN_PROFILE_KEYS]
            if not visible:
                continue
            if not first:
                self.lottery_combo.insertSeparator(self.lottery_combo.count())
            first = False
            # 分组标题（仅展示，不可选）
            self.lottery_combo.addItem(f"[{category_label(category)}]")
            for p in visible:
                self.lottery_combo.addItem(f"  {p.name} ({p.subtitle})", p.key)

    def _category_text(self) -> str:
        return f"类型: {category_label(self.current.profile.category)}"

    def _title_text(self) -> str:
        return (
            f"[{category_label(self.current.profile.category)}] "
            f"{self.current.profile.name}号码自动生成器"
        )

    def _build_generate_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(16)

        # 左侧控制面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)

        # 生成数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("生成注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(self.settings.default_count)
        self.count_spin.setSuffix(" 注")
        self.count_spin.setToolTip("设置一次生成的彩票注数。")
        count_layout.addWidget(self.count_spin)
        left_layout.addLayout(count_layout)

        # 策略面板
        self.strategy_panel = StrategyPanel(
            self.current.engine,
            profile_key=self.current_key,
            store=self._optimal_param_store,
            locked_params=self._locked_params,
            parent=self,
        )
        self.strategy_panel.recommend_requested.connect(
            self._on_recommend_parameters
        )
        self._restore_last_strategy()
        left_layout.addWidget(self.strategy_panel, 1)  # stretch=1 占满剩余空间

        layout.addWidget(left_panel, 1)

        # 右侧结果面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # 信息区（目标期+概率，紧凑展示）
        self.target_label = QLabel("")
        self.target_label.setWordWrap(True)
        self.target_label.setStyleSheet("color:#333; padding:2px;")
        self.target_label.setVisible(False)
        right_layout.addWidget(self.target_label)

        self.probability_label = QLabel("")
        self.probability_label.setWordWrap(True)
        self.probability_label.setStyleSheet("color:#D32F2F;font-weight:bold;font-size:12px; padding:2px;")
        self.probability_label.setVisible(False)
        right_layout.addWidget(self.probability_label)

        self.chart_btn = QPushButton("查看概率折线图")
        self.chart_btn.setToolTip("在独立窗口中查看更大的概率折线图")
        self.chart_btn.setVisible(False)
        self.chart_btn.clicked.connect(self._show_probability_chart)
        right_layout.addWidget(self.chart_btn)

        # 上半区：球号可视化 + 可编辑列表（左右排列）
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setHandleWidth(6)

        # 左：球号可视化展示
        self.result_area = QScrollArea()
        self.result_area.setWidgetResizable(True)
        self.result_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.result_container = QWidget()
        self.result_container_layout = QVBoxLayout(self.result_container)
        self.result_container_layout.setSpacing(4)
        self.result_container_layout.setContentsMargins(4, 4, 4, 4)
        self.result_container_layout.addStretch()
        self.result_area.setWidget(self.result_container)
        top_splitter.addWidget(self.result_area)

        # 右：可编辑号码列表（所有彩种通用）
        self.editable_numbers_group = QGroupBox("可编辑号码列表")
        editable_layout = QVBoxLayout(self.editable_numbers_group)
        editable_layout.setContentsMargins(8, 16, 8, 8)
        editable_layout.setSpacing(6)

        # 筛选行（福彩3D 专用筛选）
        self.filter_layout_container = QWidget()
        filter_layout = QHBoxLayout(self.filter_layout_container)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(QLabel("显示筛选:"))
        self.filter_zu6_check = QCheckBox("组选6")
        self.filter_zu6_check.setChecked(True)
        self.filter_zu6_check.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_zu6_check)
        self.filter_zu3_check = QCheckBox("组选3")
        self.filter_zu3_check.setChecked(True)
        self.filter_zu3_check.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_zu3_check)
        self.filter_baozi_check = QCheckBox("豹子号")
        self.filter_baozi_check.setChecked(True)
        self.filter_baozi_check.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_baozi_check)
        filter_layout.addStretch()
        self.filter_count_label = QLabel("共 0 注")
        self.filter_count_label.setStyleSheet("font-weight: bold;")
        filter_layout.addWidget(self.filter_count_label)
        editable_layout.addWidget(self.filter_layout_container)

        self.editable_numbers_table = QTableWidget()
        self.editable_numbers_table.setColumnCount(4)
        self.editable_numbers_table.setHorizontalHeaderLabels(["序号", "号码", "类型", "操作"])
        self.editable_numbers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.editable_numbers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.editable_numbers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.editable_numbers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.editable_numbers_table.setColumnWidth(0, 50)
        self.editable_numbers_table.setColumnWidth(3, 70)
        self.editable_numbers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.editable_numbers_table.verticalHeader().setVisible(False)
        editable_layout.addWidget(self.editable_numbers_table)

        # 底部输入控件
        add_layout = QHBoxLayout()
        self.add_number_input = QLineEdit()
        self.add_number_input.setPlaceholderText("输入号码")
        add_layout.addWidget(self.add_number_input)
        self.add_number_btn = QPushButton("添加")
        self.add_number_btn.clicked.connect(self._add_custom_number)
        add_layout.addWidget(self.add_number_btn)
        self.add_random_btn = QPushButton("随机添加")
        self.add_random_btn.setToolTip("随机生成一个号码并添加到列表")
        self.add_random_btn.clicked.connect(self._add_random_number)
        add_layout.addWidget(self.add_random_btn)
        editable_layout.addLayout(add_layout)

        self.editable_numbers_group.setVisible(False)
        top_splitter.addWidget(self.editable_numbers_group)

        # 设置左右比例（球号60%，可编辑列表40%）
        top_splitter.setSizes([600, 400])

        right_layout.addWidget(top_splitter, 3)

        # 下半区：生成摘要（文本）
        summary_group = QGroupBox("生成摘要")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(8, 16, 8, 8)
        summary_layout.setSpacing(4)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("点击“立即生成”获取号码...")
        self.result_text.setMaximumHeight(140)
        self.result_text.setStyleSheet("font-size:9pt; color:#555;")
        summary_layout.addWidget(self.result_text)
        right_layout.addWidget(summary_group, 1)

        layout.addWidget(right_panel, 2)

        return tab

    def _restore_last_strategy(self) -> None:
        last_id = self.settings.last_strategy_id
        idx = self.strategy_panel.strategy_combo.findData(last_id)
        if idx >= 0:
            self.strategy_panel.set_strategy_id(last_id)
            saved_options = self.settings.last_strategy_options
            if saved_options:
                self.strategy_panel.set_options(saved_options)
            # 恢复上次使用的历史记录期数
            saved_history_count = self.settings.last_history_count
            if saved_history_count != -1:
                self.strategy_panel.set_options({"history_count": saved_history_count})

    def _on_recommend_parameters(self, strategy_id: str) -> None:
        """响应策略面板的一键推荐参数请求。"""
        if strategy_id != "consensus_constraint":
            return
        context = self.context_manager.current(self.current_key)
        records = context.data_repository.get_all()
        if not records:
            QMessageBox.warning(
                self,
                "数据不足",
                "当前彩种暂无历史开奖数据，无法推荐参数。",
            )
            return
        strategy = context.engine.get(strategy_id)
        if strategy is None:
            return
        params, reasons = strategy.recommend_parameters(records)
        self.strategy_panel.set_options(params)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path("docs/reports") / f"consensus_constraint_{timestamp}.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        count = self.count_spin.value()
        generate_options = {**params, "history": records}
        _, stats = strategy._generate_with_stats(count, generate_options)
        strategy.generate_report(records, params, reasons, str(report_path), stats=stats)
        dialog = QDialog(self)
        dialog.setWindowTitle("参数推荐报告")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setSource(QUrl.fromLocalFile(str(report_path.resolve())))
        layout.addWidget(browser)
        dialog.exec()

    def _build_plugins_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "插件目录: 将自定义策略 Python 文件放入插件目录，重启后自动加载。\n"
            "插件可继承 GenerationStrategy 类或提供 register_strategies(engine) 函数。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("插件目录:"))
        pm = self.plugin_managers.get(self.current_key)
        self.plugin_dir_edit = QLineEdit(str(pm.plugin_dir) if pm else "")
        self.plugin_dir_edit.setToolTip("当前插件所在的目录。插件可扩展生成策略。")
        self.plugin_dir_edit.setReadOnly(True)
        path_layout.addWidget(self.plugin_dir_edit)
        self.choose_plugin_dir_btn = QPushButton("选择目录")
        self.choose_plugin_dir_btn.setToolTip("更改插件所在的目录。")
        self.choose_plugin_dir_btn.clicked.connect(self._choose_plugin_dir)
        path_layout.addWidget(self.choose_plugin_dir_btn)
        layout.addLayout(path_layout)

        self.reload_plugins_btn = QPushButton("重新加载插件")
        self.reload_plugins_btn.setToolTip("重新扫描插件目录并加载所有有效策略。")
        self.reload_plugins_btn.clicked.connect(self._reload_plugins)
        layout.addWidget(self.reload_plugins_btn)

        self.plugin_list_label = QLabel("已加载策略:")
        layout.addWidget(self.plugin_list_label)

        self.plugin_list = QTextEdit()
        self.plugin_list.setReadOnly(True)
        layout.addWidget(self.plugin_list)

        self._refresh_plugin_list()
        layout.addStretch()
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        # 默认注数
        count_layout = QHBoxLayout()
        count_layout.setSpacing(8)
        count_layout.addWidget(QLabel("默认生成注数:"))
        self.settings_count_spin = QSpinBox()
        self.settings_count_spin.setToolTip("设置主界面每次默认生成的彩票注数。")
        self.settings_count_spin.setRange(1, 1000)
        self.settings_count_spin.setValue(self.settings.default_count)
        count_layout.addWidget(self.settings_count_spin)
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # 主题
        theme_label = QLabel("主题：中式八卦喜庆风格")
        theme_label.setStyleSheet("font-weight: bold; color: #8B0000;")
        layout.addWidget(theme_label)

        # 老板键设置
        hotkey_layout = QHBoxLayout()
        hotkey_layout.setSpacing(8)
        hotkey_layout.addWidget(QLabel("老板键:"))
        self.boss_key_edit = HotkeyEdit()
        self.boss_key_edit.set_hotkey(self.settings.boss_key)
        self.boss_key_edit.hotkey_changed.connect(self._on_boss_key_changed)
        hotkey_layout.addWidget(self.boss_key_edit, 1)
        layout.addLayout(hotkey_layout)

        self.boss_key_hint = QLabel(
            "设置后按快捷键可快速隐藏/显示主窗口。\n"
            "建议：Ctrl+Shift+B、Alt+M。修改后点击“保存设置”即可生效。"
        )
        self.boss_key_hint.setWordWrap(True)
        self.boss_key_hint.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(self.boss_key_hint)

        # 过滤参数已移至「策略参数」面板，按各彩种分别配置
        filter_hint = QLabel(
            "号码过滤参数（双色球 / 福彩3D / 七乐彩 / 大乐透）已移至左侧"
            "「策略参数」面板，选择对应彩种策略后即可单独配置，"
            "此处不再重复设置。"
        )
        filter_hint.setWordWrap(True)
        filter_hint.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(filter_hint)

        # 保存按钮
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.setToolTip("将当前设置保存到本地配置文件。")
        self.save_settings_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_settings_btn)

        layout.addStretch()
        return tab

    def _build_parameter_group_tab(self) -> QWidget:
        """构建参数组标签页."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.parameter_group_panel = ParameterGroupPanel(
            self._param_group_store,
            self.current.profile.key,
            parent=tab,
        )
        self.parameter_group_panel.request_generate.connect(
            self._generate_from_parameter_group
        )
        layout.addWidget(self.parameter_group_panel)
        return tab

    def _build_data_tab(self) -> QWidget:
        """构建开奖数据标签页."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # 状态区
        self.data_status_label = QLabel(self._data_status_text())
        self.data_status_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        layout.addWidget(self.data_status_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.update_data_btn = QPushButton("更新开奖数据")
        self.update_data_btn.setToolTip("从网络下载全部历史开奖数据，用于统计分析和模型训练。")
        self.update_data_btn.clicked.connect(self._update_draw_data)
        self.fetch_latest_btn = QPushButton("获取最新一期")
        self.fetch_latest_btn.setToolTip("仅下载最近一期的开奖数据。")
        self.fetch_latest_btn.clicked.connect(self._fetch_latest_draw)
        self.check_update_btn = QPushButton("检查更新")
        self.check_update_btn.setToolTip("检查网络上是否有比本地更新的开奖数据。")
        self.check_update_btn.clicked.connect(self._check_for_updates)
        self.clear_data_btn = QPushButton("清空本地数据")
        self.clear_data_btn.setToolTip("删除本地保存的所有官方开奖数据。")
        self.clear_data_btn.clicked.connect(self._clear_draw_data)
        btn_layout.addWidget(self.update_data_btn)
        btn_layout.addWidget(self.fetch_latest_btn)
        btn_layout.addWidget(self.check_update_btn)
        btn_layout.addWidget(self.clear_data_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 进度条
        self.data_progress = QProgressBar()
        self.data_progress.setRange(0, 0)
        self.data_progress.setVisible(False)
        layout.addWidget(self.data_progress)

        # 自动更新设置
        auto_layout = QHBoxLayout()
        self.auto_update_check = QCheckBox("启动时自动检查更新")
        self.auto_update_check.setToolTip("启动软件时自动联网检查最新开奖数据。无网络时自动使用本地数据。")
        self.auto_update_check.setChecked(self.settings.auto_update_on_start)
        self.auto_update_check.stateChanged.connect(self._on_auto_update_changed)
        auto_layout.addWidget(self.auto_update_check)
        auto_layout.addWidget(QLabel("检查间隔（天）:"))
        self.update_interval_spin = QSpinBox()
        self.update_interval_spin.setToolTip("设置自动更新的最小间隔天数。例如设为 1 表示每天至少检查一次。")
        self.update_interval_spin.setRange(1, 30)
        self.update_interval_spin.setValue(self.settings.auto_update_interval_days)
        self.update_interval_spin.valueChanged.connect(self._on_update_interval_changed)
        auto_layout.addWidget(self.update_interval_spin)
        auto_layout.addStretch()
        layout.addLayout(auto_layout)

        # 统计信息
        layout.addWidget(QLabel("数据统计:"))
        self.data_stats_text = QTextEdit()
        self.data_stats_text.setReadOnly(True)
        self.data_stats_text.setMaximumHeight(240)
        layout.addWidget(self.data_stats_text)

        # 详细统计刷新
        self.refresh_stats_btn = QPushButton("刷新统计")
        self.refresh_stats_btn.setToolTip("根据本地数据重新计算热号、冷号、遗漏值等统计指标。")
        self.refresh_stats_btn.clicked.connect(self._refresh_data_stats)
        layout.addWidget(self.refresh_stats_btn)

        # 模型区
        self.model_section_label = QLabel(self._model_section_title())
        layout.addWidget(self.model_section_label)
        self.xgboost_status_label = QLabel(self._model_status_text())
        self.xgboost_status_label.setWordWrap(True)
        layout.addWidget(self.xgboost_status_label)

        xgb_btn_layout = QHBoxLayout()
        self.train_xgboost_btn = QPushButton("训练模型")
        self.train_xgboost_btn.setToolTip("使用本地历史数据训练模型。首次训练可能需要一些时间。")
        self.train_xgboost_btn.clicked.connect(self._train_xgboost_model)
        self.delete_model_btn = QPushButton("删除模型")
        self.delete_model_btn.setToolTip("删除本地保存的模型文件。")
        self.delete_model_btn.clicked.connect(self._delete_xgboost_model)
        xgb_btn_layout.addWidget(self.train_xgboost_btn)
        xgb_btn_layout.addWidget(self.delete_model_btn)
        xgb_btn_layout.addStretch()
        layout.addLayout(xgb_btn_layout)

        layout.addStretch()
        self._refresh_data_stats()
        return tab

    # ------------------------------------------------------------------ #
    # 彩种切换
    # ------------------------------------------------------------------ #
    def _switch_to_lottery(self, key: str) -> None:
        """通过菜单操作切换到指定彩种。"""
        if key not in profile_keys():
            return
        idx = self.lottery_combo.findData(key)
        if idx >= 0:
            self.lottery_combo.setCurrentIndex(idx)
        else:
            # 下拉框中未找到时直接切换（兼容未来新增的彩种）
            self.settings.set("current_lottery", key)
            self.settings.sync()
            self.current_key = key
            self.current = self.context_manager.get(key)
            self._refresh_for_current_context()

    def _on_lottery_changed(self, index: int) -> None:
        new_key = self.lottery_combo.itemData(index)
        # 分隔线或分类标题不可选，自动回到当前彩种
        if new_key is None:
            idx = self.lottery_combo.findData(self.current_key)
            if idx >= 0:
                self.lottery_combo.setCurrentIndex(idx)
            return
        if new_key == self.current_key:
            return
        # 保存当前策略选择
        self.settings.last_strategy_id = self.strategy_panel.current_strategy_id()
        self.settings.set("current_lottery", new_key)
        self.settings.sync()

        self.current_key = new_key
        self.current = self.context_manager.get(new_key)
        self._refresh_for_current_context()

    def _refresh_for_current_context(self) -> None:
        """刷新所有与当前彩种相关的界面元素."""
        self.setWindowTitle(self._title_text())
        self.title_label.setText(self._title_text())
        self.category_label.setText(self._category_text())

        # 策略面板重新绑定到当前引擎
        self.strategy_panel.engine = self.current.engine
        self._locked_params = self._optimal_param_store.load(self.current_key).locked
        self.strategy_panel.set_profile_key(self.current_key, self._locked_params)
        self.strategy_panel._refresh_strategies()
        self._restore_last_strategy()

        # 数据页刷新
        self.data_status_label.setText(self._data_status_text())
        self.model_section_label.setText(self._model_section_title())
        self.xgboost_status_label.setText(self._model_status_text())
        self._refresh_data_stats()

        # 参数组页刷新
        self.parameter_group_panel.set_profile_key(self.current.profile.key)

        # 插件页刷新
        pm = self.plugin_managers.get(self.current_key)
        self.plugin_dir_edit.setText(str(pm.plugin_dir) if pm else "")
        self._refresh_plugin_list()

        # 清空生成结果（避免旧彩种结果残留）
        self.result_text.clear()
        self.target_label.setVisible(False)
        self.probability_label.setVisible(False)
        self.chart_btn.setVisible(False)
        while self.result_container_layout.count() > 1:
            item = self.result_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 清空可编辑列表
        self.editable_numbers_group.setVisible(False)
        self._editable_tickets = []

    # ------------------------------------------------------------------ #
    # 数据页
    # ------------------------------------------------------------------ #
    def _data_status_text(self, offline: bool = False) -> str:
        count = self.current.data_repository.get_count()
        start, end = self.current.data_repository.get_date_range()
        last_update = self.settings.last_data_update or "从未"
        mode = "离线模式" if offline else "在线模式"
        if count == 0:
            return f"[{mode}] 本地暂无{self.current.profile.name}官方开奖数据，请点击“更新开奖数据”获取。"
        return (
            f"[{mode}] 本地已存储 {count} 期{self.current.profile.name}官方开奖数据\n"
            f"数据范围: {start.date()} 至 {end.date()}\n"
            f"上次更新: {last_update}"
        )

    def _update_draw_data(self) -> None:
        """在后台线程中获取全部开奖数据."""
        self.update_data_btn.setEnabled(False)
        self.data_progress.setVisible(True)

        self._fetch_thread = FetchAllDataThread(self, profile=self.current.profile)
        self._fetch_thread.result_ready.connect(
            self._on_data_fetched, Qt.ConnectionType.QueuedConnection
        )
        self._fetch_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_fetch_thread")
        )
        self._fetch_thread.start()

    def _on_data_fetched(self, records, error) -> None:
        self.update_data_btn.setEnabled(True)
        self.data_progress.setVisible(False)

        # 线程清理由 finished 信号统一处理，这里不操作线程对象

        if error:
            QMessageBox.critical(self, "获取失败", f"获取开奖数据失败:\n{error}")
            return
        if records is None:
            QMessageBox.warning(self, "获取失败", "未获取到有效开奖数据")
            return

        try:
            added = self.current.update_data(records)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存开奖数据失败:\n{exc}")
            return
        self.data_status_label.setText(self._data_status_text())
        self._refresh_data_stats()
        self.xgboost_status_label.setText(self._model_status_text())
        QMessageBox.information(
            self, "更新成功", f"成功更新{self.current.profile.name}开奖数据\n新增 {added} 期，本地共 {self.current.data_repository.get_count()} 期"
        )

    def _fetch_latest_draw(self) -> None:
        """获取并显示最新一期开奖（在后台线程执行）。"""
        self.fetch_latest_btn.setEnabled(False)
        self.data_progress.setVisible(True)
        self._latest_update_thread = FetchLatestDataThread(
            self, profile=self.current.profile
        )
        self._latest_update_thread.result_ready.connect(
            self._on_fetch_latest_finished, Qt.ConnectionType.QueuedConnection
        )
        self._latest_update_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_latest_update_thread")
        )
        self._latest_update_thread.start()

    def _on_fetch_latest_finished(self, latest, error) -> None:
        """最新一期获取完成回调。"""
        self.fetch_latest_btn.setEnabled(True)
        self.data_progress.setVisible(False)

        # 线程清理由 finished 信号统一处理，这里不操作线程对象

        if error:
            QMessageBox.critical(self, "获取失败", f"获取最新一期失败:\n{error}")
            return
        if latest is None:
            QMessageBox.warning(self, "获取失败", "未获取到最新一期数据")
            return

        try:
            self.current.update_data([latest])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存最新一期失败:\n{exc}")
            return
        self.data_status_label.setText(self._data_status_text())
        self._refresh_data_stats()
        self.xgboost_status_label.setText(self._model_status_text())
        QMessageBox.information(
            self,
            "最新一期",
            self._latest_draw_message(latest),
        )

    def _latest_draw_message(self, latest: DrawRecord) -> str:
        lines = [
            f"期号: {latest.issue}",
            f"日期: {latest.draw_date.date()}",
        ]
        for g in self.current.profile.pick_groups:
            nums = latest.groups.get(g.key, [])
            lines.append(f"{g.name}: {' '.join(f'{n:0{g.pad}d}' for n in nums)}")
        return "\n".join(lines)

    def _clear_draw_data(self) -> None:
        """清空本地开奖数据."""
        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确定要清空本地{self.current.profile.name}官方开奖数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.current.clear_data()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "清空失败", f"清空本地数据失败:\n{exc}")
                return
            self.data_status_label.setText(self._data_status_text())
            self.data_stats_text.clear()
            self.xgboost_status_label.setText(self._model_status_text())

    def _refresh_data_stats(self) -> None:
        """刷新统计信息."""
        if self.current.data_repository.get_count() == 0:
            self.data_stats_text.setText("暂无数据，请先更新开奖数据。")
            return
        summary = self.current.data_analyzer.summary()
        if self.current.profile.key == "ssq":
            lines = [
                f"总期数: {summary['total_records']}",
                f"最近 30 期热红球: {' '.join(f'{n:02d}' for n in summary['hot_reds_30'])}",
                f"最近 30 期冷红球: {' '.join(f'{n:02d}' for n in summary['cold_reds_30'])}",
                f"最近 30 期热蓝球: {' '.join(f'{n:02d}' for n in summary['hot_blues_30'])}",
                f"红球遗漏值 TOP5: "
                + ", ".join(f"{n:02d}({v})" for n, v in summary['missing_reds_50'][:5]),
                f"最近 100 期奇偶比: {summary['odd_even_ratio'][0]:.2%} : {summary['odd_even_ratio'][1]:.2%}",
                f"最近 100 期大小比: {summary['high_low_ratio'][0]:.2%} : {summary['high_low_ratio'][1]:.2%}",
                f"最近 100 期和值: 最小={summary['sum_stats']['min']}, 最大={summary['sum_stats']['max']}, "
                f"平均={summary['sum_stats']['avg']:.1f}, 中位数={summary['sum_stats']['median']}",
                f"最近 100 期连号出现比例: {summary['consecutive_ratio']:.2%}",
            ]
        else:
            primary = self.current.profile.primary_group
            lines = [
                f"总期数: {summary['total_records']}",
                f"最近 30 期热{primary.name}: {' '.join(f'{n:0{primary.pad}d}' for n in summary['hot_30'])}",
                f"最近 30 期冷{primary.name}: {' '.join(f'{n:0{primary.pad}d}' for n in summary['cold_30'])}",
                f"{primary.name}遗漏值 TOP5: "
                + ", ".join(f"{n:0{primary.pad}d}({v})" for n, v in summary['missing_50'][:5]),
                f"最近 100 期奇偶比: {summary['odd_even_ratio'][0]:.2%} : {summary['odd_even_ratio'][1]:.2%}",
                f"最近 100 期大小比: {summary['high_low_ratio'][0]:.2%} : {summary['high_low_ratio'][1]:.2%}",
                f"最近 100 期和值: 最小={summary['sum_stats']['min']}, 最大={summary['sum_stats']['max']}, "
                f"平均={summary['sum_stats']['avg']:.1f}, 中位数={summary['sum_stats']['median']}",
                f"最近 100 期连号出现比例: {summary['consecutive_ratio']:.2%}",
            ]
            if self.current.profile.key == "3d" and hasattr(self.current.data_analyzer, "span"):
                span = self.current.data_analyzer.span(100)
                lines.append(f"最近 100 期跨度: 最小={span['min']}, 最大={span['max']}, 平均={span['avg']:.1f}")
        self.data_stats_text.setText("\n".join(lines))

    def _model_section_title(self) -> str:
        if self.current.profile.key == "ssq":
            return "XGBoost 模型:"
        return "机器学习模型:"

    def _model_status_text(self) -> str:
        """模型状态文本（同时检查 XGBoost 与 LightGBM 模型）。"""
        model_dir = app_data_dir() / "models"
        prefixes = {self.current.profile.xgboost_prefix()}
        if self.current.profile.key != "ssq":
            prefixes.add(self.current.profile.lightgbm_prefix())
        else:
            prefixes.add("lightgbm")
        model_files = []
        if model_dir.exists():
            for prefix in prefixes:
                model_files.extend(model_dir.glob(f"{prefix}_*.pkl"))
        if not model_files:
            return "尚未训练模型。首次使用 ML 策略时会自动训练，或点击“训练模型”提前准备。"
        latest = max(model_files, key=lambda p: p.stat().st_mtime)
        mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return f"已找到训练好的模型：{latest.name}\n训练时间：{mtime}"

    # ------------------------------------------------------------------ #
    # 模型训练
    # ------------------------------------------------------------------ #
    def _start_training(
        self,
        model_class: type | None,
        prefix: str,
        after,
        backend: str = "xgboost",
    ) -> None:
        """两段式训练：先联网拉取最新一期数据，再训练带时间戳的新模型."""
        self._train_after = after
        self._train_model_class = model_class
        self._train_prefix = prefix
        self._train_backend = backend
        self._train_dialog = TrainingProgressDialog(self)
        self._train_dialog.set_stage("正在获取最新开奖数据…")
        self._train_dialog.show()

        self._pretrain_fetch_thread = FetchLatestDataThread(
            self, profile=self.current.profile
        )
        self._pretrain_fetch_thread.result_ready.connect(
            self._on_pretrain_fetch_done, Qt.ConnectionType.QueuedConnection
        )
        self._pretrain_fetch_thread.start()

    def _on_pretrain_fetch_done(self, latest, error) -> None:
        """最新数据拉取完成：更新本地数据后开始训练（离线失败则用本地数据继续）。"""
        if not error and latest is not None:
            try:
                self.current.update_data([latest])
            except Exception as exc:  # noqa: BLE001
                # 拉取到但保存失败：继续用本地数据训练，只记录日志
                logger.warning("保存最新一期数据失败: %s", exc)
            else:
                self.data_status_label.setText(self._data_status_text())
                self._refresh_data_stats()

        records = self.current.data_repository.get_all()
        if len(records) < 100:
            self._finish_training(ValueError("模型需要至少 100 期历史数据"))
            return

        model_class = getattr(self, "_train_model_class", None)
        prefix = getattr(self, "_train_prefix", "xgboost")
        backend = getattr(self, "_train_backend", "xgboost")
        lookback = compute_lookback(len(records))

        strategy_options = self.strategy_panel.current_options()
        model_path = new_model_path(
            records, lookback, prefix=prefix, options=strategy_options
        )

        dialog = getattr(self, "_train_dialog", None)
        if dialog is not None:
            dialog.set_stage("正在训练模型…")

        # 检查是否可以增量训练
        incremental = False
        new_count = 0
        if self.current.profile.key == "ssq":
            from ..ml.common.model_store import needs_incremental_update
            can_incremental, new_count = needs_incremental_update(
                records, lookback, prefix=prefix, options=strategy_options
            )
            if can_incremental and new_count > 0:
                incremental = True
                if dialog is not None:
                    dialog.set_stage(f"增量训练中（{new_count} 条新数据）…")
                logger.info("使用增量训练，新增 %d 条记录", new_count)

        kwargs: dict = {
            "records": records,
            "lookback": lookback,
            "model_path": model_path,
            "prefix": prefix,
            "parent": self,
            "incremental": incremental,
            "new_count": new_count,
        }
        if self.current.profile.key == "ssq":
            kwargs["model_class"] = model_class or LotteryXGBoostModel
        else:
            kwargs["profile"] = self.current.profile
            kwargs["backend"] = backend

        self._xgboost_thread = TrainModelThread(**kwargs)
        if dialog is not None:
            self._xgboost_thread.progress.connect(
                dialog.set_progress, Qt.ConnectionType.QueuedConnection
            )
        self._xgboost_thread.result_ready.connect(
            self._on_training_done, Qt.ConnectionType.QueuedConnection
        )
        self._xgboost_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_xgboost_thread")
        )
        self._xgboost_thread.start()

    def _on_training_done(self, success, error) -> None:
        # 线程清理由 finished 信号统一处理，这里不操作线程对象
        self._finish_training(error)

    def _finish_training(self, error) -> None:
        """关闭进度窗口并回调训练发起方。"""
        dialog = getattr(self, "_train_dialog", None)
        if dialog is not None:
            dialog.mark_finished()
            dialog.close()
            dialog.deleteLater()
            self._train_dialog = None

        after = getattr(self, "_train_after", None)
        self._train_after = None
        if after is not None:
            after(error)

    def _train_xgboost_model(self) -> None:
        """点击「训练模型」：拉取最新数据并训练."""
        records = self.current.data_repository.get_all()
        if len(records) < 100:
            QMessageBox.warning(self, "数据不足", "模型需要至少 100 期历史数据")
            return

        self.train_xgboost_btn.setEnabled(False)
        prefix = self.current.profile.xgboost_prefix()
        if self.current.profile.key == "ssq":
            self._start_training(LotteryXGBoostModel, prefix, after=self._after_button_train)
        else:
            self._start_training(None, prefix, after=self._after_button_train, backend="xgboost")

    def _after_button_train(self, error) -> None:
        self.train_xgboost_btn.setEnabled(True)
        if error:
            QMessageBox.critical(self, "训练失败", f"模型训练失败:\n{error}")
        else:
            self.xgboost_status_label.setText(self._model_status_text())
            QMessageBox.information(self, "训练完成", "模型已训练完成并保存")

    def _delete_xgboost_model(self) -> None:
        """删除本地模型（同时删除 XGBoost 与 LightGBM）。"""
        prefixes = {
            self.current.profile.xgboost_prefix(),
            self.current.profile.lightgbm_prefix(),
        }
        model_dir = app_data_dir() / "models"
        model_files = []
        if model_dir.exists():
            for prefix in prefixes:
                model_files.extend(model_dir.glob(f"{prefix}_*.pkl"))
        if not model_files:
            QMessageBox.information(self, "提示", "没有可删除的模型")
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除 {len(model_files)} 个{self.current.profile.name}模型文件吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            failed = []
            for f in model_files:
                try:
                    f.unlink()
                except OSError as exc:
                    failed.append((f.name, str(exc)))
                meta = Path(str(f) + ".meta.json")
                if meta.exists():
                    try:
                        meta.unlink()
                    except OSError as exc:
                        failed.append((meta.name, str(exc)))
            self.xgboost_status_label.setText(self._model_status_text())
            if failed:
                details = "\n".join(f"{name}: {err}" for name, err in failed)
                QMessageBox.warning(self, "删除警告", f"以下文件删除失败：\n{details}")

    # ------------------------------------------------------------------ #
    # 设置
    # ------------------------------------------------------------------ #
    def _on_auto_update_changed(self, state: int) -> None:
        self.settings.auto_update_on_start = state == Qt.CheckState.Checked.value
        self.settings.sync()

    def _on_update_interval_changed(self, value: int) -> None:
        self.settings.auto_update_interval_days = value
        self.settings.sync()

    def _should_auto_update(self) -> bool:
        if not self.settings.auto_update_on_start:
            return False
        last_update = self.settings.last_data_update
        if not last_update:
            return True
        try:
            last = datetime.fromisoformat(last_update)
            interval = timedelta(days=self.settings.auto_update_interval_days)
            return datetime.now() - last >= interval
        except ValueError:
            return True

    def _perform_auto_update(self) -> None:
        """启动时检查并更新所有彩种的开奖数据（显示进度条对话框）。"""
        if self._should_auto_update():
            # 延迟执行，避免在构造函数中启动线程导致生命周期问题
            QTimer.singleShot(500, self._show_auto_update_dialog)
        else:
            # 即使不执行自动更新，也要显示今日开奖彩种提示
            QTimer.singleShot(500, self._show_today_draws)

    def _show_auto_update_dialog(self) -> None:
        """显示自动更新对话框."""
        dialog = AutoUpdateDialog(self)
        dialog.update_finished.connect(self._on_auto_update_dialog_closed)
        dialog.exec()

    def _on_auto_update_dialog_closed(self) -> None:
        """自动更新对话框关闭后刷新界面并显示今日开奖彩种."""
        self._refresh_data_stats()
        self.data_status_label.setText(self._data_status_text(offline=False))
        self.xgboost_status_label.setText(self._model_status_text())
        # 显示今日开奖彩种提示
        self._show_today_draws()

    def _show_today_draws(self) -> None:
        """显示今日开奖彩种提示小窗口."""
        dialog = TodayDrawsDialog(self)
        dialog.exec()

    def _show_latest_results(self) -> None:
        """显示所有彩种最近一次开奖结果."""
        dialog = LatestResultsDialog(self)
        dialog.exec()

    def _start_auto_update(self) -> None:
        """实际启动自动更新线程."""
        if getattr(self, "_latest_update_thread", None) is not None:
            return

        # 不设置 parent，避免 MainWindow 销毁时自动 delete 仍在运行的线程
        self._latest_update_thread = FetchLatestDataThread(
            profile=self.current.profile
        )
        self._latest_update_thread.result_ready.connect(
            self._on_latest_update_finished, Qt.ConnectionType.QueuedConnection
        )
        self._latest_update_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_latest_update_thread")
        )
        self._latest_update_thread.start()

    def _on_latest_update_finished(self, latest, error) -> None:
        """自动更新完成回调（静默处理失败）。"""
        if error or latest is None:
            self.data_status_label.setText(self._data_status_text(offline=True))
            return

        try:
            local_latest = self.current.data_repository.get_latest()
            if local_latest is None or latest.draw_date > local_latest.draw_date:
                self.current.update_data([latest])
                self.settings.last_data_update = datetime.now().isoformat()
                self.settings.sync()
                self.data_status_label.setText(self._data_status_text(offline=False))
                self._refresh_data_stats()
                self.xgboost_status_label.setText(self._model_status_text())
            else:
                self.settings.last_data_update = datetime.now().isoformat()
                self.settings.sync()
                self.data_status_label.setText(self._data_status_text(offline=False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("自动更新处理失败: %s", exc)
            self.data_status_label.setText(self._data_status_text(offline=True))

    def _check_for_updates(self) -> None:
        """手动检查更新."""
        self.check_update_btn.setEnabled(False)
        self.data_progress.setVisible(True)

        # 如果旧线程仍在运行，只请求中断，不阻塞等待；它会在 finished 中自我清理
        old = getattr(self, "_latest_update_thread", None)
        if old is not None and old.isRunning():
            old.requestInterruption()

        self._latest_update_thread = FetchLatestDataThread(
            profile=self.current.profile
        )
        self._latest_update_thread.result_ready.connect(
            self._on_manual_update_finished, Qt.ConnectionType.QueuedConnection
        )
        self._latest_update_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_latest_update_thread")
        )
        self._latest_update_thread.start()

    def _on_manual_update_finished(self, latest, error) -> None:
        self.check_update_btn.setEnabled(True)
        self.data_progress.setVisible(False)

        # 清理线程对象由 finished 信号统一处理，这里不再重复 deleteLater

        if error or latest is None:
            QMessageBox.warning(
                self, "检查失败", f"无法连接到数据源，当前为离线模式。\n错误: {error}"
            )
            self.data_status_label.setText(self._data_status_text(offline=True))
            return

        try:
            local_latest = self.current.data_repository.get_latest()
            if local_latest is None or latest.draw_date > local_latest.draw_date:
                self.current.update_data([latest])
                self.settings.last_data_update = datetime.now().isoformat()
                self.settings.sync()
                self.data_status_label.setText(self._data_status_text(offline=False))
                self._refresh_data_stats()
                self.xgboost_status_label.setText(self._model_status_text())
                QMessageBox.information(
                    self,
                    "更新成功",
                    self._latest_draw_message(latest),
                )
            else:
                self.settings.last_data_update = datetime.now().isoformat()
                self.settings.sync()
                self.data_status_label.setText(self._data_status_text(offline=False))
                QMessageBox.information(self, "已是最新", f"当前数据已是最新一期 {local_latest.issue}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存开奖数据失败:\n{exc}")
            self.data_status_label.setText(self._data_status_text(offline=True))

    # ------------------------------------------------------------------ #
    # 菜单
    # ------------------------------------------------------------------ #
    def _setup_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")

        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 彩种菜单：按福利彩票/体育彩票分组，当前均为福利彩票
        lottery_menu = menubar.addMenu("彩种")
        for category, profiles in list_profiles_by_category().items():
            visible = [p for p in profiles if p.key not in NAV_HIDDEN_PROFILE_KEYS]
            category_menu = lottery_menu.addMenu(category_label(category))
            if not visible:
                placeholder = QAction("暂无", self)
                placeholder.setEnabled(False)
                category_menu.addAction(placeholder)
                continue
            for p in visible:
                action = QAction(p.name, self)
                action.setToolTip(f"切换到{p.name} ({p.subtitle})")
                action.triggered.connect(
                    lambda _checked=False, key=p.key: self._switch_to_lottery(key)
                )
                category_menu.addAction(action)

        tools_menu = menubar.addMenu("工具")

        today_draws_action = QAction("今日开奖彩种", self)
        today_draws_action.setToolTip("查看今日会开奖的彩种列表。")
        today_draws_action.triggered.connect(self._show_today_draws)
        tools_menu.addAction(today_draws_action)

        latest_results_action = QAction("最近开奖结果", self)
        latest_results_action.setToolTip("查看各彩种最近一次的开奖结果。")
        latest_results_action.triggered.connect(self._show_latest_results)
        tools_menu.addAction(latest_results_action)

        tools_menu.addSeparator()

        backtest_action = QAction("历史回测", self)
        backtest_action.setToolTip("选择历史开奖日期，用策略基于当时已知数据预测并对比真实结果。")
        backtest_action.triggered.connect(self._show_backtest_dialog)
        tools_menu.addAction(backtest_action)

        batch_backtest_action = QAction("批量历史回测", self)
        batch_backtest_action.setToolTip(
            "对一段日期区间逐期回测，自动为每个日期重新训练模型并汇总盈亏。"
        )
        batch_backtest_action.triggered.connect(self._show_batch_backtest_dialog)
        tools_menu.addAction(batch_backtest_action)

        backtest_history_action = QAction("回测记录", self)
        backtest_history_action.setToolTip("查看已保存的单期/批量回测结果。")
        backtest_history_action.triggered.connect(self._show_backtest_history_dialog)
        tools_menu.addAction(backtest_history_action)

        draw_analysis_action = QAction("开奖记录分析", self)
        draw_analysis_action.setToolTip(
            "查看开奖记录，并统计相邻两期之间红球/蓝球的重合情况。"
        )
        draw_analysis_action.triggered.connect(self._show_draw_analysis_dialog)
        tools_menu.addAction(draw_analysis_action)

        help_menu = menubar.addMenu("帮助")

        lottery_guide_action = QAction("彩种介绍", self)
        lottery_guide_action.setToolTip(
            "查看全部彩种（福利彩票：双色球/福彩3D/七乐彩/快乐8；"
            "体育彩票：超级大乐透/排列3/排列5/7星彩/广东36选7）的玩法规则与策略说明。"
        )
        lottery_guide_action.triggered.connect(
            lambda: self._show_doc("彩种介绍", "lottery_guide.md")
        )
        help_menu.addAction(lottery_guide_action)

        guide_action = QAction("学习文档", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.setToolTip("打开概率统计与机器学习学习文档（本窗口内查看）。")
        guide_action.triggered.connect(self._show_learning_guide)
        help_menu.addAction(guide_action)

        for label, filename in (
            ("使用帮助", "help.md"),
            ("XGBoost 使用教程", "XGBoost_TUTORIAL.md"),
            ("LightGBM 使用教程", "LightGBM_TUTORIAL.md"),
            ("CatBoost 使用教程", "CatBoost_TUTORIAL.md"),
            ("XGBoost 采样说明", "XGBoost_SAMPLING.md"),
        ):
            doc_action = QAction(label, self)
            doc_action.setToolTip(f"在内置阅读器中查看 {filename}")
            doc_action.triggered.connect(
                lambda _checked=False, t=label, f=filename: self._show_doc(t, f)
            )
            help_menu.addAction(doc_action)

        help_menu.addSeparator()
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        """创建顶部工具栏，集中放置常用生成操作."""
        self.toolbar = QToolBar("主工具栏", self)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        resources_dir = Path(__file__).resolve().parent / "resources" / "toolbar"

        def _load_icon(name: str) -> QIcon:
            path = resources_dir / f"{name}.png"
            if path.exists():
                return QIcon(str(path))
            return QIcon()

        actions = [
            ("today", "今日开奖", "查看今日会开奖的彩种列表。", self._show_today_draws),
            ("results", "最近开奖", "查看各彩种最近一次的开奖结果。", self._show_latest_results),
            ("generate", "立即生成", "根据当前策略生成号码。ML 策略首次会训练模型，请稍候。", self._generate),
            ("copy", "复制全部号码", "将生成的号码复制到剪贴板。", self._copy_all),
            ("print", "打印结果", "将生成的号码打印或导出为 PDF。", self._print_results),
            ("pdf", "导出 PDF", "将生成的号码导出为 PDF 文件，不依赖打印机驱动。", self._export_pdf_results),
            ("save", "保存到历史", "将本次生成的号码保存到本地历史记录。", self._save_to_history),
        ]

        for name, text, tooltip, slot in actions:
            action = QAction(_load_icon(name), text, self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
            setattr(self, f"{name}_action", action)

    # ------------------------------------------------------------------ #
    # 号码生成
    # ------------------------------------------------------------------ #
    def _generate(self) -> None:
        strategy_id = self.strategy_panel.current_strategy_id()
        if not strategy_id:
            QMessageBox.warning(self, "提示", "请选择一个生成策略")
            return

        try:
            options = self.strategy_panel.current_options()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        count = self.count_spin.value()

        # 保存用户设置
        user_options = {k: v for k, v in options.items() if k != "history"}
        self.settings.last_strategy_id = strategy_id
        options["_strategy_id"] = strategy_id  # 传递策略ID供过滤判断
        self.settings.default_count = count
        self.settings.last_strategy_options = user_options
        history_count = options.get("history_count", -1)
        self.settings.last_history_count = history_count
        self.settings.sync()

        # 需要历史记录的策略自动注入数据
        records: list[Any] = []
        if needs_history(strategy_id):
            records = self.current.data_repository.get_all()
            if not records:
                QMessageBox.warning(self, "缺少数据", "该策略需要官方开奖数据，请先更新数据。")
                return
            if isinstance(history_count, int) and history_count > 0:
                records = records[-history_count:]
            options["history"] = records

        # 保存实际用于训练的历史期数，供模型文件名使用
        options["_training_record_count"] = len(options.get("history", records))

        # 注入 draw records 和过滤参数供最后一层过滤使用
        profile_key = self.current.profile.key
        options["profile_key"] = profile_key  # 供策略（如八卦占卜）识别目标彩种
        if profile_key == "ssq":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_ssq_compare_periods"] = self.settings.ssq_filter_compare_periods
                options["_ssq_max_red_overlap"] = self.settings.ssq_filter_max_red_overlap
                options["_ssq_block_blue"] = self.settings.ssq_filter_block_blue
                options["_ssq_blue_periods"] = self.settings.ssq_filter_compare_periods
        elif profile_key == "3d":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_fc3d_filter_enabled"] = self.settings.fc3d_filter_enabled
                options["_fc3d_filter_compare_periods"] = self.settings.fc3d_filter_compare_periods
                options["_fc3d_filter_max_overlap"] = self.settings.fc3d_filter_max_overlap
                options["_fc3d_filter_min_sum"] = self.settings.fc3d_filter_min_sum
                options["_fc3d_filter_max_sum"] = self.settings.fc3d_filter_max_sum
        elif profile_key == "qlc":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_qlc_filter_enabled"] = self.settings.qlc_filter_enabled
                options["_qlc_filter_compare_periods"] = self.settings.qlc_filter_compare_periods
                options["_qlc_filter_max_overlap"] = self.settings.qlc_filter_max_overlap
                options["_qlc_filter_min_sum"] = self.settings.qlc_filter_min_sum
                options["_qlc_filter_max_sum"] = self.settings.qlc_filter_max_sum
        elif profile_key == "dlt":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_dlt_filter_enabled"] = self.settings.dlt_filter_enabled
                options["_dlt_filter_compare_periods"] = self.settings.dlt_filter_compare_periods
                options["_dlt_filter_max_front_overlap"] = self.settings.dlt_filter_max_front_overlap
                options["_dlt_filter_block_back"] = self.settings.dlt_filter_block_back
                options["_dlt_filter_back_compare_periods"] = self.settings.dlt_filter_back_compare_periods
                options["_dlt_filter_min_front_sum"] = self.settings.dlt_filter_min_front_sum
                options["_dlt_filter_max_front_sum"] = self.settings.dlt_filter_max_front_sum

        self._generate_single_strategy(strategy_id, count, options)

    def _generate_single_strategy(
        self, strategy_id: str, count: int, options: dict, *, on_finished=None
    ) -> None:
        """为单个策略准备模型并启动生成（支持自定义完成回调）."""
        # ML 模型策略：若当前数据对应的模型已过期，先自动重新训练
        if self.current.profile.key == "ssq" and strategy_id in ML_MODEL_STRATEGIES:
            model_class, prefix = ML_MODEL_STRATEGIES[strategy_id]
            records = self.current.data_repository.get_all()
            lookback = compute_lookback(len(records))
            if not is_model_current(records, lookback, prefix=prefix):
                self.generate_action.setEnabled(False)
                self.generate_action.setText("准备模型...")
                self._start_training(
                    model_class,
                    prefix,
                    after=lambda err: self._after_generate_train(
                        err, strategy_id, count, options, on_finished=on_finished
                    ),
                )
                return
        elif self.current.profile.key != "ssq" and is_ml_strategy(strategy_id):
            # 仅对 xgboost/lightgbm/catboost 做模型缓存检查
            # random_forest/ensemble 等策略在生成时即时训练，无需缓存
            _cached_backends = ("xgboost_", "lightgbm_", "catboost_")
            if any(strategy_id.startswith(b) for b in _cached_backends):
                if strategy_id.startswith("xgboost_"):
                    backend = "xgboost"
                elif strategy_id.startswith("lightgbm_"):
                    backend = "lightgbm"
                else:
                    backend = "catboost"
                if backend == "xgboost":
                    prefix = self.current.profile.xgboost_prefix()
                elif backend == "lightgbm":
                    prefix = self.current.profile.lightgbm_prefix()
                else:
                    prefix = self.current.profile.catboost_prefix()
                records = self.current.data_repository.get_all()
                lookback = compute_lookback(len(records))
                if not is_model_current(records, lookback, prefix=prefix):
                    self.generate_action.setEnabled(False)
                    self.generate_action.setText("准备模型...")
                    self._start_training(
                        None,
                        prefix,
                        after=lambda err: self._after_generate_train(
                            err, strategy_id, count, options, on_finished=on_finished
                        ),
                        backend=backend,
                    )
                    return

        self._launch_generation(
            strategy_id, count, options, on_finished=on_finished
        )

    def _launch_generation(self, strategy_id, count, options, *, on_finished=None) -> None:
        """在后台线程启动号码生成."""
        self.generate_action.setEnabled(False)
        self.generate_action.setText("生成中...")
        self._generate_finished_callback = on_finished or self._on_generation_finished

        # LSTM/混合策略的 loss 窗口暂不显示（matplotlib 在 Windows 上导致堆损坏）
        self._loss_window = None

        self._generate_thread = GenerateTicketsThread(
            self.current.engine, strategy_id, count, options, self
        )
        self._generate_thread.result_ready.connect(
            self._on_generation_finished_wrapper, Qt.ConnectionType.QueuedConnection
        )
        self._generate_thread.progress.connect(self._on_generation_progress)
        self._generate_thread.finished.connect(
            partial(self._cleanup_finished_thread, "_generate_thread")
        )
        self._generate_thread.start()

    def _on_generation_progress(self, message: str) -> None:
        """更新生成进度信息."""
        self.generate_action.setText(message[:30])
        # 解析 loss 信息并更新曲线
        if self._loss_window and "loss=" in message:
            parts = message.split(":")
            if len(parts) >= 2:
                model_name = parts[0].strip()
                detail = parts[1].strip()
                if "epoch" in detail and "loss=" in detail:
                    try:
                        epoch_part = detail.split(",")[0].replace("epoch", "").strip()
                        epoch = int(epoch_part.split("/")[0])
                        loss_val = float(detail.split("loss=")[1])
                        self._loss_window.add_loss(model_name, epoch, loss_val)
                    except (ValueError, IndexError):
                        pass

    def _on_generation_finished_wrapper(self, tickets, error) -> None:
        """统一分发生成完成回调."""
        callback = getattr(self, "_generate_finished_callback", self._on_generation_finished)
        callback(tickets, error)

    def _after_generate_train(
        self, error, strategy_id, count, options, *, on_finished=None
    ) -> None:
        if error:
            self.generate_action.setEnabled(True)
            self.generate_action.setText("立即生成")
            QMessageBox.critical(self, "训练失败", f"模型训练失败:\n{error}")
            return
        records = self.current.data_repository.get_all()
        is_ml = is_ml_strategy(strategy_id) or strategy_id in ML_MODEL_STRATEGIES
        if is_ml and len(records) < 100:
            self.generate_action.setEnabled(True)
            self.generate_action.setText("立即生成")
            QMessageBox.warning(self, "数据不足", "训练后历史数据不足 100 期，无法使用 ML 策略")
            return
        if needs_history(strategy_id) and len(records) < 20:
            self.generate_action.setEnabled(True)
            self.generate_action.setText("立即生成")
            QMessageBox.warning(self, "数据不足", "训练后历史数据不足 20 期，无法使用该策略")
            return
        options["history"] = records
        self._generate_single_strategy(
            strategy_id, count, options, on_finished=on_finished
        )

    def _on_generation_finished(self, tickets, error) -> None:
        """号码生成完成回调."""
        self.generate_action.setEnabled(True)
        self.generate_action.setText("立即生成")

        # 关闭 loss 曲线窗口
        if hasattr(self, "_loss_window") and self._loss_window:
            self._loss_window.close()
            self._loss_window = None

        if error:
            QMessageBox.critical(self, "生成失败", str(error))
            return

        self._last_generated = tickets
        self._annotate_target_period(tickets)
        self._display_results(tickets)
        try:
            self.history_manager.add_many(tickets)
            self.history_panel.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存历史失败", f"保存到历史记录失败:\n{exc}")

    def _generate_from_parameter_group(self, items: list) -> None:
        """根据参数组中启用的策略顺序生成号码."""
        if not items:
            QMessageBox.warning(self, "提示", "请至少启用一个策略")
            return

        self._parameter_group_items = list(items)
        self._parameter_group_tickets: list = []
        self._parameter_group_errors: list[str] = []
        self._parameter_group_count = self.parameter_group_panel.count_spin.value()

        self.generate_action.setEnabled(False)
        self.generate_action.setText("参数组生成中...")
        self._run_next_parameter_group_item()

    def _run_next_parameter_group_item(self) -> None:
        """处理参数组中的下一个启用策略."""
        if not self._parameter_group_items:
            self._finish_parameter_group_generation()
            return

        item = self._parameter_group_items.pop(0)
        strategy_id = item.strategy_id

        strategy = self.current.engine.get(strategy_id)
        if strategy is None:
            self._parameter_group_errors.append(
                f"策略 {item.strategy_name} 已不可用，已跳过"
            )
            self._run_next_parameter_group_item()
            return

        options: dict = {}
        if item.param_name is not None and item.param_value is not None:
            options[item.param_name] = item.param_value

        count = self._parameter_group_count

        # 复用历史数据注入逻辑
        records: list[Any] = []
        if needs_history(strategy_id):
            records = self.current.data_repository.get_all()
            if not records:
                self._parameter_group_errors.append(
                    f"{item.strategy_name}: 缺少历史数据"
                )
                self._run_next_parameter_group_item()
                return
            options["history"] = records

        options["_training_record_count"] = len(options.get("history", records))

        # 注入 draw records 和过滤参数供最后一层过滤使用
        profile_key = self.current.profile.key
        options["profile_key"] = profile_key  # 供策略（如八卦占卜）识别目标彩种
        if profile_key == "ssq":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_ssq_compare_periods"] = self.settings.ssq_filter_compare_periods
                options["_ssq_max_red_overlap"] = self.settings.ssq_filter_max_red_overlap
                options["_ssq_block_blue"] = self.settings.ssq_filter_block_blue
                options["_ssq_blue_periods"] = self.settings.ssq_filter_compare_periods
        elif profile_key == "3d":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_fc3d_filter_enabled"] = self.settings.fc3d_filter_enabled
                options["_fc3d_filter_compare_periods"] = self.settings.fc3d_filter_compare_periods
                options["_fc3d_filter_max_overlap"] = self.settings.fc3d_filter_max_overlap
                options["_fc3d_filter_min_sum"] = self.settings.fc3d_filter_min_sum
                options["_fc3d_filter_max_sum"] = self.settings.fc3d_filter_max_sum
        elif profile_key == "qlc":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_qlc_filter_enabled"] = self.settings.qlc_filter_enabled
                options["_qlc_filter_compare_periods"] = self.settings.qlc_filter_compare_periods
                options["_qlc_filter_max_overlap"] = self.settings.qlc_filter_max_overlap
                options["_qlc_filter_min_sum"] = self.settings.qlc_filter_min_sum
                options["_qlc_filter_max_sum"] = self.settings.qlc_filter_max_sum
        elif profile_key == "dlt":
            draw_records = self.current.data_repository.get_all()
            if draw_records:
                options["_profile_key"] = profile_key
                options["_draw_records"] = draw_records
                options["_dlt_filter_enabled"] = self.settings.dlt_filter_enabled
                options["_dlt_filter_compare_periods"] = self.settings.dlt_filter_compare_periods
                options["_dlt_filter_max_front_overlap"] = self.settings.dlt_filter_max_front_overlap
                options["_dlt_filter_block_back"] = self.settings.dlt_filter_block_back
                options["_dlt_filter_back_compare_periods"] = self.settings.dlt_filter_back_compare_periods
                options["_dlt_filter_min_front_sum"] = self.settings.dlt_filter_min_front_sum
                options["_dlt_filter_max_front_sum"] = self.settings.dlt_filter_max_front_sum

        # 使用新的生成接口，指定回调以继续队列
        self._generate_single_strategy(
            strategy_id,
            count,
            options,
            on_finished=lambda tickets, error: self._on_parameter_group_item_finished(
                item, tickets, error
            ),
        )

    def _on_parameter_group_item_finished(
        self, item, tickets, error
    ) -> None:
        """单个策略生成完成，追加结果并继续下一个."""
        if error:
            self._parameter_group_errors.append(f"{item.strategy_name}: {error}")
        elif tickets:
            for ticket in tickets:
                ticket.strategy_name = item.strategy_name
                if ticket.basis:
                    ticket.basis = f"{item.strategy_name} | {ticket.basis}"
                else:
                    ticket.basis = item.strategy_name
            self._parameter_group_tickets.extend(tickets)

        self._run_next_parameter_group_item()

    def _finish_parameter_group_generation(self) -> None:
        """参数组所有策略生成完成，汇总展示结果."""
        self.generate_action.setEnabled(True)
        self.generate_action.setText("立即生成")

        tickets = self._parameter_group_tickets
        if not tickets:
            QMessageBox.warning(
                self,
                "生成失败",
                "参数组中所有策略均未能生成号码。\n"
                + "\n".join(self._parameter_group_errors[:5]),
            )
            return

        self._last_generated = tickets
        self._annotate_target_period(tickets)
        self._display_results(tickets)
        try:
            self.history_manager.add_many(tickets)
            self.history_panel.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存历史失败", f"保存到历史记录失败:\n{exc}")

        if self._parameter_group_errors:
            QMessageBox.information(
                self,
                "部分策略未生成",
                "以下策略生成时出现问题：\n"
                + "\n".join(self._parameter_group_errors[:10]),
            )

    def _annotate_target_period(self, tickets: list) -> None:
        if not tickets:
            return
        info = self.current.data_repository.next_period_info()
        if not info:
            return
        next_date = info.get("next_date")
        if not next_date:
            return
        meta = {
            "target_issue": info["next_issue"],
            "target_date": next_date.strftime("%Y-%m-%d"),
            "base_issue": info["base_issue"],
            "base_date": info["base_date"].strftime("%Y-%m-%d"),
            "stale": next_date.date() < datetime.now().date(),
        }
        for ticket in tickets:
            ticket.details.update(meta)

    @staticmethod
    def _format_target_lines(details: dict) -> list[str]:
        target_date = details.get("target_date")
        if not target_date:
            return []
        lines: list[str] = []
        tdate = datetime.strptime(target_date, "%Y-%m-%d")
        target_issue = details.get("target_issue")
        issue_txt = f"第 {target_issue} 期" if target_issue else "下一期"
        lines.append(
            f"预测目标：{issue_txt}（预计开奖 {target_date} 周{_WEEKDAY_CN[tdate.weekday()]}）"
        )
        base_date = details.get("base_date")
        base_issue = details.get("base_issue")
        if base_date:
            bdate = datetime.strptime(base_date, "%Y-%m-%d")
            base_txt = f"第 {base_issue} 期" if base_issue else ""
            lines.append(
                f"基于最新数据：{base_txt}（{base_date} 周{_WEEKDAY_CN[bdate.weekday()]}）"
            )
        if details.get("stale"):
            lines.append("⚠ 预计开奖日期已过，请先更新最新开奖数据后再生成！")
        return lines

    def _display_results(self, tickets: list) -> None:
        # 清空可视化结果
        while self.result_container_layout.count() > 1:
            item = self.result_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        details = tickets[0].details if tickets else {}
        target_lines = self._format_target_lines(details)
        if target_lines:
            self.target_label.setText("\n".join(target_lines))
            self.target_label.setStyleSheet(
                "color:#D32F2F;font-weight:bold;" if details.get("stale") else "color:#333;"
            )
            self.target_label.setVisible(True)
        else:
            self.target_label.clear()
            self.target_label.setVisible(False)

        # 计算概率信息（仅福彩3D），一次计算供标签和文本共用
        fc3d_prob = None
        if tickets and tickets[0].profile.key == "3d":
            fc3d_prob = self._calc_fc3d_probability(tickets)
            label_lines = [
                f"🎯 覆盖概率：{fc3d_prob['total_coverage']}/1000 = {fc3d_prob['abs_p']:.2f}%"
                f"（{fc3d_prob['breakdown']}）"
            ]
            if fc3d_prob["confidence"] is not None:
                label_lines.append(
                    f"策略置信度（仅供参考，非实际中奖概率）：{fc3d_prob['confidence']:.4f}%"
                )
            label_lines.append(
                f"期望收益：≈{fc3d_prob['expected_return']:.2f}元"
                f"（投入{fc3d_prob['total_cost']}元，返奖率≈{fc3d_prob['return_rate']:.0f}%）"
            )
            self.probability_label.setText("\n".join(label_lines))
            self.probability_label.setVisible(True)
        else:
            self.probability_label.setVisible(False)

        text_lines = []
        for idx, ticket in enumerate(tickets, start=1):
            line = f"{idx:02d}. {ticket.format_compact()}"
            if ticket.profile.key == "3d":
                line += f"  [{fc3d_bet_type(ticket.groups.get('pos', []))}]"
            if ticket.basis:
                line += f"  [{ticket.basis}]"
            text_lines.append(line)
            row = TicketRowWidget(ticket, show_index=idx)
            self.result_container_layout.insertWidget(idx - 1, row)

        self._last_chart_details = self._build_chart_details(details)
        self.chart_btn.setVisible(bool(self._last_chart_details))

        header = target_lines + ["-" * 30] if target_lines else []
        if fc3d_prob:
            header.append(
                f"覆盖概率：{fc3d_prob['total_coverage']}/1000 = {fc3d_prob['abs_p']:.2f}%"
                f"（{fc3d_prob['breakdown']}）"
            )
            if fc3d_prob["confidence"] is not None:
                header.append(f"策略置信度（仅供参考）：{fc3d_prob['confidence']:.4f}%")
            header.append(
                f"期望收益：≈{fc3d_prob['expected_return']:.2f}元"
                f"（投入{fc3d_prob['total_cost']}元，返奖率≈{fc3d_prob['return_rate']:.0f}%）"
            )
        self.result_text.setText("\n".join(header + text_lines))

        # 填充可编辑号码列表（仅福彩3D）
        self._populate_editable_numbers(tickets)

    # ------------------------------------------------------------------ #
    # 福彩3D 概率计算
    # ------------------------------------------------------------------ #

    # FC3D 奖金（元）
    _FC3D_PRIZE_ZHI = 1040    # 直选
    _FC3D_PRIZE_Z3 = 346      # 组选3
    _FC3D_PRIZE_Z6 = 173      # 组选6
    _FC3D_TICKET_COST = 2     # 每注成本

    @staticmethod
    def _fc3d_display_label(ticket) -> str:
        """3D 号码的展示标签：按投注方式，组选票附带形态（组选3/组选6）。"""
        nums = ticket.groups.get("pos", [])
        bet_mode = ticket.details.get("bet_mode")
        if bet_mode == "直选":
            return "直选"
        if bet_mode == "组选":
            unique = len(set(nums))
            if unique == 2:
                return "组选3"
            if unique == 3:
                return "组选6"
            return "直选"  # 豹子号兜底（生成时已转直选，正常不会到这里）
        return fc3d_bet_type(nums)

    @staticmethod
    def _calc_fc3d_probability(tickets: list) -> dict:
        """计算福彩3D概率信息（公平、去重、含期望收益）。

        - 覆盖概率按投注方式计算：直选票覆盖 1 个号码；组选票按形态，
          组选6 覆盖 6 个号码，组选3 覆盖 3 个，豹子覆盖 1 个。
        - 对排序后相同的号码集合自动去重，避免 coverage 重叠虚高。
        - 策略置信度仅在策略提供 pos_probabilities 时计算，本质是策略的自评，
          非实际中奖概率。

        Returns:
            dict:
            - total_coverage: 去重后总覆盖号码数
            - abs_p: 覆盖概率（%）
            - breakdown: 注数分布描述（如 "直选×10 组选6×9 组选3×1"）
            - confidence: 策略置信度（%），无 pos_probabilities 时为 None
            - expected_return: 期望收益（元）
            - total_cost: 总投入（元）
            - return_rate: 返奖率（%）
            - unique_count: 去重后不重复注数
            - ticket_count: 原始注数
        """
        seen_sets: set = set()
        total_coverage = 0
        confidence = 0.0
        count_zhi = count_z6 = count_z3 = count_bz = 0

        pos_probs = tickets[0].details.get("pos_probabilities") if tickets else None
        has_valid_probs = (
            bool(pos_probs)
            and len(pos_probs) == 3
            and all(len(p) == 10 for p in pos_probs)
        )

        for t in tickets:
            digits = t.groups.get("pos", [])
            if len(digits) != 3:
                continue
            key = tuple(sorted(digits))
            if key in seen_sets:
                continue
            seen_sets.add(key)

            bet_mode = t.details.get("bet_mode")
            unique = len(set(digits))
            if bet_mode == "直选":
                total_coverage += 1
                count_zhi += 1
            elif unique == 3:
                total_coverage += 6
                count_z6 += 1
            elif unique == 2:
                total_coverage += 3
                count_z3 += 1
            else:
                total_coverage += 1
                count_bz += 1

            if has_valid_probs:
                confidence += sum(
                    pos_probs[0][p[0]] * pos_probs[1][p[1]] * pos_probs[2][p[2]]
                    for p in set(permutations(digits))
                )

        abs_p = total_coverage / 1000 * 100

        # 期望收益 = Σ(每种注数 × 中奖概率 × 奖金)，按投注方式区分
        expected_return = (
            count_zhi * (1 / 1000 * MainWindow._FC3D_PRIZE_ZHI)
            + count_z6 * (6 / 1000 * MainWindow._FC3D_PRIZE_Z6)
            + count_z3 * (3 / 1000 * MainWindow._FC3D_PRIZE_Z3)
            + count_bz * (1 / 1000 * MainWindow._FC3D_PRIZE_ZHI)
        )
        total_cost = len(tickets) * MainWindow._FC3D_TICKET_COST
        return_rate = (expected_return / total_cost * 100) if total_cost > 0 else 0.0

        parts = []
        if count_zhi:
            parts.append(f"直选×{count_zhi}")
        if count_z6:
            parts.append(f"组选6×{count_z6}")
        if count_z3:
            parts.append(f"组选3×{count_z3}")
        if count_bz:
            parts.append(f"豹子×{count_bz}")
        breakdown = " ".join(parts) if parts else "无"

        confidence_pct = round(confidence * 100, 4) if has_valid_probs else None

        return {
            "total_coverage": total_coverage,
            "abs_p": abs_p,
            "breakdown": breakdown,
            "confidence": confidence_pct,
            "expected_return": round(expected_return, 2),
            "total_cost": total_cost,
            "return_rate": round(return_rate, 1),
            "unique_count": len(seen_sets),
            "ticket_count": len(tickets),
        }

    @staticmethod
    def _build_chart_details(details: dict) -> dict | None:
        """把 details 中的概率信息整理成图表可用的字典."""
        if details.get("group_probabilities"):
            return {
                "group_probabilities": details["group_probabilities"],
                "lookback": details.get("lookback", "-"),
                "diversity_boost": details.get("diversity_boost", "-"),
                "model_name": "XGBoost" if "xgboost" in str(details) else "LightGBM",
            }
        if details.get("red_probabilities"):
            return {
                "red_probabilities": details["red_probabilities"],
                "blue_probabilities": details["blue_probabilities"],
                "lookback": details.get("lookback", "-"),
                "diversity_boost": details.get("diversity_boost", "-"),
            }
        return None

    def _show_probability_chart(self) -> None:
        """在独立窗口中显示更大的概率折线图."""
        details = getattr(self, "_last_chart_details", None)
        if not details:
            QMessageBox.information(self, "提示", "当前没有可查看的概率图表。")
            return
        dialog = ProbabilityChartDialog(details, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._chart_dialog = dialog
        dialog.show()

    @staticmethod
    def _build_probability_details_html(details: dict) -> str:
        if details.get("group_probabilities"):
            return build_group_probability_charts_html(
                group_probabilities=details["group_probabilities"],
                lookback=details.get("lookback", "-"),
                diversity_boost=details.get("diversity_boost", "-"),
                model_name=details.get("model_name", "XGBoost"),
            )
        return build_probability_charts_html(
            red_probabilities=details.get("red_probabilities", []),
            blue_probabilities=details.get("blue_probabilities", []),
            lookback=details.get("lookback", "-"),
            diversity_boost=details.get("diversity_boost", "-"),
        )

    @staticmethod
    def _build_probability_details_html_for_print(details: dict) -> str:
        return MainWindow._build_probability_details_html(details)

    # ------------------------------------------------------------------ #
    # 复制/打印/导出
    # ------------------------------------------------------------------ #
    def _copy_all(self) -> None:
        text = self.result_text.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "提示", "没有可复制的号码")
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text, QClipboard.Mode.Clipboard)
        QMessageBox.information(self, "复制成功", "号码已复制到剪贴板")

    # ------------------------------------------------------------------ #
    # 福彩3D可编辑号码列表
    # ------------------------------------------------------------------ #
    def _populate_editable_numbers(self, tickets: list) -> None:
        """将生成的号码填充到可编辑列表（所有彩种通用）."""
        if not tickets:
            self.editable_numbers_group.setVisible(False)
            return

        self.editable_numbers_group.setVisible(True)
        self._editable_tickets = list(tickets)

        # 仅福彩3D/排列3 支持 组选/直选，显示筛选复选框；
        # 排列5/7星彩为按位直选，无组选/豹子概念，不显示。
        is_fc3d = tickets[0].profile.key in ("3d", "pl3")
        self.filter_layout_container.setVisible(is_fc3d)

        # 更新输入框占位符
        profile = tickets[0].profile
        if profile.key in ("3d", "pl3"):
            self.add_number_input.setPlaceholderText("输入3位数字（如 123）")
            self.add_number_input.setMaxLength(3)
        elif profile.key == "pl5":
            self.add_number_input.setPlaceholderText("输入5位数字（如 12345）")
            self.add_number_input.setMaxLength(5)
        elif profile.key == "qxc":
            self.add_number_input.setPlaceholderText("输入7位数字（如 1234567）")
            self.add_number_input.setMaxLength(7)
        elif profile.key == "ssq":
            self.add_number_input.setPlaceholderText("红球:1,2,3,4,5,6 蓝球:1")
            self.add_number_input.setMaxLength(30)
        elif profile.key == "dlt":
            self.add_number_input.setPlaceholderText("前区:1,2,3,4,5 后区:1,2")
            self.add_number_input.setMaxLength(30)
        elif profile.key == "qlc":
            self.add_number_input.setPlaceholderText("基本号:1,2,3,4,5,6,7")
            self.add_number_input.setMaxLength(30)
        elif profile.key == "kl8":
            self.add_number_input.setPlaceholderText("号码:1,2,3,...,10（1-10个）")
            self.add_number_input.setMaxLength(30)
        else:
            self.add_number_input.setPlaceholderText("输入号码")
            self.add_number_input.setMaxLength(30)

        self._refresh_editable_table()

    def _refresh_editable_table(self) -> None:
        """刷新可编辑号码表格（所有彩种通用）."""
        if not hasattr(self, "_editable_tickets"):
            return

        # 断开旧信号避免重复触发
        try:
            self.editable_numbers_table.cellChanged.disconnect(self._on_number_edited)
        except (TypeError, RuntimeError):
            pass

        profile_key = self._editable_tickets[0].profile.key if self._editable_tickets else ""

        # 根据筛选条件过滤（仅福彩3D/排列3 有组选/豹子形态）
        if profile_key in ("3d", "pl3"):
            show_zu6 = self.filter_zu6_check.isChecked()
            show_zu3 = self.filter_zu3_check.isChecked()
            show_baozi = self.filter_baozi_check.isChecked()

            filtered_tickets = []
            for ticket in self._editable_tickets:
                nums = ticket.groups.get("pos", [])
                bet_type = fc3d_bet_type(nums)
                if bet_type == "组选6" and show_zu6:
                    filtered_tickets.append(ticket)
                elif bet_type == "组选3" and show_zu3:
                    filtered_tickets.append(ticket)
                elif bet_type == "豹子号" and show_baozi:
                    filtered_tickets.append(ticket)
            self.filter_count_label.setText(f"共 {len(filtered_tickets)} 注")
        else:
            filtered_tickets = self._editable_tickets
            self.filter_count_label.setText(f"共 {len(filtered_tickets)} 注")

        # 填充表格
        self.editable_numbers_table.setRowCount(len(filtered_tickets))
        for idx, ticket in enumerate(filtered_tickets):
            # 格式化号码显示
            num_str = self._format_ticket_display(ticket)

            # 类型标签
            bet_type = self._get_ticket_type_label(ticket)

            # 序号
            item_idx = QTableWidgetItem(str(idx + 1))
            item_idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_idx.setFlags(item_idx.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.editable_numbers_table.setItem(idx, 0, item_idx)

            # 号码（可编辑）
            item_num = QTableWidgetItem(num_str)
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.editable_numbers_table.setItem(idx, 1, item_num)

            # 类型（只读）
            item_type = QTableWidgetItem(bet_type)
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_type.setFlags(item_type.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.editable_numbers_table.setItem(idx, 2, item_type)

            # 删除按钮
            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(60)
            del_btn.clicked.connect(lambda checked, row=idx: self._delete_number(row))
            self.editable_numbers_table.setCellWidget(idx, 3, del_btn)

        # 重新连接信号
        self.editable_numbers_table.cellChanged.connect(self._on_number_edited)

    def _format_ticket_display(self, ticket) -> str:
        """格式化ticket的号码显示（通用）."""
        profile_key = ticket.profile.key
        if profile_key in ("3d", "pl3", "pl5", "qxc"):
            nums = ticket.groups.get("pos", [])
            return "".join(str(n) for n in nums)
        elif profile_key == "ssq":
            reds = ticket.groups.get("red", [])
            blues = ticket.groups.get("blue", [])
            red_str = ",".join(f"{n:02d}" for n in reds)
            blue_str = ",".join(f"{n:02d}" for n in blues)
            return f"红{red_str} 蓝{blue_str}"
        elif profile_key == "dlt":
            fronts = ticket.groups.get("front", [])
            backs = ticket.groups.get("back", [])
            front_str = ",".join(f"{n:02d}" for n in fronts)
            back_str = ",".join(f"{n:02d}" for n in backs)
            return f"前{front_str} 后{back_str}"
        elif profile_key == "qlc":
            basics = ticket.groups.get("basic", [])
            return ",".join(f"{n:02d}" for n in basics)
        elif profile_key == "kl8":
            mains = ticket.groups.get("main", [])
            return ",".join(f"{n:02d}" for n in mains)
        return ticket.format_compact()

    def _get_ticket_type_label(self, ticket) -> str:
        """获取ticket的类型标签（通用）."""
        profile_key = ticket.profile.key
        if profile_key in ("3d", "pl3"):
            return MainWindow._fc3d_display_label(ticket)
        if profile_key in ("pl5", "qxc"):
            return "直选"
        elif profile_key == "ssq":
            return "红+蓝"
        elif profile_key == "dlt":
            return "前+后"
        elif profile_key == "qlc":
            return "基本号"
        elif profile_key == "kl8":
            return "选号"
        return ""

    def _on_filter_changed(self) -> None:
        """筛选复选框变化时刷新表格."""
        self._refresh_editable_table()

    def _on_number_edited(self, row: int, col: int) -> None:
        """号码编辑完成后的处理（通用）."""
        if col != 1:  # 只处理号码列
            return
        item = self.editable_numbers_table.item(row, 1)
        if item is None:
            return
        new_num = item.text().strip()
        if 0 > row or row >= len(self._editable_tickets):
            return

        ticket = self._editable_tickets[row]
        profile_key = ticket.profile.key

        # 解析输入并更新
        try:
            if profile_key in ("3d", "pl3", "pl5", "qxc"):
                if not new_num.isdigit():
                    raise ValueError
                nums = [int(c) for c in new_num]
                expected = ticket.profile.group("pos").count
                if len(nums) != expected:
                    QMessageBox.warning(self, "输入错误", f"请输入{expected}位数字（0-9）")
                    self._refresh_editable_table()
                    return
                ticket.groups["pos"] = nums
            elif profile_key == "ssq":
                parts = new_num.replace("红", "").replace("蓝", "").split()
                reds = [int(x) for x in parts[0].split(",") if x.strip()]
                blues = [int(x) for x in parts[1].split(",") if x.strip()] if len(parts) > 1 else []
                if len(reds) != 6 or len(blues) != 1:
                    QMessageBox.warning(self, "输入错误", "格式: 红1,2,3,4,5,6 蓝1")
                    self._refresh_editable_table()
                    return
                ticket.groups["red"] = reds
                ticket.groups["blue"] = blues
            elif profile_key == "dlt":
                parts = new_num.replace("前", "").replace("后", "").split()
                fronts = [int(x) for x in parts[0].split(",") if x.strip()]
                backs = [int(x) for x in parts[1].split(",") if x.strip()] if len(parts) > 1 else []
                if len(fronts) != 5 or len(backs) != 2:
                    QMessageBox.warning(self, "输入错误", "格式: 前1,2,3,4,5 后1,2")
                    self._refresh_editable_table()
                    return
                ticket.groups["front"] = fronts
                ticket.groups["back"] = backs
            elif profile_key == "qlc":
                nums = [int(x) for x in new_num.split(",") if x.strip()]
                if len(nums) != 7:
                    QMessageBox.warning(self, "输入错误", "请输入7个号码（1-30）")
                    self._refresh_editable_table()
                    return
                ticket.groups["basic"] = nums
            elif profile_key == "kl8":
                nums = [int(x) for x in new_num.split(",") if x.strip()]
                if len(nums) < 1 or len(nums) > 10:
                    QMessageBox.warning(self, "输入错误", "请输入1-10个号码（1-80）")
                    self._refresh_editable_table()
                    return
                ticket.groups["main"] = nums
            else:
                QMessageBox.warning(self, "输入错误", "不支持的彩种")
                self._refresh_editable_table()
                return
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字")
            self._refresh_editable_table()
            return

        # 刷新显示
        self._refresh_editable_table()
        self._update_result_text()

    def _delete_number(self, row: int) -> None:
        """删除指定行的号码."""
        if 0 <= row < len(self._editable_tickets):
            self._editable_tickets.pop(row)
            self._refresh_editable_table()
            self._update_result_text()

    def _add_custom_number(self) -> None:
        """添加自定义号码（通用）."""
        from ..core.ticket import Ticket

        num_str = self.add_number_input.text().strip()
        if not num_str:
            return

        profile = self.current.profile
        profile_key = profile.key
        groups = {}

        try:
            if profile_key in ("3d", "pl3", "pl5", "qxc"):
                expected = profile.group("pos").count
                if len(num_str) != expected or not num_str.isdigit():
                    QMessageBox.warning(self, "输入错误", f"请输入{expected}位数字")
                    return
                groups = {"pos": [int(c) for c in num_str]}
            elif profile_key == "ssq":
                parts = num_str.replace("红", "").replace("蓝", "").split()
                reds = sorted(int(x) for x in parts[0].split(",") if x.strip())
                blues = sorted(int(x) for x in parts[1].split(",") if x.strip()) if len(parts) > 1 else []
                if len(reds) != 6 or len(blues) != 1:
                    QMessageBox.warning(self, "输入错误", "格式: 红1,2,3,4,5,6 蓝1")
                    return
                groups = {"red": reds, "blue": blues}
            elif profile_key == "dlt":
                parts = num_str.replace("前", "").replace("后", "").split()
                fronts = sorted(int(x) for x in parts[0].split(",") if x.strip())
                backs = sorted(int(x) for x in parts[1].split(",") if x.strip()) if len(parts) > 1 else []
                if len(fronts) != 5 or len(backs) != 2:
                    QMessageBox.warning(self, "输入错误", "格式: 前1,2,3,4,5 后1,2")
                    return
                groups = {"front": fronts, "back": backs}
            elif profile_key == "qlc":
                nums = sorted(int(x) for x in num_str.split(",") if x.strip())
                if len(nums) != 7:
                    QMessageBox.warning(self, "输入错误", "请输入7个号码（1-30）")
                    return
                groups = {"basic": nums}
            elif profile_key == "kl8":
                nums = sorted(int(x) for x in num_str.split(",") if x.strip())
                if len(nums) < 1 or len(nums) > 10:
                    QMessageBox.warning(self, "输入错误", "请输入1-10个号码（1-80）")
                    return
                groups = {"main": nums}
            else:
                QMessageBox.warning(self, "输入错误", "不支持的彩种")
                return
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字")
            return

        new_ticket = Ticket(
            profile=profile,
            groups=groups,
            strategy_name="用户添加",
            validate=False,
        )
        self._editable_tickets.append(new_ticket)
        self._refresh_editable_table()
        self._update_result_text()
        self.add_number_input.clear()

    def _add_random_number(self) -> None:
        """随机添加一个号码（通用）."""
        import random
        from ..core.ticket import Ticket

        profile = self.current.profile
        profile_key = profile.key
        groups = {}

        if profile_key in ("3d", "pl3", "pl5", "qxc"):
            grp = profile.group("pos")
            nums = [random.randint(grp.lo, grp.hi) for _ in range(grp.count)]
            groups = {"pos": nums}
        elif profile_key == "ssq":
            red_grp = profile.group("red")
            blue_grp = profile.group("blue")
            reds = sorted(random.sample(range(red_grp.lo, red_grp.hi + 1), red_grp.count))
            blues = [random.randint(blue_grp.lo, blue_grp.hi)]
            groups = {"red": reds, "blue": blues}
        elif profile_key == "dlt":
            front_grp = profile.group("front")
            back_grp = profile.group("back")
            fronts = sorted(random.sample(range(front_grp.lo, front_grp.hi + 1), front_grp.count))
            backs = sorted(random.sample(range(back_grp.lo, back_grp.hi + 1), back_grp.count))
            groups = {"front": fronts, "back": backs}
        elif profile_key == "qlc":
            grp = profile.group("basic")
            nums = sorted(random.sample(range(grp.lo, grp.hi + 1), grp.count))
            groups = {"basic": nums}
        elif profile_key == "kl8":
            grp = profile.group("main")
            pick_count = random.randint(grp.effective_pick_min, grp.effective_pick_max)
            nums = sorted(random.sample(range(grp.lo, grp.hi + 1), pick_count))
            groups = {"main": nums}
        else:
            return

        new_ticket = Ticket(
            profile=profile,
            groups=groups,
            strategy_name="随机添加",
            validate=False,
        )
        self._editable_tickets.append(new_ticket)
        self._refresh_editable_table()
        self._update_result_text()

    def _update_result_text(self) -> None:
        """更新结果文本显示（通用）."""
        if not hasattr(self, "_editable_tickets"):
            return
        text_lines = []
        for idx, ticket in enumerate(self._editable_tickets, start=1):
            line = f"{idx:02d}. {ticket.format_compact()}"
            type_label = self._get_ticket_type_label(ticket)
            if type_label:
                line += f"  [{type_label}]"
            if ticket.basis:
                line += f"  [{ticket.basis}]"
            text_lines.append(line)
        self.result_text.setText("\n".join(text_lines))

    def _print_results(self) -> None:
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        # 使用可编辑列表中的号码（如果有）
        if hasattr(self, "_editable_tickets") and self._editable_tickets:
            tickets_to_print = self._editable_tickets
        else:
            tickets_to_print = self._last_generated
        self._print_tickets(tickets_to_print, f"{self.current.profile.name}生成结果")

    def _export_pdf_results(self) -> None:
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        # 使用可编辑列表中的号码（如果有）
        if hasattr(self, "_editable_tickets") and self._editable_tickets:
            tickets_to_export = self._editable_tickets
        else:
            tickets_to_export = self._last_generated
        self._export_tickets_to_pdf(tickets_to_export, f"{self.current.profile.name}生成结果")

    def _print_tickets(self, tickets: list, title: str) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        html = self._build_print_html(tickets, title)
        from PySide6.QtGui import QTextDocument
        document = QTextDocument()
        document.setHtml(html)
        try:
            document.print_(printer)
        except Exception as exc:  # noqa: BLE001
            self._show_print_error_once(str(exc))

    def _export_tickets_to_pdf(self, tickets: list, title: str) -> None:
        from PySide6.QtGui import QPainter, QFont, QColor, QPen
        from PySide6.QtCore import Qt, QRectF, QPointF

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"caipiao_{self.current.profile.key}_result_{timestamp}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF", default_name, "PDF 文件 (*.pdf)"
        )
        if not path:
            return

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize.A4)
        painter = QPainter(writer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # QPdfWriter 默认 1200 DPI，坐标单位是像素
        # 1pt = 1200/72 ≈ 16.67 px
        PX = 1200 / 72  # pt -> px 换算系数

        page_w = writer.width()   # 9582 px
        page_h = writer.height()  # 13699 px

        # 边距和尺寸（用pt定义，再转px）
        margin_l = int(30 * PX)
        margin_r = int(30 * PX)
        margin_t = int(30 * PX)
        margin_b = int(25 * PX)
        content_w = page_w - margin_l - margin_r

        y = margin_t

        # === 标题 ===
        font_title = QFont("Microsoft YaHei", int(20 * PX / 16), QFont.Weight.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor("#D32F2F"))
        title_h = int(32 * PX)
        painter.drawText(QRectF(margin_l, y, content_w, title_h),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, title)
        y += title_h + int(6 * PX)

        # === 时间 ===
        font_meta = QFont("Microsoft YaHei", int(10 * PX / 16))
        painter.setFont(font_meta)
        painter.setPen(QColor("#666"))
        meta_h = int(18 * PX)
        painter.drawText(QRectF(margin_l, y, content_w, meta_h),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        y += meta_h + int(4 * PX)

        # === 分隔线 ===
        painter.setPen(QPen(QColor("#ccc"), max(1, int(1.2 * PX / 16))))
        painter.drawLine(QPointF(margin_l, y), QPointF(page_w - margin_r, y))
        y += int(8 * PX)

        # === 球参数（pt -> px）===
        BALL_D = int(38 * PX)     # 球直径 ~38pt
        BALL_GAP = int(6 * PX)    # 球间距
        PLUS_W = int(18 * PX)     # "+" 宽度
        IDX_W = int(32 * PX)      # 序号列宽
        ROW_H = BALL_D + int(12 * PX)  # 行高

        # 字号（QFont 用 pt，QPainter 会自动转 px）
        font_num = QFont("Arial", 13, QFont.Weight.Bold)
        font_idx = QFont("Microsoft YaHei", 12, QFont.Weight.Bold)
        font_plus = QFont("Arial", 13, QFont.Weight.Bold)

        for idx, ticket in enumerate(tickets, 1):
            render_groups = ticket.render_groups()

            # 换页检查
            if y + ROW_H > page_h - margin_b:
                writer.newPage()
                y = margin_t

            # === 画序号 ===
            painter.setFont(font_idx)
            painter.setPen(QColor("#888"))
            painter.drawText(QRectF(margin_l, y, IDX_W, ROW_H),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                             f"{idx:02d}.")

            # === 画球 ===
            x = float(margin_l + IDX_W + int(6 * PX))
            ball_cy = y + ROW_H / 2.0  # 球中心y

            for gi, rg in enumerate(render_groups):
                if gi > 0:
                    painter.setFont(font_plus)
                    painter.setPen(QColor("#999"))
                    painter.drawText(QRectF(x, ball_cy - BALL_D / 2, PLUS_W, BALL_D),
                                     Qt.AlignmentFlag.AlignCenter, "+")
                    x += PLUS_W

                for n in rg.numbers:
                    cx = x + BALL_D / 2.0  # 球中心x
                    # 画圆
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(rg.color))
                    painter.drawEllipse(QPointF(cx, ball_cy), BALL_D / 2.0, BALL_D / 2.0)
                    # 画数字
                    painter.setFont(font_num)
                    painter.setPen(QColor("white"))
                    painter.drawText(QRectF(x, ball_cy - BALL_D / 2, BALL_D, BALL_D),
                                     Qt.AlignmentFlag.AlignCenter, f"{n:0{rg.pad}d}")
                    x += BALL_D + BALL_GAP

            y += ROW_H

            # 行分隔线
            lw = max(1, int(0.5 * PX / 16))
            painter.setPen(QPen(QColor("#eee"), lw))
            painter.drawLine(QPointF(margin_l, y - int(3 * PX)), QPointF(page_w - margin_r, y - int(3 * PX)))

        # === 页脚 ===
        font_footer = QFont("Microsoft YaHei", 9)
        painter.setFont(font_footer)
        painter.setPen(QColor("#bbb"))
        painter.drawText(QRectF(margin_l, page_h - margin_b, content_w, int(14 * PX)),
                         Qt.AlignmentFlag.AlignCenter,
                         "本结果由彩票号码生成器生成，仅供娱乐参考。")

        painter.end()

        try:
            QMessageBox.information(self, "导出成功", f"已导出到: {path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _show_print_error_once(self, message: str) -> None:
        if getattr(self, "_print_error_shown", False):
            return
        self._print_error_shown = True

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("打印失败")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("调用系统打印服务失败，可能是所选打印机配置有误。")
        msg_box.setInformativeText(f"错误信息：{message}\n\n建议尝试使用“导出 PDF”功能。")

        check_box = QCheckBox("不再提示此错误")
        msg_box.setCheckBox(check_box)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
        self._print_error_shown = check_box.isChecked()

    @staticmethod
    def _build_print_html(tickets: list, title: str) -> str:
        rows = []
        for idx, ticket in enumerate(tickets, start=1):
            render_groups = ticket.render_groups()

            # 构建号码球HTML
            balls_parts = []
            for gi, rg in enumerate(render_groups):
                if gi > 0:
                    balls_parts.append(
                        '<span style="color:#999;font-weight:bold;font-size:16pt;margin:0 8pt;">+</span>'
                    )
                for n in rg.numbers:
                    balls_parts.append(
                        f'<span style="background-color:{rg.color};color:#fff;'
                        f'font-weight:bold;font-size:14pt;padding:4pt 8pt;margin:2pt 3pt;">{n:0{rg.pad}d}</span>'
                    )

            rows.append(
                f"<div style='page-break-inside:avoid;border-bottom:1pt solid #ddd;padding:8pt 0;'>"
                f"{idx:02d}. {''.join(balls_parts)}</div>"
            )

        details_html = ""
        if tickets:
            chart_details = MainWindow._build_chart_details(tickets[0].details)
            if chart_details:
                details_html = MainWindow._build_probability_details_html_for_print(chart_details)

        target_html = ""
        if tickets:
            target_lines = MainWindow._format_target_lines(tickets[0].details)
            if target_lines:
                color = "#D32F2F" if tickets[0].details.get("stale") else "#333"
                target_html = (
                    f'<p style="text-align:center;color:{color};font-weight:bold;font-size:14pt;margin:8pt 0;">'
                    f'{" &nbsp;|&nbsp; ".join(target_lines)}</p>'
                )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: "Microsoft YaHei", "Segoe UI", sans-serif; margin: 36pt; font-size: 14pt; color: #333; }}
                h1 {{ color: #D32F2F; text-align: center; font-size: 22pt; margin: 0 0 10pt 0; }}
                .meta {{ text-align: center; color: #666; font-size: 12pt; margin-bottom: 16pt; }}
                .footer {{ margin-top: 24pt; text-align: center; color: #aaa; font-size: 10pt; }}
                @media print {{
                    body {{ margin: 24pt; }}
                }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            <p class="meta">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            {target_html}
            {details_html}
            <div style="border:1pt solid #999;border-radius:4pt;">
                {''.join(rows)}
            </div>
            <p class="footer">本结果由彩票号码生成器生成，仅供娱乐参考。</p>
        </body>
        </html>
        """

    def _save_to_history(self) -> None:
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        # 生成结果已在 _on_generation_finished 中自动保存；此处仅做去重提示。
        try:
            added = self.history_manager.add_many(
                self._last_generated, skip_duplicates=True
            )
            self.history_panel.refresh()
            if added:
                QMessageBox.information(self, "保存成功", f"已保存 {added} 注新结果到历史记录")
            else:
                QMessageBox.information(self, "提示", "当前结果已存在于历史记录中")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存到历史记录失败:\n{exc}")

    def _on_history_changed(self) -> None:
        pass

    # ------------------------------------------------------------------ #
    # 插件
    # ------------------------------------------------------------------ #
    def _choose_plugin_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择插件目录", str(self.plugin_managers[self.current_key].plugin_dir))
        if path:
            for pm in self.plugin_managers.values():
                pm.plugin_dir = Path(path)
            self.plugin_dir_edit.setText(path)
            self.settings.plugin_dir = path
            self.settings.sync()

    def _reload_plugins(self) -> None:
        for ctx in self.context_manager.all_contexts():
            ctx.engine._strategies.clear()
            ctx.register_builtin_strategies()
            self.plugin_managers[ctx.profile.key].load_all()
        self.strategy_panel._refresh_strategies()
        self._restore_last_strategy()
        self._refresh_plugin_list()
        QMessageBox.information(self, "插件重载", "插件已重新加载")

    def _refresh_plugin_list(self) -> None:
        lines = []
        for strategy in self.current.engine.list_strategies():
            lines.append(
                f"• {strategy.metadata.name} ({strategy.metadata.id})\n"
                f"  {strategy.metadata.description}"
            )
        self.plugin_list.setText("\n\n".join(lines))

    # ------------------------------------------------------------------ #
    # 主题/设置
    # ------------------------------------------------------------------ #
    def _apply_theme(self) -> None:
        """应用中式八卦喜庆主题."""
        self.settings.dark_theme = False  # 统一使用中式主题
        font = self.font()
        if font.pointSize() <= 0:
            font.setPointSize(10)
            self.setFont(font)
        self.setStyleSheet(self._chinese_taoist_stylesheet())

    def _save_settings(self) -> None:
        try:
            self.settings.default_count = self.settings_count_spin.value()
            self.settings.dark_theme = self.dark_theme_check.isChecked()
            self.settings.last_strategy_id = self.strategy_panel.current_strategy_id()
            self.settings.set("current_lottery", self.current_key)
            new_boss_key = self.boss_key_edit.edit.text().strip()
            if validate_hotkey_dialog(new_boss_key, self):
                self.settings.boss_key = new_boss_key
                self._register_boss_key()
            else:
                return
            self.settings.sync()
            QMessageBox.information(self, "设置已保存", "设置已保存并生效")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存设置失败:\n{exc}")

    def _on_boss_key_changed(self, hotkey: str) -> None:
        """快捷键输入变化时实时保存并注册."""
        hotkey = hotkey.strip()
        if hotkey and not validate_hotkey_dialog(hotkey, self):
            return
        self.settings.boss_key = hotkey
        self.settings.sync()
        self._register_boss_key()

    def _register_boss_key(self) -> None:
        """注册/注销老板键."""
        hotkey = self.settings.boss_key
        if not hotkey:
            if hasattr(self, "_boss_shortcut") and self._boss_shortcut:
                self._boss_shortcut.setEnabled(False)
            return

        from PySide6.QtGui import QKeySequence, QShortcut

        if not hasattr(self, "_boss_shortcut") or self._boss_shortcut is None:
            self._boss_shortcut = QShortcut(self)
            self._boss_shortcut.activated.connect(self._toggle_boss_mode)

        self._boss_shortcut.setKey(QKeySequence(hotkey))
        self._boss_shortcut.setEnabled(True)

    def _toggle_boss_mode(self) -> None:
        """切换主窗口显示/隐藏."""
        if self.isVisible():
            self.hide()
            logger.info("老板键触发：隐藏主窗口")
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            logger.info("老板键触发：显示主窗口")

    # ------------------------------------------------------------------ #
    # 文档/关于/回测
    # ------------------------------------------------------------------ #
    def _docs_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "docs"

    def _show_doc(self, title: str, filename: str) -> None:
        md_path = self._docs_dir() / filename
        if not md_path.exists():
            QMessageBox.warning(self, "文档缺失", f"未找到文档：{md_path}")
            return
        dialog = MarkdownDialog(
            title, md_path, dark=self.settings.dark_theme, parent=self
        )
        dialog.exec()

    def _show_learning_guide(self) -> None:
        self._show_doc("学习文档 - 概率统计与机器学习", "LEARNING_GUIDE.md")

    def _show_backtest_dialog(self) -> None:
        if not self.current.data_repository.get_count():
            QMessageBox.information(
                self, "缺少数据", "请先更新本地开奖数据，再进行历史回测。"
            )
            return
        dialog = BacktestDialog(self.current, self)
        dialog.exec()

    def _show_batch_backtest_dialog(self) -> None:
        if not self.current.data_repository.get_count():
            QMessageBox.information(
                self, "缺少数据", "请先更新本地开奖数据，再进行批量历史回测。"
            )
            return
        dialog = BatchBacktestDialog(
            self.current,
            plugin_dir=str(self.plugin_managers[self.current_key].plugin_dir),
            optimal_param_store=self._optimal_param_store,
            parent=self,
        )
        dialog.exec()

    def _show_backtest_history_dialog(self) -> None:
        from .components.backtest_history_dialog import BacktestHistoryDialog

        dialog = BacktestHistoryDialog(self)
        dialog.exec()

    def _show_draw_analysis_dialog(self) -> None:
        if not self.current.data_repository.get_count():
            QMessageBox.information(
                self, "缺少数据", "请先更新本地开奖数据，再进行开奖记录分析。"
            )
            return
        dialog = DrawAnalysisDialog(self.current, self)
        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "<h2>彩票号码生成器</h2>"
            "<p>版本: 2.0.0</p>"
            "<p>基于 PySide6 开发，支持双色球、福彩3D、七乐彩、快乐8。</p>"
            "<p>本软件仅供娱乐参考，不保证中奖。</p>",
        )

    # ------------------------------------------------------------------ #
    # 中式八卦喜庆主题样式表
    # ------------------------------------------------------------------ #
    @staticmethod
    def _chinese_taoist_stylesheet() -> str:
        """中式八卦喜庆主题样式表.
        
        配色方案：
        - 主色：中国红 #C41E3A / 朱砂红 #E2231A
        - 辅色：金色 #D4A017 / 琉璃黄 #F5C518
        - 背景：宣纸色 #FDF5E6 / 米白 #F8F4E9
        - 文字：墨黑 #2D2D2D / 深棕 #3D2B1F
        - 点缀：道家青 #2E8B57 / 青瓷绿 #6B8E6B
        """
        return """
        /* ========== 全局基础 ========== */
        QWidget {
            font-family: "Microsoft YaHei", "SimSun", "KaiTi", sans-serif;
            font-size: 10pt;
            color: #2D2D2D;
            background-color: #FDF5E6;
        }
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:0.5 #F8F4E9, stop:1 #F0E6D3);
        }

        /* ========== 按钮 - 中国红渐变 ========== */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E2231A, stop:0.5 #C41E3A, stop:1 #A01830);
            color: #FFFFFF;
            border: 2px solid #D4A017;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 10pt;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #F54030, stop:0.5 #E2231A, stop:1 #C41E3A);
            border: 2px solid #F5C518;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #A01830, stop:1 #801020);
        }
        QPushButton:disabled {
            background: #CCBBAA;
            color: #888888;
            border: 1px solid #BBAA99;
        }

        /* ========== 输入框 - 宣纸质感 ========== */
        QLineEdit, QSpinBox, QComboBox, QTextEdit {
            background-color: #FFFEF9;
            border: 2px solid #D4A017;
            border-radius: 6px;
            padding: 6px 8px;
            color: #2D2D2D;
            selection-background-color: #C41E3A;
            selection-color: #FFFFFF;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border: 2px solid #C41E3A;
            background-color: #FFFFFF;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid #C41E3A;
            margin-right: 8px;
        }

        /* ========== 分组框 - 古典边框 ========== */
        QGroupBox {
            font-weight: bold;
            font-size: 10pt;
            background-color: rgba(255, 254, 249, 0.7);
            border: 2px solid #D4A017;
            border-radius: 12px;
            margin-top: 14px;
            padding-top: 14px;
            color: #8B0000;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: #C41E3A;
            font-size: 11pt;
        }

        /* ========== 标签 ========== */
        QLabel {
            color: #2D2D2D;
            background: transparent;
        }
        QLabel#app_title {
            font-size: 20pt;
            font-weight: bold;
            color: #8B0000;
            padding: 10px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.5 rgba(212, 160, 23, 0.15), stop:1 transparent);
        }

        /* ========== 标签页 - 八卦风格 ========== */
        QTabWidget::pane {
            border: 2px solid #D4A017;
            border-radius: 10px;
            background-color: rgba(255, 254, 249, 0.5);
            top: -1px;
        }
        QTabBar::tab {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:1 #F0E6D3);
            color: #8B4513;
            border: 2px solid #D4A017;
            border-bottom: none;
            padding: 10px 20px;
            margin-right: 3px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            font-weight: bold;
            font-size: 10pt;
        }
        QTabBar::tab:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #C41E3A, stop:0.5 #A01830, stop:1 #801020);
            color: #FFD700;
            border: 2px solid #D4A017;
            border-bottom: 2px solid #C41E3A;
        }
        QTabBar::tab:hover:!selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFF8E7, stop:1 #FFE4B5);
            color: #C41E3A;
        }

        /* ========== 滚动区域 ========== */
        QScrollArea > QWidget {
            background-color: transparent;
        }
        QScrollBar:vertical {
            background: #F0E6D3;
            width: 12px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #D4A017, stop:1 #C41E3A);
            border-radius: 6px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #C41E3A;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background: #F0E6D3;
            height: 12px;
            border-radius: 6px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #D4A017, stop:1 #C41E3A);
            border-radius: 6px;
            min-width: 30px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #C41E3A;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }

        /* ========== 列表控件 ========== */
        QListWidget {
            background-color: #FFFEF9;
            border: 2px solid #D4A017;
            border-radius: 10px;
            padding: 6px;
            color: #2D2D2D;
            outline: none;
        }
        QListWidget::item {
            padding: 6px;
            border-radius: 4px;
        }
        QListWidget::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #C41E3A, stop:1 #A01830);
            color: #FFD700;
        }
        QListWidget::item:hover {
            background: rgba(196, 30, 58, 0.1);
        }

        /* ========== 工具栏 ========== */
        QToolBar {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:1 #F0E6D3);
            border: 2px solid #D4A017;
            border-radius: 10px;
            padding: 4px;
            spacing: 6px;
        }
        QToolButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFEF9, stop:1 #F5EFE0);
            color: #8B0000;
            border: 1px solid #D4A017;
            border-radius: 8px;
            padding: 6px 10px;
            font-weight: bold;
            font-size: 9pt;
        }
        QToolButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFE4B5, stop:1 #FFDAB9);
            border: 1px solid #C41E3A;
            color: #C41E3A;
        }
        QToolButton:pressed {
            background: #C41E3A;
            color: #FFD700;
        }

        /* ========== 表格 ========== */
        QTableWidget {
            background-color: #FFFEF9;
            border: 2px solid #D4A017;
            border-radius: 8px;
            gridline-color: #E8DCC8;
            color: #2D2D2D;
        }
        QTableWidget::item {
            padding: 4px;
        }
        QTableWidget::item:selected {
            background: #C41E3A;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #C41E3A, stop:1 #A01830);
            color: #FFD700;
            border: 1px solid #D4A017;
            padding: 6px;
            font-weight: bold;
        }

        /* ========== 进度条 ========== */
        QProgressBar {
            border: 2px solid #D4A017;
            border-radius: 8px;
            text-align: center;
            color: #2D2D2D;
            background-color: #F0E6D3;
            height: 20px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #C41E3A, stop:0.5 #E2231A, stop:1 #C41E3A);
            border-radius: 6px;
        }

        /* ========== 复选框/单选框 ========== */
        QCheckBox, QRadioButton {
            color: #2D2D2D;
            spacing: 8px;
        }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 18px;
            height: 18px;
        }
        QCheckBox::indicator {
            border: 2px solid #D4A017;
            border-radius: 4px;
            background: #FFFEF9;
        }
        QCheckBox::indicator:checked {
            background: #C41E3A;
            border-color: #C41E3A;
        }
        QRadioButton::indicator {
            border: 2px solid #D4A017;
            border-radius: 10px;
            background: #FFFEF9;
        }
        QRadioButton::indicator:checked {
            background: #C41E3A;
            border-color: #C41E3A;
        }

        /* ========== 提示框 ========== */
        QToolTip {
            font-family: "Microsoft YaHei", sans-serif;
            font-size: 10pt;
            background-color: #FFF8DC;
            color: #2D2D2D;
            border: 2px solid #D4A017;
            border-radius: 6px;
            padding: 6px;
        }

        /* ========== 状态栏 ========== */
        QStatusBar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:1 #F0E6D3);
            border-top: 2px solid #D4A017;
            color: #8B4513;
        }

        /* ========== 菜单 ========== */
        QMenuBar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:1 #F0E6D3);
            border-bottom: 2px solid #D4A017;
            color: #2D2D2D;
        }
        QMenuBar::item:selected {
            background: #C41E3A;
            color: #FFFFFF;
        }
        QMenu {
            background: #FFFEF9;
            border: 2px solid #D4A017;
            color: #2D2D2D;
        }
        QMenu::item:selected {
            background: #C41E3A;
            color: #FFFFFF;
        }
        QMenu::separator {
            height: 2px;
            background: #D4A017;
            margin: 4px 8px;
        }

        /* ========== 对话框 ========== */
        QDialog {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FDF5E6, stop:1 #F0E6D3);
        }

        /* ========== 分割器 ========== */
        QSplitter::handle {
            background: #D4A017;
            width: 3px;
            height: 3px;
            border-radius: 2px;
        }
        QSplitter::handle:hover {
            background: #C41E3A;
        }
        """
