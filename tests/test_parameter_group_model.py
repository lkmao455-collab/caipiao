"""参数组数据模型测试."""

from caipiao.core.parameter_group import (
    ParameterGroup,
    StrategyParameterItem,
    parameter_group_from_dict,
    parameter_group_to_dict,
)


def test_create_parameter_group():
    item = StrategyParameterItem(
        strategy_id="xgboost",
        strategy_name="XGBoost 智能分析",
        param_name="history_count",
        param_value=300,
        enabled=True,
        metrics={"total_fixed_prize": 100, "hit_count": 5},
    )
    group = ParameterGroup(
        id="g1",
        name="测试组",
        profile_key="ssq",
        created_at="2026-07-05T10:00:00",
        scan_context={"start_date": "2026-01-01", "end_date": "2026-06-30"},
        items=[item],
    )
    assert group.items[0].strategy_id == "xgboost"
    assert group.items[0].metrics["hit_count"] == 5


def test_roundtrip_serialization():
    item = StrategyParameterItem(
        strategy_id="smart_hot_cold",
        strategy_name="智能冷热号",
        param_name="lookback",
        param_value=100,
        enabled=True,
        metrics={"total_fixed_prize": 80, "hit_count": 3},
    )
    group = ParameterGroup(
        id="g2",
        name="最优组",
        profile_key="ssq",
        created_at="2026-07-05T10:00:00",
        scan_context={},
        items=[item],
    )
    data = parameter_group_to_dict(group)
    restored = parameter_group_from_dict(data)
    assert restored.id == "g2"
    assert restored.items[0].param_value == 100
    assert restored.items[0].metrics["hit_count"] == 3


def test_backward_compatible_missing_fields():
    data = {
        "id": "g3",
        "name": "旧数据",
        "profile_key": "ssq",
        "created_at": "2026-07-05T10:00:00",
        "items": [
            {
                "strategy_id": "random",
                "strategy_name": "完全随机",
                "param_name": None,
                "param_value": None,
                "enabled": True,
                "metrics": {},
            }
        ],
    }
    restored = parameter_group_from_dict(data)
    assert restored.scan_context == {}
    assert restored.items[0].metrics == {}
