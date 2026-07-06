"""通用号码生成策略（按彩种档案驱动）.

为福彩3D、七乐彩、快乐8 提供与双色球对齐的 9 种策略：
完全随机、奇偶均衡、冷热号、排除/必含、智能冷热号、遗漏号、历史均衡、
XGBoost 智能分析、LightGBM 智能分析。

策略 id 带彩种后缀（如 ``random_3d``），避免与双色球策略冲突。
"""

from __future__ import annotations

import random
from abc import ABC
from collections import Counter
from typing import Any, Dict, List, Optional, Type

import numpy as np

from ...data.analyzer import DrawAnalyzer
from ...data.models import DrawRecord
from ...data.repository import DrawRepository
from ...ml.generic_predictor import GenericMLPredictor
from ...ml.model_store import compute_lookback, find_current_model, new_model_path
from ..profile import LotteryProfile, NumberGroup
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    """从 options['history'] 提取 DrawRecord 列表。"""
    history = options.get("history", []) or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            # 兼容 Ticket 对象
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records


def _get_pick_count(options: Dict[str, Any], profile: LotteryProfile) -> int:
    """返回本次生成主号码组应选几个号码。"""
    primary = profile.primary_group
    if not primary.variable_pick:
        return primary.count
    pick = options.get("pick_count")
    if pick is None:
        return primary.effective_pick_max
    try:
        pick = int(pick)
    except (TypeError, ValueError):
        return primary.effective_pick_max
    return max(primary.effective_pick_min, min(pick, primary.effective_pick_max))


def _add_pick_count_schema(
    schema: Dict[str, Any], profile: LotteryProfile, label: str = "投注个数"
) -> None:
    """为可变 pick 彩种（如快乐8）在策略参数里加入‘选几’配置。"""
    primary = profile.primary_group
    if not primary.variable_pick:
        return
    schema["pick_count"] = {
        "type": "choice",
        "label": label,
        "choices": list(range(primary.effective_pick_min, primary.effective_pick_max + 1)),
        "default": primary.effective_pick_max,
        "tooltip": f"选择投注 {primary.name} 的号码个数（选一到选十）。",
    }


def _make_ticket(profile: LotteryProfile, groups: Dict[str, List[int]], **kwargs) -> Ticket:
    return Ticket(profile=profile, groups=groups, **kwargs)


class _GenericBase(GenerationStrategy, ABC):
    """通用策略基类：绑定 profile 与 id/name 后缀。"""

    _id_base: str = ""
    _name_base: str = ""
    _description: str = ""
    _needs_history: bool = False

    def __init__(self, profile: LotteryProfile) -> None:
        self.profile = profile

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id=f"{self._id_base}_{self.profile.key}",
            name=f"{self._name_base}",
            description=self._description,
            configurable=True,
        )

    def validate_options(self, options: Dict[str, Any]) -> None:
        if self._needs_history:
            history = options.get("history", [])
            if len(history) < 20:
                raise ValueError(f"{self.metadata.name} 策略需要至少 20 期历史数据")


# --------------------------------------------------------------------------- #
# 1. 完全随机
# --------------------------------------------------------------------------- #
class GenericRandomStrategy(_GenericBase):
    """完全随机生成投注单。"""

    _id_base = "random"
    _name_base = "完全随机"
    _description = "在彩种号池范围内完全随机抽取号码。"

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            }
        }
        _add_pick_count_schema(schema, self.profile)
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        pick = _get_pick_count(options, self.profile)
        basis = f"完全随机策略：在 {self.profile.name} 号池中等概率随机抽取 {pick} 个号码。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            for g in self.profile.pick_groups:
                current_pick = pick if g.is_primary else g.count
                if g.variable_pick and not g.is_primary:
                    current_pick = rng.randint(g.effective_pick_min, g.effective_pick_max)
                if g.positional:
                    groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
                elif g.allow_repeat:
                    groups[g.key] = sorted(rng.choices(g.values, k=current_pick))
                else:
                    groups[g.key] = sorted(rng.sample(g.values, current_pick))
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets


