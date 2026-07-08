"""高级预测策略子包（按彩种隔离）。"""

from .lotteries.ssq.bayesian import SSQBayesianStrategy
from .lotteries.ssq.correlation import SSQCorrelationStrategy
from .lotteries.ssq.ensemble import SSQEnsembleStrategy
from .lotteries.ssq.markov import SSQMarkovStrategy
from .lotteries.ssq.periodic import SSQPeriodicStrategy
from .lotteries.ssq.random_forest import SSQRandomForestStrategy
from .lotteries.ssq.trend import SSQTrendStrategy
from .lotteries.ssq.transformer import SSQTransformerStrategy

__all__ = [
    "SSQRandomForestStrategy",
    "SSQBayesianStrategy",
    "SSQMarkovStrategy",
    "SSQTrendStrategy",
    "SSQPeriodicStrategy",
    "SSQEnsembleStrategy",
    "SSQCorrelationStrategy",
    "SSQTransformerStrategy",
]
