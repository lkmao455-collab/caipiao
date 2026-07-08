"""福彩3D通用 ML 策略包装器.

保留 `ml_strategy` 通用类的 FC3D 专属入口；当前未注册到 registry，
仅作为后续扩展或兼容旧配置的保留类。
"""

from __future__ import annotations

from .....strategy import StrategyMetadata
from .base import _FC3DMLStrategyBase


class FC3DMLStrategy(_FC3DMLStrategyBase):
    """福彩3D 通用 ML 策略（默认 XGBoost 后端）。"""

    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_strategy",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
