"""DrawRecord 数据模型测试."""

from datetime import datetime

import pytest

from caipiao.core.profile import SSQ, FC3D
from caipiao.data.models import DrawRecord


class TestDrawRecordConstruction:
    """DrawRecord 构造测试."""

    def test_ssq_construction(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert rec.issue == "2024001"
        assert rec.profile.key == "ssq"
        assert rec.groups["red"] == [1, 2, 3, 4, 5, 6]
        assert rec.groups["blue"] == [7]

    def test_ssq_auto_sort(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[6, 5, 4, 3, 2, 1],
            blue_ball=7,
        )
        assert rec.groups["red"] == [1, 2, 3, 4, 5, 6]

    def test_ssq_missing_blue_raises(self):
        with pytest.raises(ValueError, match="蓝球"):
            DrawRecord(
                issue="2024001",
                draw_date=datetime(2024, 1, 1),
                red_balls=[1, 2, 3, 4, 5, 6],
            )

    def test_3d_construction(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        assert rec.profile.key == "3d"
        assert rec.groups["pos"] == [1, 2, 3]

    def test_profile_object_construction(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile=FC3D,
            groups={"pos": [4, 5, 6]},
        )
        assert rec.profile.key == "3d"

    def test_groups_construction(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            groups={"red": [1, 2, 3, 4, 5, 6], "blue": [7]},
        )
        assert rec.groups["red"] == [1, 2, 3, 4, 5, 6]


class TestDrawRecordAccessors:
    """DrawRecord 访问器测试."""

    def test_red_balls(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert rec.red_balls == [1, 2, 3, 4, 5, 6]

    def test_blue_ball(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert rec.blue_ball == 7

    def test_blue_ball_none_for_3d(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        assert rec.blue_ball is None

    def test_red_balls_empty_for_3d(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        assert rec.red_balls == []


class TestDrawRecordSerialization:
    """DrawRecord 序列化测试."""

    def test_to_dict_ssq(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        d = rec.to_dict()
        assert d["issue"] == "2024001"
        assert d["draw_date"] == "2024-01-01"
        assert d["red_balls"] == [1, 2, 3, 4, 5, 6]
        assert d["blue_ball"] == 7

    def test_from_dict_ssq(self):
        d = {
            "issue": "2024001",
            "draw_date": "2024-01-01",
            "red_balls": [1, 2, 3, 4, 5, 6],
            "blue_ball": 7,
        }
        rec = DrawRecord.from_dict(d)
        assert rec.issue == "2024001"
        assert rec.groups["red"] == [1, 2, 3, 4, 5, 6]
        assert rec.groups["blue"] == [7]

    def test_to_dict_3d(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        d = rec.to_dict()
        assert d["profile"] == "3d"
        assert d["groups"]["pos"] == [1, 2, 3]

    def test_from_dict_3d(self):
        d = {
            "issue": "2024001",
            "draw_date": "2024-01-01",
            "profile": "3d",
            "groups": {"pos": [1, 2, 3]},
        }
        rec = DrawRecord.from_dict(d)
        assert rec.profile.key == "3d"
        assert rec.groups["pos"] == [1, 2, 3]

    def test_roundtrip_ssq(self):
        original = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        restored = DrawRecord.from_dict(original.to_dict())
        assert original == restored

    def test_roundtrip_3d(self):
        original = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        restored = DrawRecord.from_dict(original.to_dict())
        assert original == restored


class TestDrawRecordRepr:
    """DrawRecord 表示测试."""

    def test_repr_ssq(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        r = repr(rec)
        assert "DrawRecord" in r
        assert "红:" in r
        assert "蓝:" in r

    def test_repr_3d(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            profile="3d",
            groups={"pos": [1, 2, 3]},
        )
        r = repr(rec)
        assert "DrawRecord" in r
        assert "号码:" in r

    def test_repr_empty_ssq(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            groups={},
        )
        r = repr(rec)
        assert "无效记录" in r


class TestDrawRecordEquality:
    """DrawRecord 相等性测试."""

    def test_equal(self):
        r1 = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        r2 = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert r1 == r2

    def test_not_equal_different_issue(self):
        r1 = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        r2 = DrawRecord(
            issue="2024002",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert r1 != r2

    def test_not_equal_different_type(self):
        rec = DrawRecord(
            issue="2024001",
            draw_date=datetime(2024, 1, 1),
            red_balls=[1, 2, 3, 4, 5, 6],
            blue_ball=7,
        )
        assert rec != "not a record"
