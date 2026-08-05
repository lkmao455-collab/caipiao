"""共享 _base.py 测试."""

from __future__ import annotations

import pytest

from caipiao.core.profile import get_profile


class TestPL3Base:
    """pl3._base 测试."""

    def test_get_pick_count_fixed(self):
        from caipiao.core.strategies.lotteries.pl3._base import _get_pick_count
        # pl3 是固定 pick=3
        assert _get_pick_count({}) == 3
        assert _get_pick_count({"pick_count": 5}) == 3  # 忽略传入的 pick_count

    def test_add_pick_count_schema_noop(self):
        from caipiao.core.strategies.lotteries.pl3._base import _add_pick_count_schema
        schema = {}
        _add_pick_count_schema(schema)
        # pl3 固定 pick，不应添加 pick_count
        assert "pick_count" not in schema

    def test_make_ticket(self):
        from caipiao.core.strategies.lotteries.pl3._base import _make_ticket
        ticket = _make_ticket({"pos": [1, 2, 3]})
        assert ticket.profile.key == "pl3"
        assert ticket.groups["pos"] == [1, 2, 3]


class TestPL5Base:
    """pl5._base 测试."""

    def test_get_pick_count_fixed(self):
        from caipiao.core.strategies.lotteries.pl5._base import _get_pick_count
        assert _get_pick_count({}) == 5

    def test_add_pick_count_schema_noop(self):
        from caipiao.core.strategies.lotteries.pl5._base import _add_pick_count_schema
        schema = {}
        _add_pick_count_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        from caipiao.core.strategies.lotteries.pl5._base import _make_ticket
        ticket = _make_ticket({"pos": [1, 2, 3, 4, 5]})
        assert ticket.profile.key == "pl5"
        assert ticket.groups["pos"] == [1, 2, 3, 4, 5]


class TestQXCBase:
    """qxc._base 测试."""

    def test_get_pick_count_fixed(self):
        from caipiao.core.strategies.lotteries.qxc._base import _get_pick_count
        assert _get_pick_count({}) == 7

    def test_add_pick_count_schema_noop(self):
        from caipiao.core.strategies.lotteries.qxc._base import _add_pick_count_schema
        schema = {}
        _add_pick_count_schema(schema)
        assert "pick_count" not in schema

    def test_make_ticket(self):
        from caipiao.core.strategies.lotteries.qxc._base import _make_ticket
        ticket = _make_ticket({"pos": [1, 2, 3, 4, 5, 6, 7]})
        assert ticket.profile.key == "qxc"
        assert ticket.groups["pos"] == [1, 2, 3, 4, 5, 6, 7]


class TestKL8Base:
    """kl8._base 测试."""

    def test_get_pick_count_variable(self):
        from caipiao.core.strategies.lotteries.kl8._base import _get_pick_count
        # kl8 可变 pick，默认 max=10
        assert _get_pick_count({}) == 10
        # 自定义 pick
        assert _get_pick_count({"pick_count": 5}) == 5
        # 边界限制
        assert _get_pick_count({"pick_count": 0}) == 1
        assert _get_pick_count({"pick_count": 20}) == 10
        # 非数字默认
        assert _get_pick_count({"pick_count": "abc"}) == 10

    def test_add_pick_count_schema_adds_field(self):
        from caipiao.core.strategies.lotteries.kl8._base import _add_pick_count_schema
        schema = {}
        _add_pick_count_schema(schema)
        assert "pick_count" in schema
        assert schema["pick_count"]["choices"] == list(range(1, 11))
        assert schema["pick_count"]["default"] == 10

    def test_make_ticket(self):
        from caipiao.core.strategies.lotteries.kl8._base import _make_ticket
        ticket = _make_ticket({"main": [1, 2, 3, 4, 5]})
        assert ticket.profile.key == "kl8"
        assert ticket.groups["main"] == [1, 2, 3, 4, 5]


class TestSharedBaseFunctions:
    """验证各彩种共享相同函数签名."""

    def test_all_have_required_functions(self):
        """每个 _base 模块都应导出 _get_pick_count, _add_pick_count_schema, _make_ticket."""
        for mod_name in ["pl3._base", "pl5._base", "qxc._base", "kl8._base"]:
            mod = __import__(f"caipiao.core.strategies.lotteries.{mod_name}", fromlist=[""])
            assert hasattr(mod, "_get_pick_count")
            assert hasattr(mod, "_add_pick_count_schema")
            assert hasattr(mod, "_make_ticket")
            assert hasattr(mod, "PROFILE")

    def test_profiles_correct(self):
        """验证各彩种 PROFILE 指向正确的彩种."""
        from caipiao.core.strategies.lotteries.pl3._base import PROFILE as PL3_PROFILE
        from caipiao.core.strategies.lotteries.pl5._base import PROFILE as PL5_PROFILE
        from caipiao.core.strategies.lotteries.qxc._base import PROFILE as QXC_PROFILE
        from caipiao.core.strategies.lotteries.kl8._base import PROFILE as KL8_PROFILE

        assert PL3_PROFILE.key == "pl3"
        assert PL5_PROFILE.key == "pl5"
        assert QXC_PROFILE.key == "qxc"
        assert KL8_PROFILE.key == "kl8"

    def test_primary_group_matches(self):
        """验证各彩种 primary_group 与 profile 一致."""
        from caipiao.core.strategies.lotteries.pl3._base import PROFILE as PL3_PROFILE
        from caipiao.core.strategies.lotteries.pl5._base import PROFILE as PL5_PROFILE
        from caipiao.core.strategies.lotteries.qxc._base import PROFILE as QXC_PROFILE
        from caipiao.core.strategies.lotteries.kl8._base import PROFILE as KL8_PROFILE

        assert PL3_PROFILE.primary_group.key == "pos"
        assert PL5_PROFILE.primary_group.key == "pos"
        assert QXC_PROFILE.primary_group.key == "pos"
        assert KL8_PROFILE.primary_group.key == "main"