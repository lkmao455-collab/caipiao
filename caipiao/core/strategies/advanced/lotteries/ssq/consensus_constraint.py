"""双色球共识约束策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ......data.analyzer import DrawAnalyzer
from ......data.models import DrawRecord
from .....profile import SSQ
from .....strategy import GenerationStrategy, StrategyMetadata
from .....ticket import Ticket
from caipiao.core.strategies.advanced.lotteries.ssq.bayesian import SSQBayesianStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.markov import SSQMarkovStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.trend import SSQTrendStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.periodic import SSQPeriodicStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.correlation import SSQCorrelationStrategy


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
            "red_pool_size": {
                "type": "int",
                "label": "红球号池大小",
                "default": SSQ.group("red").size,
                "min": 1,
                "max": 100,
                "tooltip": "红球号池大小，默认取自 SSQ 档案",
            },
            "blue_pool_size": {
                "type": "int",
                "label": "蓝球号池大小",
                "default": SSQ.group("blue").size,
                "min": 1,
                "max": 100,
                "tooltip": "蓝球号池大小，默认取自 SSQ 档案",
            },
            "red_pick_count": {
                "type": "int",
                "label": "红球选取个数",
                "default": SSQ.group("red").count,
                "min": 1,
                "max": 20,
                "tooltip": "每期选取的红球个数，默认取自 SSQ 档案",
            },
            "candidate_attempt_multiplier": {
                "type": "int",
                "label": "候选生成尝试倍数",
                "default": 20,
                "min": 1,
                "max": 1000,
                "tooltip": "候选生成最大尝试次数 = candidate_count * 该值",
            },
            "high_number_threshold": {
                "type": "int",
                "label": "大号分界阈值",
                "default": SSQ.group("red").high_low_border,
                "min": 1,
                "max": 33,
                "tooltip": "判定大号的分界值，默认取自 SSQ 档案",
            },
            "score_log_epsilon": {
                "type": "int",
                "label": "对数平滑指数（10 的幂）",
                "default": -12,
                "min": -15,
                "max": -6,
                "tooltip": "log 平滑 epsilon 的指数，默认 -12 即 1e-12",
            },
            "relaxation_sum_iterations": {
                "type": "int",
                "label": "和值放宽迭代次数",
                "default": 10,
                "min": 1,
                "max": 100,
                "tooltip": "和值范围自动放宽的最大迭代次数",
            },
            "relaxation_sum_floor": {
                "type": "int",
                "label": "和值放宽下限",
                "default": 21,
                "min": 0,
                "max": 183,
                "tooltip": "和值下限自动放宽的最低值",
            },
            "relaxation_sum_cap": {
                "type": "int",
                "label": "和值放宽上限",
                "default": 183,
                "min": 0,
                "max": 1000,
                "tooltip": "和值上限自动放宽的最高值",
            },
            "relaxation_sum_expand_min": {
                "type": "int",
                "label": "和值下限放宽比例（%）",
                "default": 90,
                "min": 50,
                "max": 100,
                "tooltip": "和值下限每次放宽的百分比（90 表示乘以 0.9）",
            },
            "relaxation_sum_expand_max": {
                "type": "int",
                "label": "和值上限放宽比例（%）",
                "default": 110,
                "min": 100,
                "max": 200,
                "tooltip": "和值上限每次放宽的百分比（110 表示乘以 1.1）",
            },
            "relaxation_odd_deltas": {
                "type": "list_int",
                "label": "奇偶放宽增量",
                "default": [1, 2, 3],
                "min": 0,
                "max": 6,
                "tooltip": "奇数个数冲突时依次尝试的偏移量",
            },
            "sample_top_pool_fraction": {
                "type": "int",
                "label": "高分池采样比例（%）",
                "default": 50,
                "min": 1,
                "max": 100,
                "tooltip": "确定性抽样时从高分段选取的池比例",
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

    def _generate_candidates(
        self,
        rng: random.Random,
        red_probs: np.ndarray,
        blue_probs: np.ndarray,
        options: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, ...], int]]:
        """阶段2：按概率生成候选组合。"""
        schema = self.get_config_schema()
        candidate_count = int(options.get("candidate_count", schema["candidate_count"]["default"]))
        red_size = int(options.get("red_pool_size", schema["red_pool_size"]["default"]))
        blue_size = int(options.get("blue_pool_size", schema["blue_pool_size"]["default"]))
        red_pick_count = int(options.get("red_pick_count", schema["red_pick_count"]["default"]))
        attempt_multiplier = int(
            options.get("candidate_attempt_multiplier", schema["candidate_attempt_multiplier"]["default"])
        )
        reds = list(range(1, red_size + 1))
        blues = list(range(1, blue_size + 1))

        blue_sampling_mode = options.get("blue_sampling_mode", "weighted")
        if blue_sampling_mode == "uniform":
            effective_blue_probs = None
        else:
            effective_blue_probs = blue_probs

        candidates: Set[Tuple[Tuple[int, ...], int]] = set()
        attempts = 0
        max_attempts = candidate_count * attempt_multiplier
        while len(candidates) < candidate_count and attempts < max_attempts:
            attempts += 1
            selected = tuple(sorted(rng.choices(reds, weights=red_probs, k=red_pick_count)))
            if len(set(selected)) < red_pick_count:
                continue
            blue = rng.choices(blues, weights=effective_blue_probs, k=1)[0]
            candidates.add((selected, blue))

        return sorted(candidates)

    def _apply_hard_constraints(
        self,
        candidates: List[Tuple[Tuple[int, ...], int]],
        records: List[DrawRecord],
        options: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, ...], int]]:
        """阶段3：硬约束过滤。"""
        schema = self.get_config_schema()
        result = candidates

        if options.get("odd_even_enabled", True):
            odd_count = int(options.get("odd_count", schema["odd_count"]["default"]))
            result = [
                (reds, blue)
                for reds, blue in result
                if sum(1 for n in reds if n % 2 == 1) == odd_count
            ]

        if options.get("balanced_enabled", True) and result:
            sum_min = int(options.get("sum_min", schema["sum_min"]["default"]))
            sum_max = int(options.get("sum_max", schema["sum_max"]["default"]))
            target_high = int(options.get("target_high", schema["target_high"]["default"]))
            high_threshold = int(
                options.get("high_number_threshold", schema["high_number_threshold"]["default"])
            )
            # 奇数个数约束：若已启用 odd_even，则不再用 target_odd 重复过滤。
            if options.get("odd_even_enabled", True):
                result = [
                    (reds, blue)
                    for reds, blue in result
                    if sum_min <= sum(reds) <= sum_max
                    and abs(sum(1 for n in reds if n >= high_threshold) - target_high) <= 0
                ]
            else:
                target_odd = int(options.get("target_odd", schema["target_odd"]["default"]))
                result = [
                    (reds, blue)
                    for reds, blue in result
                    if sum_min <= sum(reds) <= sum_max
                    and abs(sum(1 for n in reds if n % 2 == 1) - target_odd) <= 0
                    and abs(sum(1 for n in reds if n >= high_threshold) - target_high) <= 0
                ]

        if options.get("exclude_include_enabled", False) and result:
            include_red: Set[int] = set(options.get("include_red", []))
            exclude_red: Set[int] = set(options.get("exclude_red", []))
            exclude_blue: Set[int] = set(options.get("exclude_blue", []))
            result = [
                (reds, blue)
                for reds, blue in result
                if include_red <= set(reds)
                and not (set(reds) & exclude_red)
                and blue not in exclude_blue
            ]

        return result

    def _score_candidates(
        self,
        candidates: List[Tuple[Tuple[int, ...], int]],
        records: List[DrawRecord],
        options: Dict[str, Any],
    ) -> List[Tuple[float, Tuple[int, ...], int]]:
        """阶段4：概率精排，返回（得分，红球，蓝球）列表。"""
        models: List[Tuple[str, np.ndarray, int]] = []

        if options.get("bayesian_enabled", True):
            prob = self._bayesian_probability(records, options)
            weight = int(options.get("bayesian_weight", 25))
            models.append(("bayesian", prob, weight))

        if options.get("markov_enabled", True):
            prob = self._markov_probability(records, options)
            weight = int(options.get("markov_weight", 20))
            models.append(("markov", prob, weight))

        if options.get("trend_enabled", True):
            prob = self._trend_probability(records, options)
            weight = int(options.get("trend_model_weight", 20))
            models.append(("trend", prob, weight))

        if options.get("periodic_enabled", True):
            prob = self._periodic_probability(records, options)
            weight = int(options.get("periodic_weight", 20))
            models.append(("periodic", prob, weight))

        if options.get("correlation_enabled", True):
            prob = self._correlation_probability(records, options)
            weight = int(options.get("correlation_model_weight", 15))
            models.append(("correlation", prob, weight))

        if not models:
            return [(0.0, reds, blue) for reds, blue in candidates]

        total_weight = sum(w for _, _, w in models)
        if total_weight == 0:
            return [(0.0, reds, blue) for reds, blue in candidates]
        weights = np.array([w for _, _, w in models], dtype=np.float64)

        schema = self.get_config_schema()
        red_pick_count = int(options.get("red_pick_count", schema["red_pick_count"]["default"]))
        epsilon = 10.0 ** int(options.get("score_log_epsilon", schema["score_log_epsilon"]["default"]))

        scored: List[Tuple[float, Tuple[int, ...], int]] = []
        for reds, blue in candidates:
            score = 0.0
            for idx, (_, prob, _) in enumerate(models):
                red_indices = np.array(reds, dtype=np.int64) - 1
                log_sum = float(np.log(np.maximum(prob[red_indices], epsilon)).sum())
                score += (log_sum / red_pick_count) * (weights[idx] / total_weight)
            scored.append((score, reds, blue))

        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        return scored

    def _model_probability(
        self,
        model_class: type,
        records: List[DrawRecord],
        options: Dict[str, Any],
        option_prefix: str,
    ) -> np.ndarray:
        """复用现有高级策略的概率计算逻辑，但完全隔离实例。"""
        model = model_class()
        model_options: Dict[str, Any] = {"history": records}
        schema = model.get_config_schema()
        prefix = option_prefix + "_"
        for key, value in options.items():
            if key.startswith(prefix):
                stripped = key[len(prefix):]
                if stripped in schema:
                    model_options[stripped] = value
                elif key in schema:
                    model_options[key] = value
        proba, _ = model._compute_probabilities(records, model_options)
        return proba

    def _bayesian_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQBayesianStrategy, records, options, "bayesian")

    def _markov_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQMarkovStrategy, records, options, "markov")

    def _trend_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQTrendStrategy, records, options, "trend")

    def _periodic_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        if not records:
            raise ValueError("周期分析需要历史数据")
        return self._model_probability(SSQPeriodicStrategy, records, options, "periodic")

    def _correlation_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQCorrelationStrategy, records, options, "correlation")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = dict(options or {})
        self.validate_options(options)
        records = self._records_from_options(options)
        seed = int(options.get("seed", 42))
        rng = random.Random(seed)

        red_probs, blue_probs, basis_prior = self._compute_statistical_prior(records, options)
        candidates = self._generate_candidates(rng, red_probs, blue_probs, options)
        filtered, relaxed_parts = self._apply_hard_constraints_with_relaxation(
            candidates, records, options
        )
        scored = self._score_candidates(filtered, records, options)
        final = self._sample_deterministically(rng, scored, count, options)

        basis = basis_prior
        if relaxed_parts:
            basis += " 约束冲突，已自动放宽：" + "；".join(relaxed_parts) + "。"
        basis += f" 随机种子：{seed}。"

        return [
            Ticket(
                profile=SSQ,
                groups={"red": list(reds), "blue": [blue]},
                strategy_name=self.metadata.name,
                basis=basis,
            )
            for reds, blue in final
        ]

    def _records_from_options(self, options: Dict[str, Any]) -> List[DrawRecord]:
        from ....common.records import records_from_options
        return records_from_options(options)

    def _apply_hard_constraints_with_relaxation(
        self,
        candidates: List[Tuple[Tuple[int, ...], int]],
        records: List[DrawRecord],
        options: Dict[str, Any],
    ) -> Tuple[List[Tuple[Tuple[int, ...], int]], List[str]]:
        """阶段3+5：硬约束过滤，若为空则自动放宽。"""
        schema = self.get_config_schema()
        if options.get("relaxation_order", "reverse") == "strict":
            return self._apply_hard_constraints(candidates, records, options), []

        working_options = dict(options)
        relaxed: List[str] = []

        result = self._apply_hard_constraints(candidates, records, working_options)
        if result:
            return result, relaxed

        # 放宽 balanced 和值范围
        if working_options.get("balanced_enabled", True):
            sum_iterations = int(
                options.get("relaxation_sum_iterations", schema["relaxation_sum_iterations"]["default"])
            )
            sum_floor = int(options.get("relaxation_sum_floor", schema["relaxation_sum_floor"]["default"]))
            sum_cap = int(options.get("relaxation_sum_cap", schema["relaxation_sum_cap"]["default"]))
            expand_min = int(
                options.get("relaxation_sum_expand_min", schema["relaxation_sum_expand_min"]["default"])
            )
            expand_max = int(
                options.get("relaxation_sum_expand_max", schema["relaxation_sum_expand_max"]["default"])
            )
            for _ in range(sum_iterations):
                sum_min = int(working_options.get("sum_min", schema["sum_min"]["default"]))
                sum_max = int(working_options.get("sum_max", schema["sum_max"]["default"]))
                new_min = max(sum_floor, int(sum_min * expand_min / 100.0))
                new_max = min(sum_cap, int(sum_max * expand_max / 100.0))
                if new_min == sum_min and new_max == sum_max:
                    break
                working_options["sum_min"] = new_min
                working_options["sum_max"] = new_max
                result = self._apply_hard_constraints(candidates, records, working_options)
                if result:
                    relaxed.append(f"放宽和值范围至 {new_min}-{new_max}")
                    return result, relaxed

        # 放宽 odd_even
        if working_options.get("odd_even_enabled", True):
            odd_count = int(working_options.get("odd_count", schema["odd_count"]["default"]))
            odd_deltas = list(
                options.get("relaxation_odd_deltas", schema["relaxation_odd_deltas"]["default"])
            )
            for delta in odd_deltas:
                for target in {max(0, odd_count - delta), min(6, odd_count + delta)}:
                    working_options["odd_count"] = target
                    result = self._apply_hard_constraints(candidates, records, working_options)
                    if result:
                        relaxed.append(f"放宽奇数个数至 {target}")
                        return result, relaxed

        # 放宽 exclude_include：减少排除
        if working_options.get("exclude_include_enabled", False):
            excludes = list(working_options.get("exclude_red", []))
            while excludes:
                excludes.pop()
                working_options["exclude_red"] = excludes
                result = self._apply_hard_constraints(candidates, records, working_options)
                if result:
                    relaxed.append("减少排除红球")
                    return result, relaxed

        # 最后防线：关闭所有硬约束
        if not result:
            working_options["odd_even_enabled"] = False
            working_options["balanced_enabled"] = False
            working_options["exclude_include_enabled"] = False
            result = self._apply_hard_constraints(candidates, records, working_options)
            if result:
                relaxed.append("关闭所有硬约束")
                return result, relaxed

        raise ValueError("无法生成任何候选组合，请检查参数设置")

    def _sample_deterministically(
        self,
        rng: random.Random,
        scored: List[Tuple[float, Tuple[int, ...], int]],
        count: int,
        options: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, ...], int]]:
        """阶段6：确定性抽样。"""
        if not scored:
            raise ValueError("没有可用候选组合")
        schema = self.get_config_schema()
        top_fraction = int(
            options.get("sample_top_pool_fraction", schema["sample_top_pool_fraction"]["default"])
        )
        # 取前 top_fraction% 作为高质量池，再随机抽样增加多样性
        top_n = max(count, int(len(scored) * top_fraction / 100))
        pool = scored[:top_n]
        if len(pool) <= count:
            return [(reds, blue) for _, reds, blue in pool]
        selected_indices = sorted(rng.sample(range(len(pool)), count))
        return [(pool[i][1], pool[i][2]) for i in selected_indices]
