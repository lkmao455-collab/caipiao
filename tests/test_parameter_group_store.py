"""参数组持久化存储测试."""

import tempfile
from pathlib import Path

from caipiao.core.parameter_group import ParameterGroup, StrategyParameterItem
from caipiao.persistence.parameter_group_store import ParameterGroupStore


def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        group = ParameterGroup(
            id="g1",
            name="测试组",
            profile_key="ssq",
            created_at="2026-07-05T10:00:00",
            items=[
                StrategyParameterItem(
                    strategy_id="random",
                    strategy_name="完全随机",
                    param_name=None,
                    param_value=None,
                )
            ],
        )
        store.save(group)
        loaded = store.load_all("ssq")
        assert len(loaded) == 1
        assert loaded[0].name == "测试组"


def test_delete_and_rename():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        group = ParameterGroup(
            id="g2",
            name="可改名",
            profile_key="ssq",
            created_at="2026-07-05T10:00:00",
            items=[],
        )
        store.save(group)
        assert store.rename("ssq", "g2", "新名字")
        loaded = store.load_all("ssq")
        assert loaded[0].name == "新名字"
        assert store.delete("ssq", "g2")
        assert store.load_all("ssq") == []


def test_corrupted_file_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        path = store.path_for("ssq")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        assert store.load_all("ssq") == []
