"""DrawRepository 集成测试."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from caipiao.core.profile import SSQ, FC3D
from caipiao.data.models import DrawRecord
from caipiao.data.repository import DrawRepository, DataRepository


# ---- Helpers ----

def _make_ssq_record(issue, reds, blue, days_ago=0):
    return DrawRecord(
        issue=issue,
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        red_balls=reds,
        blue_ball=blue,
    )


def _make_3d_record(issue, nums, days_ago=0):
    return DrawRecord(
        issue=issue,
        draw_date=datetime(2024, 1, 1) + timedelta(days=days_ago),
        profile="3d",
        groups={"pos": nums},
    )


# ---- Basic CRUD ----

class TestDrawRepositoryCRUD:
    """DrawRepository 基础增删改查."""

    def test_empty_repository(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        assert repo.get_count() == 0
        assert repo.get_all() == []
        assert repo.get_latest() is None

    def test_update_adds_records(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        added = repo.update([r1])
        assert added == 1
        assert repo.get_count() == 1

    def test_update_deduplicates(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        repo.update([r1])
        added = repo.update([r1])
        assert added == 0
        assert repo.get_count() == 1

    def test_update_multiple(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        records = [
            _make_ssq_record(f"2024{i:03d}", [1, 2, 3, 4, 5, 6], 7, days_ago=i)
            for i in range(1, 6)
        ]
        added = repo.update(records)
        assert added == 5
        assert repo.get_count() == 5

    def test_get_all_returns_copy(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo.update([r1])
        all_records = repo.get_all()
        all_records.clear()
        assert repo.get_count() == 1

    def test_get_recent(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        records = [
            _make_ssq_record(f"2024{i:03d}", [1, 2, 3, 4, 5, 6], 7, days_ago=i)
            for i in range(5)
        ]
        repo.update(records)
        recent = repo.get_recent(3)
        assert len(recent) == 3

    def test_get_recent_empty(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        assert repo.get_recent(10) == []

    def test_get_recent_zero(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo.update([r1])
        assert repo.get_recent(0) == []

    def test_get_latest(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        r2 = _make_ssq_record("2024002", [8, 9, 10, 11, 12, 13], 1, days_ago=1)
        repo.update([r1, r2])
        latest = repo.get_latest()
        assert latest.issue == "2024002"

    def test_clear(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo.update([r1])
        repo.clear()
        assert repo.get_count() == 0


# ---- Persistence ----

class TestDrawRepositoryPersistence:
    """DrawRepository 持久化测试."""

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "data.json"
        repo1 = DrawRepository(path)
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo1.update([r1])

        repo2 = DrawRepository(path)
        assert repo2.get_count() == 1
        assert repo2.get_latest().issue == "2024001"

    def test_reload_deduplicates(self, tmp_path):
        path = tmp_path / "data.json"
        repo1 = DrawRepository(path)
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo1.update([r1, r1])  # 同一批次重复
        assert repo1.get_count() == 1

    def test_corrupted_file_recovers(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text("not json", encoding="utf-8")
        repo = DrawRepository(path)
        assert repo.get_count() == 0


# ---- Date Range & Queries ----

class TestDrawRepositoryQueries:
    """DrawRepository 查询测试."""

    def test_get_date_range(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        r2 = _make_ssq_record("2024002", [8, 9, 10, 11, 12, 13], 1, days_ago=10)
        repo.update([r1, r2])
        start, end = repo.get_date_range()
        assert start is not None
        assert end is not None
        assert start < end

    def test_get_date_range_empty(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        start, end = repo.get_date_range()
        assert start is None
        assert end is None

    def test_get_records_before(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        r2 = _make_ssq_record("2024002", [8, 9, 10, 11, 12, 13], 1, days_ago=5)
        r3 = _make_ssq_record("2024003", [14, 15, 16, 17, 18, 19], 2, days_ago=10)
        repo.update([r1, r2, r3])
        cutoff = datetime(2024, 1, 1) + timedelta(days=7)
        before = repo.get_records_before(cutoff)
        assert len(before) == 2

    def test_get_record_by_date(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        repo.update([r1])
        found = repo.get_record_by_date(datetime(2024, 1, 1))
        assert found is not None
        assert found.issue == "2024001"

    def test_get_record_by_date_not_found(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        repo.update([r1])
        found = repo.get_record_by_date(datetime(2025, 1, 1))
        assert found is None


# ---- Next Period Info ----

class TestDrawRepositoryNextPeriod:
    """DrawRepository 下一期信息测试."""

    def test_next_period_info_ssq(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json", profile=SSQ)
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        repo.update([r1])
        info = repo.next_period_info()
        assert info is not None
        assert info["base_issue"] == "2024001"
        assert info["next_issue"] == "2024002"
        assert info["next_date"] > info["base_date"]

    def test_next_period_info_empty(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        assert repo.next_period_info() is None

    def test_next_period_info_cross_year(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json", profile=SSQ)
        r1 = _make_ssq_record("2024365", [1, 2, 3, 4, 5, 6], 7, days_ago=0)
        # 设置日期为年底
        r1.draw_date = datetime(2024, 12, 31)
        repo.update([r1])
        info = repo.next_period_info()
        assert info is not None
        assert info["next_issue"].startswith("2025")


# ---- Issue Normalization ----

class TestDrawRepositoryNormalization:
    """DrawRepository 期号规范化测试."""

    def test_normalize_short_issue(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("01", [1, 2, 3, 4, 5, 6], 7)
        r1.draw_date = datetime(2024, 1, 1)
        repo.update([r1])
        # 2 位期号不规范化（len < 3）
        assert repo.get_latest().issue == "01"

    def test_normalize_long_issue(self, tmp_path):
        repo = DrawRepository(tmp_path / "data.json")
        r1 = _make_ssq_record("2024001", [1, 2, 3, 4, 5, 6], 7)
        repo.update([r1])
        assert repo.get_latest().issue == "2024001"


# ---- FC3D Repository ----

class TestDrawRepositoryFC3D:
    """DrawRepository 福彩3D 测试."""

    def test_3d_update_and_query(self, tmp_path):
        repo = DrawRepository(tmp_path / "data_3d.json", profile=FC3D)
        r1 = _make_3d_record("2024001", [1, 2, 3], days_ago=0)
        r2 = _make_3d_record("2024002", [4, 5, 6], days_ago=1)
        added = repo.update([r1, r2])
        assert added == 2
        assert repo.get_count() == 2
        latest = repo.get_latest()
        assert latest.groups["pos"] == [4, 5, 6]


# ---- DataRepository Alias ----

class TestDataRepositoryAlias:
    """DataRepository 别名兼容性测试."""

    def test_alias_is_same_class(self):
        assert DataRepository is DrawRepository
