"""Core Ticket 模块单元测试."""

from datetime import datetime

import pytest

from caipiao.core.profile import SSQ, FC3D, QLC, KL8, DLT, get_profile
from caipiao.core.ticket import Ticket


class TestTicketConstruction:
    """Ticket 构造测试."""

    def test_ssq_construction(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert ticket.profile.key == "ssq"
        assert ticket.groups["red"] == [1, 2, 3, 4, 5, 6]
        assert ticket.groups["blue"] == [7]

    def test_ssq_auto_sort(self):
        ticket = Ticket(red_balls=[6, 5, 4, 3, 2, 1], blue_ball=7)
        assert ticket.groups["red"] == [1, 2, 3, 4, 5, 6]

    def test_ssq_missing_blue_raises(self):
        with pytest.raises(ValueError, match="蓝球"):
            Ticket(red_balls=[1, 2, 3, 4, 5, 6])

    def test_fc3d_construction(self):
        ticket = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        assert ticket.profile.key == "3d"
        assert ticket.groups["pos"] == [1, 2, 3]

    def test_fc3d_positional_no_sort(self):
        ticket = Ticket(profile="3d", groups={"pos": [3, 2, 1]})
        assert ticket.groups["pos"] == [3, 2, 1]

    def test_qlc_construction(self):
        # 七乐彩已停售：不加入 PROFILES，故 get_profile("qlc") 会回退双色球；
        # 此处直接用 QLC 档案对象构造，验证该彩种投注单模型本身仍然可用。
        ticket = Ticket(profile=QLC, groups={"basic": [1, 2, 3, 4, 5, 6, 7]})
        assert ticket.profile.key == "qlc"
        assert len(ticket.groups["basic"]) == 7

    def test_kl8_construction(self):
        ticket = Ticket(profile="kl8", groups={"main": [1, 2, 3, 4, 5]})
        assert ticket.profile.key == "kl8"
        assert len(ticket.groups["main"]) == 5

    def test_dlt_construction(self):
        ticket = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        assert ticket.profile.key == "dlt"
        assert ticket.groups["front"] == [1, 2, 3, 4, 5]
        assert ticket.groups["back"] == [1, 2]

    def test_from_groups_factory(self):
        ticket = Ticket.from_groups("ssq", {"red": [1, 2, 3, 4, 5, 6], "blue": [7]})
        assert ticket.profile.key == "ssq"
        assert ticket.groups["red"] == [1, 2, 3, 4, 5, 6]

    def test_generated_at_default(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert ticket.generated_at is not None

    def test_generated_at_custom(self):
        dt = datetime(2025, 1, 1, 12, 0, 0)
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7, generated_at=dt)
        assert ticket.generated_at == dt

    def test_strategy_name(self):
        ticket = Ticket(
            red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7, strategy_name="random"
        )
        assert ticket.strategy_name == "random"


class TestTicketValidation:
    """Ticket 校验测试."""

    def test_ssq_wrong_red_count_raises(self):
        with pytest.raises(ValueError, match="红球"):
            Ticket(red_balls=[1, 2, 3, 4, 5], blue_ball=7)

    def test_ssq_red_out_of_range_raises(self):
        with pytest.raises(ValueError, match="红球"):
            Ticket(red_balls=[0, 2, 3, 4, 5, 6], blue_ball=7)

    def test_ssq_red_duplicate_raises(self):
        with pytest.raises(ValueError, match="不能重复"):
            Ticket(red_balls=[1, 1, 3, 4, 5, 6], blue_ball=7)

    def test_ssq_blue_out_of_range_raises(self):
        with pytest.raises(ValueError, match="蓝球"):
            Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=0)

    def test_fc3d_wrong_count_raises(self):
        with pytest.raises(ValueError, match="号码"):
            Ticket(profile="3d", groups={"pos": [1, 2]})

    def test_fc3d_out_of_range_raises(self):
        with pytest.raises(ValueError, match="号码"):
            Ticket(profile="3d", groups={"pos": [1, 2, 10]})

    def test_fc3d_allow_repeat(self):
        ticket = Ticket(profile="3d", groups={"pos": [1, 1, 1]})
        assert ticket.groups["pos"] == [1, 1, 1]

    def test_skip_validation(self):
        ticket = Ticket(
            red_balls=[1, 2, 3, 4, 5],
            blue_ball=7,
            validate=False,
        )
        assert len(ticket.groups["red"]) == 5


