"""福彩3D生成策略."""

from .balanced import FC3DBalancedStrategy
from .dispersed_random import FC3DDispersedRandomStrategy
from .ensemble import FC3DEnsembleStrategy, FC3DStrategyFusionStrategy
from .exclude_include import FC3DExcludeIncludeStrategy
from .hot_cold import FC3DHotColdStrategy
from .missing_number import FC3DMissingNumberStrategy
from .ml.catboost import FC3DCatBoostStrategy
from .ml.lightgbm import FC3DLightGBMStrategy
from .ml.xgboost import FC3DXGBoostStrategy
from .odd_even import FC3DOddEvenStrategy
from .random import FC3DRandomStrategy
from .smart_hot_cold import FC3DSmartHotColdStrategy

__all__ = [
    "FC3DRandomStrategy",
    "FC3DOddEvenStrategy",
    "FC3DHotColdStrategy",
    "FC3DExcludeIncludeStrategy",
    "FC3DSmartHotColdStrategy",
    "FC3DMissingNumberStrategy",
    "FC3DBalancedStrategy",
    "FC3DDispersedRandomStrategy",
    "FC3DEnsembleStrategy",
    "FC3DStrategyFusionStrategy",
    "FC3DXGBoostStrategy",
    "FC3DLightGBMStrategy",
    "FC3DCatBoostStrategy",
]
