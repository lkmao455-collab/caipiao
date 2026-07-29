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
