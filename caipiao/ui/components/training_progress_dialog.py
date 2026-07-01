"""模型训练进度对话框.

训练期间以应用级模态弹窗展示进度，阻止用户对主窗口进行其他操作，
避免训练未完成时的无效点击（如重复训练、切换标签、再次生成等）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget


class TrainingProgressDialog(QDialog):
    """训练进度模态对话框.

    - 应用级模态：可见时阻止用户操作其他窗口。
    - 训练完成前禁止用户关闭（去掉关闭按钮、拦截 Esc 与关闭事件）。
    - 初始为忙碌状态（滚动条），收到首个进度回调后切换为百分比进度。
    """

    def __init__(self, parent: QWidget | None = None, title: str = "正在训练模型") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        # 去掉关闭按钮与右上角问号，防止用户中途关闭窗口
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setFixedSize(360, 140)

        self._finished = False

        layout = QVBoxLayout(self)

        self.label = QLabel("正在准备训练数据…")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.bar = QProgressBar()
        # 初始为忙碌（滚动）状态，收到进度后再切换为确定进度
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)

        hint = QLabel("训练进行中，请勿操作，完成后窗口会自动关闭。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def set_progress(self, current: int, total: int) -> None:
        """更新训练进度（由后台线程通过信号触发）."""
        if total > 0:
            if self.bar.maximum() != total:
                self.bar.setRange(0, total)
            self.bar.setValue(current)
            self.label.setText(f"正在训练分类器 {current}/{total}…")
        else:
            self.bar.setRange(0, 0)

    def set_stage(self, text: str) -> None:
        """切换到新阶段：更新提示文字并把进度条切回忙碌（滚动）状态.

        用于「获取最新数据」等无确定进度的阶段；进入训练后由 ``set_progress`` 切成百分比。
        """
        self.label.setText(text)
        self.bar.setRange(0, 0)

    def mark_finished(self) -> None:
        """标记训练已结束，此后允许关闭窗口."""
        self._finished = True

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 训练中屏蔽 Esc 关闭
        if event.key() == Qt.Key.Key_Escape and not self._finished:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 训练中拒绝关闭
        if not self._finished:
            event.ignore()
            return
        super().closeEvent(event)
