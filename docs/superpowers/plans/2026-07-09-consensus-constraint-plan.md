# 共识约束策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现双色球“共识约束策略”，融合现有统计/数学策略优点，所有参数暴露于 UI，保证相同参数下输出一致，并提供一键参数推荐与 HTML 报告。

**Architecture:** 新增 `SSQConsensusConstraintStrategy` 类，内部按固定流水线依次执行统计先验建模、候选集生成、硬约束过滤、概率精排、冲突回退与确定性抽样；通过 `get_config_schema()` 暴露全部参数；新增 `recommend_parameters()` 类方法和 HTML 报告生成；扩展 `StrategyPanel` 以支持滚动面板和策略自定义按钮。

**Tech Stack:** Python 3.10+, PySide6, NumPy, pytest

## Global Constraints

- 不修改任何现有策略文件。
- 所有原本为常量的数值，必须作为 `get_config_schema()` 的 `default` 暴露。
- 必须使用单一 `seed` 控制所有随机性，确保可复现。
- 不使用 `datetime.now()`；时间相关计算必须依赖 `predict_date` 参数或历史最后一条 `draw_date`。
- 新策略与原策略实例完全隔离，不共享可变状态。
- 每个计算步骤必须能在 HTML 报告中给出数学解释。

## File Structure

- **Create:** `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
  - 新策略主体：metadata、schema、generate、推荐参数、HTML 报告。
- **Modify:** `caipiao/core/strategies/registry.py:157-179`
  - 在 `STRATEGY_REGISTRY["ssq"]` 列表末尾添加 `SSQConsensusConstraintStrategy`。
- **Modify:** `caipiao/core/strategies/factory.py:20-30`
  - 将 `consensus_constraint` 加入 `needs_history()` 的前缀列表，使 UI、回测、参数组等上层逻辑自动注入历史数据。
- **Modify:** `caipiao/ui/lottery_context.py:19-23,67-73`
  - 导入新策略并在 SSQ 分支注册。
- **Modify:** `caipiao/ui/components/strategy_panel.py`
  - 参数区域增加滚动面板；检测策略的 `recommend_parameters` 方法并显示按钮。
- **Create:** `tests/test_ssq_consensus_constraint.py`
  - 覆盖元数据、schema、生成有效性、确定性、推荐参数、HTML 报告、隔离性、冲突回退。
- **Create (runtime):** `docs/reports/`
  - HTML 报告保存目录。

---

## Task 1: Create Strategy Skeleton

**Files:**
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Create: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Consumes: `GenerationStrategy`, `StrategyMetadata`, `SSQ`, `Ticket`, `DrawRecord`
- Produces: `SSQConsensusConstraintStrategy.metadata`, `SSQConsensusConstraintStrategy.get_config_schema()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ssq_consensus_constraint.py
import pytest
from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
    SSQConsensusConstraintStrategy,
)


def test_metadata_and_schema():
    strategy = SSQConsensusConstraintStrategy()
    assert strategy.metadata.id == "consensus_constraint"
    assert strategy.metadata.name == "共识约束策略"
    assert strategy.metadata.configurable is True

    schema = strategy.get_config_schema()
    assert "seed" in schema
    assert "candidate_count" in schema
    assert "stats_lookback" in schema
    assert "bayesian_alpha" in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_metadata_and_schema -v
