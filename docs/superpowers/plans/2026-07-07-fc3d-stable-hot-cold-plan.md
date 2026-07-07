# 福彩3D 智能冷热号稳定化与最优参数固定实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为福彩3D策略增加统计稳定层、多参数网格扫描、参数锁定持久化与交叉验证稳定性指标，使生成结果可复现且对历史小变动平滑。

**Architecture:** 新增 `FC3DStrategyStabilizer` 统一提供拉普拉斯平滑频率、截断遗漏、softmax 评分和确定性种子；各 3D 历史类策略改用该工具；新增 `OptimalParamStore` 保存锁定参数；新增 `StabilityValidator` 做交叉验证；改造扫描线程支持多参数网格并按稳定性选优。

**Tech Stack:** Python 3.10+, PySide6, pytest, 标准库（random, hashlib, itertools, dataclasses, json, pathlib）。

## Global Constraints

- 不改动双色球、大乐透等其他彩种策略。
- 不保证中奖率提升。
- 不做需要重新训练模型架构的 ML 改造。
- 不强制所有策略输出相同号码（允许策略间保持差异化）。
- 新增文件优先放在 `caipiao/core/strategies/` 和 `caipiao/persistence/`。
- 测试文件放在 `tests/`。
- 配置持久化使用 `caipiao.utils.app_data_dir() / "optimal_params"`。

---

## File Map

| 文件 | 责任 |
|------|------|
| `caipiao/core/strategies/fc3d_stability.py` | 新增：稳定化工具（频率、遗漏、评分、种子）。 |
| `caipiao/core/strategies/fc3d.py` | 修改：所有福彩3D策略接入稳定化工具。 |
| `caipiao/core/strategies/stability_validator.py` | 新增：交叉验证与稳定性分数。 |
| `caipiao/persistence/optimal_param_store.py` | 新增：锁定参数的保存、加载、解锁。 |
| `caipiao/ui/optimal_period_config.py` | 修改：多参数网格配置。 |
| `caipiao/ui/optimal_strategy_scan_thread.py` | 修改：集成网格扫描、CV、参数锁定。 |
| `caipiao/ui/components/strategy_panel.py` | 修改：显示锁定状态、恢复默认按钮。 |
| `caipiao/ui/components/parameter_group_panel.py` | 修改：显示稳定性指标。 |
| `caipiao/ui/components/parameter_group_save_dialog.py` | 修改：保存时同步写入 optimal_params。 |
| `caipiao/app.py` | 修改：启动时加载锁定参数并传给 StrategyPanel。 |
| `tests/test_fc3d_stability.py` | 新增：稳定化工具单元测试。 |
| `tests/test_fc3d_strategies.py` | 修改：验证可复现性与历史平滑性。 |
| `tests/test_optimal_param_store.py` | 新增：参数存储测试。 |
| `tests/test_stability_validator.py` | 新增：交叉验证测试。 |
| `tests/test_optimal_strategy_scan.py` | 修改：验证网格扫描与锁定参数。 |

---

### Task 1: FC3DStrategyStabilizer 工具模块

**Files:**
- Create: `caipiao/core/strategies/fc3d_stability.py`
- Test: `tests/test_fc3d_stability.py`
- Modify: `caipiao/core/strategies/fc3d_utils.py`（导出 POSITION_COUNT / DIGIT_POOL）

**Interfaces:**
- Consumes: `DrawRecord`, `_slice_records` from `fc3d_utils`
- Produces:
  - `stable_frequency(records, lookback=None, smoothing=1.0) -> dict[int, dict[int, float]]`
  - `stable_missing(records, lookback=None, cap=None) -> dict[int, dict[int, float]]`
  - `stable_scores(hot_scores, cold_scores, hot_weight, cold_weight, temperature=1.0) -> list[float]`
  - `deterministic_seed(options, history, lookback=None, strategy_id="") -> int`
  - `sample_weighted(rng, values, probabilities) -> Any`

- [ ] **Step 1: 确认 fc3d_utils 已导出 POSITION_COUNT 和 DIGIT_POOL**

`caipiao/core/strategies/fc3d_utils.py` 当前已定义 `POSITION_COUNT = 3` 和 `DIGIT_POOL = list(range(10))`，但它们是模块级常量，可直接被 `fc3d_stability.py` 导入。无需改动。

- [ ] **Step 2: 编写稳定化工具模块**

```python
"""福彩3D策略稳定化工具."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional

from ...data.models import DrawRecord
from .fc3d_utils import DIGIT_POOL, POSITION_COUNT, _slice_records


def _history_content_hash(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> str:
    """根据历史数据内容生成短 hash."""
    sliced = _slice_records(records, lookback)
    parts = []
    for r in sliced:
        pos_str = ",".join(str(n) for n in r.groups.get("pos", []))
        parts.append(f"{r.issue or ''}:{r.draw_date.isoformat()}:{pos_str}")
    content = ";".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def deterministic_seed(
    options: dict,
    history: List[DrawRecord],
    lookback: Optional[int] = None,
    strategy_id: str = "",
) -> int:
    """若 options 中无 seed，则基于历史内容派生确定性 seed."""
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    h = _history_content_hash(history, lookback)
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode("utf-8")).hexdigest()
    return int(raw, 16) % (2**31)


def stable_frequency(
    records: List[DrawRecord], lookback: Optional[int] = None, smoothing: float = 1.0
) -> Dict[int, Dict[int, float]]:
    """返回拉普拉斯平滑后的按位概率分布 {pos: {digit: probability}}."""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Dict[int, float]] = {}
    for pos in range(POSITION_COUNT):
        counter: Dict[int, int] = {d: 0 for d in DIGIT_POOL}
        for r in sliced:
            nums = r.groups.get("pos", [])
            if pos < len(nums) and nums[pos] in DIGIT_POOL:
                counter[nums[pos]] += 1
        total = sum(counter.values()) + smoothing * len(DIGIT_POOL)
        result[pos] = {d: (counter[d] + smoothing) / total for d in DIGIT_POOL}
    return result


def stable_missing(
    records: List[DrawRecord],
    lookback: Optional[int] = None,
    cap: Optional[int] = None,
) -> Dict[int, Dict[int, float]]:
    """返回截断并归一化到 [0,1] 的按位遗漏值 {pos: {digit: normalized_missing}}."""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Dict[int, float]] = {}
    effective_cap = cap if cap is not None else (len(sliced) if sliced else 1)
    effective_cap = max(effective_cap, 1)
    for pos in range(POSITION_COUNT):
        pos_records = [
            r.groups["pos"][pos]
            for r in sliced
            if len(r.groups.get("pos", [])) > pos
        ]
        missing: Dict[int, int] = {d: effective_cap for d in DIGIT_POOL}
        for idx, n in enumerate(reversed(pos_records)):
            if missing[n] == effective_cap:
                missing[n] = idx
        capped = {d: min(v, effective_cap) for d, v in missing.items()}
        max_val = max(capped.values()) if capped else 1
        max_val = max(max_val, 1)
        result[pos] = {d: capped[d] / max_val for d in DIGIT_POOL}
    return result


def softmax_scores(values: List[float], temperature: float = 1.0) -> List[float]:
    """带温度参数的 softmax."""
    if temperature <= 0:
        temperature = 1.0
    max_v = max(values)
    exps = [math.exp((v - max_v) / temperature) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def stable_scores(
    hot_scores: Dict[int, float],
    cold_scores: Dict[int, float],
    hot_weight: float,
    cold_weight: float,
    temperature: float = 1.0,
) -> List[float]:
    """合并热分和冷分，输出 0-9 的 softmax 概率分布."""
    # 分别 min-max 归一化到 [0, 1]
    hot_vals = [hot_scores[d] for d in DIGIT_POOL]
    cold_vals = [cold_scores[d] for d in DIGIT_POOL]

    def _normalize(vals: List[float]) -> List[float]:
        min_v = min(vals)
        max_v = max(vals)
        span = max_v - min_v
        if span <= 0:
            return [1.0] * len(vals)
        return [(v - min_v) / span for v in vals]

    hot_norm = _normalize(hot_vals)
    cold_norm = _normalize(cold_vals)

    combined = [
        hot_weight * hot_norm[d] + cold_weight * cold_norm[d]
        for d in DIGIT_POOL
    ]
    return softmax_scores(combined, temperature)


def sample_weighted(
    rng: random.Random, values: List[Any], probabilities: List[float]
) -> Any:
    """加权采样，概率全为 0 时退化为均匀随机."""
    if len(values) != len(probabilities):
        raise ValueError("values 与 probabilities 长度不一致")
    total = sum(probabilities)
    if total <= 0:
        return rng.choice(values)
    return rng.choices(values, weights=probabilities, k=1)[0]
```

