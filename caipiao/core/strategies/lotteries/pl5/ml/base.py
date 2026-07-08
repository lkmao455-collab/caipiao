"""排列5 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import PL5
from ......ml.lotteries.pl5.predictor import PL5Predictor

_PL5MLStrategyBase = make_generic_ml_base(PL5, predictor_class=PL5Predictor)
