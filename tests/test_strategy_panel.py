"""策略面板参数（含起卦方式 choice 类型）保存/恢复单元测试.

需要通过 QApplication 运行（无头 offscreen）。验证 set_options -> current_options
往返：重点是 choice 类型（method: time/random）以真实值而非中文标签往返，
以及 int（seed）/ bool（use_ganzhi）类型。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import pytest

from caipiao.core.engine import GenerationEngine
from caipiao.core.strategies.bagua import BaguaStrategy
from caipiao.ui.components.strategy_panel import StrategyPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    engine = GenerationEngine()
    engine.register(BaguaStrategy())
    return StrategyPanel(engine, profile_key="3d")


def test_panel_loads_bagua(panel):
    assert panel.current_strategy_id() == "bagua"


def test_panel_choice_method_roundtrip(panel):
    for value in ("time", "random"):
        panel.set_options({"method": value})
        assert panel.current_options()["method"] == value


def test_panel_int_bool_roundtrip(panel):
    panel.set_options({"seed": 7, "use_ganzhi": False})
    opts = panel.current_options()
    assert opts["seed"] == 7
    assert opts["use_ganzhi"] is False


def test_panel_combo_restore(panel):
    saved = {"method": "random", "seed": 123, "use_ganzhi": True}
    panel.set_options(saved)
    restored = panel.current_options()
    assert restored["method"] == "random"
    assert restored["seed"] == 123
    assert restored["use_ganzhi"] is True


def _bagua_panel(app, profile_key):
    """构造一个仅含八卦占卜策略、目标彩种为 profile_key 的策略面板。

    模拟真实“切换彩种”行为：每次都重建策略下拉框并选中 bagua，
    从而触发 _on_strategy_changed（过滤组可见性据此刷新）。
    """
    engine = GenerationEngine()
    engine.register(BaguaStrategy())
    panel = StrategyPanel(engine, profile_key=profile_key)
    panel.show()
    panel.set_strategy_id("bagua")
    return panel


def test_bagua_filter_follows_profile(app):
    """八卦占卜是通用策略，其过滤设置应按目标彩种显示，而非永远双色球。

    回归背景：此前过滤组可见性按策略 id 后缀判定，bagua 无彩种后缀，
    故始终显示双色球过滤；现应按 profile_key 显示对应彩种的过滤。
    """
    # 目标彩种=大乐透：应显示大乐透过滤，隐藏双色球过滤
    dlt_panel = _bagua_panel(app, "dlt")
    assert dlt_panel.filter_dlt_group.isVisible() is True
    assert dlt_panel.filter_ssq_group.isVisible() is False

    # 目标彩种=排列3（非双色球）：同样按目标彩种显示对应过滤
    pl3_panel = _bagua_panel(app, "pl3")
    assert pl3_panel.filter_pl3_group.isVisible() is True
    assert pl3_panel.filter_ssq_group.isVisible() is False

    # 目标彩种=双色球：显示双色球过滤
    ssq_panel = _bagua_panel(app, "ssq")
    assert ssq_panel.filter_ssq_group.isVisible() is True
