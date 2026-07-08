import pytest

from caipiao.core.profile import DLT, KL8, PL3, PL5, QLC, QXC, get_profile
from caipiao.core.strategies import build_strategies


@pytest.mark.parametrize("key", ["qlc", "kl8", "dlt", "pl3", "pl5", "qxc"])
def test_all_strategies_generate_valid_tickets(key):
    profile = get_profile(key)
    strategies = build_strategies(profile)
    assert len(strategies) >= 7
    for s in strategies:
        if s.metadata.id.startswith("random"):
            tickets = s.generate(count=2)
        else:
            # 其他策略需要历史数据，用随机生成的记录
            from datetime import datetime

            from caipiao.data.models import DrawRecord

            history = [
                DrawRecord(
                    f"2024{i:03d}",
                    datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                    profile=key,
                    groups={g.key: [g.lo] * g.count for g in profile.pick_groups},
                )
                for i in range(100)
            ]
            tickets = s.generate(count=2, options={"history": history})
        assert len(tickets) == 2
        for t in tickets:
            assert t.profile.key == key
            for g in profile.pick_groups:
                assert g.key in t.groups
                assert len(t.groups[g.key]) >= g.effective_pick_min