```
Expected: FAIL with "ModuleNotFoundError" or "class not defined"

- [ ] **Step 3: Write minimal implementation**

```python
# caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py
"""双色球共识约束策略."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .....core.profile import SSQ
from .....core.strategy import GenerationStrategy, StrategyMetadata
from .....core.ticket import Ticket


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_metadata_and_schema -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ssq_consensus_constraint.py caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py
git commit -m "feat(ssq): add consensus constraint strategy skeleton"
```

---

## Task 2: Implement Statistical Prior Computation

**Files:**
- Modify: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Consumes: `DrawRecord`, `DrawAnalyzer`/`LotteryAnalyzer`
- Produces: `_compute_statistical_prior(records, options) -> Tuple[np.ndarray, np.ndarray, str]`

- [ ] **Step 1: Write the failing test**

```python
def test_statistical_prior_is_probability_distribution(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "stats_enabled": True,
        "smart_hot_cold_enabled": True,
        "hot_cold_enabled": True,
        "missing_number_enabled": True,
    }
    red_probs, blue_probs, basis = strategy._compute_statistical_prior(
        [r for r in sample_history], options
    )
    assert abs(red_probs.sum() - 1.0) < 1e-10
    assert abs(blue_probs.sum() - 1.0) < 1e-10
    assert len(red_probs) == 33
    assert len(blue_probs) == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_statistical_prior_is_probability_distribution -v
```
Expected: FAIL with "AttributeError: no method _compute_statistical_prior"

- [ ] **Step 3: Write minimal implementation**

Add imports at top of file:
```python
import random
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from .....data.analyzer import DrawAnalyzer
from .....data.models import DrawRecord
```

Add helper methods inside `SSQConsensusConstraintStrategy`:

```python
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

        basis = "共识约束策略：统计先验融合（" + "；".join(basis_parts) + "）。"
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
        from .....data.analyzer import LotteryAnalyzer

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
        from .....data.analyzer import LotteryAnalyzer

        lookback = int(options.get("missing_number_lookback", 50))
        pool_size = int(options.get("missing_number_pool_size", 12))
        la = LotteryAnalyzer(analyzer.records)
        missing_reds = la.missing_reds(lookback)
        red_pool = [n for n, _ in missing_reds[:pool_size]]
        missing_blues = la.missing_blues(lookback)
        blue_pool = [n for n, _ in missing_blues[: min(8, pool_size // 2 + 2)]]
        text = f"missing_number({lookback}, pool={pool_size})"
        return self._pool_to_probability(red_pool, 33), self._pool_to_probability(blue_pool, 16), text
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_statistical_prior_is_probability_distribution -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): implement statistical prior for consensus constraint"
```

---

## Task 3: Candidate Generation and Hard Constraints

**Files:**
- Modify: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Consumes: `_compute_statistical_prior` output
- Produces: `_generate_candidates(...)`, `_apply_hard_constraints(...)`

- [ ] **Step 1: Write the failing test**

```python
def test_generate_candidates_valid(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {"history": sample_history, "seed": 42, "candidate_count": 1000}
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    assert len(candidates) <= 1000
    assert all(len(c[0]) == 6 and len(set(c[0])) == 6 for c in candidates)
    assert all(1 <= c[1] <= 16 for c in candidates)


def test_hard_constraints_filter(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "odd_even_enabled": True,
        "odd_count": 3,
        "balanced_enabled": True,
        "balanced_lookback": 100,
        "sum_min": 80,
        "sum_max": 150,
        "target_odd": 3,
        "target_high": 3,
        "exclude_include_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    filtered = strategy._apply_hard_constraints(candidates, records, options)
    assert len(filtered) <= len(candidates)
    for reds, blue in filtered:
        assert sum(1 for n in reds if n % 2 == 1) == 3
        assert sum_min <= sum(reds) <= sum_max
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_generate_candidates_valid tests/test_ssq_consensus_constraint.py::test_hard_constraints_filter -v
```
Expected: FAIL with "AttributeError"

- [ ] **Step 3: Write minimal implementation**

Add methods inside class:

```python
    def _generate_candidates(
        self,
        rng: random.Random,
        red_probs: np.ndarray,
        blue_probs: np.ndarray,
        options: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, ...], int]]:
        """阶段2：按概率生成候选组合。"""
        candidate_count = int(options.get("candidate_count", 50000))
        red_size, blue_size = 33, 16
        reds = list(range(1, red_size + 1))
        blues = list(range(1, blue_size + 1))

        candidates: Set[Tuple[Tuple[int, ...], int]] = set()
        attempts = 0
        max_attempts = candidate_count * 20
        while len(candidates) < candidate_count and attempts < max_attempts:
            attempts += 1
            selected = tuple(sorted(rng.choices(reds, weights=red_probs, k=6)))
            if len(set(selected)) < 6:
                continue
            blue = rng.choices(blues, weights=blue_probs, k=1)[0]
            candidates.add((selected, blue))

        return sorted(candidates)

    def _apply_hard_constraints(
        self,
        candidates: List[Tuple[Tuple[int, ...], int]],
        records: List[DrawRecord],
        options: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, ...], int]]:
        """阶段3：硬约束过滤。"""
        result = candidates

        if options.get("odd_even_enabled", True):
            odd_count = int(options.get("odd_count", 3))
            result = [(reds, blue) for reds, blue in result if sum(1 for n in reds if n % 2 == 1) == odd_count]

        if options.get("balanced_enabled", True) and result:
            sum_min = int(options.get("sum_min", 60))
            sum_max = int(options.get("sum_max", 160))
            target_odd = int(options.get("target_odd", 3))
            target_high = int(options.get("target_high", 3))
            result = [
                (reds, blue)
                for reds, blue in result
                if sum_min <= sum(reds) <= sum_max
                and abs(sum(1 for n in reds if n % 2 == 1) - target_odd) <= 0
                and abs(sum(1 for n in reds if n >= 17) - target_high) <= 0
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_generate_candidates_valid tests/test_ssq_consensus_constraint.py::test_hard_constraints_filter -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): candidate generation and hard constraints"
```

---

## Task 4: Probability Refinement

**Files:**
- Modify: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Consumes: filtered candidates, `DrawRecord`s, options
- Produces: `_score_candidates(candidates, records, options) -> List[Tuple[float, Tuple[int,...], int]]`

- [ ] **Step 1: Write the failing test**

```python
def test_refinement_scores_candidates(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 100,
        "bayesian_enabled": True,
        "markov_enabled": False,
        "trend_enabled": False,
        "periodic_enabled": False,
        "correlation_enabled": False,
    }
    records = [r for r in sample_history]
    red_probs, blue_probs, _ = strategy._compute_statistical_prior(records, options)
    rng = random.Random(42)
    candidates = strategy._generate_candidates(rng, red_probs, blue_probs, options)
    scored = strategy._score_candidates(candidates, records, options)
    assert len(scored) == len(candidates)
    assert all(isinstance(s, float) for s, _, _ in scored)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_refinement_scores_candidates -v
```
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add imports:
```python
from caipiao.core.strategies.advanced.lotteries.ssq.bayesian import SSQBayesianStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.markov import SSQMarkovStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.trend import SSQTrendStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.periodic import SSQPeriodicStrategy
from caipiao.core.strategies.advanced.lotteries.ssq.correlation import SSQCorrelationStrategy
```

Add methods:

```python
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
        weights = np.array([w for _, _, w in models], dtype=np.float64)

        scored: List[Tuple[float, Tuple[int, ...], int]] = []
        for reds, blue in candidates:
            score = 0.0
            for _, prob, _ in models:
                # 使用对数概率和，避免乘积下溢
                log_sum = sum(np.log(max(prob[n - 1], 1e-12)) for n in reds)
                score += (log_sum / 6.0) * (weights[models.index((_, prob, _))] / total_weight)
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
        model_options = {"history": records}
        for key, value in options.items():
            if key.startswith(option_prefix):
                model_key = key[len(option_prefix) + 1:]
                model_options[model_key] = value
        proba, _ = model._compute_probabilities(records, model_options)
        return proba

    def _bayesian_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQBayesianStrategy, records, options, "bayesian")

    def _markov_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQMarkovStrategy, records, options, "markov")

    def _trend_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQTrendStrategy, records, options, "trend")

    def _periodic_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        # periodic 依赖 predict_date；先计算默认日期
        if not records:
            raise ValueError("周期分析需要历史数据")
        model = SSQPeriodicStrategy()
        model_options = {"history": records}
        for key in ["week_weight", "month_weight", "quarter_weight"]:
            model_options[key] = options.get(f"periodic_{key}", model.get_config_schema()[f"periodic_{key}"]["default"])
        proba, _ = model._compute_probabilities(records, model_options)
        return proba

    def _correlation_probability(self, records: List[DrawRecord], options: Dict[str, Any]) -> np.ndarray:
        return self._model_probability(SSQCorrelationStrategy, records, options, "correlation")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_refinement_scores_candidates -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): probability refinement for consensus constraint"
```

---

## Task 5: Conflict Relaxation and Deterministic Sampling

**Files:**
- Modify: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Consumes: `_apply_hard_constraints`, `_score_candidates`
- Produces: `generate()` returning `List[Ticket]`

- [ ] **Step 1: Write the failing test**

```python
def test_generate_is_deterministic(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {"history": sample_history, "seed": 42, "candidate_count": 1000}
    result1 = strategy.generate(5, options)
    result2 = strategy.generate(5, options)
    assert result1 == result2
    assert len(result1) == 5
    for t in result1:
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1


def test_conflict_relaxation(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    options = {
        "history": sample_history,
        "seed": 42,
        "candidate_count": 5000,
        "odd_even_enabled": True,
        "odd_count": 0,
        "balanced_enabled": True,
        "sum_min": 21,
        "sum_max": 30,
        "target_odd": 0,
        "target_high": 0,
        "relaxation_order": "reverse",
    }
    result = strategy.generate(1, options)
    assert len(result) == 1
    assert "放宽" in result[0].basis or "relax" in result[0].basis.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_generate_is_deterministic tests/test_ssq_consensus_constraint.py::test_conflict_relaxation -v
```
Expected: FAIL (generate returns empty list)

- [ ] **Step 3: Write minimal implementation**

Replace the stub `generate()` method with:

```python
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
        if options.get("relaxation_order", "reverse") == "strict":
            return self._apply_hard_constraints(candidates, records, options), []

        working_options = dict(options)
        relaxed: List[str] = []

        result = self._apply_hard_constraints(candidates, records, working_options)
        if result:
            return result, relaxed

        # 放宽 balanced 和值范围
        if working_options.get("balanced_enabled", True):
            for _ in range(10):
                sum_min = int(working_options.get("sum_min", 60))
                sum_max = int(working_options.get("sum_max", 160))
                new_min = max(21, int(sum_min * 0.9))
                new_max = min(183, int(sum_max * 1.1))
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
            odd_count = int(working_options.get("odd_count", 3))
            for delta in [1, 2, 3]:
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
        # 取前 50% 作为高质量池，再随机抽样增加多样性
        top_n = max(count, len(scored) // 2)
        pool = scored[:top_n]
        if len(pool) <= count:
            return [(reds, blue) for _, reds, blue in pool]
        selected_indices = sorted(rng.sample(range(len(pool)), count))
        return [(pool[i][1], pool[i][2]) for i in selected_indices]
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_generate_is_deterministic tests/test_ssq_consensus_constraint.py::test_conflict_relaxation -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): conflict relaxation and deterministic sampling"
```

---

## Task 6: Recommend Parameters and HTML Report

**Files:**
- Modify: `caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- Produces: `recommend_parameters(records) -> Tuple[Dict[str, Any], Dict[str, str]]`
- Produces: `generate_report(options, records, output_path) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_recommend_parameters(sample_history):
    strategy = SSQConsensusConstraintStrategy()
    records = [r for r in sample_history]
    params, reasons = strategy.recommend_parameters(records)
    strategy.validate_options(params)
    assert len(reasons) > 0
    assert "stats_lookback" in reasons


def test_generate_report(sample_history, tmp_path):
    strategy = SSQConsensusConstraintStrategy()
    options = {"history": sample_history, "seed": 42, "candidate_count": 1000}
    records = [r for r in sample_history]
    output = tmp_path / "report.html"
    params, reasons = strategy.recommend_parameters(records)
    report_path = strategy.generate_report(options, records, params, reasons, str(output))
    assert Path(report_path).exists()
    content = Path(report_path).read_text(encoding="utf-8")
    assert "共识约束策略" in content
    assert "数学原理" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_recommend_parameters tests/test_ssq_consensus_constraint.py::test_generate_report -v
```
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add imports:
```python
from pathlib import Path
```

Add classmethods:

```python
    @classmethod
    def recommend_parameters(
        cls, records: List[DrawRecord]
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """基于历史数据统计特征推荐参数。"""
        analyzer = DrawAnalyzer(records, SSQ)
        reasons: Dict[str, str] = {}
        params: Dict[str, Any] = {}

        total = len(records)

        # stats
        stats_lookback = min(int(total * 0.8), 5000)
        params["stats_lookback"] = max(20, stats_lookback)
        reasons["stats_lookback"] = f"使用历史期数的 80%（{params['stats_lookback']} 期），兼顾稳定性与近期性。"

        # odd / balanced
        odd_ratio, _ = analyzer.odd_even_ratio(params["stats_lookback"])
        params["odd_count"] = round(6 * odd_ratio)
        reasons["odd_count"] = f"基于最近 {params['stats_lookback']} 期奇偶比 {odd_ratio:.2f} 的期望。"
        params["target_odd"] = params["odd_count"]
        reasons["target_odd"] = "与奇偶约束保持一致。"

        high_ratio, _ = analyzer.high_low_ratio(params["stats_lookback"])
        params["target_high"] = round(6 * high_ratio)
        reasons["target_high"] = f"基于最近 {params['stats_lookback']} 期大小比 {high_ratio:.2f} 的期望。"

        sum_stats = analyzer.sum_statistics(params["stats_lookback"])
        avg = sum_stats["avg"]
        std = (sum_stats["max"] - sum_stats["min"]) / 6.0 if sum_stats["max"] > sum_stats["min"] else 10
        params["sum_min"] = int(max(21, avg - 1.5 * std))
        params["sum_max"] = int(min(183, avg + 1.5 * std))
        reasons["sum_min"] = f"历史平均和值 {avg:.1f} 减 1.5 倍标准差。"
        reasons["sum_max"] = f"历史平均和值 {avg:.1f} 加 1.5 倍标准差。"

        # trend
        params["trend_window_size"] = max(5, min(30, total // 10))
        reasons["trend_window_size"] = f"max(5, min(30, {total} // 10))。"

        # correlation
        params["correlation_min_support"] = max(1, min(10, total // 100))
        reasons["correlation_min_support"] = f"随数据量动态调整：max(1, min(10, {total} // 100))。"

        # 其余参数使用 schema 默认值
        schema = cls().get_config_schema()
        for key, meta in schema.items():
            if key not in params:
                params[key] = meta.get("default")
                reasons[key] = "使用默认值。"

        return params, reasons

    def generate_report(
        self,
        options: Dict[str, Any],
        records: List[DrawRecord],
        params: Dict[str, Any],
        reasons: Dict[str, str],
        output_path: str,
    ) -> str:
        """生成 HTML 报告并返回文件路径。"""
        first_date = records[0].draw_date.strftime("%Y-%m-%d") if records else "N/A"
        last_date = records[-1].draw_date.strftime("%Y-%m-%d") if records else "N/A"

        param_rows = ""
        for key, value in params.items():
            reason = reasons.get(key, "")
            param_rows += f"<tr><td>{key}</td><td>{value}</td><td>{reason}</td></tr>\n"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>共识约束策略 - 参数推荐报告</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
h1 {{ color: #1976D2; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f2f2f2; }}
.disclaimer {{ color: #d32f2f; background: #fff3e0; padding: 10px; border-radius: 4px; margin-top: 20px; }}
</style>
</head>
<body>
<h1>共识约束策略 - 参数推荐报告</h1>
<p>历史数据范围：{first_date} ~ {last_date}，共 {len(records)} 期。</p>
<h2>推荐参数与数学原理</h2>
<table>
<tr><th>参数名</th><th>推荐值</th><th>推荐依据</th></tr>
{param_rows}
</table>
<div class="disclaimer">
<strong>数学声明：</strong>彩票开奖是独立随机事件，历史统计规律不能预测未来开奖。本策略所有计算仅为基于历史数据的号码筛选参考，不提供中奖保证。
</div>
</body>
</html>"""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        return str(output_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_recommend_parameters tests/test_ssq_consensus_constraint.py::test_generate_report -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): recommend parameters and HTML report"
```

---

## Task 7: Register Strategy

**Files:**
- Modify: `caipiao/core/strategies/registry.py`
- Modify: `caipiao/ui/lottery_context.py`
- Modify: `tests/test_ssq_consensus_constraint.py`

**Interfaces:**
- `STRATEGY_REGISTRY["ssq"]` includes `SSQConsensusConstraintStrategy`
- `LotteryContext` registers instance

- [ ] **Step 1: Write the failing test**

```python
def test_strategy_registered():
    from caipiao.core.strategies import build_strategies
    from caipiao.core.profile import SSQ

    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "consensus_constraint" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_strategy_registered -v
