"""端到端生成流程测试.

测试从策略注册到号码生成的完整流程。
"""

from datetime import datetime, timedelta

import pytest

from caipiao.core.engine import GenerationEngine
from caipiao.core.profile import SSQ, FC3D, QLC, KL8, DLT, PL3, PL5, QXC
from caipiao.core.strategies.factory import build_strategies
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


# ---- Helpers ----

def _make_ssq_records(count=100):
    records = []
    for i in range(count):
        reds = sorted([(i + j) % 33 + 1 for j in range(6)])
        blue = (i % 16) + 1
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=reds,
            blue_ball=blue,
        ))
    return records


def _make_3d_records(count=100):
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10]},
        ))
    return records


def _make_dlt_records(count=100):
    records = []
    for i in range(count):
        front = sorted([(i + j) % 35 + 1 for j in range(5)])
        back = sorted([(i + j) % 12 + 1 for j in range(2)])
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="dlt",
            groups={"front": front, "back": back},
        ))
    return records


def _make_kl8_records(count=100):
    records = []
    for i in range(count):
        main = sorted([(i + j) % 80 + 1 for j in range(20)])
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="kl8",
            groups={"main": main},
        ))
    return records


def _make_pl3_records(count=100):
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="pl3",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10]},
        ))
    return records


def _make_pl5_records(count=100):
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="pl5",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10, (i + 3) % 10, (i + 4) % 10]},
        ))
    return records


def _make_qxc_records(count=100):
    records = []
    for i in range(count):
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="qxc",
            groups={"pos": [i % 10, (i + 1) % 10, (i + 2) % 10, (i + 3) % 10, (i + 4) % 10, (i + 5) % 10, (i + 6) % 10]},
        ))
    return records


def _make_qlc_records(count=100):
    records = []
    for i in range(count):
        basic = sorted([(i + j) % 30 + 1 for j in range(7)])
        records.append(DrawRecord(
            issue=f"2024{i + 1:03d}",
            draw_date=datetime(2024, 1, 1) + timedelta(days=i),
            profile="qlc",
            groups={"basic": basic, "special": [(i % 30) + 1]},
        ))
    return records


RECORD_MAKERS = {
    "ssq": _make_ssq_records,
    "3d": _make_3d_records,
    "qlc": _make_qlc_records,
    "kl8": _make_kl8_records,
    "dlt": _make_dlt_records,
    "pl3": _make_pl3_records,
    "pl5": _make_pl5_records,
    "qxc": _make_qxc_records,
}


# ---- Engine Registration Tests ----

