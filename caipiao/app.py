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
    app.setApplicationName("彩票号码生成器")
    app.setApplicationVersion("2.0.0")

    # 设置全局字体：明确使用正像素大小，避免某些系统主题下解析出负字号。
    font = QFont("Microsoft YaHei")
    font.setPointSize(10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # 样式表统一使用 pt 单位，避免 QFont::setPointSize 因解析 px 字体产生 pointSize=-1 的警告。
    app.setStyleSheet("""
        QToolTip {
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            font-size: 10pt;
        }
    """)

    # 设置应用图标（任务栏显示）
    icon_path = Path(__file__).resolve().parent / "ui" / "resources" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
