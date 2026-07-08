"""策略注册表：按彩种管理所有生成策略类。"""

from __future__ import annotations

from typing import Dict, List, Type

from .lotteries.fc3d import balanced as fc3d_balanced
from .lotteries.fc3d import exclude_include as fc3d_exclude_include
from .lotteries.fc3d import hot_cold as fc3d_hot_cold
from .lotteries.fc3d import missing_number as fc3d_missing_number
from .lotteries.fc3d import odd_even as fc3d_odd_even
from .lotteries.fc3d import random as fc3d_random
from .lotteries.fc3d import smart_hot_cold as fc3d_smart_hot_cold
from .lotteries.fc3d.ml import catboost as fc3d_catboost
from .lotteries.fc3d.ml import lightgbm as fc3d_lightgbm
from .lotteries.fc3d.ml import xgboost as fc3d_xgboost
from .lotteries.ssq import balanced as ssq_balanced
from .lotteries.ssq import bayesian as ssq_bayesian
from .lotteries.ssq import correlation as ssq_correlation
from .lotteries.ssq import ensemble as ssq_ensemble
from .lotteries.ssq import exclude_include as ssq_exclude_include
from .lotteries.ssq import hot_cold as ssq_hot_cold
from .lotteries.ssq import markov as ssq_markov
from .lotteries.ssq import missing_number as ssq_missing_number
from .lotteries.ssq import odd_even as ssq_odd_even
from .lotteries.ssq import periodic as ssq_periodic
from .lotteries.ssq import random as ssq_random
from .lotteries.ssq import random_forest as ssq_random_forest
from .lotteries.ssq import smart_hot_cold as ssq_smart_hot_cold
from .lotteries.ssq import stats as ssq_stats
from .lotteries.ssq import transformer as ssq_transformer
from .lotteries.ssq import trend as ssq_trend
from .lotteries.ssq.ml import catboost as ssq_catboost
from .lotteries.ssq.ml import hybrid as ssq_hybrid
from .lotteries.ssq.ml import lightgbm as ssq_lightgbm
from .lotteries.ssq.ml import lstm as ssq_lstm
from .lotteries.ssq.ml import xgboost as ssq_xgboost
from ..strategy import GenerationStrategy

# 当前阶段仅注册 ssq 与 3d；其余彩种在 Phase 2 完成后补齐。
STRATEGY_REGISTRY: Dict[str, List[Type[GenerationStrategy]]] = {
    "ssq": [
        ssq_random.SSQRandomStrategy,
        ssq_odd_even.SSQOddEvenStrategy,
        ssq_hot_cold.SSQHotColdStrategy,
        ssq_exclude_include.SSQExcludeIncludeStrategy,
        ssq_smart_hot_cold.SSQSmartHotColdStrategy,
        ssq_missing_number.SSQMissingNumberStrategy,
        ssq_balanced.SSQBalancedStrategy,
        ssq_stats.SSQStatsStrategy,
        ssq_xgboost.SSQXGBoostStrategy,
        ssq_lightgbm.SSQLightGBMStrategy,
        ssq_catboost.SSQCatBoostStrategy,
        ssq_lstm.SSQLSTMStrategy,
        ssq_hybrid.SSQHybridStrategy,
        ssq_random_forest.SSQRandomForestStrategy,
        ssq_bayesian.SSQBayesianStrategy,
        ssq_markov.SSQMarkovStrategy,
        ssq_trend.SSQTrendStrategy,
        ssq_periodic.SSQPeriodicStrategy,
        ssq_ensemble.SSQEnsembleStrategy,
        ssq_correlation.SSQCorrelationStrategy,
        ssq_transformer.SSQTransformerStrategy,
    ],
    "3d": [
        fc3d_random.FC3DRandomStrategy,
        fc3d_odd_even.FC3DOddEvenStrategy,
        fc3d_hot_cold.FC3DHotColdStrategy,
        fc3d_exclude_include.FC3DExcludeIncludeStrategy,
        fc3d_smart_hot_cold.FC3DSmartHotColdStrategy,
        fc3d_missing_number.FC3DMissingNumberStrategy,
        fc3d_balanced.FC3DBalancedStrategy,
        fc3d_xgboost.FC3DXGBoostStrategy,
        fc3d_lightgbm.FC3DLightGBMStrategy,
        fc3d_catboost.FC3DCatBoostStrategy,
    ],
}
