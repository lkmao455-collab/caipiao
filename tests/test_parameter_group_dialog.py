"""参数组保存对话框测试."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QMessageBox


@contextmanager
def _no_modal(question=QMessageBox.StandardButton.Yes, info=QMessageBox.StandardButton.Ok):
    """屏蔽 _on_save 中弹出的模态消息框，避免无显示环境下阻塞。

    _on_save 在保存后会无条件调用 ``QMessageBox.information``，且可能先调用
    ``QMessageBox.question``；offscreen 下这些真实模态框会永久挂起测试。
    原本的用例只 patch 了 question，导致 information 的真实弹窗一直等待用户点击。
    """
    with patch.object(QMessageBox, "question", return_value=question), \
         patch.object(QMessageBox, "information", return_value=info), \
         patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok):
        yield

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
    scan_result.optimal_strategy_id = "xgboost"
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    spy = []
    dialog.group_saved.connect(lambda g: spy.append(g))
    with _no_modal():
        dialog._on_save()
    assert len(spy) == 1
    assert isinstance(spy[0], ParameterGroup)
    assert spy[0].items[0].strategy_id == "xgboost"
    store.save.assert_called_once()


def test_save_locks_only_overall_best_params(qtbot, tmp_path):
    """保存 top-N 时仅锁定综合排名第一的策略参数."""
    from caipiao.persistence.optimal_param_store import OptimalParamStore

    param_store = OptimalParamStore(data_dir=tmp_path)
    group_store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        (
            "smart_hot_cold_3d",
            50,
            BatchBacktestResult(
                total_rounds=10, total_cost=20, total_fixed_prize=120, hit_count=5
            ),
        ),
        (
            "missing_number_3d",
            80,
            BatchBacktestResult(
                total_rounds=10, total_cost=20, total_fixed_prize=100, hit_count=4
            ),
        ),
    ]
    scan_result.param_name = "lookback"
    scan_result.param_names = {
        "smart_hot_cold_3d": "lookback",
        "missing_number_3d": "lookback",
    }
    scan_result.best_params = {
        "smart_hot_cold_3d": {
            "lookback": 50,
            "hot_weight": 70,
            "cold_weight": 30,
            "temperature": 1.0,
        },
        "missing_number_3d": {
            "lookback": 80,
            "pool_size": 5,
        },
    }
    scan_result.cv_results = {
        "smart_hot_cold_3d": {
            "stability_score": 0.9,
            "mean_fixed_prize": 95,
            "std_fixed_prize": 3,
        },
        "missing_number_3d": {
            "stability_score": 0.8,
            "mean_fixed_prize": 90,
            "std_fixed_prize": 5,
        },
    }
    scan_result.optimal_strategy_id = "smart_hot_cold_3d"
    dialog = ParameterGroupSaveDialog(
        scan_result, "3d", group_store, optimal_param_store=param_store
    )
    qtbot.addWidget(dialog)
    with _no_modal():
        dialog._on_save()

    # 仅排名第一的策略被锁定
    locked_best = param_store.get_locked("3d", "smart_hot_cold_3d")
    assert locked_best.get("lookback") == 50
    assert locked_best.get("hot_weight") == 70
    assert locked_best.get("cold_weight") == 30
    assert locked_best.get("temperature") == 1.0

    # 排名第二的策略不应被锁定
    locked_second = param_store.get_locked("3d", "missing_number_3d")
    assert locked_second == {}

    # 但两个策略都应保存到参数组
    group_store.save.assert_called_once()
    saved_group = group_store.save.call_args[0][0]
    assert len(saved_group.items) == 2
    assert saved_group.items[0].strategy_id == "smart_hot_cold_3d"
    assert saved_group.items[1].strategy_id == "missing_number_3d"


def test_save_locks_best_params_for_single_strategy(qtbot, tmp_path):
    """只保存一个策略时仍应锁定其 best_params."""
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
    scan_result.optimal_strategy_id = "smart_hot_cold_3d"
    dialog = ParameterGroupSaveDialog(
        scan_result, "3d", group_store, optimal_param_store=param_store
    )
    qtbot.addWidget(dialog)
    with _no_modal():
        dialog._on_save()

    locked = param_store.get_locked("3d", "smart_hot_cold_3d")
    assert locked.get("lookback") == 50
    assert locked.get("hot_weight") == 70
    assert locked.get("cold_weight") == 30
    assert locked.get("temperature") == 1.0
    group_store.save.assert_called_once()


def test_save_does_not_overwrite_same_value_lock(qtbot, tmp_path):
    """保存时应跳过已锁定且值相同的参数，避免覆盖用户原锁定记录."""
    from caipiao.persistence.optimal_param_store import OptimalParamStore

    param_store = OptimalParamStore(data_dir=tmp_path)
    # 用户先锁定 lookback=50
    param_store.lock("3d", "smart_hot_cold_3d", "lookback", 50, source="user")
    original_locked_at = param_store.load("3d").locked[0].locked_at

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
        }
    }
    scan_result.cv_results = {
        "smart_hot_cold_3d": {
            "stability_score": 0.9,
            "mean_fixed_prize": 95,
            "std_fixed_prize": 3,
        }
    }
    scan_result.optimal_strategy_id = "smart_hot_cold_3d"
    dialog = ParameterGroupSaveDialog(
        scan_result, "3d", group_store, optimal_param_store=param_store
    )
    qtbot.addWidget(dialog)
    with _no_modal():
        dialog._on_save()

    locked = param_store.load("3d").locked
    lookback_entry = next(
        p for p in locked if p.strategy_id == "smart_hot_cold_3d" and p.param_name == "lookback"
    )
    # 应保持用户原锁定记录
    assert lookback_entry.source == "user"
    assert lookback_entry.locked_at == original_locked_at
    # 新参数仍应被锁定
    assert any(
        p.strategy_id == "smart_hot_cold_3d" and p.param_name == "hot_weight" and p.param_value == 70
        for p in locked
    )


def test_save_does_not_lock_when_user_declines(qtbot, tmp_path):
    """用户点击“否”时不应锁定参数，但仍保存参数组."""
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
        }
    }
    scan_result.cv_results = {
        "smart_hot_cold_3d": {
            "stability_score": 0.9,
            "mean_fixed_prize": 95,
            "std_fixed_prize": 3,
        }
    }
    scan_result.optimal_strategy_id = "smart_hot_cold_3d"
    dialog = ParameterGroupSaveDialog(
        scan_result, "3d", group_store, optimal_param_store=param_store
    )
    qtbot.addWidget(dialog)
    with _no_modal(question=QMessageBox.StandardButton.No):
        dialog._on_save()

    locked = param_store.get_locked("3d", "smart_hot_cold_3d")
    assert locked == {}
    group_store.save.assert_called_once()