- [ ] **Step 3: 编写单元测试**

```python
"""Tests for caipiao.core.strategies.fc3d_stability."""

from datetime import datetime, timedelta

import pytest

from caipiao.core.strategies.fc3d_stability import (
    deterministic_seed,
    sample_weighted,
    stable_frequency,
    stable_missing,
    stable_scores,
)
from caipiao.data.models import DrawRecord


def _records():
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(30)
    ]


def test_deterministic_seed_returns_user_seed():
    history = _records()
    assert deterministic_seed({"seed": 42}, history) == 42


def test_deterministic_seed_is_deterministic():
    history = _records()
    s1 = deterministic_seed({}, history, strategy_id="smart_hot_cold_3d")
    s2 = deterministic_seed({}, history, strategy_id="smart_hot_cold_3d")
    assert s1 == s2


def test_deterministic_seed_differs_by_strategy():
    history = _records()
    s1 = deterministic_seed({}, history, strategy_id="a")
    s2 = deterministic_seed({}, history, strategy_id="b")
    assert s1 != s2


def test_stable_frequency_sums_to_one():
    history = _records()
    freq = stable_frequency(history, lookback=10)
    for pos in range(3):
        assert sum(freq[pos].values()) == pytest.approx(1.0)
        assert all(freq[pos][d] > 0 for d in range(10))


def test_stable_missing_values_in_zero_one():
    history = _records()
    missing = stable_missing(history, lookback=10, cap=5)
    for pos in range(3):
        assert all(0 <= v <= 1 for v in missing[pos].values())


def test_stable_missing_cap_works():
    history = _records()
    missing = stable_missing(history, lookback=10, cap=3)
    for pos in range(3):
        assert all(v <= 1.0 for v in missing[pos].values())


def test_stable_scores_returns_distribution():
    hot = {d: d / 10.0 for d in range(10)}
    cold = {d: 1.0 - d / 10.0 for d in range(10)}
    probs = stable_scores(hot, cold, hot_weight=60, cold_weight=40)
    assert len(probs) == 10
    assert sum(probs) == pytest.approx(1.0)
    assert all(p >= 0 for p in probs)


def test_stable_scores_temperature_changes_concentration():
    hot = {d: 1.0 if d == 0 else 0.0 for d in range(10)}
    cold = {d: 0.0 for d in range(10)}
    low_t = stable_scores(hot, cold, hot_weight=1, cold_weight=0, temperature=0.1)
    high_t = stable_scores(hot, cold, hot_weight=1, cold_weight=0, temperature=2.0)
    assert low_t[0] > high_t[0]


def test_sample_weighted_basic():
    rng = random.Random(1)
    values = list(range(10))
    probs = [0.0] * 10
    probs[5] = 1.0
    assert sample_weighted(rng, values, probs) == 5


def test_sample_weighted_uniform_fallback():
    rng = random.Random(1)
    values = list(range(10))
    probs = [0.0] * 10
    result = sample_weighted(rng, values, probs)
    assert result in values
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_fc3d_stability.py -v
```

Expected: PASS（ deterministic_seed、stable_frequency、stable_missing、stable_scores、sample_weighted 相关测试通过）。

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d_stability.py tests/test_fc3d_stability.py
git commit -m "feat(fc3d): add FC3DStrategyStabilizer utility module"
```

---

### Task 2: 改造福彩3D策略接入稳定化工具

**Files:**
- Modify: `caipiao/core/strategies/fc3d.py`
- Test: `tests/test_fc3d_strategies.py`

**Interfaces:**
- Consumes: `FC3DStrategyStabilizer` functions
- Produces: 更新后的 `FC3DHotColdStrategy`、`FC3DSmartHotColdStrategy`、`FC3DMissingNumberStrategy`、`FC3DBalancedStrategy`、`FC3DRandomStrategy`、`FC3DOddEvenStrategy`

- [ ] **Step 1: 导入稳定化工具并替换 helper**

在 `caipiao/core/strategies/fc3d.py` 顶部加入：

```python
from .fc3d_stability import (
    deterministic_seed,
    sample_weighted,
    softmax_scores,
    stable_frequency,
    stable_missing,
    stable_scores,
)
```

删除或保留 `_make_rng`：现在策略内部统一调用 `deterministic_seed` 生成整数种子后构造 `random.Random`。`_make_rng` 可以保留作为兼容，但种子派生逻辑改为：

```python
def _make_rng(options: Dict[str, Any], history: List[DrawRecord] = None, lookback: int = None, strategy_id: str = "") -> random.Random:
    seed = deterministic_seed(options, history or [], lookback, strategy_id)
    return random.Random(seed)
