"""福彩3D三策略融合策略.

综合历史均衡、智能冷热号、遗漏号追踪三个策略的优点，
通过概率融合生成更稳健的号码。

注意（命名消歧）：
    本模块的 ``FC3DEnsembleStrategy``（id=``ensemble_v2_3d``，name="三策略融合"）
    是真实可用的概率融合策略，由 ``lotteries/fc3d/__init__.py`` 导出。
    另有一个同名的 ML 占位类位于
    ``advanced/lotteries/fc3d/ensemble.py``（id=``ensemble_3d``，generate 抛异常），
    两者通过 registry 的模块别名（``fc3d_ensemble_v2`` vs ``fc3d_ensemble``）区分。
    为避免混淆，本模块同时导出语义更清晰的别名 ``FC3DStrategyFusionStrategy``。

集成方式：
1. 概率融合：将三个策略的 per-position 概率分布加权平均
2. 逐位自适应权重：根据每个位置自身的 χ² 状态动态调整各策略权重
3. 统计检验守卫：χ²检验 + 几何分布 z-score 双重验证
4. 遗漏弃权重：遗漏子策略在某位无显著冷号时，其权重重新分配给其它策略，
   避免纯均匀分布被动稀释有效信号
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import (
    FC3D_PROFILE,
    _make_rng,
    _records_from_options,
    _weighted_sample_without_replacement,
)
from .stability import (
    chi_square_uniform_test,
    geometric_missing_zscore,
    raw_missing_periods,
    sample_weighted,
    softmax_scores,
    stable_frequency,
    stable_scores,
)
from .utils import (
    DIGIT_POOL,
    positional_frequency,
    positional_weights,
    road_012_statistics,
    shape_ratio,
)

# 去重模式下 3D 组选组合上限：组六 120 + 组三 90 + 豹子 10
FC3D_GROUP_COMBINATIONS = 220


class FC3DStrategyFusionStrategy(GenerationStrategy):
    """3D集成策略：综合三个策略的概率分布生成号码.

    改进点：
    1. 概率融合：将三个策略的 per-position 概率分布加权平均
    2. 逐位自适应权重：根据每个位置自身的 χ² 状态调整各策略权重，
       并以用户配置的 base_weights 为基准做乘性调整
    3. 统计检验守卫：χ²检验 + 几何分布 z-score 双重验证
    4. 遗漏弃权重：遗漏子策略无显著冷号时其权重重新分配给其它策略
       （但尊重用户对 balanced/hot_cold 的禁用）
    5. 历史均衡子策略：χ²守卫 + 频率/012路趋中，奇偶/大小采用显著性
       gating（仅统计显著偏离才注入），避免噪声放大
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ensemble_v2_3d",
            name="三策略融合",
            description="综合历史均衡、智能冷热号、遗漏号追踪三个策略，通过逐位概率融合生成稳健号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 30, "max": 10000},
            "balanced_weight": {
                "type": "int",
                "label": "历史均衡权重",
                "default": 33,
                "min": 0,
                "max": 100,
                "tooltip": "历史均衡策略的基准权重。自适应开启时作为乘性调整的基准（不会被忽略）。",
            },
            "hot_cold_weight": {
                "type": "int",
                "label": "智能冷热号权重",
                "default": 34,
                "min": 0,
                "max": 100,
                "tooltip": "智能冷热号策略的基准权重。自适应开启时作为乘性调整的基准。",
            },
            "missing_weight": {
                "type": "int",
                "label": "遗漏号追踪权重",
                "default": 33,
                "min": 0,
                "max": 100,
                "tooltip": "遗漏号追踪策略的基准权重。某位无显著冷号时该位权重会自动重新分配。",
            },
            "hot_weight": {
                "type": "int",
                "label": "热号权重(x0.01)",
                "default": 60,
                "min": 0,
                "max": 100,
                "tooltip": "智能冷热号中热号的权重。60=偏向热号，40=偏向冷号。",
            },
            "cold_weight": {
                "type": "int",
                "label": "冷号权重(x0.01)",
                "default": 40,
                "min": 0,
                "max": 100,
                "tooltip": "智能冷热号中冷号的权重。40=标准，60=更追冷。",
            },
            "z_threshold": {
                "type": "int",
                "label": "z-score阈值(x0.01)",
                "default": 196,
                "min": 100,
                "max": 300,
                "tooltip": "统计显著性阈值。196=95%置信(z>1.96)，258=99%置信(z>2.58)。",
            },
            "adaptive": {
                "type": "bool",
                "label": "自适应权重",
                "default": True,
                "tooltip": "开启后以基准权重为基准，根据各位置χ²状态做乘性调整。",
            },
            "temperature": {
                "type": "int",
                "label": "温度(x0.1)",
                "default": 10,
                "min": 1,
                "max": 50,
                "tooltip": "控制号码集中程度（作用于三个子策略的概率生成）。10=标准平衡，1=高度集中，50=接近随机。",
            },
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，最多220组。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 30:
            raise ValueError("集成策略需要至少 30 期历史数据（统计检验要求）")

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _zscore_list(vals: List[float]) -> List[float]:
        """z-score 标准化列表，std≈0 时返回全 0。使用总体标准差。"""
        if len(vals) < 2:
            return [0.0] * len(vals)
        mean = statistics.mean(vals)
        try:
            std = statistics.pstdev(vals)
        except statistics.StatisticsError:
            std = 0.0
        if std < 1e-10:
            return [0.0] * len(vals)
        return [(v - mean) / std for v in vals]

    @staticmethod
    def _ratio_signal(
        dev: float,
        sigma: float,
        positive_mask: List[bool],
        z_threshold: float = 2.0,
        max_gain: float = 3.0,
    ) -> List[float]:
        """基于显著性的方向性得分，避免 z-score 对二元信号的无条件放大.

        用于奇偶/大小等「二元比例」信号：仅当 |dev| 相对 sigma 超过
        z_threshold（统计显著）时才注入方向性 logit，且 gain 被 clip 防止极端。
        dev≈0（噪声）时返回全 0，不污染分布。

        - dev: 实际偏差（如 odd_ratio - 0.5）
        - sigma: 该比例在均匀假设下的标准差
        - positive_mask[d]: dev>0 时应被提升的数字为 True
        """
        if sigma < 1e-9 or abs(dev) < 1e-9:
            return [0.0] * 10
        z = abs(dev) / sigma
        gain = min(max(0.0, z - z_threshold), max_gain)
        if gain < 1e-9:
            return [0.0] * 10
        sign = 1.0 if dev > 0 else -1.0
        return [
            (sign * gain if positive_mask[d] else -sign * gain)
            for d in range(10)
        ]

    @staticmethod
    def _reallocate_missing_weight(weights: Dict[str, float]) -> Dict[str, float]:
        """遗漏子策略在某位无显著冷号时，把其权重按比例再分配给 balanced/hot_cold.

        避免纯均匀分布以原权重参与融合而被动稀释有效信号。
        当 balanced/hot_cold 都被用户禁用(权重=0)时，尊重禁用：保留 missing
        权重原样返回（该位将使用 missing 子策略的分布，通常即均匀），
        而非强行启用被禁用的策略。
        """
        w = dict(weights)
        pool = w.get("missing", 0.0)
        others = ("balanced", "hot_cold")
        other_sum = sum(w[o] for o in others)
        if other_sum <= 0:
            # 其它策略均被用户禁用：尊重用户意图，不借用，保留 missing 权重
            return w
        w["missing"] = 0.0
        for o in others:
            w[o] += pool * (w[o] / other_sum)
        return w

    # ------------------------------------------------------------------ #
    # 三个子策略的概率分布
    # ------------------------------------------------------------------ #
    def _get_balanced_probs(
        self, records: List, lookback: int, uniform_flags: List[bool],
        z_threshold: float, temperature: float
    ) -> List[List[float]]:
        """历史均衡子策略的概率分布.

        - χ² 守卫：该位被判均匀时直接返回均匀分布（与原历史均衡策略一致），
          从源头消除「均匀数据上输出极端分布」的噪声放大问题。
        - 频率/012路趋中：z-score 的 -|z|，偏好接近该位历史均值的数字（反极端）。
        - 奇偶/大小延续：基于逐位显著性的方向性信号（_ratio_signal），仅当该位
          比例偏离超过统计噪声带（z>z_threshold）时才温和注入，避免使用三位合并
          的整体比例导致信号抵消或错误传播。
        """
        weights = positional_weights(records, lookback, smoothing=1.0)
        road = road_012_statistics(records, lookback)
        pos_freq_counts = positional_frequency(records, lookback)

        odd_mask = [d % 2 == 1 for d in DIGIT_POOL]   # 奇数
        high_mask = [d >= 5 for d in DIGIT_POOL]      # 大数

        pos_probs: List[List[float]] = []
        for pos in range(3):
            # χ² 守卫：该位均匀 → 返回均匀（与原 balanced 策略一致）
            if uniform_flags[pos]:
                pos_probs.append([1.0 / 10.0] * 10)
                continue

            # 逐位奇偶/大小比例与标准差
            counts = pos_freq_counts[pos]
            total = sum(counts.values()) or 1
            odd_ratio = sum(counts.get(d, 0) for d in [1, 3, 5, 7, 9]) / total
            high_ratio = sum(counts.get(d, 0) for d in [5, 6, 7, 8, 9]) / total
            sigma_ratio = 0.5 / math.sqrt(max(total, 1))

            # 维度1：频率趋中（-|z|，接近均值得分高）
            freq_z = self._zscore_list([weights[pos][d] for d in DIGIT_POOL])
            freq_score = [-abs(z) for z in freq_z]
            # 维度2：012路趋中
            road_z = self._zscore_list([road[pos][d % 3] for d in DIGIT_POOL])
            road_score = [-abs(z) for z in road_z]
            # 维度3：奇偶延续（显著性 gating，噪声不注入）
            parity_score = self._ratio_signal(
                odd_ratio - 0.5, sigma_ratio, odd_mask, z_threshold=z_threshold
            )
            # 维度4：大小延续
            size_score = self._ratio_signal(
                high_ratio - 0.5, sigma_ratio, high_mask, z_threshold=z_threshold
            )

            combined = [
                freq_score[d] + road_score[d] + parity_score[d] + size_score[d]
                for d in DIGIT_POOL
            ]
            probs = softmax_scores(combined, temperature=temperature)
            pos_probs.append(probs)

        return pos_probs

    def _get_hot_cold_probs(
        self,
        records: List,
        lookback: int,
        hot_weight: float,
        cold_weight: float,
        geo_z: Dict[int, Dict[int, float]],
        temperature: float,
    ) -> List[List[float]]:
        """获取智能冷热号策略的概率分布（geo_z 由调用方共享，避免重复计算）."""
        freq = stable_frequency(records, lookback)

        pos_probs: List[List[float]] = []
        for pos in range(3):
            probs = stable_scores(
                freq[pos], geo_z[pos], hot_weight, cold_weight, temperature
            )
            pos_probs.append(probs)

        return pos_probs

    def _get_missing_probs(
        self,
        geo_z: Dict[int, Dict[int, float]],
        z_threshold: float,
        uniform_flags: List[bool],
        temperature: float,
    ) -> Tuple[List[List[float]], List[bool]]:
        """获取遗漏号追踪策略的概率分布（geo_z 由调用方共享）.

        与原 ``FC3DMissingNumberStrategy`` 一致采用双层守卫：
        先看该位 χ² 检验是否均匀，均匀则直接退化为均匀分布（不找冷号），
        避免「整体均匀但单数字随机长遗漏」造成的假阳性（赌徒谬误）。

        Returns:
            (pos_probs, has_signal): has_signal[pos] 表示该位是否存在统计显著冷号。
        """
        pos_probs: List[List[float]] = []
        has_signal: List[bool] = []
        for pos in range(3):
            # 第一层守卫：χ² 检验认为该位均匀 → 无显著冷号
            if uniform_flags[pos]:
                has_signal.append(False)
                pos_probs.append([1.0 / 10.0] * 10)
                continue
            # 第二层：z-score 超阈值的显著偏冷号码
            cold_digits = [
                d for d in DIGIT_POOL if geo_z[pos][d] > z_threshold
            ]
            if not cold_digits:
                has_signal.append(False)
                pos_probs.append([1.0 / 10.0] * 10)
            else:
                has_signal.append(True)
                logits = [geo_z[pos][d] for d in DIGIT_POOL]
                probs = softmax_scores(logits, temperature=temperature)
                pos_probs.append(probs)

        return pos_probs, has_signal

    # ------------------------------------------------------------------ #
    # 逐位自适应权重
    # ------------------------------------------------------------------ #
    def _adaptive_weights_per_pos(
        self,
        uniform_flags: List[bool],
        base_weights: Dict[str, float],
        missing_has_signal: List[bool],
    ) -> Dict[int, Dict[str, float]]:
        """逐位自适应权重：以 base_weights 为基准，根据实际信号类型做乘性调整.

        - 以用户配置的 base_weights 为基准（修正旧实现忽略用户配置的问题）；
        - 该位均匀时维持基准权重；
        - 该位非均匀且存在显著冷号时，提升 missing（追冷），降低 balanced；
        - 该位非均匀但无显著冷号时，提升 hot_cold（追热/结构），降低 missing；
        - base_weights 为 0 的策略调整后仍为 0（尊重用户明确禁用）。
        """
        result: Dict[int, Dict[str, float]] = {}
        keys = ("balanced", "hot_cold", "missing")
        for pos in range(3):
            if uniform_flags[pos]:
                # 该位均匀：维持基准权重
                mult = {"balanced": 1.0, "hot_cold": 1.0, "missing": 1.0}
            elif missing_has_signal[pos]:
                # 存在显著冷号：提升遗漏号追踪（追冷），略降 balanced
                mult = {"balanced": 0.8, "hot_cold": 1.0, "missing": 1.5}
            else:
                # 非均匀但无显著冷号：提升智能冷热号（追热/结构）
                mult = {"balanced": 1.0, "hot_cold": 1.2, "missing": 0.8}
            adjusted = {
                k: max(base_weights.get(k, 0) * mult[k], 0.0) for k in keys
            }
            total = sum(adjusted.values())
            if total <= 0:
                # 基准全为 0：退化为均权
                adjusted = {k: 1.0 for k in keys}
                total = float(len(keys))
            result[pos] = {k: adjusted[k] / total for k in keys}
        return result

    # ------------------------------------------------------------------ #
    # 主生成
    # ------------------------------------------------------------------ #
    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        balanced_weight = int(options.get("balanced_weight", 33))
        hot_cold_weight = int(options.get("hot_cold_weight", 34))
        missing_weight = int(options.get("missing_weight", 33))
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        z_threshold = int(options.get("z_threshold", 196)) / 100.0
        adaptive = bool(options.get("adaptive", True))
        temperature = int(options.get("temperature", 10)) / 10.0
        dedup = bool(options.get("dedup", True))
        rng = _make_rng(options, records, lookback, self.metadata.id)

        # 去重模式下数量上限（组选组合上限）
        if dedup and count > FC3D_GROUP_COMBINATIONS:
            raise ValueError(
                f"去重模式下最多生成 {FC3D_GROUP_COMBINATIONS} 组"
                f"（3D组选组合上限：组六120+组三90+豹子10），"
                f"当前请求 {count} 组。可关闭去重(dedup=False)或减少数量。"
            )

        # 1. χ²均匀性检验（逐位）
        pos_freq_counts = positional_frequency(records, lookback)
        chi2_values: List[float] = []
        uniform_flags: List[bool] = []
        for pos in range(3):
            counts = [pos_freq_counts[pos].get(d, 0) for d in range(10)]
            chi2, is_uniform = chi_square_uniform_test(counts)
            chi2_values.append(round(chi2, 2))
            uniform_flags.append(is_uniform)

        # 2. 共享遗漏统计与 missing 信号（自适应权重需要）
        raw_missing = raw_missing_periods(records, lookback)
        geo_z = geometric_missing_zscore(raw_missing)
        missing_probs, missing_has_signal = self._get_missing_probs(
            geo_z, z_threshold, uniform_flags, temperature
        )

        # 3. 逐位自适应权重（以用户 base_weights 为基准）
        base_weights = {
            "balanced": balanced_weight,
            "hot_cold": hot_cold_weight,
            "missing": missing_weight,
        }
        if adaptive:
            pos_weights = self._adaptive_weights_per_pos(
                uniform_flags, base_weights, missing_has_signal
            )
        else:
            total_bw = sum(base_weights.values())
            if total_bw > 0:
                norm_bw = {k: v / total_bw for k, v in base_weights.items()}
            else:
                norm_bw = {k: 1.0 / 3 for k in base_weights}
            pos_weights = {pos: dict(norm_bw) for pos in range(3)}

        # 4. 其余策略概率分布
        balanced_probs = self._get_balanced_probs(
            records, lookback, uniform_flags, z_threshold, temperature
        )
        hot_cold_probs = self._get_hot_cold_probs(
            records, lookback, hot_weight, cold_weight, geo_z, temperature
        )

        # 4. 逐位概率融合（含遗漏弃权重的再分配）
        pos_probs: List[List[float]] = []
        final_pos_weights: List[Dict[str, float]] = []
        for pos in range(3):
            w = dict(pos_weights[pos])
            # 遗漏子策略在该位无显著冷号：权重重新分配给 balanced/hot_cold
            if not missing_has_signal[pos] and w.get("missing", 0.0) > 0.0:
                w = self._reallocate_missing_weight(w)

            fused = [
                w["balanced"] * balanced_probs[pos][d]
                + w["hot_cold"] * hot_cold_probs[pos][d]
                + w["missing"] * missing_probs[pos][d]
                for d in range(10)
            ]

            # 归一化
            total = sum(fused)
            if total > 0:
                fused = [p / total for p in fused]
            else:
                fused = [1.0 / 10.0] * 10
            pos_probs.append(fused)
            final_pos_weights.append({k: round(v, 3) for k, v in w.items()})

        # 5. 构建说明文本
        all_uniform = all(uniform_flags)
        deviating = [p + 1 for p, u in enumerate(uniform_flags) if not u]
        missing_active = [p + 1 for p in range(3) if missing_has_signal[p]]

        basis = (
            f"三策略融合：基于最近 {lookback} 期，"
            f"温度={temperature}，自适应={adaptive}。"
        )
        if all_uniform:
            basis += "χ²检验显示各位置接近均匀分布，历史统计信号较弱。"
        else:
            basis += f"χ²检验显示第{deviating}位显著偏离均匀分布。"

        # 逐位权重说明
        weight_parts = [
            f"第{pos + 1}位(均衡{final_pos_weights[pos]['balanced']:.0%}"
            f"/冷热{final_pos_weights[pos]['hot_cold']:.0%}"
            f"/遗漏{final_pos_weights[pos]['missing']:.0%})"
            for pos in range(3)
        ]
        basis += "逐位权重：" + "，".join(weight_parts) + "。"

        if missing_active:
            basis += f"遗漏号追踪在第{missing_active}位检测到显著冷号(z>{z_threshold})。"
        else:
            basis += (
                "遗漏号追踪在所有位置均无统计显著冷号，"
                "其权重已重新分配给历史均衡与智能冷热号。"
            )

        # 小样本降级提示
        actual_n = min(lookback, len(records))
        if actual_n < 50:
            basis += (
                f"警告：实际统计样本仅{actual_n}期(<50)，"
                "χ²/z-score检验功效偏低，信号可靠性下降。"
            )

        basis += (
            "数学说明：历史均衡(χ²守卫+频率/012路趋中，奇偶/大小仅统计显著时注入)、"
            "智能冷热号(频率+几何分布遗漏z-score)、"
            "遗漏号追踪(χ²守卫+显著冷号)逐位融合。"
            "注意：历史均衡的频率维度为趋中(反极端)，与智能冷热号追热号方向相反，"
            "二者融合时频率信号会被部分平衡，属均衡策略的预期行为。"
            "历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        user_seed = options.get("seed")
        if user_seed is not None:
            basis += f" 随机种子：{user_seed}。"

        # 6. 形态修正（仅在去重模式下通过 group 权重生效）
        theoretical_shape = {"leopard": 0.01, "group3": 0.27, "group6": 0.72}
        hist_shape = shape_ratio(records, lookback)
        shape_weights: Optional[Dict[str, float]] = None
        if dedup:
            shape_weights = {}
            for key in theoretical_shape:
                hist = hist_shape.get(key, theoretical_shape[key])
                if hist <= 0:
                    hist = theoretical_shape[key]
                shape_weights[key] = min(
                    max(theoretical_shape[key] / hist, 0.2), 5.0
                )
            basis += (
                f"形态修正权重：豹子{shape_weights['leopard']:.2f}/"
                f"组三{shape_weights['group3']:.2f}/"
                f"组六{shape_weights['group6']:.2f}。"
            )

        # 7. 采样生成号码
        if dedup:
            results = _weighted_sample_without_replacement(
                pos_probs, count, rng, shape_weights=shape_weights
            )
        else:
            results = [
                [sample_weighted(rng, list(range(10)), pos_probs[pos]) for pos in range(3)]
                for _ in range(count)
            ]

        # 三位平均权重（概览，兼容旧访问 weights['balanced']）；逐位完整数据见 pos_weights
        avg_weights = {
            k: round(
                sum(final_pos_weights[pos][k] for pos in range(3)) / 3, 3
            )
            for k in ("balanced", "hot_cold", "missing")
        }

        tickets: List[Ticket] = []
        for result in results:
            ticket = Ticket(
                profile=FC3D_PROFILE,
                groups={"pos": result},
                strategy_name=self.metadata.name,
                basis=basis,
            )
            ticket.details = {
                "pos_probabilities": pos_probs,
                "chi_square": chi2_values,
                "is_uniform": uniform_flags,
                # 三位平均权重（概览）；逐位完整数据见 pos_weights
                "weights": avg_weights,
                # 逐位实际权重（含遗漏弃权重后的再分配）
                "pos_weights": final_pos_weights,
                "missing_has_signal": missing_has_signal,
                "adaptive": adaptive,
                "temperature": temperature,
                "shape_weights": shape_weights,
                "strategy_components": {
                    "balanced": "历史均衡",
                    "hot_cold": "智能冷热号",
                    "missing": "遗漏号追踪",
                },
            }
            tickets.append(ticket)

        return tickets


# 兼容旧导入名：保留 FC3DEnsembleStrategy 作为别名
FC3DEnsembleStrategy = FC3DStrategyFusionStrategy