class TestEngineRegistration:
    """策略注册测试."""

    def test_register_and_list(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        for s in strategies:
            engine.register(s)
        listed = engine.list_strategies()
        assert len(listed) >= 2

    def test_get_strategy(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        engine.register(strategies[0])
        found = engine.get(strategies[0].metadata.id)
        assert found is not None
        assert found.metadata.id == strategies[0].metadata.id

    def test_get_unknown_returns_none(self):
        engine = GenerationEngine()
        assert engine.get("nonexistent") is None

    def test_unregister(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        engine.register(strategies[0])
        engine.unregister(strategies[0].metadata.id)
        assert engine.get(strategies[0].metadata.id) is None


# ---- SSQ Generation Tests ----

class TestSSQGeneration:
    """双色球生成端到端测试."""

    def test_generate_single(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_ssq_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        assert len(tickets) == 1
        assert isinstance(tickets[0], Ticket)
        assert tickets[0].profile.key == "ssq"

    def test_generate_multiple(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_ssq_records(100)
        tickets = engine.generate(strategy_id, count=5, options={"history": history})
        assert len(tickets) == 5
        unique = set(t.format_compact() for t in tickets)
        assert len(unique) >= 1

    def test_ticket_valid_ssq(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_ssq_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        ticket = tickets[0]
        assert len(ticket.groups["red"]) == 6
        assert all(1 <= n <= 33 for n in ticket.groups["red"])
        assert len(ticket.groups["blue"]) == 1
        assert 1 <= ticket.groups["blue"][0] <= 16

    def test_all_ssq_strategies(self):
        engine = GenerationEngine()
        strategies = build_strategies(SSQ)
        for s in strategies:
            engine.register(s)
        history = _make_ssq_records(100)
        for s in strategies:
            tickets = engine.generate(s.metadata.id, count=2, options={"history": history})
            assert len(tickets) == 2
            assert all(t.profile.key == "ssq" for t in tickets)


# ---- FC3D Generation Tests ----

class TestFC3DGeneration:
    """福彩3D 生成端到端测试."""

    def test_generate_single(self):
        engine = GenerationEngine()
        strategies = build_strategies(FC3D)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_3d_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        assert len(tickets) == 1
        assert tickets[0].profile.key == "3d"

    def test_ticket_valid_3d(self):
        engine = GenerationEngine()
        strategies = build_strategies(FC3D)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_3d_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        ticket = tickets[0]
        assert len(ticket.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in ticket.groups["pos"])


# ---- DLT Generation Tests ----

class TestDLTGeneration:
    """超级大乐透生成端到端测试."""

    def test_generate_single(self):
        engine = GenerationEngine()
        strategies = build_strategies(DLT)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_dlt_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        assert len(tickets) == 1
        assert tickets[0].profile.key == "dlt"

    def test_ticket_valid_dlt(self):
        engine = GenerationEngine()
        strategies = build_strategies(DLT)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_dlt_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        ticket = tickets[0]
        assert len(ticket.groups["front"]) == 5
        assert all(1 <= n <= 35 for n in ticket.groups["front"])
        assert len(ticket.groups["back"]) == 2
        assert all(1 <= n <= 12 for n in ticket.groups["back"])


# ---- KL8 Generation Tests ----

class TestKL8Generation:
    """快乐8 生成端到端测试."""

    def test_generate_single(self):
        engine = GenerationEngine()
        strategies = build_strategies(KL8)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_kl8_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        assert len(tickets) == 1
        assert tickets[0].profile.key == "kl8"

    def test_ticket_valid_kl8(self):
        engine = GenerationEngine()
        strategies = build_strategies(KL8)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_kl8_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        ticket = tickets[0]
        # KL8 默认选 4 个号
        assert len(ticket.groups["main"]) == 4
        assert all(1 <= n <= 80 for n in ticket.groups["main"])


# ---- PL3 Generation Tests ----

class TestPL3Generation:
    """排列3 生成端到端测试."""

    def test_generate_single(self):
        engine = GenerationEngine()
        strategies = build_strategies(PL3)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_pl3_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        assert len(tickets) == 1
        assert tickets[0].profile.key == "pl3"

    def test_ticket_valid_pl3(self):
        engine = GenerationEngine()
        strategies = build_strategies(PL3)
        for s in strategies:
            engine.register(s)
        strategy_id = strategies[0].metadata.id
        history = _make_pl3_records(100)
        tickets = engine.generate(strategy_id, count=1, options={"history": history})
        ticket = tickets[0]
        assert len(ticket.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in ticket.groups["pos"])


# ---- Cross-Lottery Tests ----

class TestCrossLottery:
    """跨彩种生成测试."""

    def test_all_lotteries_generate(self):
        """验证所有彩种都能生成有效号码."""
        profiles = [SSQ, FC3D, DLT, KL8, PL3, PL5, QXC]
        for profile in profiles:
            engine = GenerationEngine()
            strategies = build_strategies(profile)
            for s in strategies:
                engine.register(s)
            strategy_id = strategies[0].metadata.id
            history = RECORD_MAKERS[profile.key](100)
            tickets = engine.generate(strategy_id, count=1, options={"history": history})
            assert len(tickets) == 1
            assert tickets[0].profile.key == profile.key

    def test_generate_unknown_strategy_raises(self):
        engine = GenerationEngine()
        with pytest.raises(ValueError, match="未找到策略"):
            engine.generate("nonexistent", count=1)


# ---- Strategy Metadata Tests ----

class TestStrategyMetadata:
    """策略元数据测试."""

    def test_all_strategies_have_metadata(self):
        profiles = [SSQ, FC3D, DLT, KL8, PL3, PL5, QXC]
        for profile in profiles:
            strategies = build_strategies(profile)
            for s in strategies:
                assert s.metadata.id
                assert s.metadata.name
                assert s.metadata.description

    def test_strategy_ids_unique_per_profile(self):
        profiles = [SSQ, FC3D, DLT, KL8, PL3, PL5, QXC]
        for profile in profiles:
            strategies = build_strategies(profile)
            ids = [s.metadata.id for s in strategies]
            assert len(ids) == len(set(ids))