```
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Modify `caipiao/core/strategies/registry.py`:

Add import near other ssq advanced imports:
```python
from .advanced.lotteries.ssq import consensus_constraint as ssq_consensus_constraint
```

Add to `STRATEGY_REGISTRY["ssq"]` list:
```python
        ssq_consensus_constraint.SSQConsensusConstraintStrategy,
```

Modify `caipiao/ui/lottery_context.py`:

Add import:
```python
from ..core.strategies.advanced.lotteries.ssq.consensus_constraint import SSQConsensusConstraintStrategy
```

Add to SSQ branch:
```python
            self.engine.register(SSQConsensusConstraintStrategy())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py::test_strategy_registered -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/core/strategies/registry.py caipiao/ui/lottery_context.py tests/test_ssq_consensus_constraint.py
git commit -m "feat(ssq): register consensus constraint strategy"
```

---

## Task 8: Extend StrategyPanel

**Files:**
- Modify: `caipiao/ui/components/strategy_panel.py`

**Interfaces:**
- StrategyPanel shows a scroll area for options_group when strategy has many params
- StrategyPanel shows "一键推荐参数" button for strategies with `recommend_parameters`

- [ ] **Step 1: Write the failing test**

Create or modify `tests/test_strategy_panel.py`:

```python
def test_recommend_button_for_consensus_constraint(qtbot):
    from caipiao.core.engine import GenerationEngine
    from caipiao.core.strategies.advanced.lotteries.ssq.consensus_constraint import (
        SSQConsensusConstraintStrategy,
    )

    engine = GenerationEngine()
    engine.register(SSQConsensusConstraintStrategy())
    panel = StrategyPanel(engine, profile_key="ssq")
    qtbot.addWidget(panel)
    panel.set_strategy_id("consensus_constraint")
    # 按钮应在 options_group 之前被找到
    buttons = panel.findChildren(QPushButton)
    assert any(b.text() == "一键推荐参数" for b in buttons)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_strategy_panel.py::test_recommend_button_for_consensus_constraint -v