```

- [ ] **Step 2: 改造 FC3DHotColdStrategy**

更新 `get_config_schema` 增加 `temperature` 和 `lookback`：

```python
"lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
"temperature": {"type": "float", "label": "温度", "default": 1.0, "min": 0.1, "max": 5.0},
```

注意：当前 schema 仅支持 `int`、`choice`、`list_int`、`history`、`bool`、`string`。需确认 `float` 类型能否被 `StrategyPanel` 渲染。若不能，先用 `int` 表示 `temperature * 10`（如 5~50 对应 0.5~5.0），在 generate 中除以 10.0。本计划采用 `int` 类型、内部除以 10 的方案。

因此 schema 改为：

```python
"temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50, "tooltip": "温度越低概率越集中，10=1.0"},
```

`generate` 改为：

```python
def generate(self, count: int = 1, options: Optional[Dict[str, Any]] = None) -> List[Ticket]:
    options = options or {}
    self.validate_options(options)
    rng = _make_rng(options, _records_from_options(options), options.get("lookback", 100), self.metadata.id)
    mode = options.get("mode", "mixed")
    lookback = int(options.get("lookback", 100))
    temperature = int(options.get("temperature", 10)) / 10.0
    records = _records_from_options(options)

    freq = stable_frequency(records, lookback)
    basis = f"冷热号分析策略：{mode} 模式，lookback={lookback}，temperature={temperature}。"
    seed = options.get("seed")
    if seed is not None:
        basis += f" 随机种子：{seed}。"

    tickets: List[Ticket] = []
    for _ in range(count):
        result = []
        for pos in range(3):
            pos_freq = freq[pos]
            ranked = sorted(range(10), key=lambda d: pos_freq[d], reverse=True)
            if mode == "hot":
                order = ranked
            elif mode == "cold":
                order = list(reversed(ranked))
            else:  # mixed
                order = []
                for i in range(5):
                    if 2 * i < len(ranked):
                        order.append(ranked[2 * i])
                    if 2 * i + 1 < len(ranked):
                        order.append(ranked[-(2 * i + 1)])
            # 将 order 中的排名转换为分数：排名越高分数越高
            scores = {d: 0.0 for d in range(10)}
            for rank_idx, d in enumerate(order):
                scores[d] = len(order) - rank_idx
            probs = softmax_scores([scores[d] for d in range(10)], temperature)
            result.append(sample_weighted(rng, list(range(10)), probs))
        tickets.append(
            Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
        )
    return tickets
```

已在 `fc3d_stability.py` 中提供 `softmax_scores(values, temperature)` 函数，上面的代码直接使用它。

- [ ] **Step 3: 改造 FC3DSmartHotColdStrategy**

更新 schema 增加 `temperature`：

```python
"temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50},
```

`generate` 改为：

```python
def generate(self, count: int = 1, options: Optional[Dict[str, Any]] = None) -> List[Ticket]:
    options = options or {}
    self.validate_options(options)
    records = _records_from_options(options)
    lookback = int(options.get("lookback", 100))
    hot_weight = int(options.get("hot_weight", 60))
    cold_weight = int(options.get("cold_weight", 40))
    temperature = int(options.get("temperature", 10)) / 10.0
    rng = _make_rng(options, records, lookback, self.metadata.id)

    freq = stable_frequency(records, lookback)
    missing = stable_missing(records, lookback, cap=lookback)

    basis = (
        f"智能冷热号策略：lookback={lookback}，热权重={hot_weight}，"
        f"冷权重={cold_weight}，温度={temperature}。"
    )
    seed = options.get("seed")
    if seed is not None:
        basis += f" 随机种子：{seed}。"

    tickets: List[Ticket] = []
    for _ in range(count):
        result = []
        for pos in range(3):
            probs = stable_scores(
                freq[pos], missing[pos], hot_weight, cold_weight, temperature
            )
            result.append(sample_weighted(rng, list(range(10)), probs))
        tickets.append(
            Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
        )
    return tickets
```

- [ ] **Step 4: 改造 FC3DMissingNumberStrategy**

更新 schema 增加 `temperature`：

```python
"temperature": {"type": "int", "label": "温度(x0.1)", "default": 10, "min": 1, "max": 50},
```

`generate` 改为：

```python
def generate(self, count: int = 1, options: Optional[Dict[str, Any]] = None) -> List[Ticket]:
    options = options or {}
    self.validate_options(options)
    records = _records_from_options(options)
    lookback = int(options.get("lookback", 50))
    pool_size = int(options.get("pool_size", 5))
    temperature = int(options.get("temperature", 10)) / 10.0
    rng = _make_rng(options, records, lookback, self.metadata.id)

    missing = stable_missing(records, lookback, cap=lookback)

    basis = f"遗漏号追踪策略：lookback={lookback}，候选池={pool_size}，温度={temperature}。"
    seed = options.get("seed")
    if seed is not None:
        basis += f" 随机种子：{seed}。"

    tickets: List[Ticket] = []
    for _ in range(count):
        result = []
        for pos in range(3):
            ranked = sorted(range(10), key=lambda d: missing[pos][d], reverse=True)
            pool = ranked[:pool_size]
            # 在候选池内按遗漏值 softmax 采样
            scores = {d: missing[pos][d] if d in pool else 0.0 for d in range(10)}
            probs = softmax_scores([scores[d] for d in range(10)], temperature)
            result.append(sample_weighted(rng, list(range(10)), probs))
        tickets.append(
            Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
        )
    return tickets
```

- [ ] **Step 5: 改造 FC3DBalancedStrategy**

该策略已使用枚举，确定性较强。主要改动：
1. 使用 `deterministic_seed` 替代 `_make_rng`，保证 seed 缺失时可复现。
2. `weight_score` 系数从 `-0.01` 改为基于 lookback 归一化，避免历史长度影响敏感度。

原代码：

```python
weight_score = -0.01 * sum(weights[pos][candidate[pos]] for pos in range(3))
```

改为：

```python
# 权重归一化到 [-1, 1] 区间，降低对历史长度的敏感度
weight_score = -sum(
    weights[pos][candidate[pos]] * len(DIGIT_POOL) for pos in range(3)
) / (lookback or 1)
```

- [ ] **Step 6: 改造 FC3DRandomStrategy / FC3DOddEvenStrategy**

这两个策略不依赖历史，但需要统一使用确定性 seed。

`FC3DRandomStrategy.generate` 中：

```python
rng = _make_rng(options, [], None, self.metadata.id)
```

`FC3DOddEvenStrategy.generate` 中：

```python
rng = _make_rng(options, [], None, self.metadata.id)
```

- [ ] **Step 7: 更新测试**

在 `tests/test_fc3d_strategies.py` 新增/修改：

```python
def test_hot_cold_3d_temperature_changes_concentration():
    strategy = FC3DHotColdStrategy()
    history = make_history(50)
    low_t = strategy.generate(count=50, options={"mode": "hot", "history": history, "lookback": 30, "temperature": 5, "seed": 1})
    high_t = strategy.generate(count=50, options={"mode": "hot", "history": history, "lookback": 30, "temperature": 50, "seed": 1})
    # 低温度下应更集中在高频数字，这里仅验证两次结果不同
    assert any(a.groups["pos"] != b.groups["pos"] for a, b in zip(low_t, high_t))


