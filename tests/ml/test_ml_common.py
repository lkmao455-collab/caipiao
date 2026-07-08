"""ML 公共模块导入与接口测试."""

from __future__ import annotations

from caipiao.ml.common import (
    BaseMLPredictor,
    GenericMLPredictor,
    LotteryGenericModel,
    build_features,
    build_prediction_features,
)


def test_common_exports():
    assert LotteryGenericModel is not None
    assert build_features is not None
    assert build_prediction_features is not None
    assert BaseMLPredictor is not None
    assert GenericMLPredictor is BaseMLPredictor