class TestTicketSerialization:
    """Ticket 序列化测试."""

    def test_ssq_to_dict(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        d = ticket.to_dict()
        assert d["red"] == [1, 2, 3, 4, 5, 6]
        assert d["blue"] == 7
        assert "generated_at" in d
        assert "strategy_name" in d

    def test_ssq_from_dict(self):
        d = {
            "red": [1, 2, 3, 4, 5, 6],
            "blue": 7,
            "generated_at": "2025-01-01T12:00:00",
            "strategy_name": "test",
        }
        ticket = Ticket.from_dict(d)
        assert ticket.profile.key == "ssq"
        assert ticket.groups["red"] == [1, 2, 3, 4, 5, 6]
        assert ticket.groups["blue"] == [7]

    def test_fc3d_to_dict(self):
        ticket = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        d = ticket.to_dict()
        assert d["profile"] == "3d"
        assert d["groups"]["pos"] == [1, 2, 3]

    def test_fc3d_from_dict(self):
        d = {
            "profile": "3d",
            "groups": {"pos": [1, 2, 3]},
            "generated_at": "2025-01-01T12:00:00",
        }
        ticket = Ticket.from_dict(d)
        assert ticket.profile.key == "3d"
        assert ticket.groups["pos"] == [1, 2, 3]

    def test_roundtrip_ssq(self):
        original = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7, strategy_name="test")
        restored = Ticket.from_dict(original.to_dict())
        assert original == restored

    def test_roundtrip_fc3d(self):
        original = Ticket(profile="3d", groups={"pos": [1, 2, 3]}, strategy_name="test")
        restored = Ticket.from_dict(original.to_dict())
        assert original == restored


class TestTicketDisplay:
    """Ticket 展示测试."""

    def test_format_pretty_ssq(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        text = ticket.format_pretty()
        assert "红球" in text
        assert "蓝球" in text
        assert "01" in text
        assert "07" in text

    def test_format_compact_ssq(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        text = ticket.format_compact()
        assert "+" in text
        assert "01" in text

    def test_format_pretty_fc3d(self):
        ticket = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        text = ticket.format_pretty()
        assert "1" in text

    def test_str_equals_format_pretty(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert str(ticket) == ticket.format_pretty()

    def test_repr(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert "Ticket(" in repr(ticket)


class TestTicketEquality:
    """Ticket 相等性测试."""

    def test_equal_ssq(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert t1 == t2

    def test_not_equal_different_red(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 7], blue_ball=7)
        assert t1 != t2

    def test_not_equal_different_blue(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=8)
        assert t1 != t2

    def test_not_equal_different_type(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert ticket != "not a ticket"

    def test_hash_consistency(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        assert hash(t1) == hash(t2)

    def test_hash_in_set(self):
        t1 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        t2 = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        s = {t1, t2}
        assert len(s) == 1


class TestTicketRenderGroups:
    """Ticket 渲染组测试."""

    def test_ssq_render_groups(self):
        ticket = Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7)
        groups = ticket.render_groups()
        assert len(groups) == 2
        assert groups[0].name == "红球"
        assert groups[0].numbers == [1, 2, 3, 4, 5, 6]
        assert groups[1].name == "蓝球"
        assert groups[1].numbers == [7]

    def test_fc3d_render_groups(self):
        ticket = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        groups = ticket.render_groups()
        assert len(groups) == 1
        assert groups[0].numbers == [1, 2, 3]

    def test_dlt_render_groups(self):
        ticket = Ticket(profile="dlt", groups={"front": [1, 2, 3, 4, 5], "back": [1, 2]})
        groups = ticket.render_groups()
        assert len(groups) == 2
        assert groups[0].name == "前区"
        assert groups[1].name == "后区"
