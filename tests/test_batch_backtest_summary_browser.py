"""批量回测汇总面板改用 QTextBrowser（浏览器控件）显示的回归测试."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QTextBrowser

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ
from caipiao.core.strategies.lotteries.ssq.random import SSQRandomStrategy
from caipiao.data.models import DrawRecord
from caipiao.ui.components import batch_backtest_dialog as bbd_mod
from caipiao.ui.components.batch_backtest_dialog import BatchBacktestDialog


def _make_records(n=35):
    return [
        DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        for i in range(n)
    ]


def _make_context():
    ctx = MagicMock()
    ctx.profile = SSQ
    engine = GenerationEngine()
    engine.register(SSQRandomStrategy())
    ctx.engine = engine
    records = _make_records(35)
    repo = MagicMock()
    repo.get_date_range.return_value = (records[0].draw_date, records[-1].draw_date)
    repo.get_all.return_value = records
    ctx.data_repository = repo
    return ctx


@pytest.fixture
def dialog(qtbot, monkeypatch):
    """构造一个 BatchBacktestDialog，屏蔽真实 DB / 参数组存储副作用."""
    monkeypatch.setattr(bbd_mod, "BacktestDatabase", lambda *a, **k: MagicMock())
    monkeypatch.setattr(bbd_mod, "ParameterGroupStore", lambda *a, **k: MagicMock())
    store = MagicMock()
    store.load.return_value = MagicMock(locked=[])
    dlg = BatchBacktestDialog(_make_context(), optimal_param_store=store)
    qtbot.addWidget(dlg)
    return dlg


def test_summary_widget_is_text_browser(dialog):
    """汇总控件应为 QTextBrowser（可滚动），而非会被布局截断的 QLabel。"""
    assert isinstance(dialog.summary_label, QTextBrowser)
    assert not isinstance(dialog.summary_label, QLabel)


def test_initial_summary_placeholder(dialog):
    assert "尚未开始" in dialog._summary_plain
    assert "尚未开始" in dialog.summary_label.toPlainText()


def test_set_summary_displays_full_multiline_content(dialog):
    """长文本（含多注中奖明细）应完整显示，不被截断。"""
    text = (
        "回测期数：10 期\n"
        "每期注数：5 注\n"
        "总花费：100 元\n"
        "固定奖金合计：250 元\n"
        "各注中奖次数：第 1 注：3 次（30.0%） | 第 2 注：2 次（20.0%） | "
        "第 3 注：1 次（10.0%） | 第 4 注：0 次（0.0%） | 第 5 注：0 次（0.0%）\n"
        "盈亏：+150 元"
    )
    dialog._set_summary(text)
    plain = dialog.summary_label.toPlainText()
    # 每一行都应完整出现（修复前 QLabel 会截断“各注中奖次数”这一长行）
    assert "回测期数：10 期" in plain
    assert "第 5 注：0 次（0.0%）" in plain
    assert "盈亏：+150 元" in plain
    assert dialog._summary_plain == text


def test_set_summary_colors_profit_positive(dialog):
    dialog._set_summary("盈亏：+150 元")
    html = dialog.summary_label.toHtml().lower()
    assert "#2e7d32" in html  # 绿色
    assert "+150" in dialog.summary_label.toPlainText()


def test_set_summary_colors_profit_negative(dialog):
    dialog._set_summary("盈亏：-80 元")
    html = dialog.summary_label.toHtml().lower()
    assert "#c62828" in html  # 红色
    assert "-80" in dialog.summary_label.toPlainText()


def test_set_summary_escapes_html(dialog):
    """含 HTML 特殊字符的内容应被转义，不被当作标签解析。"""
    dialog._set_summary("策略：<script>alert(1)</script> & data")
    html = dialog.summary_label.toHtml()
    assert "<script>alert(1)</script>" not in html  # 未转义的原始标签不应存在
    plain = dialog.summary_label.toPlainText()
    assert "<script>alert(1)</script>" in plain  # 纯文本可还原原始字符


def test_stopped_append_uses_summary_plain(dialog):
    """「已停止」追加基于 _summary_plain，而非已废弃的 QLabel.text()。"""
    dialog._set_summary("正在批量回测，请稍候...")
    dialog._set_summary(dialog._summary_plain + "\n（已停止）")
    assert "（已停止）" in dialog._summary_plain
    assert "（已停止）" in dialog.summary_label.toPlainText()


def test_save_button_in_header_not_blocking_browser(dialog):
    """「保存为参数组」按钮单独成行，不应挤压汇总浏览器宽度。"""
    assert dialog.save_group_btn.parentWidget() is not None
    # 浏览器有最小高度，保证多行内容可见
    assert dialog.summary_label.minimumHeight() >= 100
