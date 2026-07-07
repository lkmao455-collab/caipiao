"""Tests for caipiao.persistence.optimal_param_store."""

from pathlib import Path

import pytest

from caipiao.persistence.optimal_param_store import OptimalParamStore


@pytest.fixture
def store(tmp_path):
    return OptimalParamStore(data_dir=tmp_path)


def test_load_missing_returns_empty(store):
    config = store.load("3d")
    assert config.profile_key == "3d"
    assert config.locked == []


def test_lock_and_load(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100, source="scan")
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked == {"lookback": 100}


def test_lock_overwrites_same_param(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    store.lock("3d", "smart_hot_cold_3d", "lookback", 150)
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked["lookback"] == 150


def test_unlock(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    store.unlock("3d", "smart_hot_cold_3d", "lookback")
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked == {}


def test_apply_defaults(store):
    schema = {
        "lookback": {"type": "int", "default": 50, "min": 10, "max": 1000},
        "hot_weight": {"type": "int", "default": 60, "min": 0, "max": 100},
    }
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    new_schema = store.apply_defaults("3d", "smart_hot_cold_3d", schema)
    assert new_schema["lookback"]["default"] == 100
    assert new_schema["hot_weight"]["default"] == 60