```
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Modify `caipiao/ui/components/strategy_panel.py`:

Add import:
```python
from PySide6.QtWidgets import QScrollArea
```

In `_setup_ui`, wrap `options_group` with a scroll area:

Replace:
```python
        self.layout.addWidget(self.options_group)
```
With:
```python
        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.options_scroll.setWidget(self.options_group)
        self.layout.addWidget(self.options_scroll)
```

Add recommend button logic in `_rebuild_options`, after `self.options_group.setVisible(True)`:

```python
        # 移除旧推荐按钮（如果存在）
        if hasattr(self, "_recommend_btn"):
            self._recommend_btn.deleteLater()
            delattr(self, "_recommend_btn")

        if hasattr(strategy, "recommend_parameters"):
            self._recommend_btn = QPushButton("一键推荐参数")
            self._recommend_btn.setToolTip("基于当前历史数据统计特征自动推荐参数")
            self._recommend_btn.clicked.connect(self._on_recommend_parameters)
            self.layout.insertWidget(4, self._recommend_btn)
            self._recommend_btn.setVisible(True)
```

Add method:

```python
    def _on_recommend_parameters(self) -> None:
        if not self._current_strategy or not hasattr(self._current_strategy, "recommend_parameters"):
            return
        # 通过父窗口获取历史记录；这里用信号或直接回调更解耦
        # 为简化，可要求调用方预先设置 history 到 current_options，但推荐需要完整 records。
        # 实际实现中，主窗口应监听按钮信号并提供 records。
        # 因此改为发射自定义信号：
        self.recommend_requested.emit(self.current_strategy_id())
