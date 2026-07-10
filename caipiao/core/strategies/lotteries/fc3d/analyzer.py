"""福彩3D三策略统一分析框架.

支持同时运行历史均衡、智能冷热号、遗漏号追踪三种策略，
并生成对比分析报告。
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .....data.models import DrawRecord
from .balanced import FC3DBalancedStrategy
from .missing_number import FC3DMissingNumberStrategy
from .smart_hot_cold import FC3DSmartHotColdStrategy
from .stability import chi_square_uniform_test
from .utils import (
    DIGIT_POOL,
    fc3d_bet_type,
    overall_high_low_ratio,
    overall_odd_even_ratio,
    positional_frequency,
    span_statistics,
    sum_statistics,
)


@dataclass
class StrategyResult:
    """单个策略的运行结果."""
    strategy_name: str
    tickets: List[Dict[str, Any]]
    basis: str
    details: Dict[str, Any]
    execution_time: float = 0.0


@dataclass
class ComparisonReport:
    """策略对比报告."""
    history_size: int
    lookback: int
    chi_square: List[float]
    is_uniform: List[bool]
    strategy_results: Dict[str, StrategyResult]
    comparison_metrics: Dict[str, Any]
    recommendation: str


class FC3DAnalyzer:
    """福彩3D三策略统一分析框架."""

    def __init__(self, records: List[DrawRecord], lookback: int = 100):
        """
        初始化分析器.

        Args:
            records: 历史开奖记录
            lookback: 统计期数
        """
        self.records = records
        self.lookback = lookback
        self.strategies = {
            "balanced": FC3DBalancedStrategy(),
            "smart_hot_cold": FC3DSmartHotColdStrategy(),
            "missing_number": FC3DMissingNumberStrategy(),
        }
        self._chi_square: Optional[List[float]] = None
        self._is_uniform: Optional[List[bool]] = None

    def _run_chi_square_test(self) -> Tuple[List[float], List[bool]]:
        """运行χ²均匀性检验."""
        if self._chi_square is not None:
            return self._chi_square, self._is_uniform

        pos_freq = positional_frequency(self.records, self.lookback)
        chi2_values = []
        uniform_flags = []

        for pos in range(3):
            counts = [pos_freq[pos].get(d, 0) for d in range(10)]
            chi2, is_uniform = chi_square_uniform_test(counts)
            chi2_values.append(round(chi2, 2))
            uniform_flags.append(is_uniform)

        self._chi_square = chi2_values
        self._is_uniform = uniform_flags
        return chi2_values, uniform_flags

    def run_strategy(
        self,
        strategy_name: str,
        count: int = 5,
        options: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        """
        运行单个策略.

        Args:
            strategy_name: 策略名称 (balanced/smart_hot_cold/missing_number)
            count: 生成号码数量
            options: 策略参数

        Returns:
            策略运行结果
        """
        import time
        start_time = time.time()

        if strategy_name not in self.strategies:
            raise ValueError(f"未知策略: {strategy_name}")

        strategy = self.strategies[strategy_name]
        default_options = {"history": self.records, "lookback": self.lookback}
        if options:
            default_options.update(options)

        tickets = strategy.generate(count=count, options=default_options)
        
        execution_time = time.time() - start_time

        # 提取ticket信息
        ticket_dicts = []
        for ticket in tickets:
            ticket_dicts.append({
                "numbers": ticket.groups.get("pos", []),
                "basis": ticket.basis,
                "details": ticket.details,
            })

        return StrategyResult(
            strategy_name=strategy_name,
            tickets=ticket_dicts,
            basis=tickets[0].basis if tickets else "",
            details=tickets[0].details if tickets else {},
            execution_time=execution_time,
        )

    def run_all_strategies(
        self,
        count: int = 5,
        options: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, StrategyResult]:
        """
        运行所有策略.

        Args:
            count: 每个策略生成号码数量
            options: 各策略的参数 {"balanced": {...}, "smart_hot_cold": {...}, ...}

        Returns:
            各策略运行结果
        """
        results = {}
        options = options or {}

        for name in self.strategies:
            strategy_options = options.get(name, {})
            results[name] = self.run_strategy(name, count, strategy_options)

        return results

    def _analyze_numbers(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析生成的号码特征."""
        all_numbers = []
        for ticket in tickets:
            all_numbers.extend(ticket["numbers"])

        digit_counts = Counter(all_numbers)
        total = len(all_numbers)

        # 计算频率分布
        freq_dist = {d: digit_counts.get(d, 0) / total for d in range(10)}

        # 计算奇偶比
        odd_count = sum(1 for n in all_numbers if n % 2 == 1)
        odd_ratio = odd_count / total if total > 0 else 0.5

        # 计算大小比
        high_count = sum(1 for n in all_numbers if n >= 5)
        high_ratio = high_count / total if total > 0 else 0.5

        # 计算和值统计
        sums = [sum(ticket["numbers"]) for ticket in tickets]
        avg_sum = statistics.mean(sums) if sums else 0

        # 计算跨度统计
        spans = [max(ticket["numbers"]) - min(ticket["numbers"]) for ticket in tickets]
        avg_span = statistics.mean(spans) if spans else 0

        # 计算形态分布
        shape_counts = Counter()
        for ticket in tickets:
            shape = fc3d_bet_type(ticket["numbers"])
            shape_counts[shape] += 1
        shape_dist = {k: v / len(tickets) for k, v in shape_counts.items()} if tickets else {}

        # 计算频率熵（均匀性指标）
        probs = [freq_dist[d] for d in range(10)]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(10)
        uniformity = entropy / max_entropy if max_entropy > 0 else 0

        return {
            "digit_frequency": freq_dist,
            "odd_ratio": round(odd_ratio, 3),
            "high_ratio": round(high_ratio, 3),
            "avg_sum": round(avg_sum, 2),
            "avg_span": round(avg_span, 2),
            "shape_distribution": shape_dist,
            "entropy": round(entropy, 3),
            "uniformity": round(uniformity, 3),
        }

    def _calculate_distance(
        self, metrics1: Dict[str, Any], metrics2: Dict[str, Any]
    ) -> float:
        """计算两个策略结果之间的距离（相似度）."""
        # 频率分布的欧氏距离
        freq1 = [metrics1["digit_frequency"].get(d, 0) for d in range(10)]
        freq2 = [metrics2["digit_frequency"].get(d, 0) for d in range(10)]
        freq_distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(freq1, freq2)))

        # 其他指标的距离
        odd_distance = abs(metrics1["odd_ratio"] - metrics2["odd_ratio"])
        high_distance = abs(metrics1["high_ratio"] - metrics2["high_ratio"])
        sum_distance = abs(metrics1["avg_sum"] - metrics2["avg_sum"]) / 27.0
        span_distance = abs(metrics1["avg_span"] - metrics2["avg_span"]) / 9.0

        # 综合距离
        return (
            freq_distance
            + odd_distance
            + high_distance
            + sum_distance
            + span_distance
        )

    def compare_strategies(
        self, results: Dict[str, StrategyResult]
    ) -> Dict[str, Any]:
        """
        对比分析各策略结果.

        Args:
            results: 各策略运行结果

        Returns:
            对比分析结果
        """
        # 分析各策略的号码特征
        strategy_metrics = {}
        for name, result in results.items():
            strategy_metrics[name] = self._analyze_numbers(result.tickets)

        # 计算策略间的距离矩阵
        strategy_names = list(results.keys())
        distance_matrix = {}
        for i, name1 in enumerate(strategy_names):
            for j, name2 in enumerate(strategy_names):
                if i != j:
                    distance = self._calculate_distance(
                        strategy_metrics[name1], strategy_metrics[name2]
                    )
                    distance_matrix[(name1, name2)] = round(distance, 4)

        # 计算各策略的综合得分
        scores = {}
        for name, metrics in strategy_metrics.items():
            # 均匀性得分（越高越好）
            uniformity_score = metrics["uniformity"]

            # 奇偶平衡得分（越接近0.5越好）
            odd_balance = 1 - abs(metrics["odd_ratio"] - 0.5) * 2

            # 大小平衡得分（越接近0.5越好）
            high_balance = 1 - abs(metrics["high_ratio"] - 0.5) * 2

            # 综合得分
            scores[name] = round(
                (uniformity_score + odd_balance + high_balance) / 3, 3
            )

        # 找出最佳策略
        best_strategy = max(scores, key=scores.get)

        return {
            "strategy_metrics": strategy_metrics,
            "distance_matrix": distance_matrix,
            "scores": scores,
            "best_strategy": best_strategy,
        }

    def generate_comparison_report(
        self,
        count: int = 5,
        options: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ComparisonReport:
        """
        生成完整的对比分析报告.

        Args:
            count: 每个策略生成号码数量
            options: 各策略的参数

        Returns:
            完整的对比分析报告
        """
        # 运行所有策略
        results = self.run_all_strategies(count, options)

        # 运行χ²检验
        chi2_values, uniform_flags = self._run_chi_square_test()

        # 对比分析
        comparison = self.compare_strategies(results)

        # 生成推荐建议
        recommendation = self._generate_recommendation(
            chi2_values, uniform_flags, comparison
        )

        return ComparisonReport(
            history_size=len(self.records),
            lookback=self.lookback,
            chi_square=chi2_values,
            is_uniform=uniform_flags,
            strategy_results=results,
            comparison_metrics=comparison,
            recommendation=recommendation,
        )

    def _generate_recommendation(
        self,
        chi2_values: List[float],
        uniform_flags: List[bool],
        comparison: Dict[str, Any],
    ) -> str:
        """生成推荐建议."""
        all_uniform = all(uniform_flags)
        best_strategy = comparison["best_strategy"]
        scores = comparison["scores"]

        lines = []

        # 数据状态分析
        if all_uniform:
            lines.append("📊 数据状态：各位置接近均匀分布，历史统计信号较弱。")
        else:
            deviating = [p + 1 for p, u in enumerate(uniform_flags) if not u]
            lines.append(f"📊 数据状态：第{deviating}位显著偏离均匀分布，历史统计有效。")

        # 策略评分
        lines.append("\n📈 策略评分：")
        for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            strategy_names = {
                "balanced": "历史均衡",
                "smart_hot_cold": "智能冷热号",
                "missing_number": "遗漏号追踪",
            }
            lines.append(f"  • {strategy_names[name]}: {score:.3f}")

        # 最佳策略
        strategy_names = {
            "balanced": "历史均衡",
            "smart_hot_cold": "智能冷热号",
            "missing_number": "遗漏号追踪",
        }
        lines.append(f"\n🏆 推荐策略：{strategy_names[best_strategy]}")

        # 使用建议
        lines.append("\n💡 使用建议：")
        if all_uniform:
            lines.append("  • 数据接近均匀分布，所有策略效果相近")
            lines.append("  • 建议使用智能冷热号（均衡参数）或直接随机选号")
        else:
            if best_strategy == "balanced":
                lines.append("  • 历史均衡策略表现最佳，适合多维度分析")
                lines.append("  • 建议使用枚举模式获得确定性结果")
            elif best_strategy == "smart_hot_cold":
                lines.append("  • 智能冷热号策略表现最佳，适合综合热冷分析")
                lines.append("  • 建议调整热权重/冷权重以匹配个人偏好")
            else:
                lines.append("  • 遗漏号追踪策略表现最佳，适合追冷号")
                lines.append("  • 建议关注z>1.96的显著偏冷号码")

        return "\n".join(lines)


def format_report(report: ComparisonReport) -> str:
    """格式化对比报告为可读文本."""
    strategy_names = {
        "balanced": "历史均衡",
        "smart_hot_cold": "智能冷热号",
        "missing_number": "遗漏号追踪",
    }

    lines = []
    lines.append("=" * 80)
    lines.append("福彩3D三策略对比分析报告")
    lines.append("=" * 80)

    # 基本信息
    lines.append(f"\n📋 基本信息：")
    lines.append(f"  • 历史数据量：{report.history_size} 期")
    lines.append(f"  • 统计期数：{report.lookback} 期")

    # χ²检验结果
    lines.append(f"\n📊 χ²均匀性检验：")
    for pos in range(3):
        uniform_text = "均匀" if report.is_uniform[pos] else "不均匀"
        lines.append(
            f"  • 第{pos+1}位：χ²={report.chi_square[pos]}, {uniform_text}"
        )

    # 各策略结果
    lines.append(f"\n🎲 各策略生成号码：")
    for name, result in report.strategy_results.items():
        lines.append(f"\n  【{strategy_names[name]}】")
        for i, ticket in enumerate(result.tickets[:3], 1):
            nums = ticket["numbers"]
            lines.append(f"    第{i}组: {nums[0]} {nums[1]} {nums[2]}")

    # 对比分析
    comparison = report.comparison_metrics
    lines.append(f"\n📈 策略评分：")
    for name, score in sorted(
        comparison["scores"].items(), key=lambda x: x[1], reverse=True
    ):
        lines.append(f"  • {strategy_names[name]}: {score:.3f}")

    # 策略间距离
    lines.append(f"\n📏 策略间差异度：")
    for (name1, name2), distance in comparison["distance_matrix"].items():
        if name1 < name2:  # 避免重复
            lines.append(
                f"  • {strategy_names[name1]} vs {strategy_names[name2]}: {distance:.4f}"
            )

    # 推荐建议
    lines.append(f"\n{'=' * 80}")
    lines.append(report.recommendation)
    lines.append("=" * 80)

    return "\n".join(lines)
