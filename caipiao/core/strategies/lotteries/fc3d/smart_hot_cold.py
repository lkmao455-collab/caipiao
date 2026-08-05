"""福彩3D智能冷热号策略."""

from __future__ import annotations

from typing import Any

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
    stable_frequency,
    stable_scores,
)
from .utils import positional_frequency


class FC3DSmartHotColdStrategy(GenerationStrategy):
    """3D智能冷热号：综合按位频率与遗漏值。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_3d",
            name="智能冷热号",
            description="结合历史数据中的按位热号频率与冷号遗漏值加权生成。",
            configurable=True,
        )

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50, "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中（强烈偏向热/冷号），50=接近随机均匀分布"},
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码，112和121视为相同号码。",
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
        if len(options.get("history", [])) < 20:
            raise ValueError("智能冷热号策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        temperature = int(options.get("temperature", 10)) / 10.0
        rng = _make_rng(options, records, lookback, self.metadata.id)

        # 热号信号: 拉普拉斯平滑后的按位频率概率
        freq = stable_frequency(records, lookback)

        # 冷号信号: 原始遗漏期数 → 几何分布 z-score
        # 在均匀假设(p=0.1)下 E[遗漏]=9, σ=9.49
        # z>1.96 才算 95% 置信的统计显著偏冷，避免赌徒谬误
        raw_missing = raw_missing_periods(records, lookback)
        geo_z = geometric_missing_zscore(raw_missing)

        # χ² 均匀性检验守卫: 判断各位置是否统计显著偏离均匀分布
        pos_freq_counts = positional_frequency(records, lookback)
        chi2_values: list[float] = []
        uniform_flags: list[bool] = []
        for pos in range(3):
            counts = [pos_freq_counts[pos].get(d, 0) for d in range(10)]
            chi2, is_uniform = chi_square_uniform_test(counts)
            chi2_values.append(round(chi2, 2))
            uniform_flags.append(is_uniform)

        pos_probs: list[list[float]] = []
        for pos in range(3):
            pos_probs.append(stable_scores(
                freq[pos], geo_z[pos], hot_weight, cold_weight, temperature
            ))

        # 构建说明文本
        all_uniform = all(uniform_flags)
        basis = (
            f"智能冷热号策略：lookback={lookback}，热权重={hot_weight}，"
            f"冷权重={cold_weight}，温度={temperature}。"
        )
        if all_uniform:
            basis += (
                "χ²检验显示各位置接近均匀分布（频率波动在统计噪声范围内），"
                "冷热信号较弱。"
            )
        else:
            deviating = [p + 1 for p, u in enumerate(uniform_flags) if not u]
            basis += f"χ²检验显示第{deviating}位显著偏离均匀分布，冷热信号有效。"
        basis += "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        details: dict[str, Any] = {
            "pos_probabilities": pos_probs,
            "chi_square": chi2_values,
            "is_uniform": uniform_flags,
            "cold_signal": "geometric_zscore",
        }

        dedup = bool(options.get("dedup", True))

        if dedup:
            # 加权无放回采样: 枚举全部1000种组合按联合概率抽取，
            # 保持概率分布形状，避免拒绝采样在概率集中时扭曲输出
            results = _weighted_sample_without_replacement(pos_probs, count, rng)
        else:
            # 不去重: 逐位独立采样
            results = [
                [sample_weighted(rng, list(range(10)), pos_probs[pos]) for pos in range(3)]
                for _ in range(count)
            ]

        tickets: list[Ticket] = []
        for result in results:
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE, groups={"pos": result},
                    strategy_name=self.metadata.name, basis=basis,
                    details=details.copy(),
                )
            )
        return tickets
