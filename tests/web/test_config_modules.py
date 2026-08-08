"""发布/数据治理/备份 模块持久化集成测试（定义写入数据库，重启不丢失）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _make_env():
    tmp = Path(tempfile.mkdtemp(prefix="caipiao_cfg_test_"))
    os.environ["CAIPIAO_WEB_DB"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["CAIPIAO_WEB_DATA"] = str(tmp)
    os.environ["CAIPIAO_WEB_SECRET"] = "test-secret"
    os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
    os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
    return tmp


@pytest.fixture
def tmp_db():
    _make_env()
    from caipiao.web import db as _webdb

    _webdb._ensure_engine()
    _webdb.init_db()
    yield
    _webdb._engine = None
    _webdb._SessionLocal = None


def test_release_manager_persists(tmp_db):
    from caipiao.web.release_manager import (
        Deployment,
        FeatureFlag,
        ReleaseManager,
        ReleaseVersion,
    )

    mgr = ReleaseManager()
    mgr.create_flag(FeatureFlag(key="new_ui", name="新界面", enabled=True, rollout_percentage=50))
    mgr.create_version(
        ReleaseVersion(id="v1", version="1.0.0", name="首发", features=["new_ui"])
    )

    fresh = ReleaseManager()
    assert fresh.get_flag("new_ui").enabled is True
    assert fresh.get_flag("new_ui").rollout_percentage == 50
    assert fresh.get_version("v1").version == "1.0.0"

    dep = mgr.release_version("v1", environment="production")
    assert dep is not None
    fresh2 = ReleaseManager()
    assert len(fresh2.get_deployments("v1")) == 1
    assert fresh2.get_version("v1").status == "production"


def test_data_governance_persists(tmp_db):
    from caipiao.web.data_governance import (
        DataGovernancePlatform,
        Dataset,
        DataLineage,
        DataQualityRule,
        MetadataField,
    )

    plat = DataGovernancePlatform()
    plat.create_dataset(
        Dataset(
            id="ds1",
            name="销售数据",
            schema=[MetadataField(name="amount", type="number", is_sensitive=True)],
            tags=["finance"],
        )
    )
    plat.add_lineage(DataLineage(id="ln1", source_dataset="ds0", target_dataset="ds1", transform_type="aggregate"))
    plat.create_quality_rule(DataQualityRule(id="qr1", dataset_id="ds1", rule_type="not_null", field_name="amount"))

    fresh = DataGovernancePlatform()
    ds = fresh.get_dataset("ds1")
    assert ds is not None
    assert ds.name == "销售数据"
    assert ds.schema[0].is_sensitive is True
    assert len(fresh.get_upstream("ds1")) == 1
    assert len(fresh.get_quality_rules("ds1")) == 1


def test_backup_manager_persists(tmp_db):
    from caipiao.web.backup_manager import BackupConfig, BackupManager

    mgr = BackupManager(backup_dir=str(Path(tempfile.mkdtemp(prefix="bk_"))))
    cfg = BackupConfig(id="cfg1", name="每日备份", backup_type="full", source_paths=[], destination="/tmp/x")
    mgr.create_config(cfg)

    fresh = BackupManager(backup_dir=str(Path(tempfile.mkdtemp(prefix="bk_"))))
    loaded = fresh.get_config("cfg1")
    assert loaded is not None
    assert loaded.name == "每日备份"
    assert loaded.destination == "/tmp/x"

    # 删除后持久化
    mgr.delete_config("cfg1")
    fresh2 = BackupManager(backup_dir=str(Path(tempfile.mkdtemp(prefix="bk_"))))
    assert fresh2.get_config("cfg1") is None