# --------------------------------------------------------------------------- #
# 2. 奇偶均衡
# --------------------------------------------------------------------------- #
class GenericOddEvenStrategy(_GenericBase):
    """控制主号码组中奇偶比例。"""

    _id_base = "odd_even"
    _name_base = "奇偶均衡"
    _description = "控制号码中奇数和偶数的比例，默认接近均衡。"

    def get_config_schema(self) -> Dict[str, Any]:
        primary = self.profile.primary_group
        pick = primary.effective_pick_max
        schema: Dict[str, Any] = {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": pick // 2,
                "min": 0,
                "max": pick,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, self.profile, label=f"{primary.name}投注个数")
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)
        odd_count = options.get("odd_count", pick // 2)
        if not isinstance(odd_count, int) or not (0 <= odd_count <= pick):
            raise ValueError(f"奇数个数必须是 0-{pick} 的整数")
        if primary.variable_pick:
            pc = options.get("pick_count")
            if pc is not None:
                pc = int(pc)
                if not (primary.effective_pick_min <= pc <= primary.effective_pick_max):
                    raise ValueError(
                        f"投注个数必须在 {primary.effective_pick_min}-{primary.effective_pick_max} 之间"
                    )

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)
        odd_count = int(options.get("odd_count", pick // 2))
        even_count = pick - odd_count
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        odd_pool = [n for n in primary.values if n % 2 == 1]
        even_pool = [n for n in primary.values if n % 2 == 0]
        if odd_count > len(odd_pool) or even_count > len(even_pool):
            raise ValueError("奇偶数量超出可选范围")

        basis = f"奇偶均衡策略：{primary.name}中强制包含 {odd_count} 个奇数、{even_count} 个偶数。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                # 按位：奇数/偶数约束不适用，退化为随机
                groups[primary.key] = [rng.randint(primary.lo, primary.hi) for _ in range(primary.count)]
            else:
                groups[primary.key] = sorted(rng.sample(odd_pool, odd_count) + rng.sample(even_pool, even_count))
            # 其它组随机
            self._fill_other_groups(groups, rng)
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_other_groups(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in self.profile.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# --------------------------------------------------------------------------- #
# 3. 冷热号
# --------------------------------------------------------------------------- #
class GenericHotColdStrategy(_GenericBase):
    """基于历史频率选择热号或冷号。"""

    _id_base = "hot_cold"
    _name_base = "冷热号分析"
    _description = "基于历史记录统计出现频率，优先选择热号或冷号。"
    _needs_history = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "mode": {
                "type": "choice",
                "label": "模式",
                "choices": ["hot", "cold", "mixed"],
                "default": "mixed",
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, self.profile)
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        mode = options.get("mode", "mixed")
        records = _records_from_options(options)
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)

        analyzer = DrawAnalyzer(records, self.profile)
        freq = analyzer.frequency(primary.key)
        all_vals = primary.values[:]
        if not freq:
            ranked = all_vals[:]
            rng.shuffle(ranked)
        else:
            ranked = sorted(all_vals, key=lambda n: freq.get(n, 0), reverse=True)

        half = pick // 2
        if mode == "hot":
            pool = ranked[: max(pick, len(ranked) // 2)]
        elif mode == "cold":
            pool = ranked[-max(pick, len(ranked) // 2):]
        else:
            pool = ranked[:half] + ranked[-(pick - half):]

        basis = f"冷热号分析策略：{mode} 模式，基于历史频率选取候选池，投注 {pick} 个号码。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.choice(pool) for _ in range(primary.count)]
            else:
                chosen = min(pick, len(pool))
                groups[primary.key] = sorted(rng.sample(pool, chosen))
            self._fill_random_other(groups, rng)
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in self.profile.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = rng.randint(g.effective_pick_min, g.effective_pick_max) if g.variable_pick else g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# --------------------------------------------------------------------------- #
# 4. 排除/必含
# --------------------------------------------------------------------------- #
class GenericExcludeIncludeStrategy(_GenericBase):
    """排除或强制包含某些号码。"""

    _id_base = "exclude_include"
    _name_base = "排除/必含"
    _description = "排除不想要的号码，或强制包含某些幸运号码。"

    def get_config_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {}
        for g in self.profile.pick_groups:
            schema[f"include_{g.key}"] = {
                "type": "list_int",
                "label": f"必含 {g.name}",
                "default": [],
                "min": g.lo,
                "max": g.hi,
            }
            schema[f"exclude_{g.key}"] = {
                "type": "list_int",
                "label": f"排除 {g.name}",
                "default": [],
                "min": g.lo,
                "max": g.hi,
            }
        schema["seed"] = {
            "type": "int",
            "label": "随机种子（可选）",
            "default": None,
            "min": 0,
            "max": 999999999,
        }
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        for g in self.profile.pick_groups:
            include = set(options.get(f"include_{g.key}", []))
            exclude = set(options.get(f"exclude_{g.key}", []))
            valid_range = set(g.values)
            if not (include <= valid_range):
                raise ValueError(f"必含 {g.name} 包含越界号码")
            if not (exclude <= valid_range):
                raise ValueError(f"排除 {g.name} 包含越界号码")
            if include & exclude:
                raise ValueError(f"{g.name} 中同一号码不能同时必含和排除")
            if len(include) > g.effective_pick_max:
                raise ValueError(f"必含 {g.name} 数量不能超过 {g.effective_pick_max}")
            available = valid_range - exclude
            if len(available) < g.effective_pick_min:
                raise ValueError(f"{g.name} 排除后剩余号码不足")
            if not (include <= available):
                raise ValueError(f"必含 {g.name} 不能出现在排除列表中")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        basis_parts = ["排除/必含策略："]
        for g in self.profile.pick_groups:
            inc = set(options.get(f"include_{g.key}", []))
            exc = set(options.get(f"exclude_{g.key}", []))
            if inc:
                basis_parts.append(f"必含 {g.name} {sorted(inc)}；")
            if exc:
                basis_parts.append(f"排除 {g.name} {sorted(exc)}；")
        basis = " ".join(basis_parts) + "其余号码在可用范围内随机补充。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            for g in self.profile.pick_groups:
                include = set(options.get(f"include_{g.key}", []))
                exclude = set(options.get(f"exclude_{g.key}", []))
                available = list(set(g.values) - exclude - include)
                if g.positional:
                    # 按位：必含/排除作用于每一位独立选择
                    pos_chosen = []
                    pool = list(set(g.values) - exclude)
                    for _ in range(g.count):
                        pos_pool = list(include) if include and rng.random() < 0.5 else pool
                        if not pos_pool:
                            pos_pool = g.values[:]
                        pos_chosen.append(rng.choice(pos_pool))
                    groups[g.key] = pos_chosen
                else:
                    if g.variable_pick:
                        pick = rng.randint(g.effective_pick_min, g.effective_pick_max)
                        pick = max(pick, len(include))
                        pick = min(pick, g.effective_pick_max)
                    else:
                        pick = g.count
                    if len(include) >= pick:
                        groups[g.key] = sorted(include)[:pick]
                        continue
                    need = pick - len(include)
                    if len(available) < need:
                        raise ValueError(f"{g.name} 排除后可用号码不足 {need} 个")
                    chosen = sorted(set(rng.sample(available, need)) | include)
                    groups[g.key] = chosen
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets


# --------------------------------------------------------------------------- #
# 5. 智能冷热号
# --------------------------------------------------------------------------- #
class GenericSmartHotColdStrategy(_GenericBase):
    """综合热号频率与冷号遗漏值加权生成。"""

    _id_base = "smart_hot_cold"
    _name_base = "智能冷热号"
    _description = "结合历史数据中的热号频率与冷号遗漏值加权生成号码。"
    _needs_history = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, self.profile)
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)

        analyzer = DrawAnalyzer(records, self.profile)
        freq = analyzer.frequency(primary.key)
        max_freq = max(freq.values()) if freq else 1
        missing = dict(analyzer.missing(primary.key, lookback))
        max_missing = max(missing.values()) if missing else 1

        scores: Dict[int, float] = {n: 0.0 for n in primary.values}
        for n, f in freq.items():
            scores[n] += hot_weight * (f / max_freq)
        for n, m in missing.items():
            scores[n] += cold_weight * (m / max_missing)
        min_score = min(scores.values())
        weights = [max(0.1, scores[n] - min_score + 1.0) for n in primary.values]

        basis = (
            f"智能冷热号策略：综合最近 {lookback} 期热号频率（权重 {hot_weight}）"
            f"与冷号遗漏值（权重 {cold_weight}）加权评分后随机抽取 {pick} 个号码。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.choices(primary.values, weights=weights, k=1)[0] for _ in range(primary.count)]
            else:
                selected = sorted(rng.choices(primary.values, weights=weights, k=pick))
                # 去重重抽
                while len(set(selected)) < pick and not primary.allow_repeat:
                    selected = sorted(rng.choices(primary.values, weights=weights, k=pick))
                groups[primary.key] = selected
            self._fill_random_other(groups, rng)
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in self.profile.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# --------------------------------------------------------------------------- #
# 6. 遗漏号
# --------------------------------------------------------------------------- #
class GenericMissingNumberStrategy(_GenericBase):
    """优先选择高遗漏号码。"""

    _id_base = "missing_number"
    _name_base = "遗漏号追踪"
    _description = "选择近期遗漏值较高的号码，适合追冷号。"
    _needs_history = True

    def get_config_schema(self) -> Dict[str, Any]:
        primary = self.profile.primary_group
        pick = primary.effective_pick_max
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 50, "min": 10, "max": 10000},
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": max(pick, min(12, primary.size // 2)),
                "min": pick,
                "max": primary.size,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, self.profile)
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 50))
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)
        default_pool_size = max(pick, min(12, primary.size // 2))
        pool_size = int(options.get("pool_size", default_pool_size))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        analyzer = DrawAnalyzer(records, self.profile)
        missing = analyzer.missing(primary.key, lookback)
        pool = [n for n, _ in missing[:pool_size]]

        basis = f"遗漏号追踪策略：基于最近 {lookback} 期，从高遗漏值候选池抽取 {pick} 个号码。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            groups: Dict[str, List[int]] = {}
            if primary.positional:
                groups[primary.key] = [rng.choice(pool) for _ in range(primary.count)]
            else:
                chosen = min(pick, len(pool))
                groups[primary.key] = sorted(rng.sample(pool, chosen))
            self._fill_random_other(groups, rng)
            tickets.append(_make_ticket(self.profile, groups, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in self.profile.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# --------------------------------------------------------------------------- #
# 7. 历史均衡
# --------------------------------------------------------------------------- #
class GenericBalancedStrategy(_GenericBase):
    """使奇偶、大小、和值接近历史平均。"""

    _id_base = "balanced"
    _name_base = "历史均衡"
    _description = "根据历史数据的奇偶比、大小比和和值分布生成均衡号码。"
    _needs_history = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema = {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }
        _add_pick_count_schema(schema, self.profile)
        return schema

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        primary = self.profile.primary_group
        pick = _get_pick_count(options, self.profile)

        analyzer = DrawAnalyzer(records, self.profile)
        odd_ratio, _ = analyzer.odd_even_ratio(lookback)
        high_ratio, _ = analyzer.high_low_ratio(lookback)
        sum_stats = analyzer.sum_statistics(lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6.0 or 1.0
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])
        target_odd = round(pick * odd_ratio)
        target_high = round(pick * high_ratio)

        freq = analyzer.frequency(primary.key)
        max_freq = max(freq.values()) if freq else 1
        weights = [max(0.1, freq.get(n, 0) / max_freq + 0.2) for n in primary.values]

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"使 {pick} 个号码的奇偶比、大小比、和值接近历史平均。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            best: Optional[Dict[str, List[int]]] = None
            best_score = float("inf")
            for _ in range(max_attempts):
                if primary.allow_repeat:
                    candidate_primary = sorted(rng.choices(primary.values, weights=weights, k=pick))
                else:
                    candidate_primary = sorted(rng.sample(primary.values, pick))
                odd_count = sum(1 for n in candidate_primary if n % 2 == 1)
                high_count = sum(1 for n in candidate_primary if n >= primary.high_low_border)
                total = sum(candidate_primary)
                score = (
                    abs(odd_count - target_odd)
                    + abs(high_count - target_high)
                    + (0 if sum_min <= total <= sum_max else abs(total - avg_sum) / 10.0)
                )
                if score < best_score:
                    best_score = score
                    groups: Dict[str, List[int]] = {primary.key: candidate_primary}
                    self._fill_random_other(groups, rng)
                    best = groups
                if best_score <= 0.5:
                    break
            if best is None:
                # Fallback: ensure at least one valid ticket
                if primary.allow_repeat:
                    candidate_primary = sorted(rng.choices(primary.values, k=pick))
                else:
                    candidate_primary = sorted(rng.sample(primary.values, pick))
                groups = {primary.key: candidate_primary}
                self._fill_random_other(groups, rng)
                best = groups
            tickets.append(_make_ticket(self.profile, best, strategy_name=self.metadata.name, basis=basis))
        return tickets

    def _fill_random_other(self, groups: Dict[str, List[int]], rng: random.Random) -> None:
        for g in self.profile.pick_groups:
            if g.key in groups:
                continue
            if g.positional:
                groups[g.key] = [rng.randint(g.lo, g.hi) for _ in range(g.count)]
            else:
                pick = rng.randint(g.effective_pick_min, g.effective_pick_max) if g.variable_pick else g.count
                groups[g.key] = sorted(rng.sample(g.values, pick))


# --------------------------------------------------------------------------- #
# 8/9. XGBoost / LightGBM 策略
# --------------------------------------------------------------------------- #
class _GenericMLStrategy(_GenericBase):
    _backend: str = "xgboost"
    _id_base = "xgboost"
    _name_base = "XGBoost 智能分析"
    _description = "基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。"
    _needs_history = True
    is_ml = True

    def get_config_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {
            "diversity_boost": {
                "type": "int",
                "label": "多样性增强 (0-10)",
                "default": 3,
                "min": 0,
                "max": 10,
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
                "tooltip": "-1 表示使用全部历史记录；正数表示只使用最近 N 期训练模型。",
            },
        }
        # 快乐8 额外让玩家选择投注个数
        _add_pick_count_schema(schema, self.profile, label="投注个数")
        return schema

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")
        primary = self.profile.primary_group
        if primary.variable_pick:
            pc = options.get("pick_count")
            if pc is not None:
                pc = int(pc)
                if not (primary.effective_pick_min <= pc <= primary.effective_pick_max):
                    raise ValueError(
                        f"投注个数必须在 {primary.effective_pick_min}-{primary.effective_pick_max} 之间"
                    )

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        seed = 42

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]

        lookback = compute_lookback(len(records))
        if self._backend == "xgboost":
            prefix = self.profile.xgboost_prefix()
        elif self._backend == "lightgbm":
            prefix = self.profile.lightgbm_prefix()
        else:
            prefix = self.profile.catboost_prefix()
        model_path = find_current_model(
            records, lookback, prefix=prefix, options=options
        ) or new_model_path(
            records, lookback, prefix=prefix, options=options
        )

        predictor = GenericMLPredictor(
            records, profile=self.profile, lookback=lookback, model_path=model_path, backend=self._backend
        )
        if not predictor.is_ready():
            predictor.train()

        proba = predictor.predict()
        proba_lists: Dict[str, Any] = {}
        for k, v in proba.items():
            if v.ndim == 1:
                proba_lists[k] = [round(float(p), 4) for p in v]
            else:
                proba_lists[k] = [[round(float(x), 4) for x in row] for row in v]
        # 图表可用的分组概率描述
        group_probabilities = []
        for g in self.profile.pick_groups:
            if g.key not in proba_lists:
                raise ValueError(f"模型未返回号码组 {g.name} 的概率")
            p = proba_lists[g.key]
            if g.positional:
                # 按位：拆成 count 个子图
                for pos in range(g.count):
                    group_probabilities.append(
                        (
                            f"{g.name}第{pos + 1}位概率",
                            p[pos],
                            g.color,
                            1,
                            f"数字 ({g.lo}-{g.hi})",
                        )
                    )
            else:
                group_probabilities.append(
                    (
                        f"{g.name}概率",
                        p,
                        g.color,
                        g.effective_pick_max,
                        f"{g.name}号码 ({g.lo}-{g.hi})",
                    )
                )
        details = {
            "lookback": lookback,
            "diversity_boost": int(diversity * 10),
            "probabilities": proba_lists,
            "group_probabilities": group_probabilities,
            "model_name": self._backend.upper(),
        }
        basis = (
            f"{self.metadata.name}：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样。"
        )

        # 每组默认 pick 数
        group_picks = {}
        for g in self.profile.pick_groups:
            pick = _get_pick_count(options, self.profile) if g.is_primary else g.count
            group_picks[g.key] = pick

        tickets: List[Ticket] = []
        if count <= 0:
            return tickets

        # 所有策略均取消“第一组使用预测概率最高号码”规则，全部使用加权采样
        for i in range(count):
            np_rng = np.random.RandomState(seed + i)
            rec_groups = predictor.recommend(group_picks=group_picks, diversity_boost=diversity, rng=np_rng)
            tickets.append(
                _make_ticket(
                    self.profile,
                    rec_groups,
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details,
                )
            )
        return tickets


class GenericXGBoostStrategy(_GenericMLStrategy):
    _backend = "xgboost"
    _id_base = "xgboost"
    _name_base = "XGBoost 智能分析"
    _description = "基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。"


class GenericLightGBMStrategy(_GenericMLStrategy):
    _backend = "lightgbm"
    _id_base = "lightgbm"
    _name_base = "LightGBM 智能分析"
    _description = "基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。"


class GenericCatBoostStrategy(_GenericMLStrategy):
    _backend = "catboost"
    _id_base = "catboost"
    _name_base = "CatBoost 智能分析"
    _description = "基于 CatBoost 模型分析历史数据，生成概率优先的号码组合。"


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #
_GENERIC_STRATEGY_CLASSES: List[Type[_GenericBase]] = [
    GenericRandomStrategy,
    GenericOddEvenStrategy,
    GenericHotColdStrategy,
    GenericExcludeIncludeStrategy,
    GenericSmartHotColdStrategy,
    GenericMissingNumberStrategy,
    GenericBalancedStrategy,
    GenericXGBoostStrategy,
    GenericLightGBMStrategy,
    GenericCatBoostStrategy,
]


def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]:
    """为指定彩种生成全部通用策略实例。"""
    return [cls(profile) for cls in _GENERIC_STRATEGY_CLASSES]


def needs_history(strategy_id: str) -> bool:
    """判断策略是否需要历史开奖数据。"""
    for key in ("hot_cold", "smart_hot_cold", "missing_number", "balanced",
                "xgboost", "lightgbm", "catboost", "stats", "ml_",
                "lstm", "hybrid"):
        if strategy_id.startswith(key):
            return True
    return False


def is_ml_strategy(strategy_id: str) -> bool:
    return (strategy_id.startswith("xgboost_") or strategy_id.startswith("lightgbm_")
            or strategy_id.startswith("catboost_") or strategy_id.startswith("ml_"))
