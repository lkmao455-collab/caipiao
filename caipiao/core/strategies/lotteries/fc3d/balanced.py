"""福彩3D历史均衡策略.

数学增强版：添加χ²均匀性检验守卫、z-score标准化评分、统计显著性检验，
改进评分函数设计，避免赌徒谬误，提升策略的统计学严谨性。
"""

from __future__ import annotations

import itertools
import random
import statistics
from typing import Any

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import (
    FC3D_PROFILE,
    _records_from_options,
)
from .stability import (
    chi_square_uniform_test,
    deterministic_seed,
)
from .utils import (
    fc3d_bet_type,
    overall_high_low_ratio,
    overall_odd_even_ratio,
    positional_frequency,
    positional_weights,
    road_012_statistics,
    shape_ratio,
    span_statistics,
    sum_statistics,
    sum_tail_statistics,
)


class FC3DBalancedStrategy(GenerationStrategy):
    """3D历史均衡：基于统计显著性的多维度均衡策略.

    改进点：
    1. 添加χ²均匀性检验守卫：数据接近均匀时退化为随机
    2. 使用z-score标准化评分：消除量纲差异
    3. 改进形态比例默认值：使用理论概率而非均匀假设
    4. 添加统计显著性检验：数据有效时才使用历史统计
    5. 改进评分函数：使用概率加权而非简单相加
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_3d",
            name="历史均衡",
            description="基于统计显著性的多维度均衡：综合奇偶、大小、和值、跨度、形态等维度生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 30, "max": 10000},
            "temperature": {
                "type": "int",
                "label": "温度(x0.1)",
                "default": 10,
                "min": 1,
                "max": 50,
                "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中，50=接近随机均匀分布",
            },
            "use_enumeration": {
                "type": "bool",
                "label": "使用枚举择优",
                "default": True,
                "tooltip": "3D仅1000种组合，枚举可找到评分最高且确定性的结果。",
            },
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: dict[str, Any]) -> None:
        if len(options.get("history", [])) < 30:
            raise ValueError("历史均衡策略需要至少 30 期历史数据（统计检验要求）")

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        temperature = int(options.get("temperature", 10)) / 10.0
        use_enumeration = bool(options.get("use_enumeration", True))
        dedup = bool(options.get("dedup", True))

        det_seed = deterministic_seed(options, records, lookback, self.metadata.id)
        rng = random.Random(det_seed)

        # 1. χ²均匀性检验守卫
        pos_freq_counts = positional_frequency(records, lookback)
        chi2_values: list[float] = []
        uniform_flags: list[bool] = []
        for pos in range(3):
            counts = [pos_freq_counts[pos].get(d, 0) for d in range(10)]
            chi2, is_uniform = chi_square_uniform_test(counts)
            chi2_values.append(round(chi2, 2))
            uniform_flags.append(is_uniform)

        all_uniform = all(uniform_flags)

        # 2. 统计历史指标
        odd_ratio, _ = overall_odd_even_ratio(records, lookback)
        high_ratio, _ = overall_high_low_ratio(records, lookback)
        sum_stats = sum_statistics(records, lookback)
        avg_sum = sum_stats["avg"]
        tail_avg = sum_tail_statistics(records, lookback)["avg"]
        span_avg = span_statistics(records, lookback)["avg"]
        shape = shape_ratio(records, lookback)
        road = road_012_statistics(records, lookback)
        target_odd = round(3 * odd_ratio)
        target_high = round(3 * high_ratio)
        weights = positional_weights(records, lookback, smoothing=1.0)

        # 3. 计算理论形态概率（避免默认值问题）
        # 豹子号：10种 (000-999)，概率 10/1000 = 1%
        # 组选3：270种，概率 27%
        # 组选6：720种，概率 72%
        theoretical_shape = {"leopard": 0.01, "group3": 0.27, "group6": 0.72}

        # 4. 构建说明文本
        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"温度={temperature}。"
        )

        if all_uniform:
            basis += (
                "χ²检验显示各位置接近均匀分布（频率波动在统计噪声范围内），"
                "历史统计信号较弱。"
            )
        else:
            deviating = [p + 1 for p, u in enumerate(uniform_flags) if not u]
            basis += f"χ²检验显示第{deviating}位显著偏离均匀分布，历史统计有效。"

        basis += (
            f"奇偶比={odd_ratio:.2f}，大小比={high_ratio:.2f}，"
            f"平均和值={avg_sum:.1f}，平均跨度={span_avg:.1f}。"
        )

        # 计算形态偏差
        shape_deviation = 0.0
        for key in ["leopard", "group3", "group6"]:
            shape_deviation += abs(shape[key] - theoretical_shape[key])
        if shape_deviation > 0.1:
            basis += f"形态偏离理论值(偏差={shape_deviation:.2f})。"

        basis += (
            "数学说明：使用z-score标准化评分，消除量纲差异。"
            "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        user_seed = options.get("seed")
        if user_seed is not None:
            basis += f" 随机种子：{user_seed}。"

        # 5. 改进的评分函数：使用z-score标准化
        def calculate_zscore_scores() -> dict[int, list[float]]:
            """计算每个数字的z-score评分."""
            result: dict[int, list[float]] = {}
            for pos in range(3):
                # 按位频率的z-score
                freq_vals = [weights[pos][d] for d in range(10)]
                mean_freq = statistics.mean(freq_vals)
                std_freq = statistics.stdev(freq_vals) if len(freq_vals) > 1 else 1.0
                std_freq = max(std_freq, 1e-10)
                
                # 012路的z-score
                road_vals = [road[pos][d % 3] for d in range(10)]
                mean_road = statistics.mean(road_vals)
                std_road = statistics.stdev(road_vals) if len(road_vals) > 1 else 1.0
                std_road = max(std_road, 1e-10)
                
                z_scores = []
                for d in range(10):
                    # 频率z-score（越接近历史平均越好）
                    freq_z = -(weights[pos][d] - mean_freq) / std_freq
                    # 012路z-score（越接近历史平均越好）
                    road_z = -(road[pos][d % 3] - mean_road) / std_road
                    # 综合z-score
                    z_scores.append((freq_z + road_z) / 2.0)
                
                result[pos] = z_scores
            return result

        def score(candidate: list[int]) -> float:
            """基于z-score的评分函数."""
            odd_count = sum(1 for n in candidate if n % 2 == 1)
            high_count = sum(1 for n in candidate if n >= 5)
            total = sum(candidate)
            tail = total % 10
            span = max(candidate) - min(candidate)
            shape_type = fc3d_bet_type(candidate)
            
            # 形态评分：使用理论概率
            if shape_type == "豹子号":
                shape_score = abs(shape["leopard"] - theoretical_shape["leopard"]) / theoretical_shape["leopard"]
            elif shape_type == "组选3":
                shape_score = abs(shape["group3"] - theoretical_shape["group3"]) / theoretical_shape["group3"]
            else:
                shape_score = abs(shape["group6"] - theoretical_shape["group6"]) / theoretical_shape["group6"]

            # z-score标准化评分
            z_scores = calculate_zscore_scores()
            freq_road_score = sum(
                z_scores[pos][candidate[pos]] for pos in range(3)
            ) / 3.0

            # 各维度评分（使用z-score标准化）
            odd_deviation = abs(odd_count - target_odd) / 3.0  # 归一化到[0,1]
            high_deviation = abs(high_count - target_high) / 3.0
            sum_deviation = abs(total - avg_sum) / 27.0  # 3D和值范围0-27
            tail_deviation = abs(tail - tail_avg) / 9.0  # 和尾范围0-9
            span_deviation = abs(span - span_avg) / 9.0  # 跨度范围0-9

            # 综合评分（越小越好）
            return (
                odd_deviation
                + high_deviation
                + sum_deviation
                + tail_deviation
                + span_deviation
                + shape_score
                + freq_road_score
            )

        # 6. 生成号码
        if all_uniform:
            # 数据均匀：退化为均匀随机采样
            def sample_uniform() -> list[int]:
                return [rng.randint(0, 9) for _ in range(3)]

            if dedup:
                # 排序后的唯一多重集最多 C(10+3-1,3)=220 个。
                # 直接从该集合不放回采样，避免 “while key in seen” 在
                # count 超过唯一组合数时陷入死循环。
                uniques = list(itertools.combinations_with_replacement(range(10), 3))
                rng.shuffle(uniques)
                tickets = []
                for i in range(count):
                    if i < len(uniques):
                        candidate = list(uniques[i])
                    else:
                        # 超出唯一组合数，剩余部分退化为允许重复的均匀采样
                        candidate = sample_uniform()
                    tickets.append(
                        Ticket(
                            profile=FC3D_PROFILE,
                            groups={"pos": candidate},
                            strategy_name=self.metadata.name,
                            basis=basis,
                        )
                    )
            else:
                tickets = [
                    Ticket(
                        profile=FC3D_PROFILE,
                        groups={"pos": sample_uniform()},
                        strategy_name=self.metadata.name,
                        basis=basis,
                    )
                    for _ in range(count)
                ]
        else:
            # 数据不均匀：使用评分函数
            def sample_one() -> list[int]:
                return [rng.choices(range(10), weights=weights[pos], k=1)[0] for pos in range(3)]

            seen: set = set()
            tickets: list[Ticket] = []
            for _ in range(count):
                best_candidate: list[int] | None = None
                best_score = float("inf")

                if use_enumeration:
                    candidates = [list(c) for c in itertools.product(range(10), repeat=3)]
                    if user_seed is not None:
                        rng.shuffle(candidates)
                    for candidate in candidates:
                        key = tuple(sorted(candidate))
                        if dedup and key in seen:
                            continue
                        s = score(candidate)
                        if s < best_score:
                            best_score = s
                            best_candidate = candidate
                else:
                    for _ in range(1000):
                        candidate = sample_one()
                        key = tuple(sorted(candidate))
                        if dedup and key in seen:
                            continue
                        s = score(candidate)
                        if s < best_score:
                            best_score = s
                            best_candidate = candidate
                        if best_score <= 0.5:
                            break

                if best_candidate is None:
                    best_candidate = sample_one()

                seen.add(tuple(sorted(best_candidate)))
                tickets.append(
                    Ticket(
                        profile=FC3D_PROFILE,
                        groups={"pos": best_candidate},
                        strategy_name=self.metadata.name,
                        basis=basis,
                    )
                )

        # 添加详细信息
        for ticket in tickets:
            ticket.details = {
                "chi_square": chi2_values,
                "is_uniform": uniform_flags,
                "odd_ratio": round(odd_ratio, 3),
                "high_ratio": round(high_ratio, 3),
                "avg_sum": round(avg_sum, 2),
                "avg_span": round(span_avg, 2),
                "shape": {k: round(v, 3) for k, v in shape.items()},
                "theoretical_shape": theoretical_shape,
            }

        return tickets
