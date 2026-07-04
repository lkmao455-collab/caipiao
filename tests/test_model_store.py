"""模型文件存储与新鲜度逻辑测试."""

import json
from datetime import datetime, timedelta

from caipiao.data.models import DrawRecord
from caipiao.ml import model_store


def make_records(count: int = 120):
    records = []
    for i in range(count):
        records.append(
            DrawRecord(
                issue=f"2024{i + 1:03d}",
                draw_date=datetime(2024, 1, 1) + timedelta(days=i),
                red_balls=sorted([(i + j) % 33 + 1 for j in range(6)]),
                blue_ball=(i % 16) + 1,
            )
        )
    return records


def _write_model(directory, lookback, fingerprint, when, prefix="xgboost"):
    """在指定目录写入一个假的模型文件及其元数据."""
    records = make_records(120)
    path = model_store.new_model_path(records, lookback, directory=directory, when=when, prefix=prefix)
    path.write_bytes(b"fake-model")
    meta = model_store._meta_path(path)
    meta.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
    return path


def test_compute_lookback():
    assert model_store.compute_lookback(80) == 50   # 下限 50
    assert model_store.compute_lookback(150) == 50
    assert model_store.compute_lookback(3000) == 2900


def test_data_fingerprint_reflects_latest():
    records = make_records(120)
    fp1 = model_store.data_fingerprint(records)
    # 记录数与最新一期都参与指纹
    assert fp1.startswith("120|")
    records2 = make_records(121)
    assert model_store.data_fingerprint(records2) != fp1
    # 空数据
    assert model_store.data_fingerprint([]) == "empty"


def test_new_model_path_naming(tmp_path):
    records = make_records(120)
    path = model_store.new_model_path(
        records, 50, directory=tmp_path, when=datetime(2025, 7, 1, 9, 3, 53)
    )
    assert path.name.startswith("xgboost_20240429_default_lookback50_20250701_090353")
    assert path.parent == tmp_path


def test_new_model_path_prefix(tmp_path):
    records = make_records(120)
    path = model_store.new_model_path(
        records, 50, directory=tmp_path, when=datetime(2025, 7, 1, 9, 3, 53), prefix="lightgbm"
    )
    assert path.name.startswith("lightgbm_20240429_default_lookback50_20250701_090353")
    assert path.name.endswith(".pkl")


def test_find_current_model_isolated_by_prefix(tmp_path):
    """不同前缀的模型互不干扰：xgboost 的缓存不会被当作 lightgbm 的。"""
    records = make_records(120)
    lookback = model_store.compute_lookback(len(records))
    fp = model_store.data_fingerprint(records)

    # 只写入一个 xgboost 前缀的匹配模型
    _write_model(tmp_path, lookback, fp, datetime(2025, 6, 1, 0, 0, 0))

    # xgboost 前缀能找到，lightgbm 前缀找不到
    assert (
        model_store.find_current_model(records, lookback, directory=tmp_path)
        is not None
    )
    assert (
        model_store.find_current_model(
            records, lookback, directory=tmp_path, prefix="lightgbm"
        )
        is None
    )


def test_find_current_model_matches_fingerprint(tmp_path):
    records = make_records(120)
    lookback = model_store.compute_lookback(len(records))
    fp = model_store.data_fingerprint(records)

    # 没有任何模型时
    assert model_store.find_current_model(records, lookback, directory=tmp_path) is None
    assert not model_store.is_model_current(records, lookback, directory=tmp_path)

    # 写一个指纹不匹配的旧模型
    _write_model(tmp_path, lookback, "stale-fingerprint", datetime(2025, 1, 1, 0, 0, 0))
    assert model_store.find_current_model(records, lookback, directory=tmp_path) is None

    # 写一个指纹匹配的模型 -> 应被找到
    matching = _write_model(tmp_path, lookback, fp, datetime(2025, 6, 1, 0, 0, 0))
    found = model_store.find_current_model(records, lookback, directory=tmp_path)
    assert found == matching
    assert model_store.is_model_current(records, lookback, directory=tmp_path)


def test_model_dir_respects_env_var(tmp_path, monkeypatch):
    """model_dir 应优先使用 CAIPIAO_MODEL_DIR 环境变量。"""
    monkeypatch.setenv("CAIPIAO_MODEL_DIR", str(tmp_path))
    assert model_store.model_dir() == tmp_path


def test_model_dir_env_var_creates_directory(tmp_path, monkeypatch):
    """CAIPIAO_MODEL_DIR 指向的目录不存在时应自动创建。"""
    target = tmp_path / "nested" / "models"
    monkeypatch.setenv("CAIPIAO_MODEL_DIR", str(target))
    assert model_store.model_dir() == target
    assert target.exists()


def test_find_current_model_prefers_newest(tmp_path):
    records = make_records(120)
    lookback = model_store.compute_lookback(len(records))
    fp = model_store.data_fingerprint(records)

    older = _write_model(tmp_path, lookback, fp, datetime(2025, 1, 1, 0, 0, 0))
    newer = _write_model(tmp_path, lookback, fp, datetime(2025, 6, 1, 0, 0, 0))
    # 用不同 mtime 明确区分新旧
    import os

    os.utime(older, (1_600_000_000, 1_600_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))

    found = model_store.find_current_model(records, lookback, directory=tmp_path)
    assert found == newer
