"""双色球共识约束策略."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ......data.analyzer import DrawAnalyzer
from ......data.models import DrawRecord
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
        schema = self.get_config_schema()
        sum_min = options.get("sum_min", schema["sum_min"]["default"])
        sum_max = options.get("sum_max", schema["sum_max"]["default"])
        if sum_min > sum_max:
            raise ValueError("和值下限不能大于上限")

    def _compute_statistical_prior(
        self, records: List[DrawRecord], options: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, str]:
        """阶段1：统计先验建模，返回红球概率、蓝球概率、依据说明。"""
        analyzer = DrawAnalyzer(records, SSQ)

        red_probs_list: List[np.ndarray] = []
        blue_probs_list: List[np.ndarray] = []
        weights: List[int] = []
        basis_parts: List[str] = []

        if options.get("stats_enabled", True):
            r, b, text = self._stats_prior(analyzer, options)
            red_probs_list.append(r)
            blue_probs_list.append(b)
            weights.append(int(options.get("stats_weight", 25)))
            basis_parts.append(text)

        if options.get("smart_hot_cold_enabled", True):
            r, b, text = self._smart_hot_cold_prior(analyzer, options)
            red_probs_list.append(r)
            blue_probs_list.append(b)
            weights.append(int(options.get("smart_hot_cold_weight", 25)))
            basis_parts.append(text)

        if options.get("hot_cold_enabled", True):
            r, b, text = self._hot_cold_prior(analyzer, options)
            red_probs_list.append(r)
            blue_probs_list.append(b)
            weights.append(int(options.get("hot_cold_weight", 25)))
            basis_parts.append(text)

        if options.get("missing_number_enabled", True):
            r, b, text = self._missing_number_prior(analyzer, options)
            red_probs_list.append(r)
            blue_probs_list.append(b)
            weights.append(int(options.get("missing_number_weight", 25)))
            basis_parts.append(text)

        if not red_probs_list:
            red_prior = np.ones(33) / 33.0
            blue_prior = np.ones(16) / 16.0
            basis = "未启用任何统计模型，使用均匀先验。"
            return red_prior, blue_prior, basis

        weights_arr = np.array(weights, dtype=np.float64)
        red_fused = np.average(red_probs_list, axis=0, weights=weights_arr)
        blue_fused = np.average(blue_probs_list, axis=0, weights=weights_arr)

        basis = "共识约束策略：统计先验融合（" + "；".join(basis_parts) + ")。"
        return red_fused, blue_fused, basis

    def _pool_to_probability(self, pool: List[int], size: int) -> np.ndarray:
        """将候选池转换为概率向量（池内等概率，池外为0）。"""
        probs = np.zeros(size, dtype=np.float64)
        if pool:
            for n in pool:
                if 1 <= n <= size:
                    probs[n - 1] = 1.0 / len(pool)
        else:
            probs = np.ones(size) / size
        return probs

    def _stats_prior(
        self, analyzer: DrawAnalyzer, options: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, str]:
        mode = options.get("stats_mode", "smart")
        lookback = int(options.get("stats_lookback", 100))
        all_reds = list(range(1, 34))

        if mode in ("hot", "cold", "mixed"):
            freq = analyzer.frequency("red", lookback)
            ranked = sorted(all_reds, key=lambda n: freq.get(n, 0), reverse=True)
            if mode == "hot":
                pool = ranked[:16]
            elif mode == "cold":
                pool = ranked[-16:]
            else:
                pool = ranked[:8] + ranked[-8:]
            blue_freq = analyzer.frequency("blue", lookback)
            blue_pool = sorted(range(1, 17), key=lambda n: blue_freq.get(n, 0), reverse=True)[:8]
            text = f"stats({mode}, {lookback})"
        elif mode == "missing":
            pool_size = int(options.get("stats_pool_size", 12))
            missing_red = dict(analyzer.missing("red", lookback))
            pool = sorted(all_reds, key=lambda n: missing_red.get(n, 0), reverse=True)[:pool_size]
            missing_blue = dict(analyzer.missing("blue", lookback))
            blue_pool = sorted(range(1, 17), key=lambda n: missing_blue.get(n, 0), reverse=True)[:8]
            text = f"stats(missing, {lookback}, pool={pool_size})"
        else:  # smart
            hot_w = int(options.get("stats_hot_weight", 60))
            cold_w = int(options.get("stats_cold_weight", 40))
            freq_red = analyzer.frequency("red", lookback)
            missing_red = dict(analyzer.missing("red", lookback))
            max_freq = max(freq_red.values()) if freq_red else 1
            max_miss = max(missing_red.values()) if missing_red else 1
            scores = {}
            for n in all_reds:
                f_score = freq_red.get(n, 0) / max_freq if max_freq else 0
                m_score = missing_red.get(n, 0) / max_miss if max_miss else 0
                scores[n] = hot_w * f_score + cold_w * m_score
            pool = sorted(all_reds, key=lambda n: scores[n], reverse=True)[:12]
            freq_blue = analyzer.frequency("blue", lookback)
            blue_pool = sorted(range(1, 17), key=lambda n: freq_blue.get(n, 0), reverse=True)[:8]
            text = f"stats(smart, {lookback}, hot={hot_w}, cold={cold_w})"

        return self._pool_to_probability(pool, 33), self._pool_to_probability(blue_pool, 16), text

    def _smart_hot_cold_prior(
        self, analyzer: DrawAnalyzer, options: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, str]:
        from ......data.analyzer import LotteryAnalyzer

        hot_w = int(options.get("smart_hot_cold_hot_weight", 60))
        cold_w = int(options.get("smart_hot_cold_cold_weight", 40))
        lookback = int(options.get("smart_hot_cold_lookback", 100))

        la = LotteryAnalyzer(analyzer.records)
        red_scores: Dict[int, float] = {n: 0.0 for n in range(1, 34)}
        freq = la.red_frequency(lookback)
        max_freq = max(freq.values()) if freq else 1
        for n, f in freq.items():
            red_scores[n] += hot_w * (f / max_freq)
        missing = dict(la.missing_reds(lookback))
        max_missing = max(missing.values()) if missing else 1
        for n, m in missing.items():
            red_scores[n] += cold_w * (m / max_missing)
        min_score = min(red_scores.values())
        red_weights = [max(0.1, red_scores[n] - min_score + 1.0) for n in range(1, 34)]
        red_probs = np.array(red_weights, dtype=np.float64)
        red_probs /= red_probs.sum()

        blue_scores: Dict[int, float] = {n: 0.0 for n in range(1, 17)}
        blue_freq = la.blue_frequency(lookback)
        max_blue_freq = max(blue_freq.values()) if blue_freq else 1
        for n, f in blue_freq.items():
            blue_scores[n] += hot_w * (f / max_blue_freq)
        blue_missing = dict(la.missing_blues(lookback))
        max_blue_missing = max(blue_missing.values()) if blue_missing else 1
        for n, m in blue_missing.items():
            blue_scores[n] += cold_w * (m / max_blue_missing)
        min_blue_score = min(blue_scores.values())
        blue_weights = [max(0.1, blue_scores[n] - min_blue_score + 1.0) for n in range(1, 17)]
        blue_probs = np.array(blue_weights, dtype=np.float64)
        blue_probs /= blue_probs.sum()

        text = f"smart_hot_cold({lookback}, hot={hot_w}, cold={cold_w})"
        return red_probs, blue_probs, text

    def _hot_cold_prior(
        self, analyzer: DrawAnalyzer, options: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, str]:
        mode = options.get("hot_cold_mode", "mixed")
        freq = analyzer.frequency("red", None)
        all_reds = list(range(1, 34))
        ranked = sorted(all_reds, key=lambda n: freq.get(n, 0), reverse=True)
        if mode == "hot":
            pool = ranked[:16]
        elif mode == "cold":
            pool = ranked[-16:]
        else:
            pool = ranked[:8] + ranked[-8:]
        blue_pool = sorted(range(1, 17), key=lambda n: freq.get(n, 0), reverse=True)[:8]
        text = f"hot_cold({mode})"
        return self._pool_to_probability(pool, 33), self._pool_to_probability(blue_pool, 16), text

    def _missing_number_prior(
        self, analyzer: DrawAnalyzer, options: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, str]:
        from ......data.analyzer import LotteryAnalyzer

        lookback = int(options.get("missing_number_lookback", 50))
        pool_size = int(options.get("missing_number_pool_size", 12))
        la = LotteryAnalyzer(analyzer.records)
        missing_reds = la.missing_reds(lookback)
        red_pool = [n for n, _ in missing_reds[:pool_size]]
        missing_blues = la.missing_blues(lookback)
        blue_pool = [n for n, _ in missing_blues[: min(8, pool_size // 2 + 2)]]
        text = f"missing_number({lookback}, pool={pool_size})"
        return self._pool_to_probability(red_pool, 33), self._pool_to_probability(blue_pool, 16), text

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        # TODO: implemented in later tasks
        return []
