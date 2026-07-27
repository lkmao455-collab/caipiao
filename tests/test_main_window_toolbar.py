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


def test_validated_current_key_falls_back_for_hidden_lottery():
    """已从导航隐藏的彩种（七乐彩）作为当前彩种时应回退到双色球。"""
    from caipiao.ui.main_window import MainWindow

    assert MainWindow._validated_current_key("qlc") == "ssq"
    assert MainWindow._validated_current_key("ssq") == "ssq"
    assert MainWindow._validated_current_key("3d") == "3d"
    assert MainWindow._validated_current_key("nonexistent") == "ssq"


@pytest.mark.slow
@pytest.mark.filterwarnings("ignore::pytest.PytestUnknownMarkWarning")
def test_qlc_hidden_from_lottery_combo(tmp_path, monkeypatch):
    """彩种下拉框不应包含七乐彩。"""
    _ensure_qapp()

    from caipiao.ui.main_window import MainWindow

    monkeypatch.setattr(
        "caipiao.ui.main_window.app_data_dir", lambda: tmp_path / ".caipiao"
    )

    window = MainWindow()
    try:
        keys = [
            window.lottery_combo.itemData(i)
            for i in range(window.lottery_combo.count())
        ]
        assert "qlc" not in keys
        assert "ssq" in keys
        assert "3d" in keys
    finally:
        window.close()
        window.deleteLater()
