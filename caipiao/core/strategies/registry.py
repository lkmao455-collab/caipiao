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
from .lotteries.dlt import balanced as dlt_balanced
from .lotteries.dlt import exclude_include as dlt_exclude_include
from .lotteries.dlt import hot_cold as dlt_hot_cold
from .lotteries.dlt import missing_number as dlt_missing_number
from .lotteries.dlt import odd_even as dlt_odd_even
from .lotteries.dlt import random as dlt_random
from .lotteries.dlt import smart_hot_cold as dlt_smart_hot_cold
from .lotteries.dlt.ml import catboost as dlt_catboost
from .lotteries.dlt.ml import lightgbm as dlt_lightgbm
from .lotteries.dlt.ml import xgboost as dlt_xgboost
from .lotteries.kl8 import balanced as kl8_balanced
from .lotteries.kl8 import exclude_include as kl8_exclude_include
from .lotteries.kl8 import hot_cold as kl8_hot_cold
from .lotteries.kl8 import missing_number as kl8_missing_number
from .lotteries.kl8 import odd_even as kl8_odd_even
from .lotteries.kl8 import random as kl8_random
from .lotteries.kl8 import smart_hot_cold as kl8_smart_hot_cold
from .lotteries.kl8.ml import catboost as kl8_catboost
from .lotteries.kl8.ml import lightgbm as kl8_lightgbm
from .lotteries.kl8.ml import xgboost as kl8_xgboost
from .lotteries.pl3 import balanced as pl3_balanced
from .lotteries.pl3 import exclude_include as pl3_exclude_include
from .lotteries.pl3 import hot_cold as pl3_hot_cold
from .lotteries.pl3 import missing_number as pl3_missing_number
from .lotteries.pl3 import odd_even as pl3_odd_even
from .lotteries.pl3 import random as pl3_random
from .lotteries.pl3 import smart_hot_cold as pl3_smart_hot_cold
from .lotteries.pl3.ml import catboost as pl3_catboost
from .lotteries.pl3.ml import lightgbm as pl3_lightgbm
from .lotteries.pl3.ml import xgboost as pl3_xgboost
from .lotteries.pl5 import balanced as pl5_balanced
from .lotteries.pl5 import exclude_include as pl5_exclude_include
from .lotteries.pl5 import hot_cold as pl5_hot_cold
from .lotteries.pl5 import missing_number as pl5_missing_number
from .lotteries.pl5 import odd_even as pl5_odd_even
from .lotteries.pl5 import random as pl5_random
from .lotteries.pl5 import smart_hot_cold as pl5_smart_hot_cold
from .lotteries.pl5.ml import catboost as pl5_catboost
from .lotteries.pl5.ml import lightgbm as pl5_lightgbm
from .lotteries.pl5.ml import xgboost as pl5_xgboost
from .lotteries.qlc import balanced as qlc_balanced
from .lotteries.qlc import exclude_include as qlc_exclude_include
from .lotteries.qlc import hot_cold as qlc_hot_cold
from .lotteries.qlc import missing_number as qlc_missing_number
from .lotteries.qlc import odd_even as qlc_odd_even
from .lotteries.qlc import random as qlc_random
from .lotteries.qlc import smart_hot_cold as qlc_smart_hot_cold
from .lotteries.qlc.ml import catboost as qlc_catboost
from .lotteries.qlc.ml import lightgbm as qlc_lightgbm
from .lotteries.qlc.ml import xgboost as qlc_xgboost
from .lotteries.qxc import balanced as qxc_balanced
from .lotteries.qxc import exclude_include as qxc_exclude_include
from .lotteries.qxc import hot_cold as qxc_hot_cold
from .lotteries.qxc import missing_number as qxc_missing_number
from .lotteries.qxc import odd_even as qxc_odd_even
from .lotteries.qxc import random as qxc_random
from .lotteries.qxc import smart_hot_cold as qxc_smart_hot_cold
from .lotteries.qxc.ml import catboost as qxc_catboost
from .lotteries.qxc.ml import lightgbm as qxc_lightgbm
from .lotteries.qxc.ml import xgboost as qxc_xgboost
from ..strategy import GenerationStrategy

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
    "qlc": [
        qlc_random.QLCRandomStrategy,
        qlc_odd_even.QLCOddEvenStrategy,
        qlc_hot_cold.QLCHotColdStrategy,
        qlc_exclude_include.QLCExcludeIncludeStrategy,
        qlc_smart_hot_cold.QLCSmartHotColdStrategy,
        qlc_missing_number.QLCMissingNumberStrategy,
        qlc_balanced.QLCBalancedStrategy,
        qlc_xgboost.QLCXGBoostStrategy,
        qlc_lightgbm.QLCLightGBMStrategy,
        qlc_catboost.QLCCatBoostStrategy,
    ],
    "kl8": [
        kl8_random.KL8RandomStrategy,
        kl8_odd_even.KL8OddEvenStrategy,
        kl8_hot_cold.KL8HotColdStrategy,
        kl8_exclude_include.KL8ExcludeIncludeStrategy,
        kl8_smart_hot_cold.KL8SmartHotColdStrategy,
        kl8_missing_number.KL8MissingNumberStrategy,
        kl8_balanced.KL8BalancedStrategy,
        kl8_xgboost.KL8XGBoostStrategy,
        kl8_lightgbm.KL8LightGBMStrategy,
        kl8_catboost.KL8CatBoostStrategy,
    ],
    "dlt": [
        dlt_random.DLTRandomStrategy,
        dlt_odd_even.DLTOddEvenStrategy,
        dlt_hot_cold.DLTHotColdStrategy,
        dlt_exclude_include.DLTExcludeIncludeStrategy,
        dlt_smart_hot_cold.DLTSmartHotColdStrategy,
        dlt_missing_number.DLTMissingNumberStrategy,
        dlt_balanced.DLTBalancedStrategy,
        dlt_xgboost.DLTXGBoostStrategy,
        dlt_lightgbm.DLTLightGBMStrategy,
        dlt_catboost.DLTCatBoostStrategy,
    ],
    "pl3": [
        pl3_random.PL3RandomStrategy,
        pl3_odd_even.PL3OddEvenStrategy,
        pl3_hot_cold.PL3HotColdStrategy,
        pl3_exclude_include.PL3ExcludeIncludeStrategy,
        pl3_smart_hot_cold.PL3SmartHotColdStrategy,
        pl3_missing_number.PL3MissingNumberStrategy,
        pl3_balanced.PL3BalancedStrategy,
        pl3_xgboost.PL3XGBoostStrategy,
        pl3_lightgbm.PL3LightGBMStrategy,
        pl3_catboost.PL3CatBoostStrategy,
    ],
    "pl5": [
        pl5_random.PL5RandomStrategy,
        pl5_odd_even.PL5OddEvenStrategy,
        pl5_hot_cold.PL5HotColdStrategy,
        pl5_exclude_include.PL5ExcludeIncludeStrategy,
        pl5_smart_hot_cold.PL5SmartHotColdStrategy,
        pl5_missing_number.PL5MissingNumberStrategy,
        pl5_balanced.PL5BalancedStrategy,
        pl5_xgboost.PL5XGBoostStrategy,
        pl5_lightgbm.PL5LightGBMStrategy,
        pl5_catboost.PL5CatBoostStrategy,
    ],
    "qxc": [
        qxc_random.QXCRandomStrategy,
        qxc_odd_even.QXCOddEvenStrategy,
        qxc_hot_cold.QXCHotColdStrategy,
        qxc_exclude_include.QXCExcludeIncludeStrategy,
        qxc_smart_hot_cold.QXCSmartHotColdStrategy,
        qxc_missing_number.QXCMissingNumberStrategy,
        qxc_balanced.QXCBalancedStrategy,
        qxc_xgboost.QXCXGBoostStrategy,
        qxc_lightgbm.QXCLightGBMStrategy,
        qxc_catboost.QXCCatBoostStrategy,
    ],
}
