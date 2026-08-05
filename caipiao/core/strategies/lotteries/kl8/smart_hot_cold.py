"""快乐8智能冷热号策略.

在「每号每期独立同分布（出现概率 p=0.25）」的零假设下，用统计显著
的冷热信号驱动加权采样，并用 χ² 均匀性检验守卫防止把随机噪声当作
预测信号（赌徒谬误）。温度参数控制偏离均匀的程度，温度→∞ 退化为
纯随机均匀采样，符合「彩票是随机的」基本原则。
"""

from __future__ import annotations

import copy
import random
from typing import Any

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options
from ._base import (
    PROFILE,
    _add_pick_count_schema,
    _get_pick_count,
    _make_ticket,
)
from .stability import (
    MAIN_POOL,
    chi_square_uniform_test,
    frequency_counts,
    geometric_missing_zscore,
    raw_missing_periods,
    stable_frequency,
    stable_scores,
    weighted_sample_without_replacement,
)

# 智能冷热号策略默认选四（快乐8 选1-选10 共 10 种玩法）
DEFAULT_PICK_COUNT = 4


class KL8SmartHotColdStrategy(GenerationStrategy):
    """综合热号频率与冷号遗漏值加权生成.

    数学要点:
        - 热号信号: 拉普拉斯平滑频率（小样本向均匀先验收缩）
        - 冷号信号: 遗漏期数 → 几何分布 z-score（仅统计显著偏离才计分）
        - χ² 守卫: 判断整体是否显著偏离均匀，否则冷热信号弱
        - z-score 标准化 + softmax 温度: 控制集中程度，温度→∞ 即纯随机
        - 加权无放回采样: 选取 pick 个互不重复号码
    """

    _needs_history = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_kl8",
            name="智能冷热号",
            description="结合历史数据中的热号频率与冷号遗漏值加权生成号码。",
            configurable=True,
        )

    def get_config_schema(self) -> dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "temperature": {
                "type": "int",
                "label": "温度(x0.1)",
                "default": 10,
                "min": 1,
                "max": 50,
                "tooltip": "控制号码集中程度。10=标准平衡，1=高度集中（强烈偏向热/冷号），50=接近随机均匀分布",
            },
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同，112和121视为相同。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, default_pick=DEFAULT_PICK_COUNT)
        return schema

    def validate_options(self, options: dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 20:
            raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: dict[str, Any] | None = None
    ) -> list[Ticket]:
        options = options or {}
        self.validate_options(options)
        records = records_from_options(options)
        lookback = int(options.get("lookback", 100))
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        temperature = int(options.get("temperature", 10)) / 10.0
        pick = _get_pick_count(options, default_pick=DEFAULT_PICK_COUNT)
        rng = self._make_rng(options)
        primary = PROFILE.primary_group

        # 热号信号: 拉普拉斯平滑后的号码概率分布
        freq_prob = stable_frequency(records, lookback)

        # 冷号信号: 原始遗漏期数 → 几何分布 z-score
        # 在均匀假设(p=0.25)下 E[遗漏]=3, σ≈3.464
        # z>1.96 才算 95% 置信的统计显著偏冷，避免赌徒谬误
        raw_missing = raw_missing_periods(records, lookback)
        geo_z = geometric_missing_zscore(raw_missing)

        # χ² 均匀性检验守卫: 用原始观测计数判断整体是否统计显著偏离均匀
        counts = list(frequency_counts(records, lookback).values())
        chi2_value, is_uniform = chi_square_uniform_test(counts)

        # z-score 标准化 + softmax 温度 → 1-80 概率分布
        probabilities = stable_scores(
            freq_prob, geo_z, hot_weight, cold_weight, temperature
        )

        # 构建说明文本
        basis = (
            f"智能冷热号策略：lookback={lookback}，热权重={hot_weight}，"
            f"冷权重={cold_weight}，温度={temperature}，选{pick}。"
            f"每期加权随机预测20个候选号码，购买号码从中选取。"
        )
        if is_uniform:
            basis += (
                "χ²检验显示号码分布接近均匀（频率波动在统计噪声范围内），"
                "冷热信号较弱。"
            )
        else:
            basis += "χ²检验显示号码分布显著偏离均匀，冷热信号有效。"
        basis += "注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        details: dict[str, Any] = {
            "probabilities": probabilities,
            "chi_square": round(chi2_value, 2),
            "is_uniform": is_uniform,
            "cold_signal": "geometric_zscore",
            "pick_count": pick,
        }

        dedup = bool(options.get("dedup", True))

        seen: set = set()
        tickets: list[Ticket] = []
        max_attempts = count * 50 if dedup else 1
        for _ in range(count):
            selected: list[int] | None = None
            predicted_sorted: list[int] | None = None
            for _attempt in range(max_attempts):
                # 预测20个候选号码（加权随机，每次不同），
                # 购买号码从候选中按权重再选 pick 个
                predicted = weighted_sample_without_replacement(
                    rng, MAIN_POOL, probabilities, 20
                )
                pred_weights = [probabilities[n - 1] for n in predicted]
                chosen = weighted_sample_without_replacement(
                    rng, predicted, pred_weights, pick
                )
                chosen_sorted = sorted(chosen)
                if not dedup or tuple(chosen_sorted) not in seen:
                    if dedup:
                        seen.add(tuple(chosen_sorted))
                    selected = chosen_sorted
                    predicted_sorted = sorted(predicted)
                    break
            if selected is None:
                # 兜底: 均匀随机抽样（不应常见，仅在 dedup 候选耗尽时触发）
                selected = sorted(rng.sample(MAIN_POOL, pick))
            groups: dict[str, list[int]] = {primary.key: selected}
            self._fill_random_other(groups, rng)
            ticket_details = copy.deepcopy(details)
            if predicted_sorted is not None:
                ticket_details["prediction"] = predicted_sorted
            tickets.append(
                _make_ticket(
                    groups, strategy_name=self.metadata.name, basis=basis,
                    details=ticket_details,
                )
            )
        return tickets

    def _make_rng(self, options: dict[str, Any]) -> random.Random:
        """用户显式设置 seed 时可复现；未设置时真随机，每次生成结果不同。"""
        seed = options.get("seed")
        if seed is not None:
            return random.Random(int(seed))
        return random.Random()

    def _fill_random_other(self, groups: dict[str, list[int]], rng: random.Random) -> None:
        for g in PROFILE.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))