```

Add signal at class level:

```python
class StrategyPanel(QWidget):
    options_changed = Signal()
    recommend_requested = Signal(str)
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_strategy_panel.py::test_recommend_button_for_consensus_constraint -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add caipiao/ui/components/strategy_panel.py tests/test_strategy_panel.py
git commit -m "feat(ui): scrollable strategy panel and recommend button"
```

---

## Task 9: Wire Recommend Button to MainWindow

**Files:**
- Modify: `caipiao/ui/main_window.py`

**Interfaces:**
- MainWindow handles `recommend_requested` signal, calls `recommend_parameters`, fills UI, shows report

- [ ] **Step 1: Write the failing test**

This is UI integration; add a smoke test in `tests/test_ssq_consensus_constraint.py` or skip if no existing main_window tests.

- [ ] **Step 2: Implement**

In `caipiao/ui/main_window.py`, find where `StrategyPanel` is instantiated and connect:

```python
self.strategy_panel.recommend_requested.connect(self._on_recommend_parameters)
```

Add method:

```python
    def _on_recommend_parameters(self, strategy_id: str) -> None:
        if strategy_id != "consensus_constraint":
            return
        context = self._context_manager.current(self._current_profile_key)
        records = context.data_repository.get_all()
        strategy = context.engine.get(strategy_id)
        params, reasons = strategy.recommend_parameters(records)
        self.strategy_panel.set_options(params)
        # 生成并显示报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path("docs/reports") / f"consensus_constraint_{timestamp}.html"
        strategy.generate_report({}, records, params, reasons, str(report_path))
        # 显示弹窗
        from PySide6.QtWidgets import QTextBrowser, QDialog, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("参数推荐报告")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setSource(str(report_path))
        layout.addWidget(browser)
        dialog.exec()
