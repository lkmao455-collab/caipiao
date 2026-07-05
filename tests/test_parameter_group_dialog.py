"""参数组保存对话框测试."""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from caipiao.core.parameter_group import ParameterGroup
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.ui.components.parameter_group_save_dialog import (
    ParameterGroupSaveDialog,
)


def test_auto_name_contains_date_and_count(qtbot):
    store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        (
            "xgboost",
            300,
            BatchBacktestResult(total_rounds=10, total_fixed_prize=100, hit_count=5),
        ),
        (
            "smart_hot_cold",
            100,
            BatchBacktestResult(total_rounds=10, total_fixed_prize=80, hit_count=3),
        ),
    ]
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    assert "前2策略" in dialog.name_edit.text()


def test_save_emits_group_saved(qtbot):
    store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        (
            "xgboost",
            300,
            BatchBacktestResult(total_rounds=10, total_fixed_prize=100, hit_count=5),
        ),
    ]
    scan_result.param_name = "history_count"
    scan_result.optimal_result = BatchBacktestResult(
        total_rounds=10, total_cost=20, total_fixed_prize=100, hit_count=5
    )
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    spy = []
    dialog.group_saved.connect(lambda g: spy.append(g))
    dialog._on_save()
    assert len(spy) == 1
    assert isinstance(spy[0], ParameterGroup)
    assert spy[0].items[0].strategy_id == "xgboost"
    store.save.assert_called_once()
