"""主窗口."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QClipboard, QKeySequence
from PySide6.QtGui import QIcon, QPageSize, QPdfWriter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.engine import GenerationEngine
from ..core.strategies import (
    BalancedStrategy,
    ExcludeIncludeStrategy,
    HotColdStrategy,
    MissingNumberStrategy,
    OddEvenStrategy,
    RandomStrategy,
    SmartHotColdStrategy,
    XGBoostStrategy,
)
from ..data.analyzer import LotteryAnalyzer
from ..data.fetcher import LotteryDataFetcher
from ..data.repository import DataRepository
from ..ml.model_store import compute_lookback, is_model_current, new_model_path
from ..persistence.history import HistoryManager
from ..persistence.settings import AppSettings
from ..plugins.plugin_manager import PluginManager
from .chart_utils import ProbabilityChartDialog, build_probability_charts_html
from .components.backtest_dialog import BacktestDialog
from .components.ball_display import TicketRowWidget
from .components.history_panel import HistoryPanel
from .components.strategy_panel import StrategyPanel
from .components.training_progress_dialog import TrainingProgressDialog
from .markdown_view import MarkdownDialog
from .workers import (
    FetchAllDataThread,
    FetchLatestDataThread,
    GenerateTicketsThread,
    TrainXGBoostThread,
)

# 周几中文，用于展示开奖日期（weekday(): 周一=0 ... 周日=6）
_WEEKDAY_CN = "一二三四五六日"


class MainWindow(QMainWindow):
    """双色球生成器主窗口."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("双色球号码生成器")
        self.setMinimumSize(900, 700)

        # 设置窗口图标
        icon_path = Path(__file__).resolve().parent / "resources" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # 数据目录
        self.data_dir = Path.home() / ".caipiao"
        self.data_dir.mkdir(exist_ok=True)

        # 设置
        self.settings = AppSettings()

        # 引擎与策略
        self.engine = GenerationEngine()
        self._register_builtin_strategies()

        # 插件
        plugin_dir = Path(self.settings.plugin_dir or Path.cwd() / "plugins")
        plugin_dir.mkdir(exist_ok=True)
        self.plugin_manager = PluginManager(self.engine, plugin_dir)
        self.plugin_manager.load_all()

        # 历史
        self.history_manager = HistoryManager(self.data_dir / "history.json")

        # 官方开奖数据
        self.data_repository = DataRepository(self.data_dir / "draws.json")
        self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())

        self._setup_ui()
        self._setup_menu()
        self._apply_theme()

        # 启动时自动检查更新（离线时静默失败，不影响使用）
        self._perform_auto_update()

    def closeEvent(self, event) -> None:
        """关闭窗口时等待后台线程结束."""
        for attr in (
            "_fetch_thread",
            "_latest_update_thread",
            "_pretrain_fetch_thread",
            "_xgboost_thread",
            "_generate_thread",
        ):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(5000)
        event.accept()

    def _register_builtin_strategies(self) -> None:
        self.engine.register(RandomStrategy())
        self.engine.register(OddEvenStrategy())
        self.engine.register(HotColdStrategy())
        self.engine.register(ExcludeIncludeStrategy())
        self.engine.register(SmartHotColdStrategy())
        self.engine.register(MissingNumberStrategy())
        self.engine.register(BalancedStrategy())
        self.engine.register(XGBoostStrategy())

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("双色球号码自动生成器")
        title.setObjectName("app_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

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

        # 插件页
        self.plugins_tab = self._build_plugins_tab()
        self.tabs.addTab(self.plugins_tab, "插件管理")

        # 设置页
        self.settings_tab = self._build_settings_tab()
        self.tabs.addTab(self.settings_tab, "设置")

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
        self.count_spin.setRange(1, 100)
        self.count_spin.setValue(self.settings.default_count)
        self.count_spin.setSuffix(" 注")
        self.count_spin.setToolTip("设置一次生成的彩票注数。")
        count_layout.addWidget(self.count_spin)
        left_layout.addLayout(count_layout)

        # 策略面板
        self.strategy_panel = StrategyPanel(self.engine)
        self.strategy_panel.set_strategy_id(self.settings.last_strategy_id)
        saved_options = self.settings.last_strategy_options
        if saved_options:
            self.strategy_panel.set_options(saved_options)
        left_layout.addWidget(self.strategy_panel)

        # 生成按钮
        self.generate_btn = QPushButton("立即生成")
        self.generate_btn.setObjectName("generate_btn")
        self.generate_btn.setToolTip("根据当前策略生成号码。XGBoost 策略首次会训练模型，请稍候。")
        self.generate_btn.clicked.connect(self._generate)
        left_layout.addWidget(self.generate_btn)

        # 复制按钮
        self.copy_btn = QPushButton("复制全部号码")
        self.copy_btn.setToolTip("将生成的号码复制到剪贴板。")
        self.copy_btn.clicked.connect(self._copy_all)
        left_layout.addWidget(self.copy_btn)

        # 打印按钮
        self.print_btn = QPushButton("打印结果")
        self.print_btn.setToolTip("将生成的号码打印或导出为 PDF。")
        self.print_btn.clicked.connect(self._print_results)
        left_layout.addWidget(self.print_btn)

        # 导出 PDF 按钮
        self.export_pdf_btn = QPushButton("导出 PDF")
        self.export_pdf_btn.setToolTip("将生成的号码导出为 PDF 文件，不依赖打印机驱动。")
        self.export_pdf_btn.clicked.connect(self._export_pdf_results)
        left_layout.addWidget(self.export_pdf_btn)

        # 保存按钮
        self.save_btn = QPushButton("保存到历史")
        self.save_btn.setToolTip("将本次生成的号码保存到本地历史记录。")
        self.save_btn.clicked.connect(self._save_to_history)
        left_layout.addWidget(self.save_btn)

        left_layout.addStretch()
        layout.addWidget(left_panel, 1)

        # 右侧结果面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("生成结果:"))

        self.target_label = QLabel("")
        self.target_label.setWordWrap(True)
        self.target_label.setStyleSheet("color:#333;")
        self.target_label.setVisible(False)
        right_layout.addWidget(self.target_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("点击“立即生成”获取号码...")
        right_layout.addWidget(self.result_text, 1)

        self.chart_btn = QPushButton("查看 XGBoost 概率折线图")
        self.chart_btn.setToolTip("在独立窗口中查看更大的概率折线图")
        self.chart_btn.setVisible(False)
        self.chart_btn.clicked.connect(self._show_probability_chart)
        right_layout.addWidget(self.chart_btn)

        self.result_area = QScrollArea()
        self.result_area.setWidgetResizable(True)
        self.result_container = QWidget()
        self.result_container_layout = QVBoxLayout(self.result_container)
        self.result_container_layout.setSpacing(6)
        self.result_container_layout.addStretch()
        self.result_area.setWidget(self.result_container)
        right_layout.addWidget(self.result_area, 2)

        layout.addWidget(right_panel, 2)

        return tab

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
        self.plugin_dir_edit = QLineEdit(str(self.plugin_manager.plugin_dir))
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

        # 默认注数
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("默认生成注数:"))
        self.settings_count_spin = QSpinBox()
        self.settings_count_spin.setToolTip("设置主界面每次默认生成的彩票注数。")
        self.settings_count_spin.setRange(1, 100)
        self.settings_count_spin.setValue(self.settings.default_count)
        count_layout.addWidget(self.settings_count_spin)
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # 主题
        from PySide6.QtWidgets import QCheckBox

        self.dark_theme_check = QCheckBox("深色主题")
        self.dark_theme_check.setToolTip("切换深色/浅色主题。深色主题适合夜间使用。")
        self.dark_theme_check.setChecked(self.settings.dark_theme)
        self.dark_theme_check.stateChanged.connect(self._apply_theme)
        layout.addWidget(self.dark_theme_check)

        # 保存按钮
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.setToolTip("将当前设置保存到本地配置文件。")
        self.save_settings_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_settings_btn)

        layout.addStretch()
        return tab

    def _build_data_tab(self) -> QWidget:
        """构建开奖数据标签页."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # 状态区
        self.data_status_label = QLabel(self._data_status_text())
        self.data_status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.data_status_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.update_data_btn = QPushButton("更新开奖数据")
        self.update_data_btn.setToolTip("从网络下载全部历史开奖数据（2003 年至今），用于统计分析和模型训练。")
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
        self.data_stats_text.setMaximumHeight(200)
        layout.addWidget(self.data_stats_text)

        # 详细统计刷新
        self.refresh_stats_btn = QPushButton("刷新统计")
        self.refresh_stats_btn.setToolTip("根据本地数据重新计算热号、冷号、遗漏值等统计指标。")
        self.refresh_stats_btn.clicked.connect(self._refresh_data_stats)
        layout.addWidget(self.refresh_stats_btn)

        # XGBoost 模型区
        layout.addWidget(QLabel("XGBoost 模型:"))
        self.xgboost_status_label = QLabel(self._xgboost_status_text())
        self.xgboost_status_label.setWordWrap(True)
        layout.addWidget(self.xgboost_status_label)

        xgb_btn_layout = QHBoxLayout()
        self.train_xgboost_btn = QPushButton("训练模型")
        self.train_xgboost_btn.setToolTip("使用本地历史数据训练 XGBoost 模型。首次训练约 10-20 秒。")
        self.train_xgboost_btn.clicked.connect(self._train_xgboost_model)
        self.delete_model_btn = QPushButton("删除模型")
        self.delete_model_btn.setToolTip("删除本地保存的 XGBoost 模型文件。")
        self.delete_model_btn.clicked.connect(self._delete_xgboost_model)
        xgb_btn_layout.addWidget(self.train_xgboost_btn)
        xgb_btn_layout.addWidget(self.delete_model_btn)
        xgb_btn_layout.addStretch()
        layout.addLayout(xgb_btn_layout)

        layout.addStretch()
        self._refresh_data_stats()
        return tab

    def _data_status_text(self, offline: bool = False) -> str:
        count = self.data_repository.get_count()
        start, end = self.data_repository.get_date_range()
        last_update = self.settings.last_data_update or "从未"
        mode = "离线模式" if offline else "在线模式"
        if count == 0:
            return f"[{mode}] 本地暂无官方开奖数据，请点击“更新开奖数据”获取。"
        return (
            f"[{mode}] 本地已存储 {count} 期官方开奖数据\n"
            f"数据范围: {start.date()} 至 {end.date()}\n"
            f"上次更新: {last_update}"
        )

    def _update_draw_data(self) -> None:
        """在后台线程中获取全部开奖数据."""
        self.update_data_btn.setEnabled(False)
        self.data_progress.setVisible(True)

        self._fetch_thread = FetchAllDataThread(self)
        self._fetch_thread.result_ready.connect(self._on_data_fetched)
        self._fetch_thread.start()

    def _on_data_fetched(self, records, error) -> None:
        self.update_data_btn.setEnabled(True)
        self.data_progress.setVisible(False)

        if error:
            QMessageBox.critical(self, "获取失败", f"获取开奖数据失败:\n{error}")
            return

        added = self.data_repository.update(records)
        self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())
        self.data_status_label.setText(self._data_status_text())
        self._refresh_data_stats()
        QMessageBox.information(
            self, "更新成功", f"成功更新开奖数据\n新增 {added} 期，本地共 {self.data_repository.get_count()} 期"
        )

    def _fetch_latest_draw(self) -> None:
        """获取并显示最新一期开奖."""
        try:
            fetcher = LotteryDataFetcher()
            latest = fetcher.fetch_latest()
            if latest:
                self.data_repository.update([latest])
                self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())
                self.data_status_label.setText(self._data_status_text())
                self._refresh_data_stats()
                QMessageBox.information(
                    self,
                    "最新一期",
                    f"期号: {latest.issue}\n"
                    f"日期: {latest.draw_date.date()}\n"
                    f"红球: {' '.join(f'{r:02d}' for r in latest.red_balls)}\n"
                    f"蓝球: {latest.blue_ball:02d}",
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "获取失败", str(exc))

    def _clear_draw_data(self) -> None:
        """清空本地开奖数据."""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空本地官方开奖数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.data_repository.clear()
            self.data_analyzer = LotteryAnalyzer([])
            self.data_status_label.setText(self._data_status_text())
            self.data_stats_text.clear()

    def _refresh_data_stats(self) -> None:
        """刷新统计信息."""
        if self.data_repository.get_count() == 0:
            self.data_stats_text.setText("暂无数据，请先更新开奖数据。")
            return
        summary = self.data_analyzer.summary()
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
        self.data_stats_text.setText("\n".join(lines))

    def _xgboost_status_text(self) -> str:
        """XGBoost 模型状态文本."""
        model_dir = Path.home() / ".caipiao" / "models"
        model_files = list(model_dir.glob("xgboost_*.pkl")) if model_dir.exists() else []
        if not model_files:
            return "尚未训练 XGBoost 模型。首次使用“XGBoost 智能分析”策略时会自动训练，或点击“训练模型”提前准备。"
        latest = max(model_files, key=lambda p: p.stat().st_mtime)
        from datetime import datetime

        mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return f"已找到训练好的模型：{latest.name}\n训练时间：{mtime}"

    def _start_training(self, after) -> None:
        """两段式训练：先联网拉取最新一期数据，再训练带时间戳的新模型.

        全程弹出模态进度窗口，阻止训练期间的无效操作。训练结束后调用
        ``after(error)``（``error`` 为 None 表示成功），由调用方决定后续动作。
        """
        self._train_after = after
        self._train_dialog = TrainingProgressDialog(self)
        self._train_dialog.set_stage("正在获取最新开奖数据…")
        self._train_dialog.show()

        self._pretrain_fetch_thread = FetchLatestDataThread(self)
        self._pretrain_fetch_thread.result_ready.connect(self._on_pretrain_fetch_done)
        self._pretrain_fetch_thread.start()

    def _on_pretrain_fetch_done(self, latest, error) -> None:
        """最新数据拉取完成：更新本地数据后开始训练（离线失败则用本地数据继续）."""
        if not error and latest is not None:
            self.data_repository.update([latest])
            self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())
            self.data_status_label.setText(self._data_status_text())
            self._refresh_data_stats()

        records = self.data_repository.get_all()
        if len(records) < 100:
            self._finish_training(ValueError("XGBoost 模型需要至少 100 期历史数据"))
            return

        lookback = compute_lookback(len(records))
        model_path = new_model_path(lookback)

        dialog = getattr(self, "_train_dialog", None)
        if dialog is not None:
            dialog.set_stage("正在训练模型…")

        self._xgboost_thread = TrainXGBoostThread(
            records, lookback=lookback, model_path=model_path, parent=self
        )
        if dialog is not None:
            self._xgboost_thread.progress.connect(dialog.set_progress)
        self._xgboost_thread.result_ready.connect(self._on_training_done)
        self._xgboost_thread.start()

    def _on_training_done(self, success, error) -> None:
        self._finish_training(error)

    def _finish_training(self, error) -> None:
        """关闭进度窗口并回调训练发起方."""
        dialog = getattr(self, "_train_dialog", None)
        if dialog is not None:
            dialog.mark_finished()
            dialog.close()
            self._train_dialog = None

        after = getattr(self, "_train_after", None)
        self._train_after = None
        if after is not None:
            after(error)

    def _train_xgboost_model(self) -> None:
        """点击「训练模型」：拉取最新数据并训练，训练期间弹模态进度窗口."""
        records = self.data_repository.get_all()
        if len(records) < 100:
            QMessageBox.warning(self, "数据不足", "XGBoost 模型需要至少 100 期历史数据")
            return

        self.train_xgboost_btn.setEnabled(False)
        self._start_training(after=self._after_button_train)

    def _after_button_train(self, error) -> None:
        self.train_xgboost_btn.setEnabled(True)
        if error:
            QMessageBox.critical(self, "训练失败", f"XGBoost 模型训练失败:\n{error}")
        else:
            self.xgboost_status_label.setText(self._xgboost_status_text())
            QMessageBox.information(self, "训练完成", "XGBoost 模型已训练完成并保存")

    def _delete_xgboost_model(self) -> None:
        """删除本地 XGBoost 模型."""
        model_dir = Path.home() / ".caipiao" / "models"
        model_files = list(model_dir.glob("xgboost_*.pkl")) if model_dir.exists() else []
        if not model_files:
            QMessageBox.information(self, "提示", "没有可删除的模型")
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除 {len(model_files)} 个 XGBoost 模型文件吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for f in model_files:
                f.unlink()
                # 一并删除对应的元数据文件
                meta = Path(str(f) + ".meta.json")
                if meta.exists():
                    meta.unlink()
            self.xgboost_status_label.setText(self._xgboost_status_text())

    def _on_auto_update_changed(self, state: int) -> None:
        """自动更新开关变化."""
        self.settings.auto_update_on_start = state == Qt.CheckState.Checked.value
        self.settings.sync()

    def _on_update_interval_changed(self, value: int) -> None:
        """更新间隔变化."""
        self.settings.auto_update_interval_days = value
        self.settings.sync()

    def _should_auto_update(self) -> bool:
        """判断是否需要自动更新."""
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
        """启动时静默检查并更新最新一期数据."""
        if not self._should_auto_update():
            return

        self._latest_update_thread = FetchLatestDataThread(self)
        self._latest_update_thread.result_ready.connect(self._on_latest_update_finished)
        self._latest_update_thread.start()

    def _on_latest_update_finished(self, latest, error) -> None:
        """自动更新完成回调（静默处理失败）."""
        if error or latest is None:
            # 静默失败：标记为离线模式，使用本地数据
            self.data_status_label.setText(self._data_status_text(offline=True))
            return

        local_latest = self.data_repository.get_latest()
        if local_latest is None or latest.draw_date > local_latest.draw_date:
            self.data_repository.update([latest])
            self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())
            self.settings.last_data_update = datetime.now().isoformat()
            self.settings.sync()
            self.data_status_label.setText(self._data_status_text(offline=False))
            self._refresh_data_stats()
        else:
            self.settings.last_data_update = datetime.now().isoformat()
            self.settings.sync()
            self.data_status_label.setText(self._data_status_text(offline=False))

    def _check_for_updates(self) -> None:
        """手动检查更新."""
        self.check_update_btn.setEnabled(False)
        self.data_progress.setVisible(True)

        self._latest_update_thread = FetchLatestDataThread(self)
        self._latest_update_thread.result_ready.connect(self._on_manual_update_finished)
        self._latest_update_thread.start()

    def _on_manual_update_finished(self, latest, error) -> None:
        self.check_update_btn.setEnabled(True)
        self.data_progress.setVisible(False)

        if error or latest is None:
            QMessageBox.warning(
                self, "检查失败", f"无法连接到数据源，当前为离线模式。\n错误: {error}"
            )
            self.data_status_label.setText(self._data_status_text(offline=True))
            return

        local_latest = self.data_repository.get_latest()
        if local_latest is None or latest.draw_date > local_latest.draw_date:
            self.data_repository.update([latest])
            self.data_analyzer = LotteryAnalyzer(self.data_repository.get_all())
            self.settings.last_data_update = datetime.now().isoformat()
            self.settings.sync()
            self.data_status_label.setText(self._data_status_text(offline=False))
            self._refresh_data_stats()
            QMessageBox.information(
                self,
                "更新成功",
                f"已更新到最新一期 {latest.issue}\n"
                f"开奖日期: {latest.draw_date.date()}\n"
                f"红球: {' '.join(f'{r:02d}' for r in latest.red_balls)}\n"
                f"蓝球: {latest.blue_ball:02d}",
            )
        else:
            self.settings.last_data_update = datetime.now().isoformat()
            self.settings.sync()
            self.data_status_label.setText(self._data_status_text(offline=False))
            QMessageBox.information(self, "已是最新", f"当前数据已是最新一期 {local_latest.issue}")

    def _setup_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")

        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        tools_menu = menubar.addMenu("工具")
        backtest_action = QAction("历史回测", self)
        backtest_action.setToolTip("选择历史开奖日期，用策略基于当时已知数据预测并对比真实结果。")
        backtest_action.triggered.connect(self._show_backtest_dialog)
        tools_menu.addAction(backtest_action)

        help_menu = menubar.addMenu("帮助")
        guide_action = QAction("学习文档", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.setToolTip("打开概率统计与机器学习学习文档（本窗口内查看）。")
        guide_action.triggered.connect(self._show_learning_guide)
        help_menu.addAction(guide_action)

        # 其余帮助文档，统一由内置 Markdown 阅读器渲染显示
        for label, filename in (
            ("使用帮助", "help.md"),
            ("XGBoost 使用教程", "XGBoost_TUTORIAL.md"),
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

        # 保存用户设置的策略、注数与参数，下次启动自动恢复
        user_options = {k: v for k, v in options.items() if k != "history"}
        self.settings.last_strategy_id = strategy_id
        self.settings.default_count = count
        self.settings.last_strategy_options = user_options
        self.settings.sync()

        # 需要历史记录的策略自动注入数据
        history_dependent = {
            "hot_cold",
            "smart_hot_cold",
            "missing_number",
            "balanced",
            "xgboost",
        }
        if strategy_id in history_dependent:
            records = self.data_repository.get_all()
            if not records:
                QMessageBox.warning(self, "缺少数据", "该策略需要官方开奖数据，请先更新数据。")
                return
            options["history"] = records

        # XGBoost：若当前数据对应的模型已过期，先（拉取最新数据并）训练，再生成
        if strategy_id == "xgboost":
            records = self.data_repository.get_all()
            lookback = compute_lookback(len(records))
            if not is_model_current(records, lookback):
                self.generate_btn.setEnabled(False)
                self.generate_btn.setText("准备模型...")
                self._start_training(
                    after=lambda err: self._after_generate_train(
                        err, strategy_id, count, options
                    )
                )
                return

        self._launch_generation(strategy_id, count, options)

    def _launch_generation(self, strategy_id, count, options) -> None:
        """在后台线程启动号码生成（避免耗时策略冻结 UI）."""
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("生成中...")

        self._generate_thread = GenerateTicketsThread(
            self.engine, strategy_id, count, options, self
        )
        self._generate_thread.result_ready.connect(self._on_generation_finished)
        self._generate_thread.start()

    def _after_generate_train(self, error, strategy_id, count, options) -> None:
        """生成前的模型训练完成：成功则用最新数据继续生成，失败则提示."""
        if error:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("立即生成")
            QMessageBox.critical(self, "训练失败", f"模型训练失败:\n{error}")
            return
        # 训练已把最新数据合并入库，用更新后的数据重新注入历史后再生成
        options["history"] = self.data_repository.get_all()
        self._launch_generation(strategy_id, count, options)

    def _on_generation_finished(self, tickets, error) -> None:
        """号码生成完成回调."""
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("立即生成")

        if error:
            QMessageBox.critical(self, "生成失败", str(error))
            return

        self._last_generated = tickets
        self._annotate_target_period(tickets)
        self._display_results(tickets)
        self.history_manager.add_many(tickets)
        self.history_panel.refresh()

    def _annotate_target_period(self, tickets: list) -> None:
        """为本次生成的号码标注预测目标期号与开奖日期.

        信息写入每张投注单的 details，从而同时用于界面展示、PDF/打印与历史记录，
        提醒用户当前预测的是哪一期，避免忘记先更新最新开奖数据。
        """
        if not tickets:
            return
        info = self.data_repository.next_period_info()
        if not info:
            return
        next_date = info["next_date"]
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
        """根据 details 中的目标期号信息生成展示文本行（无信息则返回空列表）."""
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
            if details.get("stale"):
                self.target_label.setStyleSheet("color:#D32F2F;font-weight:bold;")
            else:
                self.target_label.setStyleSheet("color:#333;")
            self.target_label.setVisible(True)
        else:
            self.target_label.clear()
            self.target_label.setVisible(False)

        text_lines = []
        for idx, ticket in enumerate(tickets, start=1):
            line = f"{idx:02d}. {ticket.format_compact()}"
            if ticket.basis:
                line += f"  [{ticket.basis}]"
            text_lines.append(line)
            row = TicketRowWidget(ticket, show_index=idx)
            self.result_container_layout.insertWidget(idx - 1, row)

        # 如果包含概率详情，提供独立窗口查看大图
        self._last_chart_details = details
        has_chart = bool(self._last_chart_details.get("red_probabilities"))
        self.chart_btn.setVisible(has_chart)

        header = target_lines + ["-" * 30] if target_lines else []
        self.result_text.setText("\n".join(header + text_lines))

    def _show_probability_chart(self) -> None:
        """在独立窗口中显示更大的概率折线图."""
        details = getattr(self, "_last_chart_details", None)
        if not details or not details.get("red_probabilities"):
            QMessageBox.information(self, "提示", "当前没有可查看的概率图表。")
            return
        dialog = ProbabilityChartDialog(details, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._chart_dialog = dialog
        dialog.show()

    @staticmethod
    def _build_probability_details_html(details: dict) -> str:
        """生成 XGBoost 概率详情的 HTML 字符串（折线图）."""
        return build_probability_charts_html(
            red_probabilities=details.get("red_probabilities", []),
            blue_probabilities=details.get("blue_probabilities", []),
            lookback=details.get("lookback", "-"),
            diversity_boost=details.get("diversity_boost", "-"),
        )

    @staticmethod
    def _build_probability_details_html_for_print(details: dict) -> str:
        """生成适合 PDF/打印的概率详情 HTML（折线图）."""
        return build_probability_charts_html(
            red_probabilities=details.get("red_probabilities", []),
            blue_probabilities=details.get("blue_probabilities", []),
            lookback=details.get("lookback", "-"),
            diversity_boost=details.get("diversity_boost", "-"),
        )

    def _copy_all(self) -> None:
        text = self.result_text.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "提示", "没有可复制的号码")
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text, QClipboard.Mode.Clipboard)
        QMessageBox.information(self, "复制成功", "号码已复制到剪贴板")

    def _print_results(self) -> None:
        """打印当前生成结果."""
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        self._print_tickets(self._last_generated, "双色球生成结果")

    def _export_pdf_results(self) -> None:
        """导出当前生成结果为 PDF."""
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        self._export_tickets_to_pdf(self._last_generated, "双色球生成结果")

    def _print_tickets(self, tickets: list, title: str) -> None:
        """通用打印方法，打印失败时只提示一次."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        html = self._build_print_html(tickets, title)
        document = QTextEdit()
        document.setHtml(html)
        try:
            document.print_(printer)
        except Exception as exc:  # noqa: BLE001
            self._show_print_error_once(str(exc))

    def _export_tickets_to_pdf(self, tickets: list, title: str) -> None:
        """导出为 PDF，不依赖打印机驱动."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"caipiao_result_{timestamp}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF", default_name, "PDF 文件 (*.pdf)"
        )
        if not path:
            return

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize.A4)
        html = self._build_print_html(tickets, title)
        document = QTextEdit()
        document.setHtml(html)
        try:
            document.print_(writer)
            QMessageBox.information(self, "导出成功", f"已导出到: {path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _show_print_error_once(self, message: str) -> None:
        """会话内只显示一次打印错误."""
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
            reds = " ".join(
                f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
                f'text-align:center;border-radius:14px;background:#D32F2F;color:#fff;'
                f'margin:2px;font-weight:bold;">{b.number:02d}</span>'
                for b in ticket.red_balls
            )
            blue = (
                f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
                f'text-align:center;border-radius:14px;background:#1976D2;color:#fff;'
                f'margin:2px;font-weight:bold;">{ticket.blue_ball.number:02d}</span>'
            )
            rows.append(
                f"<tr><td style='padding:8px;border-bottom:1px solid #ddd;'>"
                f"<b>{idx:02d}.</b></td>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;'>{reds} {blue}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;color:#666;'>"
                f"{ticket.format_compact()}</td></tr>"
            )
            if ticket.basis:
                rows.append(
                    f"<tr><td></td>"
                    f"<td colspan='2' style='padding:0 8px 8px 8px;color:#888;font-size:12px;'>"
                    f"生成依据：{ticket.basis}</td></tr>"
                )

        details_html = ""
        if tickets and tickets[0].details.get("red_probabilities"):
            details_html = MainWindow._build_probability_details_html_for_print(tickets[0].details)

        target_html = ""
        if tickets:
            target_lines = MainWindow._format_target_lines(tickets[0].details)
            if target_lines:
                color = "#D32F2F" if tickets[0].details.get("stale") else "#333"
                target_html = (
                    f'<p style="text-align:center;color:{color};font-weight:bold;">'
                    f'{"<br>".join(target_lines)}</p>'
                )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: "Microsoft YaHei", sans-serif; margin: 40px; }}
                h1 {{ color: #D32F2F; text-align: center; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #f5f5f5; padding: 10px; text-align: left; }}
                td {{ vertical-align: middle; }}
                .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 12px; }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            <p style="text-align:center;color:#666;">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            {target_html}
            {details_html}
            <table>
                <tr>
                    <th style="width:60px;">序号</th>
                    <th>号码</th>
                    <th style="width:140px;">紧凑格式</th>
                </tr>
                {''.join(rows)}
            </table>
            <p class="footer">本结果由双色球号码生成器生成，仅供娱乐参考。</p>
        </body>
        </html>
        """


    def _save_to_history(self) -> None:
        if not hasattr(self, "_last_generated") or not self._last_generated:
            QMessageBox.information(self, "提示", "请先生成号码")
            return
        self.history_manager.add_many(self._last_generated)
        self.history_panel.refresh()
        QMessageBox.information(self, "保存成功", f"已保存 {len(self._last_generated)} 注到历史记录")

    def _on_history_changed(self) -> None:
        # 历史变化时的回调，可扩展统计更新
        pass

    def _choose_plugin_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择插件目录", str(self.plugin_manager.plugin_dir))
        if path:
            self.plugin_manager.plugin_dir = Path(path)
            self.plugin_dir_edit.setText(path)
            self.settings.plugin_dir = path
            self.settings.sync()

    def _reload_plugins(self) -> None:
        self.plugin_manager.unload_all()
        self._register_builtin_strategies()
        self.plugin_manager.load_all()
        self.strategy_panel._refresh_strategies()
        self._refresh_plugin_list()
        QMessageBox.information(self, "插件重载", "插件已重新加载")

    def _refresh_plugin_list(self) -> None:
        lines = []
        for strategy in self.engine.list_strategies():
            lines.append(
                f"• {strategy.metadata.name} ({strategy.metadata.id})\n"
                f"  {strategy.metadata.description}"
            )
        self.plugin_list.setText("\n\n".join(lines))

    def _apply_theme(self) -> None:
        is_dark = self.dark_theme_check.isChecked()
        self.settings.dark_theme = is_dark
        if is_dark:
            self.setStyleSheet(self._dark_stylesheet())
        else:
            self.setStyleSheet(self._light_stylesheet())

    def _save_settings(self) -> None:
        self.settings.default_count = self.settings_count_spin.value()
        self.settings.dark_theme = self.dark_theme_check.isChecked()
        self.settings.last_strategy_id = self.strategy_panel.current_strategy_id()
        self.settings.sync()
        QMessageBox.information(self, "设置已保存", "设置已保存并生效")

    def _docs_dir(self) -> Path:
        """返回项目 docs 目录."""
        return Path(__file__).resolve().parents[2] / "docs"

    def _show_doc(self, title: str, filename: str) -> None:
        """用内置 Markdown 阅读器打开 docs 目录下的文档."""
        md_path = self._docs_dir() / filename
        if not md_path.exists():
            QMessageBox.warning(self, "文档缺失", f"未找到文档：{md_path}")
            return
        dialog = MarkdownDialog(
            title, md_path, dark=self.settings.dark_theme, parent=self
        )
        dialog.exec()

    def _show_learning_guide(self) -> None:
        """在应用内打开学习文档（Markdown 渲染）."""
        self._show_doc("学习文档 - 概率统计与机器学习", "LEARNING_GUIDE.md")

    def _show_backtest_dialog(self) -> None:
        """打开历史回测对话框."""
        if not self.data_repository.get_count():
            QMessageBox.information(
                self, "缺少数据", "请先更新本地开奖数据，再进行历史回测。"
            )
            return
        dialog = BacktestDialog(self.engine, self.data_repository, self)
        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "<h2>双色球号码生成器</h2>"
            "<p>版本: 1.0.0</p>"
            "<p>基于 PySide6 开发，支持多种生成策略与插件扩展。</p>"
            "<p>本软件仅供娱乐参考，不保证中奖。</p>",
        )

    @staticmethod
    def _light_stylesheet() -> str:
        return """
        QWidget {
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            font-size: 13px;
            color: #0A2540;
            background-color: #EEF4F9;
        }
        QMainWindow {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.9,
                stop:0 #F6FAFC, stop:1 #DCE8F2);
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0077B6, stop:1 #023E8A);
            color: #FFFFFF;
            border: 1px solid #0096C7;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0096C7, stop:1 #0077B6);
            border: 1px solid #48CAE4;
        }
        QPushButton:pressed {
            background: #005F73;
        }
        QPushButton#generate_btn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #D90429, stop:1 #8D0801);
            color: #FFFFFF;
            border: 1px solid #EF233C;
            font-size: 15px;
            padding: 10px 18px;
        }
        QPushButton#generate_btn:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #EF233C, stop:1 #D90429);
            border: 1px solid #FF5C7F;
        }
        QLineEdit, QSpinBox, QComboBox, QTextEdit {
            background-color: rgba(255, 255, 255, 0.85);
            border: 1px solid rgba(0, 119, 182, 0.45);
            border-radius: 6px;
            padding: 6px;
            color: #0A2540;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border: 1px solid #0077B6;
        }
        QGroupBox {
            font-weight: bold;
            background-color: rgba(255, 255, 255, 0.55);
            border: 1px solid rgba(0, 119, 182, 0.30);
            border-radius: 12px;
            margin-top: 12px;
            padding-top: 12px;
            color: #0A2540;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: #0077B6;
        }
        QLabel {
            color: #0A2540;
        }
        QLabel#app_title {
            font-size: 24px;
            font-weight: bold;
            color: #023E8A;
            padding: 8px;
        }
        QTabWidget::pane {
            border: 1px solid rgba(0, 119, 182, 0.25);
            border-radius: 12px;
            background-color: rgba(255, 255, 255, 0.35);
        }
        QTabBar::tab {
            background: rgba(255, 255, 255, 0.55);
            color: #0077B6;
            border: 1px solid rgba(0, 119, 182, 0.25);
            padding: 8px 18px;
            margin-right: 4px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0077B6, stop:1 #023E8A);
            color: #FFFFFF;
            border: 1px solid #0096C7;
        }
        QTabBar::tab:hover:!selected {
            background: rgba(0, 150, 199, 0.15);
        }
        QScrollArea > QWidget {
            background-color: transparent;
        }
        QListWidget {
            background-color: rgba(255, 255, 255, 0.55);
            border: 1px solid rgba(0, 119, 182, 0.25);
            border-radius: 10px;
            padding: 6px;
            color: #0A2540;
        }
        """

    @staticmethod
    def _dark_stylesheet() -> str:
        return """
        QWidget {
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            font-size: 13px;
            color: #E0F7FF;
            background-color: #05070A;
        }
        QMainWindow {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.9,
                stop:0 #0B1021, stop:1 #030408);
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #00B4D8, stop:1 #0077B6);
            color: #FFFFFF;
            border: 1px solid #48CAE4;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #48CAE4, stop:1 #0096C7);
            border: 1px solid #90E0EF;
        }
        QPushButton:pressed {
            background: #005F73;
        }
        QPushButton#generate_btn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #FF4D6D, stop:1 #D90429);
            color: #FFFFFF;
            border: 1px solid #FF758F;
            font-size: 15px;
            padding: 10px 18px;
        }
        QPushButton#generate_btn:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #FF758F, stop:1 #FF4D6D);
            border: 1px solid #FFB3C1;
        }
        QLineEdit, QSpinBox, QComboBox, QTextEdit {
            background-color: rgba(10, 14, 23, 0.85);
            border: 1px solid rgba(0, 210, 255, 0.45);
            border-radius: 6px;
            padding: 6px;
            color: #E0F7FF;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border: 1px solid #00D2FF;
        }
        QGroupBox {
            font-weight: bold;
            background-color: rgba(16, 24, 39, 0.65);
            border: 1px solid rgba(0, 210, 255, 0.30);
            border-radius: 12px;
            margin-top: 12px;
            padding-top: 12px;
            color: #E0F7FF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: #48CAE4;
        }
        QLabel {
            color: #E0F7FF;
        }
        QLabel#app_title {
            font-size: 24px;
            font-weight: bold;
            color: #48CAE4;
            padding: 8px;
        }
        QTabWidget::pane {
            border: 1px solid rgba(0, 210, 255, 0.25);
            border-radius: 12px;
            background-color: rgba(10, 16, 28, 0.50);
        }
        QTabBar::tab {
            background: rgba(16, 24, 39, 0.65);
            color: #90E0EF;
            border: 1px solid rgba(0, 210, 255, 0.25);
            padding: 8px 18px;
            margin-right: 4px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #00B4D8, stop:1 #0077B6);
            color: #FFFFFF;
            border: 1px solid #48CAE4;
        }
        QTabBar::tab:hover:!selected {
            background: rgba(0, 180, 216, 0.20);
        }
        QScrollArea > QWidget {
            background-color: transparent;
        }
        QListWidget {
            background-color: rgba(10, 16, 28, 0.55);
            border: 1px solid rgba(0, 210, 255, 0.25);
            border-radius: 10px;
            padding: 6px;
            color: #E0F7FF;
        }
        """
