"""八卦占卜策略单元测试：验证生成号码随目标彩种（profile_key）变化。

回归背景：此前 main_window 仅注入 _profile_key（下划线），而策略读取的是
profile_key（无下划线），导致策略始终回退到默认双色球。本测试锁定“传入
profile_key 时生成对应彩种号码”的行为，并对每个可选彩种做参数化校验。
"""

import pytest

from caipiao.core.profile import profile_keys
from caipiao.core.strategies.bagua import BaguaStrategy

STRAT = BaguaStrategy()


@pytest.mark.parametrize("pk", profile_keys())
def test_bagua_generates_for_each_profile(pk):
    tickets = STRAT.generate(1, {"method": "random", "seed": 1, "profile_key": pk})
    assert tickets[0].profile.key == pk


def test_bagua_defaults_to_ssq_when_no_profile_key():
    ticket = STRAT.generate(1, {"method": "random", "seed": 1})[0]
    assert ticket.profile.key == "ssq"