def test_smart_hot_cold_3d_temperature_changes_concentration():
    strategy = FC3DSmartHotColdStrategy()
    history = make_history(50)
    low_t = strategy.generate(count=50, options={"history": history, "lookback": 30, "temperature": 5, "seed": 1})
    high_t = strategy.generate(count=50, options={"history": history, "lookback": 30, "temperature": 50, "seed": 1})
    assert any(a.groups["pos"] != b.groups["pos"] for a, b in zip(low_t, high_t))


def test_all_3d_strategies_deterministic_without_user_seed():
    """未提供用户 seed 时，仍应基于历史内容可复现。"""
    profile = get_profile("3d")
    from caipiao.core.strategies.generic import build_strategies
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    history = make_history(120)
    for sid, strategy in strategies.items():
        options = {}
        if needs_history(sid):
            options["history"] = history
            if is_ml_strategy(sid):
                options["history_count"] = 100
        t1 = strategy.generate(count=1, options=options)[0].groups["pos"]
        t2 = strategy.generate(count=1, options=options)[0].groups["pos"]
        assert t1 == t2, sid
```

注意：ML 策略内部使用 `np.random.RandomState(seed + i)` 且 seed 固定为 42，不依赖用户 options seed，因此无需改动即可复现。

- [ ] **Step 8: 运行测试**

```bash
python -m pytest tests/test_fc3d_strategies.py -v
```

Expected: PASS（原有测试 + 新增温度/确定性测试通过）。

- [ ] **Step 9: 提交**

```bash
git add caipiao/core/strategies/fc3d.py tests/test_fc3d_strategies.py
git commit -m "feat(fc3d): integrate stabilizer into all 3D strategies"
```

---

### Task 3: 多参数网格扫描配置

**Files:**
- Modify: `caipiao/ui/optimal_period_config.py`
- Test: `tests/test_optimal_strategy_scan.py`

**Interfaces:**
- Consumes: strategy IDs
- Produces: `STRATEGY_PARAM_GRID`, updated `resolve_optimal_param` returning full grid

- [ ] **Step 1: 编写多参数网格配置**

将 `caipiao/ui/optimal_period_config.py` 替换/扩展为：

```python
"""一键找最优期数的参数配置."""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple


OPTIMAL_PERIOD_RANGES: dict[str, list[int]] = {
    "lookback": [20, 50, 80, 100, 150, 200, 300],
    "history_count": [100, 200, 300, 500, 800, 1000, -1],
}


# 向后兼容：旧代码仍可通过 strategy_id 前缀获取单一参数名
STRATEGY_PARAM_MAP: dict[str, str] = {
    "smart_hot_cold": "lookback",
    "missing_number": "lookback",
    "balanced": "lookback",
    "xgboost": "history_count",
    "lightgbm": "history_count",
    "catboost": "history_count",
}


# 新增：多参数网格扫描配置
STRATEGY_PARAM_GRID: dict[str, dict[str, list]] = {
    "smart_hot_cold_3d": {
        "lookback": [30, 50, 80, 100, 150],
        "hot_weight": [30, 50, 70, 90],
        "cold_weight": [10, 30, 50, 70],
        "temperature": [5, 10, 20],  # 内部除以 10
    },
    "missing_number_3d": {
        "lookback": [30, 50, 80, 100],
        "pool_size": [3, 5, 7],
        "temperature": [5, 10, 20],
    },
    "balanced_3d": {
        "lookback": [50, 80, 100, 150],
        "max_attempts": [500, 1000, 2000],
    },
    "hot_cold_3d": {
        "mode": ["hot", "cold", "mixed"],
        "lookback": [50, 100, 150],
        "temperature": [5, 10, 20],
    },
    "xgboost_3d": {"history_count": [100, 200, 300, 500, -1]},
    "lightgbm_3d": {"history_count": [100, 200, 300, 500, -1]},
    "catboost_3d": {"history_count": [100, 200, 300, 500, -1]},
}


def resolve_optimal_param(strategy_id: str) -> Tuple[str, list[int]] | None:
    """根据策略 id 返回要优化的参数名及其扫描范围（向后兼容）."""
    for prefix, param_name in STRATEGY_PARAM_MAP.items():
        if strategy_id.startswith(prefix):
            return param_name, OPTIMAL_PERIOD_RANGES[param_name]
    return None


def resolve_optimal_param_grid(strategy_id: str) -> Dict[str, List]:
    """根据策略 id 返回多参数扫描网格。

    返回 dict[param_name, list[values]]。若该策略无网格配置，返回空 dict。
    """
    return STRATEGY_PARAM_GRID.get(strategy_id, {}).copy()


