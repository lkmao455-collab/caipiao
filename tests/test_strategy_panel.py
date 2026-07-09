"""StrategyPanel 锁定参数 UI 测试."""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QSpinBox

from caipiao.core.engine import GenerationEngine
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket
from caipiao.persistence.optimal_param_store import OptimalParamStore
from caipiao.ui.components.strategy_panel import StrategyPanel


class _DummyStrategy(GenerationStrategy):
    """带可锁定参数的测试策略."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="dummy_lockable",
            name="可锁定测试策略",
            description="测试",
            version="1.0.0",
            author="test",
        )

    def get_config_schema(self) -> dict:
        return {
            "lookback": {
                "type": "int",
                "label": "回看期数",
                "default": 10,
                "min": 1,
                "max": 100,
            },
            "hot_weight": {
                "type": "int",
                "label": "热号权重",
                "default": 50,
                "min": 0,
                "max": 100,
            },
        }

    def generate(self, count: int = 1, options=None) -> list:
        return [Ticket(profile="3d", groups={"pos": [1, 2, 3]}) for _ in range(count)]


def test_locked_param_is_disabled_and_shows_lock_label(qtbot, tmp_path):
    """已锁定参数对应的控件应禁用并显示 [锁定] 文本."""
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "dummy_lockable", "lookback", 42)

    engine = GenerationEngine()
    engine.register(_DummyStrategy())

    panel = StrategyPanel(engine, profile_key="3d", store=store)
    qtbot.addWidget(panel)
    panel.set_strategy_id("dummy_lockable")

    lookback_widget = panel._option_widgets["lookback"]
    hot_widget = panel._option_widgets["hot_weight"]

    assert isinstance(lookback_widget, QSpinBox)
    assert isinstance(hot_widget, QSpinBox)
    assert not lookback_widget.isEnabled()
    assert hot_widget.isEnabled()
    assert lookback_widget.value() == 42

    # 检查界面上存在 [锁定] 标签
    lock_labels = [
        child
        for child in panel.options_group.findChildren(QLabel)
        if child.text() == "[锁定]"
    ]
    assert len(lock_labels) == 1
    assert "42" in lock_labels[0].toolTip()


def test_locked_params_from_memory_cache_take_precedence(qtbot, tmp_path):
    """传入的内存锁定缓存应优先于持久化存储."""
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "dummy_lockable", "lookback", 10)

    engine = GenerationEngine()
    engine.register(_DummyStrategy())

    from caipiao.persistence.optimal_param_store import LockedParameter

    memory_locked = [LockedParameter("dummy_lockable", "hot_weight", 77, "scan", "")]
    panel = StrategyPanel(
        engine, profile_key="3d", store=store, locked_params=memory_locked
    )
    qtbot.addWidget(panel)
    panel.set_strategy_id("dummy_lockable")

    # 内存缓存只有 hot_weight，lookback 不应被锁定
    lookback_widget = panel._option_widgets["lookback"]
    hot_widget = panel._option_widgets["hot_weight"]

    assert lookback_widget.isEnabled()
    assert not hot_widget.isEnabled()
    assert hot_widget.value() == 77


def test_recommend_button_for_consensus_constraint(qtbot):
    from caipiao.core.engine import GenerationEngine
    from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
        SSQConsensusConstraintStrategy,
    )

    engine = GenerationEngine()
    engine.register(SSQConsensusConstraintStrategy())
    panel = StrategyPanel(engine, profile_key="ssq")
    qtbot.addWidget(panel)
    panel.set_strategy_id("consensus_constraint")
    # 按钮应在 options_group 之前被找到
    buttons = panel.findChildren(QPushButton)
    assert any(b.text() == "一键推荐参数" for b in buttons)


def test_recommend_requested_signal_emitted(qtbot):
    from caipiao.core.engine import GenerationEngine
    from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
        SSQConsensusConstraintStrategy,
    )

    engine = GenerationEngine()
    engine.register(SSQConsensusConstraintStrategy())
    panel = StrategyPanel(engine, profile_key="ssq")
    qtbot.addWidget(panel)
    panel.set_strategy_id("consensus_constraint")

    with qtbot.waitSignal(panel.recommend_requested, timeout=1000) as blocker:
        panel._recommend_btn.click()
    assert blocker.args == ["consensus_constraint"]