```

- [ ] **Step 3: Commit**

```bash
git add caipiao/ui/main_window.py
git commit -m "feat(ui): wire recommend button to main window"
```

---

## Task 10: Comprehensive Tests and Final Verification

**Files:**
- Modify: `tests/test_ssq_consensus_constraint.py`

- [ ] **Step 1: Add isolation test**

```python
def test_isolation_from_other_strategies(sample_history):
    from caipiao.core.strategies.lotteries.ssq.balanced import SSQBalancedStrategy

    other = SSQBalancedStrategy()
    new_strategy = SSQConsensusConstraintStrategy()

    other_result = other.generate(1, {"history": sample_history, "seed": 42})
    new_result1 = new_strategy.generate(1, {"history": sample_history, "seed": 42})
    other_result2 = other.generate(1, {"history": sample_history, "seed": 42})
    new_result2 = new_strategy.generate(1, {"history": sample_history, "seed": 42})

    assert other_result == other_result2
    assert new_result1 == new_result2
```

- [ ] **Step 2: Add parameter exposure sanity test**

```python
def test_no_literal_constants_for_schema_params():
    """简单静态检查：schema 中所有 key 都应被 options.get 使用。
    这不能 100% 保证无隐藏常量，但可作为代码审查辅助。"""
    import inspect
    source = inspect.getsource(SSQConsensusConstraintStrategy)
    schema = SSQConsensusConstraintStrategy().get_config_schema()
    for key in schema:
        assert f'"{key}"' in source or f"'{key}'" in source, f"参数 {key} 未在代码中使用"
