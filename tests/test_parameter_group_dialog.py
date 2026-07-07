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
    scan_result.param_names = {}
    scan_result.best_params = {}
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
            BatchBacktestResult(total_rounds=10, total_cost=20, total_fixed_prize=100, hit_count=5),
        ),
    ]
    scan_result.param_name = "history_count"
    scan_result.param_names = {"xgboost": "history_count"}
    scan_result.best_params = {"xgboost": {"history_count": 300}}
    scan_result.cv_results = {
        "xgboost": {
            "stability_score": 0.8,
            "mean_fixed_prize": 90,
            "std_fixed_prize": 5,
        }
    }
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    spy = []
    dialog.group_saved.connect(lambda g: spy.append(g))
    dialog._on_save()
    assert len(spy) == 1
    assert isinstance(spy[0], ParameterGroup)
    assert spy[0].items[0].strategy_id == "xgboost"
    store.save.assert_called_once()


def test_save_locks_all_best_params(qtbot, tmp_path):
    """保存多参数策略时应锁定 best_params 中的所有参数."""
    from caipiao.persistence.optimal_param_store import OptimalParamStore

    param_store = OptimalParamStore(data_dir=tmp_path)
    group_store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        (
            "smart_hot_cold_3d",
            50,
            BatchBacktestResult(total_rounds=10, total_cost=20, total_fixed_prize=100, hit_count=5),
        ),
    ]
    scan_result.param_name = "lookback"
    scan_result.param_names = {"smart_hot_cold_3d": "lookback"}
    scan_result.best_params = {
        "smart_hot_cold_3d": {
            "lookback": 50,
            "hot_weight": 70,
            "cold_weight": 30,
            "temperature": 1.0,
        }
    }
    scan_result.cv_results = {
        "smart_hot_cold_3d": {
            "stability_score": 0.9,
            "mean_fixed_prize": 95,
            "std_fixed_prize": 3,
        }
    }
    dialog = ParameterGroupSaveDialog(
        scan_result, "3d", group_store, optimal_param_store=param_store
    )
    qtbot.addWidget(dialog)
    dialog._on_save()

    locked = param_store.get_locked("3d", "smart_hot_cold_3d")
    assert locked.get("lookback") == 50
    assert locked.get("hot_weight") == 70
    assert locked.get("cold_weight") == 30
    assert locked.get("temperature") == 1.0
    group_store.save.assert_called_once()
