"""主窗口工具栏冒烟测试."""

import pytest


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.slow
@pytest.mark.filterwarnings("ignore::pytest.PytestUnknownMarkWarning")
def test_main_window_has_toolbar_with_five_actions(tmp_path, monkeypatch):
    """启动 MainWindow 后，顶部工具栏应包含 5 个指定操作."""
    _ensure_qapp()

    from caipiao.ui.main_window import MainWindow

    # 使用临时数据目录，避免污染真实数据
    monkeypatch.setattr(
        "caipiao.ui.main_window.app_data_dir", lambda: tmp_path / ".caipiao"
    )

    window = MainWindow()
    try:
        assert hasattr(window, "toolbar")
        assert window.toolbar is not None

        texts = [action.text() for action in window.toolbar.actions()]
        expected = ["立即生成", "复制全部号码", "打印结果", "导出 PDF", "保存到历史"]
        assert texts == expected
    finally:
        window.close()
        window.deleteLater()