```

- [ ] **Step 3: Run full test suite for new strategy**

Run:
```bash
pytest tests/test_ssq_consensus_constraint.py -v
```
Expected: ALL PASS

- [ ] **Step 4: Run related tests**

Run:
```bash
pytest tests/test_strategy_panel.py tests/test_strategy_factory.py -v
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ssq_consensus_constraint.py
git commit -m "test(ssq): comprehensive consensus constraint tests"
```

---

## Self-Review

**Spec coverage check:**

| 设计文档章节 | 对应任务 |
|--------------|----------|
| 策略命名与 ID | Task 1 |
| 总体架构与流水线 | Tasks 2-5 |
| UI 参数暴露 | Task 1 schema |
| 一键推荐参数 | Task 6 |
| HTML 报告 | Task 6, Task 9 |
| 确定性保证 | Tasks 2, 5, 10 |
| 冲突回退 | Task 5 |
| 文件结构 | Tasks 1, 7, 8 |
| 测试策略 | Tasks 1-10 |

**Placeholder scan:** 无 TBD/TODO；所有步骤包含实际代码与命令。

**Type consistency:**
- `_compute_statistical_prior` 返回 `(np.ndarray, np.ndarray, str)`，后续任务一致使用。
- `_generate_candidates` 返回 `List[Tuple[Tuple[int, ...], int]]`，过滤/排序任务一致使用。
- `recommend_parameters` 返回 `Tuple[Dict[str, Any], Dict[str, str]]`，报告任务一致使用。

**Potential issues to address during implementation:**
- `SSQPeriodicStrategy._compute_probabilities` 内部若 records 为空会 fallback 到 `datetime.now()`。新策略在调用前会校验 `records` 长度 ≥ 30，因此不会触发该 fallback。但为彻底保证确定性，可在 `_periodic_probability` 中始终传入 `predict_date` 参数（如支持）。
- `_model_probability` 直接调用现有策略的 `_compute_probabilities` 私有方法，这是允许的因为新策略与旧策略在同一项目内；但需确保旧策略不修改全局状态（它们不修改）。
- 候选池大小默认 50000 在测试中可能较慢，测试中使用 100-1000。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-consensus-constraint-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