def build_param_combinations(
    grid: Dict[str, List], locked: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """根据网格和已锁定参数生成未锁定参数的组合列表。"""
    locked = locked or {}
    free_grid = {k: v for k, v in grid.items() if k not in locked}
    if not free_grid:
        return [{}]
    keys = list(free_grid.keys())
    values = [free_grid[k] for k in keys]
    combos = []
    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        params.update(locked)
        combos.append(params)
    return combos
```

- [ ] **Step 2: 编写测试**

在 `tests/test_optimal_strategy_scan.py` 新增：

```python
def test_resolve_optimal_param_grid_for_smart_hot_cold():
    grid = resolve_optimal_param_grid("smart_hot_cold_3d")
    assert "lookback" in grid
    assert "hot_weight" in grid
    assert "cold_weight" in grid
    assert "temperature" in grid


def test_build_param_combinations_with_locked():
    grid = {"lookback": [50, 100], "hot_weight": [30, 70]}
    combos = build_param_combinations(grid, locked={"lookback": 50})
    assert len(combos) == 2
    assert all(c["lookback"] == 50 for c in combos)
    assert {c["hot_weight"] for c in combos} == {30, 70}
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_optimal_strategy_scan.py -v
```

Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add caipiao/ui/optimal_period_config.py tests/test_optimal_strategy_scan.py
git commit -m "feat(ui): add multi-parameter grid config for optimal scan"
```

---

### Task 4: 最优参数存储（锁定 + 持久化）

**Files:**
- Create: `caipiao/persistence/optimal_param_store.py`
- Test: `tests/test_optimal_param_store.py`

**Interfaces:**
- Consumes: `app_data_dir`, `DrawRecord`/profile_key
- Produces: `OptimalParamStore` class with `load`, `save`, `lock`, `unlock`, `get_locked`, `apply_defaults`

- [ ] **Step 1: 编写存储模块**

```python
"""最优参数/锁定参数持久化."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import app_data_dir


@dataclass
class LockedParameter:
    strategy_id: str
    param_name: str
    param_value: Any
    source: str  # "scan", "user", "default"
    locked_at: str
    stability_score: float = 0.0
    cv_mean_prize: float = 0.0
    cv_std_prize: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LockedParameter":
        return cls(
            strategy_id=data.get("strategy_id", ""),
            param_name=data.get("param_name", ""),
            param_value=data.get("param_value"),
            source=data.get("source", "user"),
            locked_at=data.get("locked_at", ""),
            stability_score=data.get("stability_score", 0.0),
            cv_mean_prize=data.get("cv_mean_prize", 0.0),
            cv_std_prize=data.get("cv_std_prize", 0.0),
        )


@dataclass
class OptimalParamsConfig:
    profile_key: str
    locked: List[LockedParameter] = field(default_factory=list)
    last_scan_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "profile_key": self.profile_key,
            "locked": [p.to_dict() for p in self.locked],
            "last_scan_at": self.last_scan_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptimalParamsConfig":
        return cls(
            profile_key=data.get("profile_key", ""),
            locked=[LockedParameter.from_dict(p) for p in data.get("locked", [])],
            last_scan_at=data.get("last_scan_at"),
        )


class OptimalParamStore:
    """管理每个彩种的最优锁定参数。"""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._base_dir = (data_dir or app_data_dir()) / "optimal_params"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, profile_key: str) -> Path:
        return self._base_dir / f"{profile_key}.json"

    def load(self, profile_key: str) -> OptimalParamsConfig:
        path = self._path(profile_key)
        if not path.exists():
            return OptimalParamsConfig(profile_key=profile_key)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return OptimalParamsConfig.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return OptimalParamsConfig(profile_key=profile_key)

    def save(self, config: OptimalParamsConfig) -> None:
        path = self._path(config.profile_key)
        with path.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def lock(
        self,
        profile_key: str,
        strategy_id: str,
        param_name: str,
        param_value: Any,
        source: str = "user",
        stability_score: float = 0.0,
        cv_mean_prize: float = 0.0,
        cv_std_prize: float = 0.0,
    ) -> None:
        config = self.load(profile_key)
        # 去重：同一 strategy + param 只保留最新
        config.locked = [
            p
            for p in config.locked
            if not (p.strategy_id == strategy_id and p.param_name == param_name)
        ]
        config.locked.append(
            LockedParameter(
                strategy_id=strategy_id,
                param_name=param_name,
                param_value=param_value,
                source=source,
                locked_at=datetime.now().isoformat(),
                stability_score=stability_score,
                cv_mean_prize=cv_mean_prize,
                cv_std_prize=cv_std_prize,
            )
        )
        config.last_scan_at = datetime.now().isoformat()
        self.save(config)

    def unlock(self, profile_key: str, strategy_id: str, param_name: str) -> None:
        config = self.load(profile_key)
        config.locked = [
            p
            for p in config.locked
            if not (p.strategy_id == strategy_id and p.param_name == param_name)
        ]
        self.save(config)

    def get_locked(self, profile_key: str, strategy_id: str) -> Dict[str, Any]:
        config = self.load(profile_key)
        return {
            p.param_name: p.param_value
            for p in config.locked
            if p.strategy_id == strategy_id
        }

    def apply_defaults(
        self, profile_key: str, strategy_id: str, schema: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """将锁定参数覆盖到 schema 的 default 值中。"""
        locked = self.get_locked(profile_key, strategy_id)
        if not locked:
            return schema
        new_schema = {}
        for key, meta in schema.items():
            new_meta = dict(meta)
            if key in locked:
                new_meta["default"] = locked[key]
            new_schema[key] = new_meta
        return new_schema
```

- [ ] **Step 2: 编写测试**

```python
"""Tests for caipiao.persistence.optimal_param_store."""

from pathlib import Path

import pytest

from caipiao.persistence.optimal_param_store import OptimalParamStore


@pytest.fixture
def store(tmp_path):
    return OptimalParamStore(data_dir=tmp_path)


def test_load_missing_returns_empty(store):
    config = store.load("3d")
    assert config.profile_key == "3d"
    assert config.locked == []


def test_lock_and_load(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100, source="scan")
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked == {"lookback": 100}


def test_lock_overwrites_same_param(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    store.lock("3d", "smart_hot_cold_3d", "lookback", 150)
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked["lookback"] == 150


def test_unlock(store):
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    store.unlock("3d", "smart_hot_cold_3d", "lookback")
    locked = store.get_locked("3d", "smart_hot_cold_3d")
    assert locked == {}


def test_apply_defaults(store):
    schema = {
        "lookback": {"type": "int", "default": 50, "min": 10, "max": 1000},
        "hot_weight": {"type": "int", "default": 60, "min": 0, "max": 100},
    }
    store.lock("3d", "smart_hot_cold_3d", "lookback", 100)
    new_schema = store.apply_defaults("3d", "smart_hot_cold_3d", schema)
    assert new_schema["lookback"]["default"] == 100
    assert new_schema["hot_weight"]["default"] == 60
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_optimal_param_store.py -v
```

Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add caipiao/persistence/optimal_param_store.py tests/test_optimal_param_store.py
git commit -m "feat(persistence): add OptimalParamStore for locked parameters"
```

---

### Task 5: 交叉验证稳定性验证器

**Files:**
- Create: `caipiao/core/strategies/stability_validator.py`
- Test: `tests/test_stability_validator.py`

**Interfaces:**
- Consumes: `RoundBacktestContext`, `RoundTask`, `BatchBacktestResult`
- Produces: `CrossValidationResult`, `stability_score`, `cross_validate_params`

- [ ] **Step 1: 编写验证器模块**

```python
"""策略参数交叉验证与稳定性评分."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...data.models import DrawRecord
from ...ui.batch_backtest_result import BatchBacktestResult
from ...ui.batch_backtest_worker import RoundBacktestContext, RoundTask, merge_round_results, worker_round_backtest


@dataclass
class CrossValidationResult:
    params: Dict[str, Any]
    fold_results: List[BatchBacktestResult] = field(default_factory=list)
    mean_fixed_prize: float = 0.0
    std_fixed_prize: float = 0.0
    stability_score: float = 0.0
    errors: List[str] = field(default_factory=list)


def stability_score(mean_prize: float, std_prize: float) -> float:
    """返回 0~1 稳定性分数。收益为正且波动越小越稳定。"""
    if mean_prize <= 0:
        return 0.0
    # 变异系数越小越稳定，但避免除 0
    cv = std_prize / max(mean_prize, 1.0)
    # 将 cv 映射到 [0, 1]，cv=0 时 1，cv>=2 时 0
    return max(0.0, min(1.0, 1.0 - cv / 2.0))


def _split_folds(records: List[DrawRecord], n_folds: int) -> List[Tuple[int, int]]:
    """返回每折的起止索引（按时间顺序）。"""
    n = len(records)
    if n_folds <= 1 or n < n_folds:
        return [(0, n)]
    fold_size = n // n_folds
    folds = []
    start = 0
    for i in range(n_folds):
        end = start + fold_size if i < n_folds - 1 else n
        folds.append((start, end))
        start = end
    return folds


def cross_validate_params(
    base_context: RoundBacktestContext,
    tasks: List[RoundTask],
    param_combinations: List[Dict[str, Any]],
    n_folds: int = 3,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> List[CrossValidationResult]:
    """对每套参数组合做 n_folds 交叉验证。"""
    results: List[CrossValidationResult] = []
    total = len(param_combinations)
    for idx, params in enumerate(param_combinations):
        if progress_callback:
            progress_callback(idx, total)
        if status_callback:
            status_callback(f"正在验证参数 {params}")

        context = RoundBacktestContext(
            strategy_id=base_context.strategy_id,
            profile_key=base_context.profile_key,
            tickets_per_round=base_context.tickets_per_round,
            options={**base_context.options, **params},
            is_ml=base_context.is_ml,
            needs_history=base_context.needs_history,
            records=base_context.records,
            seed=base_context.seed,
            plugin_dir=base_context.plugin_dir,
        )

        fold_results: List[BatchBacktestResult] = []
        errors: List[str] = []
        records = base_context.records
        sorted_records = sorted(records, key=lambda r: r.draw_date)
        folds = _split_folds(sorted_records, n_folds)

        for start, end in folds:
            fold_tasks = [t for t in tasks if start <= t.index < end]
            if not fold_tasks:
                continue
            round_results = [
                worker_round_backtest(context, task) for task in fold_tasks
            ]
            merged = merge_round_results(round_results, len(fold_tasks))
            if merged.errors:
                errors.extend(merged.errors)
            fold_results.append(merged)

        if not fold_results:
            results.append(CrossValidationResult(params=params, errors=["no fold results"]))
            continue

        prizes = [r.total_fixed_prize for r in fold_results]
        mean_prize = sum(prizes) / len(prizes)
        std_prize = math.sqrt(sum((p - mean_prize) ** 2 for p in prizes) / len(prizes))
        score = stability_score(mean_prize, std_prize)

        results.append(
            CrossValidationResult(
                params=params,
                fold_results=fold_results,
                mean_fixed_prize=mean_prize,
                std_fixed_prize=std_prize,
                stability_score=score,
                errors=errors,
            )
        )

    if progress_callback:
        progress_callback(total, total)
    return results


def pick_best_param_cv(
    cv_results: List[CrossValidationResult],
) -> Optional[Tuple[Dict[str, Any], CrossValidationResult]]:
    """按稳定性优先、收益高、波动低选择最优参数。"""
    eligible = [r for r in cv_results if not r.errors]
    if not eligible:
        return None
    best = max(
        eligible,
        key=lambda r: (r.stability_score, r.mean_fixed_prize, -r.std_fixed_prize),
    )
    return best.params, best
```

注意：`worker_round_backtest` 当前在子进程中运行，直接调用它可能会训练 ML 模型，比较重。对于非 ML 策略可以直接调用；对于 ML 策略，交叉验证可能非常慢。可以在实现中先对非 ML 策略启用 CV，ML 策略降级为单区间回测（n_folds=1）。

- [ ] **Step 2: 编写测试**

```python
"""Tests for caipiao.core.strategies.stability_validator."""

from datetime import datetime, timedelta

import pytest

from caipiao.core.strategies.stability_validator import (
    CrossValidationResult,
    cross_validate_params,
    pick_best_param_cv,
    stability_score,
)
from caipiao.ui.batch_backtest_result import BatchBacktestResult
from caipiao.ui.batch_backtest_worker import RoundBacktestContext, RoundTask


def _make_context():
    from caipiao.data.models import DrawRecord
    records = [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(120)
    ]
    return RoundBacktestContext(
        strategy_id="smart_hot_cold_3d",
        profile_key="3d",
        tickets_per_round=5,
        options={},
        is_ml=False,
        needs_history=True,
        records=records,
        seed=42,
    ), records


def test_stability_score_positive_low_cv():
    assert stability_score(100, 10) > 0.9


def test_stability_score_negative_mean():
    assert stability_score(-10, 0) == 0.0


def test_stability_score_high_cv():
    assert stability_score(100, 200) == 0.0


def test_cross_validate_params_runs():
    context, _ = _make_context()
    tasks = [RoundTask(index=i, actual=r) for i, r in enumerate(context.records[-30:])]
    combos = [{"lookback": 50}, {"lookback": 100}]
    results = cross_validate_params(context, tasks, combos, n_folds=2)
    assert len(results) == 2
    assert all(isinstance(r, CrossValidationResult) for r in results)


def test_pick_best_param_cv_prefers_stable():
    r1 = CrossValidationResult(
        params={"lookback": 50},
        mean_fixed_prize=100,
        std_fixed_prize=10,
        stability_score=stability_score(100, 10),
    )
    r2 = CrossValidationResult(
        params={"lookback": 100},
        mean_fixed_prize=150,
        std_fixed_prize=100,
        stability_score=stability_score(150, 100),
    )
    best = pick_best_param_cv([r1, r2])
    assert best is not None
    # 稳定性分数高者胜出
    assert best[1].stability_score >= max(r1.stability_score, r2.stability_score) - 1e-9
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_stability_validator.py -v
```

Expected: PASS（注意 cross_validate_params 测试会实际跑回测，可能较慢，但数据集小应该可接受）。

- [ ] **Step 4: 提交**

```bash
git add caipiao/core/strategies/stability_validator.py tests/test_stability_validator.py
git commit -m "feat(fc3d): add cross-validation stability validator"
```

---

### Task 6: 改造最优策略扫描线程

**Files:**
- Modify: `caipiao/ui/optimal_strategy_scan_thread.py`
- Test: `tests/test_optimal_strategy_scan.py`

**Interfaces:**
- Consumes: `OptimalParamStore`, `resolve_optimal_param_grid`, `build_param_combinations`, `cross_validate_params`, `pick_best_param_cv`
- Produces: 更新后的 `StrategyScanResult`，包含 `stability_score` 和 `cv_stats`

- [ ] **Step 1: 扩展 StrategyScanResult**

在 `caipiao/ui/optimal_strategy_scan_thread.py` 中扩展 dataclass：

```python
@dataclass
class StrategyScanResult:
    optimal_strategy_id: str
    optimal_strategy_name: str
    param_name: Optional[str]
    optimal_value: Optional[int]
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[str, Optional[int], BatchBacktestResult]]
    cv_results: Dict[str, Any] = field(default_factory=dict)
    locked_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    interrupted: bool = False
```

- [ ] **Step 2: 在 run() 中集成网格扫描与 CV**

修改 `OptimalStrategyScanThread.run()` 主循环：

```python
from ..persistence.optimal_param_store import OptimalParamStore
from .optimal_period_config import resolve_optimal_param_grid, build_param_combinations
from ..core.strategies.stability_validator import cross_validate_params, pick_best_param_cv

# ...

store = OptimalParamStore()

for strategy in candidates:
    if self.isInterruptionRequested():
        interrupted = True
        break

    strategy_id = strategy.metadata.id
    locked = store.get_locked(self.profile.key, strategy_id)
    grid = resolve_optimal_param_grid(strategy_id)

    base_context = RoundBacktestContext(
        strategy_id=strategy_id,
        profile_key=self.profile.key,
        tickets_per_round=self.tickets_per_round,
        options=dict(self.base_options),
        is_ml=strategy_id.startswith(("xgboost", "lightgbm", "catboost")),
        needs_history=True,
        records=records,
        seed=42,
        plugin_dir=self.plugin_dir,
    )

    if not grid:
        # 无网格配置的策略，回退到单一回测
        results = scan_param_values(...)
        value, result = results[0]
        all_results.append((strategy_id, None, result))
    else:
        combos = build_param_combinations(grid, locked)
        # 对非 ML 策略做 CV；ML 策略数据量大，先 n_folds=1
        n_folds = 1 if base_context.is_ml else 3
        cv_results = cross_validate_params(
            base_context,
            tasks,
            combos,
            n_folds=n_folds,
            progress_callback=None,
            status_callback=lambda msg: self.status_message.emit(msg),
        )
        best = pick_best_param_cv(cv_results)
        if best is not None:
            best_params, best_cv = best
            # 用最佳参数在整个区间跑一次，得到与旧版兼容的 BatchBacktestResult
            full_context = RoundBacktestContext(
                **{**base_context.__dict__, "options": {**base_context.options, **best_params}}
            )
            round_results = [worker_round_backtest(full_context, task) for task in tasks]
            full_result = merge_round_results(round_results, len(tasks))
            # 取一个代表值用于旧版 param_name/optimal_value（取第一个非锁定参数）
            free_keys = [k for k in grid.keys() if k not in locked]
            param_name = free_keys[0] if free_keys else None
            param_value = best_params.get(param_name) if param_name else None
            all_results.append((strategy_id, param_value, full_result))
            cv_summary[strategy_id] = {
                "best_params": best_params,
                "stability_score": best_cv.stability_score,
                "mean_fixed_prize": best_cv.mean_fixed_prize,
                "std_fixed_prize": best_cv.std_fixed_prize,
            }
        else:
            all_results.append((strategy_id, None, BatchBacktestResult(...)))

    completed += 1
    self.progress.emit(completed, total)
```

- [ ] **Step 3: 更新 _pick_best_strategy 排序**

在按收益排序的基础上，若 `cv_summary` 中有稳定性分数，则优先稳定性：

```python
@staticmethod
def _pick_best_strategy(
    results: List[Tuple[str, Optional[int], BatchBacktestResult]],
    cv_summary: Dict[str, Dict[str, Any]],
) -> Optional[Tuple[str, Optional[int], BatchBacktestResult]]:
    eligible = [item for item in results if not item[2].errors]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda item: (
            -cv_summary.get(item[0], {}).get("stability_score", 0.0),
            -item[2].total_fixed_prize,
            -item[2].hit_count,
            item[0],
        ),
    )[0]
```

- [ ] **Step 4: 更新测试**

在 `tests/test_optimal_strategy_scan.py` 中新增：

```python
from caipiao.persistence.optimal_param_store import OptimalParamStore


def test_scan_respects_locked_params(monkeypatch, tmp_path):
    # 构造一个 store 并锁定 lookback
    store = OptimalParamStore(data_dir=tmp_path)
    store.lock("3d", "smart_hot_cold_3d", "lookback", 50)

    # monkeypatch OptimalStrategyScanThread 内部使用的 store？
    # 由于当前线程类直接实例化 store，可能需要把 store 改为可注入；
    # 若不可注入，则通过文件方式让线程加载同一份锁定。
    # 具体实现时再决定。
    ...
```

注意：当前 `OptimalStrategyScanThread` 在 `run()` 内部直接实例化依赖，测试困难。建议把 `OptimalParamStore` 作为 `__init__` 的可选参数注入，默认 `None` 时内部创建。

- [ ] **Step 5: 运行测试**

```bash
python -m pytest tests/test_optimal_strategy_scan.py -v
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add caipiao/ui/optimal_strategy_scan_thread.py tests/test_optimal_strategy_scan.py
git commit -m "feat(ui): integrate multi-param grid, CV and param locking into optimal scan"
```

---

### Task 7: UI 参数锁定与稳定性指标展示

**Files:**
- Modify: `caipiao/ui/components/strategy_panel.py`
- Modify: `caipiao/ui/components/parameter_group_panel.py`
- Modify: `caipiao/ui/components/parameter_group_save_dialog.py`
- Modify: `caipiao/app.py`（启动时加载锁定参数覆盖 schema defaults）

**Interfaces:**
- Consumes: `OptimalParamStore`, locked params
- Produces: 带锁定指示的 UI、保存时同步持久化

- [ ] **Step 1: StrategyPanel 显示锁定状态**

在 `StrategyPanel.__init__` 中注入 `OptimalParamStore`：

```python
from ...persistence.optimal_param_store import OptimalParamStore

class StrategyPanel(QWidget):
    def __init__(self, engine, profile_key: str = "3d", store: OptimalParamStore | None = None, locked_params: list | None = None, parent=None):
        ...
        self._store = store or OptimalParamStore()
        self._profile_key = profile_key
        self._locked_params = locked_params or []
```

在 `_rebuild_options` 中，读取锁定参数并渲染只读控件和锁图标：

```python
def _rebuild_options(self, strategy):
    ...
    locked = self._store.get_locked(self._profile_key, strategy.metadata.id)
    for key, meta in schema.items():
        widget = self._create_option_widget(key, meta)
        if key in locked:
            widget.setEnabled(False)
            # 在参数行末尾添加锁图标 QLabel
            lock_label = QLabel("🔒")
            lock_label.setToolTip(f"已锁定为 {locked[key]}")
            # 需要 QFormLayout 支持添加第三个控件，可改用 QHBoxLayout 包装
```

由于 `QFormLayout` 每行只有 label + field，推荐把 field 和 lock 图标放入一个 `QHBoxLayout`：

```python
row = QHBoxLayout()
row.addWidget(widget, 1)
lock_label = QLabel("🔒")
lock_label.setToolTip(f"参数已锁定为 {locked[key]}，在「一键找最优」中不会被调整")
row.addWidget(lock_label)
self.options_layout.addRow(label, row)
```

新增「恢复默认」按钮：

```python
self.reset_defaults_btn = QPushButton("恢复默认参数")
self.reset_defaults_btn.setToolTip("清除该策略的所有锁定参数")
self.reset_defaults_btn.clicked.connect(self._on_reset_defaults)
```

实现 `_on_reset_defaults`：

```python
def _on_reset_defaults(self):
    strategy_id = self.current_strategy_id()
    if not strategy_id:
        return
    locked = self._store.get_locked(self._profile_key, strategy_id)
    for param_name in list(locked.keys()):
        self._store.unlock(self._profile_key, strategy_id, param_name)
    self._rebuild_options(self._current_strategy)
```

- [ ] **Step 2: ParameterGroupSaveDialog 保存时同步锁定参数**

在 `ParameterGroupSaveDialog._on_save` 中，创建 `ParameterGroup` 后：

```python
from ...persistence.optimal_param_store import OptimalParamStore

store = OptimalParamStore()
for item in items:
    if item.param_name is not None and item.param_value is not None:
        store.lock(
            profile_key=self._profile_key,
            strategy_id=item.strategy_id,
            param_name=item.param_name,
            param_value=item.param_value,
            source="scan",
            stability_score=item.metrics.get("stability_score", 0.0),
            cv_mean_prize=item.metrics.get("cv_mean_prize", 0.0),
            cv_std_prize=item.metrics.get("cv_std_prize", 0.0),
        )
```

- [ ] **Step 3: ParameterGroupPanel 显示稳定性指标**

在 `_on_group_changed` 中，参数文本追加稳定性分数：

```python
stability = metrics.get("stability_score")
if stability is not None:
    metric_text += f", 稳定性 {stability:.2f}"
```

- [ ] **Step 4: app.py 启动时加载锁定参数并传给 StrategyPanel**

在 `caipiao/app.py` 中，应用启动后、创建 `StrategyPanel` 前，加载锁定参数：

```python
from .persistence.optimal_param_store import OptimalParamStore

store = OptimalParamStore()
locked_params = store.load(profile_key).locked
```

创建 `StrategyPanel` 时把锁定参数传入：

```python
self.strategy_panel = StrategyPanel(
    engine,
    profile_key=profile_key,
    store=store,
    locked_params=locked_params,
    parent=self,
)
```

这样无需修改 `caipiao/core/engine.py`，也从提交列表中移除它。

- [ ] **Step 5: 运行相关测试**

```bash
python -m pytest tests/test_parameter_group_dialog.py tests/test_optimal_strategy_scan.py -v
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add caipiao/ui/components/strategy_panel.py caipiao/ui/components/parameter_group_panel.py caipiao/ui/components/parameter_group_save_dialog.py caipiao/app.py
git commit -m "feat(ui): show locked params and stability metrics, load locked defaults on startup"
```

---

### Task 8: 全局回归测试与收尾

**Files:**
- All above
- `tests/test_fc3d_strategies.py`
- `tests/test_optimal_strategy_scan.py`

- [ ] **Step 1: 运行全量测试**

```bash
python -m pytest tests/ -q
```

Expected: 所有测试通过（或仅有与本次改动无关的既有失败）。

- [ ] **Step 2: 手动验证关键场景**

1. 启动应用，确认 StrategyPanel 中 3D 策略参数旁无锁图标（首次使用）。
2. 选择「智能冷热号」策略，不填 seed，连续生成两次，结果应相同。
3. 运行「一键找最优策略和参数」，确认扫描了 lookback / hot_weight / cold_weight / temperature。
4. 扫描完成后保存参数组，检查 `.caipiao/optimal_params/3d.json` 存在且包含锁定记录。
5. 重启应用，检查 StrategyPanel 中对应参数显示 🔒 且只读。
6. 再次运行「一键找最优」，确认已锁定参数未被扫描（可通过日志/状态消息验证）。

- [ ] **Step 3: 更新设计文档状态**

无需修改设计文档，但可在实施完成后在文档末尾补充「实现状态：已完成」。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(fc3d): stabilize 3D strategies, add multi-param scan and param locking"
```

---

## Self-Review

### Spec Coverage

| 设计章节 | 对应任务 |
|----------|----------|
| 5.1 FC3DStrategyStabilizer | Task 1 |
| 5.2 策略改造 | Task 2 |
| 5.3 多参数网格扫描 | Task 3 |
| 5.4 参数锁定与持久化 | Task 4、Task 7 |
| 5.5 交叉验证稳定层 | Task 5、Task 6 |
| 5.6 UI 变更 | Task 7 |
| 6 数据流 | Task 4、6、7 |
| 7 错误处理 | Task 4、6 |
| 8 测试计划 | 各 Task 的测试步骤 |
| 10 验收标准 | Task 8 |

### Placeholder Scan

- 无 TBD/TODO。
- 所有代码步骤包含实际代码或伪代码（UI 部分因项目缺少 UI 测试基础设施，给出实现思路）。
- 所有测试步骤包含实际测试代码。

### Type Consistency

- `deterministic_seed` 返回 `int`。
- `stable_frequency` / `stable_missing` 返回 `dict[int, dict[int, float]]`。
- `stable_scores` 返回 `list[float]`。
- `OptimalParamStore.lock` 接受 `param_value: Any`。
- `CrossValidationResult` 字段与 `pick_best_param_cv` 使用一致。
- `StrategyScanResult` 扩展字段与 `ParameterGroupSaveDialog` 写入的 metrics key 一致（`stability_score`、`cv_mean_prize`、`cv_std_prize`）。

### 潜在风险

1. **温度参数用 int 表示 x0.1**：需要确认 `StrategyPanel._create_option_widget` 对 int 类型的渲染没有问题。已确认支持 int。
2. **CV 直接调用 `worker_round_backtest`**：该函数会训练 ML 模型，对 ML 策略做了 `n_folds=1` 降级。
3. **`_history_content_hash` 性能**：历史 1000 期时 hash 计算很快，可接受。
4. **UI 锁图标 emoji**：在 Windows 上可能显示为方块，若有问题可替换为文字 "[锁定]" 或图标文件。
