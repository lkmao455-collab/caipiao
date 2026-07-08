"""大乐透 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import DLT
from ......ml.lotteries.dlt.predictor import DLTPredictor

_DLTMLStrategyBase = make_generic_ml_base(DLT, predictor_class=DLTPredictor)
