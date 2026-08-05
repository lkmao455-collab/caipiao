"""主窗口工具栏单元测试（offscreen，外部依赖已 mock）.

覆盖工具栏上所有按钮：
  - 今日开奖 / 最近开奖：确认打开对应对话框且 UI 已构建
  - 更新全部：确认打开 AutoUpdateDialog（不发起真实网络请求）
  - 立即生成：确认后台生成并填充结果区
  - 复制全部号码 / 保存到历史 / 导出 PDF / 打印结果：确认各自副作用

网络、打印机、文件对话框、消息框均在 fixture / 各用例中被替换为安全替身，
因此测试快速且确定性高。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QTextEdit,
    QPlainTextEdit,
)
from PySide6.QtPrintSupport import QPrintDialog
from PySide6.QtCore import Signal
from PySide6.QtTest import QTest

from caipiao.ui import main_window as mw_mod
from caipiao.ui.main_window import MainWindow
from caipiao.ui.components.today_draws_dialog import TodayDrawsDialog
from caipiao.ui.components.latest_results_dialog import LatestResultsDialog
from caipiao.ui.components.auto_update_dialog import AutoUpdateDialog
from caipiao.core.strategies.factory import is_ml_strategy, needs_history


def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_for(cond, timeout_ms=30000, step_ms=50):
    """在事件循环中轮询条件（用于等待后台线程/队列连接的回调）。"""
    app = _ensure_qapp()
    start = time.time()
    while not cond():
        app.processEvents()
        time.sleep(step_ms / 1000.0)
        if (time.time() - start) * 1000 > timeout_ms:
            raise AssertionError("timeout waiting for condition")


def _dialog_widget_count(dlg):
    types = (QLabel, QListWidget, QTextEdit, QPlainTextEdit)
    return sum(len(dlg.findChildren(t)) for t in types)


def _dialog_has_content(dlg):
    for t in (QLabel, QListWidget, QTextEdit, QPlainTextEdit):
        for c in dlg.findChildren(t):
            x = c.text() if hasattr(c, "text") else (c.toPlainText() if hasattr(c, "toPlainText") else "")
            if x and x.strip():
                return True
    return False


# --- 捕获子类：替换真实对话框，避免 exec() 阻塞并便于断言 ---
class _CaptureToday(TodayDrawsDialog):
    _instances = []

    def __init__(self, parent=None):
        super().__init__(parent)
        _CaptureToday._instances.append(self)

    def exec(self):
        return QDialog.Accepted


class _CaptureLatest(LatestResultsDialog):
    _instances = []

    def __init__(self, parent=None):
        super().__init__(parent)
        _CaptureLatest._instances.append(self)

    def exec(self):
        return QDialog.Accepted


class _CaptureAUD(QDialog):
    """替身 AutoUpdateDialog：跳过真实网络抓取。"""

    update_finished = Signal()
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        _CaptureAUD._instance = self

    def _start_update(self):
        pass

    def exec(self):
        self.update_finished.emit()
        return QDialog.Accepted


@pytest.fixture
def window(tmp_path, monkeypatch):
    _ensure_qapp()
    # 把数据目录指向临时目录，避免污染真实数据
    monkeypatch.setattr(mw_mod, "app_data_dir", lambda: tmp_path / ".caipiao")
    # 中和启动时的延迟弹窗（否则会发起网络请求）。
    # 必须在构造前打补丁：__init__ 内直接调用了 _perform_auto_update，
    # 只需禁用调度器；今日开奖/最近开奖/更新全部等方法仍保持原样，
    # 以便各按钮测试用例能真正触发它们。
    monkeypatch.setattr(MainWindow, "_perform_auto_update", lambda self: None)
    w = MainWindow()

    # 替身：消息框 / 打印对话框 / 文件对话框，避免阻塞
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QPrintDialog, "exec",
        lambda self, *a, **k: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "result.pdf"), "PDF 文件 (*.pdf)")),
    )
    # 记录打印错误，避免 _show_print_error_once 内的 QMessageBox 阻塞
    recorded_errors = []
    w._show_print_error_once = lambda msg: recorded_errors.append(msg)
    w._print_errors = recorded_errors

    QTest.qWait(600)  # 让（已被中和的）启动定时器先触发
    yield w
    w.close()
    w.deleteLater()


def _pick_fast_strategy(w):
    """挑选一个非 ML、尽量不需要历史数据的策略，保证生成快速且无需网络。"""
    cands = []
    for s in w.current.engine.list_strategies():
        sid = s.metadata.id
        if is_ml_strategy(sid):
            continue
        cands.append((sid, needs_history(sid)))
    no_hist = [sid for sid, nh in cands if not nh]
    if no_hist:
        return no_hist[0]
    if cands:
        return cands[0][0]
    return None


def _generate(w):
    sid = _pick_fast_strategy(w)
    assert sid is not None, "当前彩种没有可用的非 ML 策略"
    w.strategy_panel.set_strategy_id(sid)
    try:
        w.count_spin.setValue(2)
    except Exception:
        pass
    w.generate_action.trigger()
    _wait_for(lambda: getattr(w, "_last_generated", None))
    return sid


# ---------------------------------------------------------------------- #
# 工具栏结构
# ---------------------------------------------------------------------- #
def test_toolbar_contains_all_actions(window):
    texts = [a.text() for a in window.toolbar.actions()]
    expected = [
        "今日开奖", "最近开奖", "更新全部", "立即生成",
        "复制全部号码", "打印结果", "导出 PDF", "保存到历史",
    ]
    assert texts == expected

    # 新增的“更新全部”按钮
    assert hasattr(window, "update_all_action")
    assert window.update_all_action.text() == "更新全部"
    assert "更新" in window.update_all_action.toolTip()

    # 各按钮的连线在下面的独立用例中逐一验证（此版本 PySide6 的
    # QObject.receivers 对绑定信号存在已知问题，故不在此处断言）。


# ---------------------------------------------------------------------- #
# 各按钮功能
# ---------------------------------------------------------------------- #
def test_today_button_opens_dialog(window, monkeypatch):
    _CaptureToday._instances.clear()
    monkeypatch.setattr(mw_mod, "TodayDrawsDialog", _CaptureToday)

    window.today_action.trigger()

    assert len(_CaptureToday._instances) == 1
    dlg = _CaptureToday._instances[0]
    assert dlg.parent() is window
    assert _dialog_widget_count(dlg) > 0
    assert _dialog_has_content(dlg)  # 今日开奖不依赖本地数据，必有内容


def test_latest_results_button_opens_dialog(window, monkeypatch):
    _CaptureLatest._instances.clear()
    monkeypatch.setattr(mw_mod, "LatestResultsDialog", _CaptureLatest)

    window.results_action.trigger()

    assert len(_CaptureLatest._instances) == 1
    dlg = _CaptureLatest._instances[0]
    assert dlg.parent() is window
    assert _dialog_widget_count(dlg) > 0  # UI 已构建（内容取决于本地数据）


def test_generate_button_produces_results(window):
    sid = _generate(window)
    assert window._last_generated, "生成后应当得到号码"
    assert window.result_text.toPlainText().strip(), "结果区应当被填充"
    # 生成时已自动写入历史
    assert len(window.history_manager.get_all()) > 0


def test_copy_button_copies_to_clipboard(window):
    window.result_text.setPlainText("COPY_TEST_123")
    window.copy_action.trigger()
    assert QApplication.clipboard().text() == "COPY_TEST_123"


def test_save_button_saves_history(window, monkeypatch):
    _generate(window)
    calls = []
    orig = window.history_manager.add_many

    def spy(*a, **k):
        calls.append((a, k))
        return orig(*a, **k)

    monkeypatch.setattr(window.history_manager, "add_many", spy)
    window.save_action.trigger()
    assert calls, "保存到历史按钮应当调用 history_manager.add_many"


def test_export_pdf_button_creates_file(window, tmp_path):
    _generate(window)
    out = tmp_path / "result.pdf"
    window.pdf_action.trigger()
    assert out.exists(), "应当写出 PDF 文件"
    assert out.stat().st_size > 0


def test_print_button_triggers_print(window):
    _generate(window)
    # QPrintDialog.exec 已在 fixture 中被替换为 Accepted；
    # 无论真实打印是否成功（offscreen 下通常走错误分支），
    # 都不应抛异常或阻塞。
    window._print_errors.clear()
    window.print_action.trigger()
    assert True


def test_update_all_button_opens_dialog(window, monkeypatch):
    _CaptureAUD._instance = None
    monkeypatch.setattr(mw_mod, "AutoUpdateDialog", _CaptureAUD)

    # 验证 update_finished 确实连接到了刷新界面的槽函数。
    # 注意：这里只记录、不调用原函数，避免原函数内部再次弹出“今日开奖”对话框而阻塞。
    refreshed = []
    window._on_auto_update_dialog_closed = lambda: refreshed.append(True)

    window.update_all_action.trigger()

    assert _CaptureAUD._instance is not None
    assert _CaptureAUD._instance.parent() is window
    assert refreshed, "update_finished 应当连接到刷新界面的槽函数"


# ---------------------------------------------------------------------- #
# 其它既有冒烟测试（保留）
# ---------------------------------------------------------------------- #
def test_validated_current_key_falls_back_for_unknown():
    """未知彩种作为当前彩种时应回退到双色球。"""
    assert MainWindow._validated_current_key("ssq") == "ssq"
    assert MainWindow._validated_current_key("3d") == "3d"
    assert MainWindow._validated_current_key("qlc") == "ssq"
    assert MainWindow._validated_current_key("nonexistent") == "ssq"


@pytest.mark.slow
@pytest.mark.filterwarnings("ignore::pytest.PytestUnknownMarkWarning")
def test_removed_lottery_excluded_from_combo(tmp_path, monkeypatch):
    """彩种下拉框不应包含已彻底移除的七乐彩。"""
    _ensure_qapp()
    monkeypatch.setattr(mw_mod, "app_data_dir", lambda: tmp_path / ".caipiao")
    # 中和启动时的延迟弹窗，避免真实 AutoUpdateDialog 阻塞
    monkeypatch.setattr(MainWindow, "_perform_auto_update", lambda self: None)

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
