"""Tests for caipiao.persistence.optimal_param_store."""

from caipiao.persistence.optimal_param_store import OptimalParamStore


def test_load_returns_empty_config_for_missing_file(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    config = store.load("3d")
    assert config.profile_key == "3d"
    assert config.locked == []
    assert config.last_scan_at is None


def test_lock_and_load_round_trip(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "smart_hot_cold_3d", "lookback", 50, source="scan")
    config = store.load("3d")
    assert config.profile_key == "3d"
    assert len(config.locked) == 1
    assert config.locked[0].strategy_id == "smart_hot_cold_3d"
    assert config.locked[0].param_name == "lookback"
    assert config.locked[0].param_value == 50
    assert config.locked[0].source == "scan"


def test_lock_overwrites_same_strategy_param(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "s", "p", 1, source="user")
    store.lock("3d", "s", "p", 2, source="scan")
    config = store.load("3d")
    assert len(config.locked) == 1
    assert config.locked[0].param_value == 2
    assert config.locked[0].source == "scan"


def test_unlock_removes_entry(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "s", "p", 1)
    store.unlock("3d", "s", "p")
    config = store.load("3d")
    assert config.locked == []


def test_load_backs_up_corrupted_file(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    path = tmp_path / "optimal_params" / "3d.json"
    path.write_text("not valid json", encoding="utf-8")

    config = store.load("3d")
    assert config.profile_key == "3d"
    assert config.locked == []
    assert not path.exists()

    backups = list((tmp_path / "optimal_params").glob("3d.corrupted-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "not valid json"


def test_apply_defaults_overrides_locked_values(tmp_path):
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "s", "lookback", 80)
    schema = {
        "lookback": {"type": "int", "default": 100, "min": 10, "max": 1000},
        "other": {"type": "int", "default": 5},
    }
    new_schema = store.apply_defaults("3d", "s", schema)
    assert new_schema["lookback"]["default"] == 80
    assert new_schema["other"]["default"] == 5
