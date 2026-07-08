"""排列3 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import PL3
from ......ml.lotteries.pl3.predictor import PL3Predictor

_PL3MLStrategyBase = make_generic_ml_base(PL3, predictor_class=PL3Predictor)
