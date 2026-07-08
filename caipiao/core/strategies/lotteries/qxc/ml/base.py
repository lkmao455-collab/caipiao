"""7星彩 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import QXC
from ......ml.lotteries.qxc.predictor import QXCPredictor

_QXCMLStrategyBase = make_generic_ml_base(QXC, predictor_class=QXCPredictor)
