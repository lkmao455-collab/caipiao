"""启动时自动更新所有彩种数据的进度对话框."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.profile import LotteryProfile
from ...data.models import DrawRecord
from ...persistence.settings import AppSettings
from ..workers import FetchAllLotteriesThread

logger = logging.getLogger(__name__)

# 进度条最少显示时间（毫秒）
MIN_DISPLAY_TIME_MS = 2000


class AutoUpdateDialog(QDialog):
    """启动时自动更新所有彩种数据的进度对话框."""

    update_finished = Signal()  # 更新完成信号

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("正在更新开奖数据")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self.settings = AppSettings()
        self._results: List[Tuple[LotteryProfile, DrawRecord | None, str | None]] = []
        self._success_count = 0
        self._fail_count = 0
        self._start_time = time.time()
        self._update_finished = False

        self._setup_ui()
        self._start_update()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 状态标签
        self.status_label = QLabel("正在准备更新...")
        layout.addWidget(self.status_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 详情标签
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #666;")
        layout.addWidget(self.detail_label)

        # 跳过按钮（更新完成后变为关闭按钮）
        self.skip_btn = QPushButton("跳过")
        self.skip_btn.clicked.connect(self._on_skip)
        layout.addWidget(self.skip_btn)

    def _start_update(self) -> None:
        """启动更新线程."""
        self._start_time = time.time()
        self._thread = FetchAllLotteriesThread(self, timeout=30)
        self._thread.progress.connect(self._on_progress)
        self._thread.result_ready.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, name: str, current: int, total: int) -> None:
        """更新进度显示."""
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"正在更新: {name}")
        self.detail_label.setText(f"进度: {current + 1}/{total}")

    def _on_finished(self, results, error) -> None:
        """更新完成处理."""
        self._update_finished = True

        if error:
            self.status_label.setText("更新失败")
            self.detail_label.setText(f"错误: {error}")
            self._schedule_close()
            return

        if results is None:
            self.status_label.setText("更新失败")
            self.detail_label.setText("未获取到数据")
            self._schedule_close()
            return

        self._results = results
        self._success_count = sum(1 for _, r, _ in results if r is not None)
        self._fail_count = sum(1 for _, r, _ in results if r is None)

        # 保存更新的数据
        self._save_updates()

        # 更新完成
        self.progress_bar.setValue(100)
        self.status_label.setText("更新完成")
        self.detail_label.setText(
            f"成功: {self._success_count} 个彩种, 失败: {self._fail_count} 个彩种"
        )
        self.skip_btn.setText("关闭")

        # 记录更新时间
        self.settings.last_data_update = datetime.now().isoformat()
        self.settings.sync()

        # 确保进度条至少显示 MIN_DISPLAY_TIME_MS
        self._schedule_close()

    def _schedule_close(self) -> None:
        """安排关闭对话框，确保进度条至少显示 MIN_DISPLAY_TIME_MS."""
        elapsed_ms = int((time.time() - self._start_time) * 1000)
        remaining_ms = max(0, MIN_DISPLAY_TIME_MS - elapsed_ms)

        if remaining_ms > 0:
            # 还需要等待
            self.skip_btn.setEnabled(False)
            self.skip_btn.setText(f"请稍候...")
            QTimer.singleShot(remaining_ms, self._enable_close)
        else:
            # 已经显示够了，可以立即关闭
            self.skip_btn.setText("关闭")
            self.skip_btn.setEnabled(True)

    def _enable_close(self) -> None:
        """启用关闭按钮."""
        self.skip_btn.setText("关闭")
        self.skip_btn.setEnabled(True)

    def _save_updates(self) -> None:
        """保存更新的数据到本地."""
        for profile, record, error in self._results:
            if record is None:
                continue

            try:
                # 获取上下文并更新数据
                from ...ui.lottery_context import ContextManager
                from ...persistence.history import HistoryManager
                from ...utils import app_data_dir

                data_dir = app_data_dir()
                history_manager = HistoryManager(data_dir / "history.json")
                context_manager = ContextManager(data_dir, history_manager)
                context = context_manager.get(profile.key)
                context.update_data([record])
                logger.info("已更新 %s 数据: %s", profile.name, record)
            except Exception as exc:
                logger.warning("保存 %s 数据失败: %s", profile.name, exc)

    def _on_skip(self) -> None:
        """跳过或关闭."""
        if self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.wait(3000)
        self.accept()
        self.update_finished.emit()
