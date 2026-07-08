"""七乐彩 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import QLC
from ......ml.lotteries.qlc.predictor import QLCPredictor

_QLCMLStrategyBase = make_generic_ml_base(QLC, predictor_class=QLCPredictor)
