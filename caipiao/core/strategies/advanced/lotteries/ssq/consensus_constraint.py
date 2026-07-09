"""双色球共识约束策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .....profile import SSQ
from .....strategy import GenerationStrategy, StrategyMetadata
from .....ticket import Ticket


class SSQConsensusConstraintStrategy(GenerationStrategy):
    """融合现有统计/数学策略优点的综合策略."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="consensus_constraint",
            name="共识约束策略",
            description=(
                "融合随机、统计、概率推断等多种数学方法的综合策略。"
                "所有参数可调，相同参数下输出一致。"
            ),
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "seed": {
                "type": "int",
                "label": "随机种子",
                "default": 42,
                "min": 0,
                "max": 999999999,
                "tooltip": "统一随机种子，相同历史数据+相同全部参数=相同输出",
            },
            "candidate_count": {
                "type": "int",
                "label": "候选池大小",
                "default": 50000,
                "min": 1000,
                "max": 300000,
                "tooltip": "初始生成的候选组合数量",
            },
            "relaxation_order": {
                "type": "choice",
                "label": "冲突回退模式",
                "choices": ["reverse", "strict"],
                "default": "reverse",
                "tooltip": "reverse=自动放宽约束；strict=严格报错",
            },
            "predict_date": {
                "type": "string",
                "label": "预测日期 (YYYY-MM-DD)",
                "default": "",
                "tooltip": "周期分析使用的日期；留空使用历史最后一期+1天",
            },
            "blue_sampling_mode": {
                "type": "choice",
                "label": "蓝球抽样方式",
                "choices": ["uniform", "weighted"],
                "default": "weighted",
                "tooltip": "uniform=均匀随机；weighted=按阶段1概率加权",
            },
            # stats
            "stats_enabled": {"type": "bool", "label": "启用统计分析", "default": True},
            "stats_mode": {
                "type": "choice",
                "label": "统计模式",
                "choices": ["hot", "cold", "mixed", "smart", "missing"],
                "default": "smart",
            },
            "stats_lookback": {"type": "int", "label": "统计回看期数", "default": 100, "min": 20, "max": 5000},
            "stats_hot_weight": {"type": "int", "label": "统计热号权重", "default": 60, "min": 0, "max": 100},
            "stats_cold_weight": {"type": "int", "label": "统计冷号权重", "default": 40, "min": 0, "max": 100},
            "stats_pool_size": {"type": "int", "label": "统计候选池大小", "default": 12, "min": 6, "max": 20},
            "stats_weight": {"type": "int", "label": "统计模型融合权重", "default": 25, "min": 0, "max": 100},
            # smart hot cold
            "smart_hot_cold_enabled": {"type": "bool", "label": "启用智能冷热", "default": True},
            "smart_hot_cold_lookback": {"type": "int", "label": "智能冷热统计期数", "default": 100, "min": 10, "max": 10000},
            "smart_hot_cold_hot_weight": {"type": "int", "label": "智能冷热热号权重", "default": 60, "min": 0, "max": 100},
            "smart_hot_cold_cold_weight": {"type": "int", "label": "智能冷热冷号权重", "default": 40, "min": 0, "max": 100},
            "smart_hot_cold_weight": {"type": "int", "label": "智能冷热融合权重", "default": 25, "min": 0, "max": 100},
            # hot cold
            "hot_cold_enabled": {"type": "bool", "label": "启用冷热号", "default": True},
            "hot_cold_mode": {"type": "choice", "label": "冷热号模式", "choices": ["hot", "cold", "mixed"], "default": "mixed"},
            "hot_cold_weight": {"type": "int", "label": "冷热号融合权重", "default": 25, "min": 0, "max": 100},
            # missing number
            "missing_number_enabled": {"type": "bool", "label": "启用遗漏号", "default": True},
            "missing_number_lookback": {"type": "int", "label": "遗漏号统计期数", "default": 50, "min": 10, "max": 10000},
            "missing_number_pool_size": {"type": "int", "label": "遗漏号候选池大小", "default": 12, "min": 6, "max": 20},
            "missing_number_weight": {"type": "int", "label": "遗漏号融合权重", "default": 25, "min": 0, "max": 100},
            # odd even
            "odd_even_enabled": {"type": "bool", "label": "启用奇偶约束", "default": True},
            "odd_count": {"type": "int", "label": "红球奇数个数", "default": 3, "min": 0, "max": 6},
            # balanced
            "balanced_enabled": {"type": "bool", "label": "启用历史均衡", "default": True},
            "balanced_lookback": {"type": "int", "label": "均衡统计期数", "default": 100, "min": 10, "max": 10000},
            "sum_min": {"type": "int", "label": "红球和值下限", "default": 60, "min": 21, "max": 183},
            "sum_max": {"type": "int", "label": "红球和值上限", "default": 160, "min": 21, "max": 183},
            "target_odd": {"type": "int", "label": "目标奇数个数", "default": 3, "min": 0, "max": 6},
            "target_high": {"type": "int", "label": "目标大号个数", "default": 3, "min": 0, "max": 6},
            # exclude include
            "exclude_include_enabled": {"type": "bool", "label": "启用排除/必含", "default": False},
            "include_red": {"type": "list_int", "label": "必含红球", "default": [], "min": 1, "max": 33},
            "exclude_red": {"type": "list_int", "label": "排除红球", "default": [], "min": 1, "max": 33},
            "exclude_blue": {"type": "list_int", "label": "排除蓝球", "default": [], "min": 1, "max": 16},
            # bayesian
            "bayesian_enabled": {"type": "bool", "label": "启用贝叶斯推断", "default": True},
            "bayesian_prior_weight": {"type": "int", "label": "贝叶斯先验权重", "default": 60, "min": 10, "max": 90},
            "bayesian_lookback": {"type": "int", "label": "贝叶斯观测窗口", "default": 50, "min": 10, "max": 500},
            "bayesian_alpha": {"type": "int", "label": "贝叶斯先验强度", "default": 2, "min": 1, "max": 10},
            "bayesian_weight": {"type": "int", "label": "贝叶斯融合权重", "default": 25, "min": 0, "max": 100},
            # markov
            "markov_enabled": {"type": "bool", "label": "启用马尔可夫链", "default": True},
            "markov_order": {"type": "choice", "label": "马尔可夫阶数", "choices": ["1", "2", "3"], "default": "2"},
            "markov_lookback": {"type": "int", "label": "马尔可夫融合窗口", "default": 10, "min": 3, "max": 30},
            "markov_transition_weight": {"type": "int", "label": "马尔可夫转移权重", "default": 30, "min": 0, "max": 100},
            "markov_weight": {"type": "int", "label": "马尔可夫融合权重", "default": 20, "min": 0, "max": 100},
            # trend
            "trend_enabled": {"type": "bool", "label": "启用趋势分析", "default": True},
            "trend_window_size": {"type": "int", "label": "趋势窗口大小", "default": 10, "min": 5, "max": 30},
            "trend_weight": {"type": "int", "label": "趋势权重", "default": 50, "min": 0, "max": 100},
            "trend_model_weight": {"type": "int", "label": "趋势模型融合权重", "default": 20, "min": 0, "max": 100},
            # periodic
            "periodic_enabled": {"type": "bool", "label": "启用周期分析", "default": True},
            "periodic_week_weight": {"type": "int", "label": "周周期权重", "default": 40, "min": 0, "max": 100},
            "periodic_month_weight": {"type": "int", "label": "月周期权重", "default": 35, "min": 0, "max": 100},
            "periodic_quarter_weight": {"type": "int", "label": "季度周期权重", "default": 25, "min": 0, "max": 100},
            "periodic_weight": {"type": "int", "label": "周期模型融合权重", "default": 20, "min": 0, "max": 100},
            # correlation
            "correlation_enabled": {"type": "bool", "label": "启用相关性挖掘", "default": True},
            "correlation_min_support": {"type": "int", "label": "相关性最小支持度", "default": 5, "min": 1, "max": 20},
            "correlation_weight": {"type": "int", "label": "相关性权重", "default": 60, "min": 0, "max": 100},
            "correlation_model_weight": {"type": "int", "label": "相关性模型融合权重", "default": 15, "min": 0, "max": 100},
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        from ....common.records import records_from_options

        records = records_from_options(options)
        if len(records) < 30:
            raise ValueError("共识约束策略需要至少 30 期历史数据")
        if options.get("sum_min", 60) > options.get("sum_max", 160):
            raise ValueError("和值下限不能大于上限")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        # TODO: implemented in later tasks
        return []
