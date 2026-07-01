"""应用入口."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def run() -> int:
    """启动应用程序."""
    # QtWebEngine（帮助文档渲染）要求在创建 QApplication 前开启 OpenGL 上下文共享。
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv)
    app.setApplicationName("双色球号码生成器")
    app.setApplicationVersion("1.0.0")

    # 设置全局字体，避免某些控件出现负字号警告
    app.setFont(QFont("Microsoft YaHei", 10))

    # 设置应用图标（任务栏显示）
    icon_path = Path(__file__).resolve().parent / "ui" / "resources" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
