"""大乐透 ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

from ....common.ml import make_generic_ml_base
from .....profile import DLT

_DLTMLStrategyBase = make_generic_ml_base(DLT)
