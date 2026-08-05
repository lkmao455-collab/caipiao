"""对话框单元测试（offscreen，外部依赖已 mock）.

覆盖工具栏相关的三个对话框：
  - TodayDrawsDialog / LotteryItem：今日开奖彩种提示
  - LatestResultsDialog / DrawResultCard：各彩种最近一期开奖结果
  - AutoUpdateDialog：批量更新进度（用假线程替代真实网络抓取）

网络抓取、QSettings 持久化目录、文件写入均被替换为安全替身，
因此测试快速且确定性高。
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

from caipiao.data.models import DrawRecord
from caipiao.core.profile import (
    SSQ,
    DLT,
    KL8,
    FC3D,
    list_profiles,
)
from caipiao.ui.components.today_draws_dialog import TodayDrawsDialog, LotteryItem
from caipiao.ui.components.latest_results_dialog import (
    LatestResultsDialog,
    DrawResultCard,
)
from caipiao.ui.components import auto_update_dialog as aud_mod
from caipiao.ui.components.auto_update_dialog import AutoUpdateDialog


# --------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------- #
def _find_label(widget, text):
    """返回文本完全等于 text 的第一个 QLabel（不含子控件）。"""
    for c in widget.findChildren(QLabel):
        if c.text() == text:
            return c
    return None


def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _seed_record(tmp_path: Path, profile_key: str, record: DrawRecord) -> None:
    """在 tmp_path 下写入某彩种的最近一期开奖记录。"""
    import json

    storage = {
        "ssq": "draws.json",
        "3d": "draws_3d.json",
        "kl8": "draws_kl8.json",
        "dlt": "draws_dlt.json",
        "pl3": "draws_pl3.json",
        "pl5": "draws_pl5.json",
        "qxc": "draws_qxc.json",
    }[profile_key]
    (tmp_path / storage).write_text(
        json.dumps([record.to_dict()], ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------- #
# TodayDrawsDialog
# --------------------------------------------------------------------- #
def test_today_dialog_constructs(qtbot):
    dlg = TodayDrawsDialog()
    qtbot.addWidget(dlg)
    assert isinstance(dlg, TodayDrawsDialog)
    assert dlg.windowTitle() == "今日开奖彩种"
    # 至少宽度限制被设置
    assert dlg.minimumWidth() == 320
    assert dlg.maximumWidth() == 450


def test_today_dialog_lists_today_profiles(qtbot):
    dlg = TodayDrawsDialog()
    qtbot.addWidget(dlg)

    # 用与对话框一致的规则计算期望值，使断言与“今天星期几”无关
    today_weekday = datetime.now().weekday()
    expected = [
        p
        for p in list_profiles()
        if p.is_daily or today_weekday in p.draw_weekdays
    ]
    assert dlg._today_profiles == expected

    # 每个今日彩种都应渲染为一个 LotteryItem
    items = dlg.findChildren(LotteryItem)
    assert len(items) == len(expected)
    rendered_keys = {it.profile.key for it in items}
    assert rendered_keys == {p.key for p in expected}


def test_today_dialog_close_button_accepts(qtbot):
    dlg = TodayDrawsDialog()
    qtbot.addWidget(dlg)

    # findChildren 默认递归，可直接拿到“关闭”按钮
    close_btn = next(
        b for b in dlg.findChildren(QPushButton) if b.text() == "关闭"
    )
    assert close_btn is not None

    QTest.mouseClick(close_btn, Qt.MouseButton.LeftButton)
    assert dlg.result() == dlg.DialogCode.Accepted


def test_today_dialog_close_button_is_disabled(qtbot):
    dlg = TodayDrawsDialog()
    qtbot.addWidget(dlg)
    # 标题栏的关闭（X）按钮被禁用，只能点“关闭”按钮
    assert dlg.windowFlags() & Qt.WindowType.WindowCloseButtonHint == 0


# --------------------------------------------------------------------- #
# LotteryItem
# --------------------------------------------------------------------- #
def test_lottery_item_shows_daily_schedule(qtbot):
    item = LotteryItem(FC3D)  # 福彩3D 每日开奖
    qtbot.addWidget(item)
    assert _find_label(item, FC3D.name) is not None
    schedule = next(
        c for c in item.findChildren(QLabel) if c.text() == "每日开奖"
    )
    assert schedule is not None


def test_lottery_item_shows_weekday_schedule(qtbot):
    item = LotteryItem(SSQ)  # 双色球 周二/四/日
    qtbot.addWidget(item)
    assert _find_label(item, SSQ.name) is not None
    # 周X开奖 形式（至少含“开奖”二字）
    schedule = next(
        c for c in item.findChildren(QLabel) if "开奖" in c.text()
    )
    assert "周" in schedule.text() and "开奖" in schedule.text()


# --------------------------------------------------------------------- #
# DrawResultCard（纯逻辑与渲染）
# --------------------------------------------------------------------- #
def test_draw_result_card_display_groups_ssq():
    rec = DrawRecord(
        "2024010", date(2024, 1, 10), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7
    )
    card = DrawResultCard(SSQ, rec)
    groups = card._get_display_groups()
    assert groups[0] == ("红球", [1, 2, 3, 4, 5, 6], "#D32F2F")
    assert groups[1] == ("蓝球", [7], "#1976D2")


def test_draw_result_card_display_groups_dlt():
    rec = DrawRecord(
        "24010", date(2024, 1, 10),
        profile=DLT, groups={"front": [1, 2, 3, 4, 5], "back": [6, 7]},
    )
    card = DrawResultCard(DLT, rec)
    groups = card._get_display_groups()
    assert groups[0] == ("前区", [1, 2, 3, 4, 5], "#D32F2F")
    assert groups[1] == ("后区", [6, 7], "#1976D2")


def test_draw_result_card_display_groups_kl8_split_rows():
    rec = DrawRecord(
        "2024010", date(2024, 1, 10),
        profile=KL8, groups={"main": list(range(1, 21))},
    )
    card = DrawResultCard(KL8, rec)
    groups = card._get_display_groups()
    # 快乐8：20 个号拆成两行
    assert len(groups) == 2
    assert groups[0][1] == list(range(1, 11))
    assert groups[1][1] == list(range(11, 21))


def test_draw_result_card_display_groups_positional():
    rec = DrawRecord(
        "2024010", date(2024, 1, 10),
        profile=FC3D, groups={"pos": [1, 2, 3]},
    )
    card = DrawResultCard(FC3D, rec)
    groups = card._get_display_groups()
    assert groups == [("号码", [1, 2, 3], "#F57C00")]


def test_draw_result_card_none_record_returns_empty_groups():
    card = DrawResultCard(SSQ, None)
    assert card._get_display_groups() == []


def test_draw_result_card_renders_name_and_issue(qtbot):
    rec = DrawRecord(
        "2024010", date(2024, 1, 10), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7
    )
    card = DrawResultCard(SSQ, rec)
    qtbot.addWidget(card)
    assert _find_label(card, SSQ.name) is not None
    # 期号信息被渲染（含“第...期”）
    info = next(c for c in card.findChildren(QLabel) if c.text().startswith("第"))
    assert "2024010" in info.text()


def test_draw_result_card_renders_no_data(qtbot):
    card = DrawResultCard(SSQ, None)
    qtbot.addWidget(card)
    assert _find_label(card, "暂无开奖数据") is not None


# --------------------------------------------------------------------- #
# LatestResultsDialog（依赖本地数据，需 seed）
# --------------------------------------------------------------------- #
def test_latest_dialog_loads_seeded_record(qtbot, tmp_path, monkeypatch):
    # 把数据目录指向临时目录并写入双色球最近一期
    monkeypatch.setattr(
        "caipiao.utils.app_data_dir", lambda: tmp_path
    )
    rec = DrawRecord(
        "2024010", date(2024, 1, 10), red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7
    )
    _seed_record(tmp_path, "ssq", rec)

    dlg = LatestResultsDialog()
    qtbot.addWidget(dlg)

    # 应渲染出双色球的卡片
    cards = dlg.findChildren(DrawResultCard)
    ssq_card = next(c for c in cards if c.profile.key == "ssq")
    assert ssq_card.record == rec
    # 卡片中应出现双色球名称
    assert _find_label(ssq_card, SSQ.name) is not None


def test_latest_dialog_shows_no_data_when_empty(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "caipiao.utils.app_data_dir", lambda: tmp_path
    )
    # 不写入任何数据文件
    dlg = LatestResultsDialog()
    qtbot.addWidget(dlg)

    cards = dlg.findChildren(DrawResultCard)
    # 7 个彩种都应有卡片（即便无数据）
    assert len(cards) == len(list_profiles())
    for c in cards:
        assert c.record is None
        assert _find_label(c, "暂无开奖数据") is not None


# --------------------------------------------------------------------- #
# AutoUpdateDialog（用假线程替代真实网络抓取）
# --------------------------------------------------------------------- #
class _FakeFetchThread(QThread):
    """替身线程：在 start() 中同步发射进度与结果，避免真实网络请求。"""

    progress = Signal(str, int, int)
    result_ready = Signal(object, object)

    def __init__(self, parent=None, timeout=30, results=None, error=None):
        super().__init__(parent)
        self._results = results
        self._error = error
        self._running = True

    def start(self, *args):
        total = len(self._results) if self._results else 0
        for i, (p, _r, _e) in enumerate(self._results or []):
            self.progress.emit(p.name, i, total)
        self.result_ready.emit(self._results, self._error)
        self._running = False

    def isRunning(self):  # noqa: N802
        return self._running

    def requestInterruption(self):  # noqa: N802
        self._running = False

    def wait(self, *args):  # noqa: N802
        return True


def _make_fake_records():
    """构造一份全部成功的假结果。"""
    return [
        (SSQ, DrawRecord("2024010", date(2024, 1, 10),
                         red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7), None),
        (FC3D, DrawRecord("2024010", date(2024, 1, 10),
                          profile=FC3D, groups={"pos": [1, 2, 3]}), None),
        (KL8, None, "未获取到数据"),
    ]


def test_auto_update_dialog_success_updates_state(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("caipiao.utils.app_data_dir", lambda: tmp_path)
    # 关闭 MIN_DISPLAY_TIME 等待，使按钮文案在同步构造后立即确定
    monkeypatch.setattr(aud_mod, "MIN_DISPLAY_TIME_MS", 0)
    monkeypatch.setattr(
        aud_mod, "FetchAllLotteriesThread",
        lambda *a, **k: _FakeFetchThread(results=_make_fake_records(), error=None),
    )

    dlg = AutoUpdateDialog()
    qtbot.addWidget(dlg)

    assert dlg._update_finished is True
    # 2 成功（SSQ/FC3D），1 失败（KL8）
    assert dlg._success_count == 2
    assert dlg._fail_count == 1
    assert dlg.status_label.text() == "更新完成"
    assert "成功: 2" in dlg.detail_label.text()
    # 按钮在完成后变为“关闭”
    assert dlg.skip_btn.text() == "关闭"
    assert dlg.progress_bar.value() == 100


def test_auto_update_dialog_error_path(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("caipiao.utils.app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        aud_mod, "FetchAllLotteriesThread",
        lambda *a, **k: _FakeFetchThread(results=None, error="网络异常"),
    )

    dlg = AutoUpdateDialog()
    qtbot.addWidget(dlg)

    assert dlg._update_finished is True
    assert dlg.status_label.text() == "更新失败"
    assert "网络异常" in dlg.detail_label.text()


def test_auto_update_dialog_skip_emits_finished(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("caipiao.utils.app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        aud_mod, "FetchAllLotteriesThread",
        lambda *a, **k: _FakeFetchThread(results=_make_fake_records(), error=None),
    )

    dlg = AutoUpdateDialog()
    qtbot.addWidget(dlg)

    emitted = []
    dlg.update_finished.connect(lambda: emitted.append(True))

    dlg._on_skip()

    assert emitted, "点击跳过/关闭应当发射 update_finished 信号"
    assert dlg.result() == dlg.DialogCode.Accepted
