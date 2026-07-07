"""福彩3D专属生成策略."""

from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Any, Dict, List, Optional

from ..profile import get_profile
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket
from ...data.analyzer import DrawAnalyzer
from ...data.models import DrawRecord
from .fc3d_utils import (
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


FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    history = options.get("history", []) or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records


def _make_rng(options: Dict[str, Any]) -> random.Random:
    seed = options.get("seed")
    return random.Random(seed) if seed is not None else random.Random()


class FC3DRandomStrategy(GenerationStrategy):
    """3D完全随机：每位独立0-9。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_3d",
            name="完全随机",
            description="在福彩3D的百、十、个位上分别独立随机生成0-9数字。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            }
        }

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        basis = "完全随机策略：百、十、个位分别独立随机生成0-9数字。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"
        tickets: List[Ticket] = []
        for _ in range(count):
            groups = {"pos": [rng.randint(0, 9) for _ in range(3)]}
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups=groups, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DOddEvenStrategy(GenerationStrategy):
    """3D奇偶均衡：控制整体奇数个数或按位奇偶。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even_3d",
            name="奇偶均衡",
            description="控制福彩3D号码中奇数和偶数的比例。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": 1,
                "min": 0,
                "max": 3,
            },
            "positional": {
                "type": "list_int",
                "label": "按位奇偶（可选）",
                "default": [],
                "min": 0,
                "max": 1,
                "tooltip": "长度为3的列表，1表示奇数，0表示偶数，空则使用整体奇数个数。",
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
        positional = options.get("positional", [])
        if positional and len(positional) != 3:
            raise ValueError("按位奇偶必须提供3个值")
        if positional and any(p not in (0, 1) for p in positional):
            raise ValueError("按位奇偶值必须是0或1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        positional = options.get("positional", [])
        odd_count = int(options.get("odd_count", 1))

        odd_pool = [1, 3, 5, 7, 9]
        even_pool = [0, 2, 4, 6, 8]

        if positional:
            basis = f"奇偶均衡策略：按位控制奇偶为 {positional}。"
        else:
            basis = f"奇偶均衡策略：整体包含 {odd_count} 个奇数、{3 - odd_count} 个偶数。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            if positional:
                result = [
                    rng.choice(odd_pool if p == 1 else even_pool)
                    for p in positional
                ]
            else:
                result = rng.sample(odd_pool, odd_count) + rng.sample(even_pool, 3 - odd_count)
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DExcludeIncludeStrategy(GenerationStrategy):
    """3D排除/必含：支持按位必含/排除。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include_3d",
            name="排除/必含",
            description="排除不想要的号码，或强制包含某些幸运号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "include_pos": {
                "type": "list_int_list",
                "label": "必含 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组必含数字，空列表表示不约束。",
            },
            "exclude_pos": {
                "type": "list_int_list",
                "label": "排除 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组排除数字，空列表表示不约束。",
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
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], []])
        for key, value in (("include_pos", include_pos), ("exclude_pos", exclude_pos)):
            if len(value) != 3:
                raise ValueError(f"{key} 必须提供3个位置的列表")
            for idx, nums in enumerate(value):
                if not all(0 <= n <= 9 for n in nums):
                    raise ValueError(f"{key} 第{idx}位包含越界号码")
        for idx in range(3):
            if not include_pos[idx] and set(exclude_pos[idx]) == set(range(10)):
                raise ValueError(f"第{idx + 1}位排除后没有可用号码")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], []])

        basis_parts = ["排除/必含策略："]
        for idx in range(3):
            inc = set(include_pos[idx])
            exc = set(exclude_pos[idx])
            if inc:
                basis_parts.append(f"第{idx+1}位必含 {sorted(inc)}；")
            if exc:
                basis_parts.append(f"第{idx+1}位排除 {sorted(exc)}；")
        basis = " ".join(basis_parts) + "其余位在可用范围内随机。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for idx in range(3):
                include = set(include_pos[idx])
                exclude = set(exclude_pos[idx])
                if include:
                    chosen = rng.choice(list(include))
                else:
                    available = set(range(10)) - exclude
                    chosen = rng.choice(list(available))
                result.append(chosen)
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DHotColdStrategy(GenerationStrategy):
    """3D冷热号分析：基于按位历史频率。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold_3d",
            name="冷热号分析",
            description="基于历史记录统计每位数字出现频率，优先选择热号或冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
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

    def validate_options(self, options: Dict[str, Any]) -> None:
        if not options.get("history"):
            raise ValueError("冷热号分析策略需要历史开奖数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        mode = options.get("mode", "mixed")
        records = _records_from_options(options)

        freq = positional_frequency(records)
        tickets: List[Ticket] = []
        basis = f"冷热号分析策略：{mode} 模式，基于按位历史频率抽取号码。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        for _ in range(count):
            result = []
            for pos in range(3):
                pos_freq = freq.get(pos, {})
                ranked = sorted(range(10), key=lambda d: pos_freq.get(d, 0), reverse=True)
                if mode == "hot":
                    pool = ranked[:5]
                elif mode == "cold":
                    pool = ranked[-5:]
                else:
                    pool = ranked[:2] + ranked[-2:]
                result.append(rng.choice(pool))
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


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

    def get_config_schema(self) -> Dict[str, Any]:
        return {
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

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 20:
            raise ValueError("智能冷热号策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))

        analyzer = DrawAnalyzer(records, FC3D_PROFILE)
        freq = analyzer.frequency("pos")
        max_freq = max(freq.values()) if freq else 1
        missing = dict(analyzer.missing("pos", lookback))
        max_missing = max(missing.values()) if missing else 1
        max_missing = max(max_missing, 1)

        basis = (
            f"智能冷热号策略：综合最近 {lookback} 期按位热号频率（权重 {hot_weight}）"
            f"与冷号遗漏值（权重 {cold_weight}）加权评分后抽取号码。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for pos in range(3):
                pos_records = [r.groups["pos"][pos] for r in records[-lookback:] if len(r.groups.get("pos", [])) > pos]
                pos_freq = Counter(pos_records)
                pos_missing = {}
                for idx, n in enumerate(reversed(pos_records)):
                    if n not in pos_missing:
                        pos_missing[n] = idx
                for d in range(10):
                    pos_missing.setdefault(d, len(pos_records))

                scores = []
                for d in range(10):
                    hot_score = hot_weight * (pos_freq.get(d, 0) / max_freq)
                    cold_score = cold_weight * (pos_missing[d] / max_missing)
                    scores.append(max(0.1, hot_score + cold_score))
                result.append(rng.choices(range(10), weights=scores, k=1)[0])
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DMissingNumberStrategy(GenerationStrategy):
    """3D遗漏号追踪：按位优先选择高遗漏号码。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_3d",
            name="遗漏号追踪",
            description="选择近期按位遗漏值较高的号码，适合追冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 50, "min": 10, "max": 10000},
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": 5,
                "min": 1,
                "max": 10,
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
        if len(options.get("history", [])) < 20:
            raise ValueError("遗漏号追踪策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 50))
        pool_size = int(options.get("pool_size", 5))

        analyzer = DrawAnalyzer(records, FC3D_PROFILE)

        basis = f"遗漏号追踪策略：基于最近 {lookback} 期，按位从高遗漏值候选池抽取号码。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for pos in range(3):
                pos_records = [r.groups["pos"][pos] for r in records[-lookback:] if len(r.groups.get("pos", [])) > pos]
                missing: Dict[int, int] = {d: lookback for d in range(10)}
                for idx, n in enumerate(reversed(pos_records)):
                    if missing[n] == lookback:
                        missing[n] = idx
                pool = [d for d, _ in sorted(missing.items(), key=lambda x: x[1], reverse=True)[:pool_size]]
                result.append(rng.choice(pool))
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DBalancedStrategy(GenerationStrategy):
    """3D历史均衡：按位统计，保留顺序，支持枚举择优。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_3d",
            name="历史均衡",
            description="根据历史数据的按位频率、奇偶、大小、跨度、和尾、012路和形态生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
            "use_enumeration": {
                "type": "bool",
                "label": "使用枚举择优",
                "default": True,
                "tooltip": "3D仅1000种组合，枚举可找到评分最高且确定性的结果。",
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
        if len(options.get("history", [])) < 20:
            raise ValueError("历史均衡策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        use_enumeration = bool(options.get("use_enumeration", True))

        odd_ratio, _ = overall_odd_even_ratio(records, lookback)
        high_ratio, _ = overall_high_low_ratio(records, lookback)
        sum_stats = sum_statistics(records, lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6.0 or 1.0
        tail_avg = sum_tail_statistics(records, lookback)["avg"]
        span_avg = span_statistics(records, lookback)["avg"]
        shape = shape_ratio(records, lookback)
        road = road_012_statistics(records, lookback)
        target_odd = round(3 * odd_ratio)
        target_high = round(3 * high_ratio)
        weights = positional_weights(records, lookback, smoothing=1.0)

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"使3D号码的按位频率、奇偶、大小、和值、跨度、和尾、012路和形态接近历史平均。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        def score(candidate: List[int]) -> float:
            odd_count = sum(1 for n in candidate if n % 2 == 1)
            high_count = sum(1 for n in candidate if n >= 5)
            total = sum(candidate)
            tail = total % 10
            span = max(candidate) - min(candidate)
            shape_type = fc3d_bet_type(candidate)
            shape_score = 0.0
            if shape_type == "豹子号":
                shape_score = 1 - shape["leopard"]
            elif shape_type == "组选3":
                shape_score = 1 - shape["group3"]
            else:
                shape_score = 1 - shape["group6"]

            # 按位权重作为轻量级 tie-breaker，保留历史中的位置顺序
            weight_score = -0.01 * sum(
                weights[pos][candidate[pos]] for pos in range(3)
            )
            road_score = sum(
                1.0 - road[pos][candidate[pos] % 3] for pos in range(3)
            )

            return (
                abs(odd_count - target_odd)
                + abs(high_count - target_high)
                + abs(total - avg_sum) / 10.0
                + abs(tail - tail_avg) / 5.0
                + abs(span - span_avg) / 5.0
                + shape_score
                + weight_score
                + road_score
            )

        def sample_one() -> List[int]:
            return [rng.choices(range(10), weights=weights[pos], k=1)[0] for pos in range(3)]

        tickets: List[Ticket] = []
        for _ in range(count):
            best_candidate: Optional[List[int]] = None
            best_score = float("inf")

            if use_enumeration:
                candidates = [list(c) for c in itertools.product(range(10), repeat=3)]
                if seed is not None:
                    rng.shuffle(candidates)
                for candidate in candidates:
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
            else:
                for _ in range(max_attempts):
                    candidate = sample_one()
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
                    if best_score <= 0.5:
                        break

            if best_candidate is None:
                best_candidate = sample_one()

            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": best_candidate},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets


import numpy as np

from ...ml.generic_predictor import GenericMLPredictor
from ...ml.model_store import compute_lookback, find_current_model, new_model_path


class _FC3DMLStrategy(GenerationStrategy):
    _backend: str = "xgboost"

    @property
    def is_ml(self) -> bool:
        return True

    def get_config_schema(self) -> Dict[str, Any]:
        return {
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
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]

        lookback = compute_lookback(len(records))
        if self._backend == "xgboost":
            prefix = FC3D_PROFILE.xgboost_prefix()
        elif self._backend == "lightgbm":
            prefix = FC3D_PROFILE.lightgbm_prefix()
        else:
            prefix = FC3D_PROFILE.catboost_prefix()

        model_path = (
            find_current_model(records, lookback, prefix=prefix, options=options)
            or new_model_path(records, lookback, prefix=prefix, options=options)
        )

        predictor = GenericMLPredictor(
            records, profile=FC3D_PROFILE, lookback=lookback, model_path=model_path, backend=self._backend
        )
        if not predictor.is_ready():
            predictor.train()

        proba = predictor.predict()
        proba_lists = {}
        for k, v in proba.items():
            if v.ndim == 1:
                proba_lists[k] = [round(float(p), 4) for p in v]
            else:
                proba_lists[k] = [[round(float(x), 4) for x in row] for row in v]

        details = {
            "lookback": lookback,
            "diversity_boost": int(diversity * 10),
            "probabilities": proba_lists,
            "model_name": self._backend.upper(),
        }
        basis = (
            f"{self.metadata.name}：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样。"
        )

        group_picks = {"pos": 3}
        tickets: List[Ticket] = []
        seed = 42
        for i in range(count):
            np_rng = np.random.RandomState(seed + i)
            rec_groups = predictor.recommend(group_picks=group_picks, diversity_boost=diversity, rng=np_rng)
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups=rec_groups,
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details,
                )
            )
        return tickets


class FC3DXGBoostStrategy(_FC3DMLStrategy):
    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_3d",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


class FC3DLightGBMStrategy(_FC3DMLStrategy):
    _backend = "lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_3d",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


class FC3DCatBoostStrategy(_FC3DMLStrategy):
    _backend = "catboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="catboost_3d",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


def build_fc3d_strategies(profile) -> List[GenerationStrategy]:
    return [
        FC3DRandomStrategy(),
        FC3DOddEvenStrategy(),
        FC3DHotColdStrategy(),
        FC3DExcludeIncludeStrategy(),
        FC3DSmartHotColdStrategy(),
        FC3DMissingNumberStrategy(),
        FC3DBalancedStrategy(),
        FC3DXGBoostStrategy(),
        FC3DLightGBMStrategy(),
        FC3DCatBoostStrategy(),
    ]
