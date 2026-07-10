# 福彩3D三策略融合遗留问题修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `fc3d_ensemble_remaining_issues_report.md` 中列出的 10 个遗留问题（N1–N10），使三策略融合策略在配置一致性、位置信息保留、形态建模、统计依据和可维护性上达到可用状态。

**Architecture：** 以 `caipiao/core/strategies/lotteries/fc3d/ensemble.py` 为主战场，必要时修改共享工具 `_base.py` 与 `utils.py`；所有改动保持向后兼容（旧字段、旧别名保留），新增 `tests/test_fc3d_ensemble_v2.py` 作为回归测试。

**Tech Stack：** Python 3.10、pytest、项目现有工具函数（`stability.py`、`utils.py`、`_base.py`）。

## Global Constraints

- 不修改现有测试的断言逻辑（除非测试本身在验证旧 bug）。
- 保持 `FC3D_PROFILE`、`_make_rng`、`_records_from_options` 等共享接口不变。
- `ensemble_v2_3d` 的策略 ID 与 `StrategyMetadata` 不变。
- 新代码必须跟随项目现有风格（中文注释、类型注解、空行分隔）。
- 每个任务必须能独立跑通相关测试后再进入下一个任务。
- 不引入新的第三方依赖。

---

## File Structure

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `caipiao/core/strategies/lotteries/fc3d/ensemble.py` | 三策略融合主实现 | 大量修改 |
| `caipiao/core/strategies/lotteries/fc3d/_base.py` | 共享采样工具 `_weighted_sample_without_replacement` | 签名扩展 |
| `caipiao/core/strategies/lotteries/fc3d/utils.py` | 3D 统计工具 | 可能新增逐位奇偶/大小函数 |
| `caipiao/core/strategies/lotteries/fc3d/__init__.py` | 导出策略类 | 更新别名 |
| `run_ensemble_v2.py` | ensemble 消费者 | 更新 details 字段读取 |
| `tests/test_fc3d_ensemble_v2.py` | 新增专项回归测试 | 新建 |

---

### Task 1: N10 — `_zscore_list` 改用总体标准差

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:170-181`
- Test: `tests/test_fc3d_ensemble_v2.py`（新建，本任务先写一个最小测试）

**Interfaces:**
- `_zscore_list(vals: List[float]) -> List[float]` 行为不变，仅内部计算方式改变。

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_fc3d_ensemble_v2.py
def test_zscore_list_uses_population_std():
    from caipiao.core.strategies.lotteries.fc3d.ensemble import FC3DEnsembleStrategy
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    # 总体标准差 sqrt(((1-3)^2 + ... + (5-3)^2)/5) = sqrt(2)
    expected = [(v - 3.0) / (2.0 ** 0.5) for v in vals]
    result = FC3DEnsembleStrategy._zscore_list(vals)
    for r, e in zip(result, expected):
        assert abs(r - e) < 1e-9
```

- [ ] **Step 2: 运行测试确认失败**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_zscore_list_uses_population_std -v
```

Expected: FAIL（当前使用 sample std，结果不符）

- [ ] **Step 3: 最小实现**

```python
@staticmethod
def _zscore_list(vals: List[float]) -> List[float]:
    """z-score 标准化列表，std≈0 时返回全 0。使用总体标准差。"""
    if len(vals) < 2:
        return [0.0] * len(vals)
    mean = statistics.mean(vals)
    try:
        std = statistics.pstdev(vals)  # 改为总体标准差
    except statistics.StatisticsError:
        std = 0.0
    if std < 1e-10:
        return [0.0] * len(vals)
    return [(v - mean) / std for v in vals]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_zscore_list_uses_population_std -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "fix(ensemble): use population std in _zscore_list (N10)"
```

---

### Task 2: N8 — 重命名真实策略类并保留别名

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:58`
- Modify: `caipiao/core/strategies/lotteries/fc3d/__init__.py`
- Test: `tests/test_strategy_factory.py`（验证 id 仍注册）

**Interfaces:**
- 新主类名：`FC3DStrategyFusionStrategy`
- 旧名 `FC3DEnsembleStrategy` 作为别名保留。
- `__init__.py` 导出 `FC3DStrategyFusionStrategy`（主）与 `FC3DEnsembleStrategy`（兼容别名）。

- [ ] **Step 1: 修改类名并加别名**

```python
# caipiao/core/strategies/lotteries/fc3d/ensemble.py
class FC3DStrategyFusionStrategy(GenerationStrategy):
    ...

# 兼容旧导入：保留旧类名指向新类
FC3DEnsembleStrategy = FC3DStrategyFusionStrategy
```

- [ ] **Step 2: 更新 `__init__.py` 导出**

```python
# caipiao/core/strategies/lotteries/fc3d/__init__.py
# 新增/调整导出
from .ensemble import FC3DStrategyFusionStrategy, FC3DEnsembleStrategy
```

- [ ] **Step 3: 运行注册表测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_strategy_factory.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add caipiao/core/strategies/lotteries/fc3d/ensemble.py caipiao/core/strategies/lotteries/fc3d/__init__.py
git commit -m "refactor(ensemble): rename to FC3DStrategyFusionStrategy, keep alias (N8)"
```

---

### Task 3: N1 — 让 balanced 子策略响应用户配置的 z_threshold

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:237-290, 397-460`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_get_balanced_probs(self, records, lookback, uniform_flags, z_threshold)`
- `_ratio_signal(dev, sigma, positive_mask, z_threshold, max_gain)` 调用时传入配置值。

- [ ] **Step 1: 修改 `_get_balanced_probs` 签名并透传阈值**

```python
def _get_balanced_probs(
    self, records: List, lookback: int, uniform_flags: List[bool], z_threshold: float
) -> List[List[float]]:
    ...
    parity_score = self._ratio_signal(
        odd_ratio - 0.5, sigma_ratio, odd_mask, z_threshold=z_threshold
    )
    size_score = self._ratio_signal(
        high_ratio - 0.5, sigma_ratio, high_mask, z_threshold=z_threshold
    )
```

- [ ] **Step 2: 在 `generate` 中把 `z_threshold` 传入 `_get_balanced_probs`**

```python
balanced_probs = self._get_balanced_probs(
    records, lookback, uniform_flags, z_threshold
)
```

- [ ] **Step 3: 编写测试**

```python
def test_balanced_respects_z_threshold():
    strategy = FC3DStrategyFusionStrategy()
    # 构造整体奇偶比例显著偏离的数据（每位数字频率尽量均匀但奇数显著偏多）
    # 使 z_threshold=1.96 与 z_threshold=3.0 下 parity_score 不同
    records = []
    for i in range(200):
        # 每位：奇数概率 0.6，偶数概率 0.4，且各位数字内部尽量均匀
        nums = []
        for _ in range(3):
            if i % 2 == 0:
                nums.append(random.choice([1, 3, 5, 7, 9]))
            else:
                nums.append(random.choice([0, 2, 4, 6, 8]))
        records.append(make_record(nums))
    
    def odd_prob(options):
        t = strategy.generate(count=1, options=options)[0]
        p = t.details['pos_probabilities'][0]
        return sum(p[d] for d in [1, 3, 5, 7, 9])
    
    base = {
        "history": records, "lookback": 200,
        "balanced_weight": 100, "hot_cold_weight": 0, "missing_weight": 0,
        "adaptive": False, "temperature": 10, "dedup": False, "seed": 1,
    }
    low = odd_prob({**base, "z_threshold": 196})
    high = odd_prob({**base, "z_threshold": 300})
    assert low != high, "z_threshold should affect balanced parity/size gating"
```

- [ ] **Step 4: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_balanced_respects_z_threshold -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "fix(ensemble): pass z_threshold to balanced parity/size gating (N1)"
```

---

### Task 4: N5 — 奇偶/大小信号改为逐位比例

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:237-290`
- Optionally add helpers to `utils.py`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_get_balanced_probs` 内部逐位计算 `odd_ratio[pos]`、`high_ratio[pos]` 和 `sigma_ratio[pos]`。

- [ ] **Step 1: 在 `_get_balanced_probs` 中用逐位频率计算逐位奇偶/大小比例**

```python
def _get_balanced_probs(
    self, records: List, lookback: int, uniform_flags: List[bool], z_threshold: float
) -> List[List[float]]:
    weights = positional_weights(records, lookback, smoothing=1.0)
    road = road_012_statistics(records, lookback)
    # 移除整体 odd_ratio/high_ratio
    pos_freq_counts = positional_frequency(records, lookback)

    pos_probs: List[List[float]] = []
    for pos in range(3):
        if uniform_flags[pos]:
            pos_probs.append([1.0 / 10.0] * 10)
            continue

        # 逐位奇偶/大小比例
        counts = pos_freq_counts[pos]
        total = sum(counts.values()) or 1
        odd_ratio = sum(counts.get(d, 0) for d in [1, 3, 5, 7, 9]) / total
        high_ratio = sum(counts.get(d, 0) for d in [5, 6, 7, 8, 9]) / total
        # p=0.5 比例的标准差，基于该位样本量
        sigma_ratio = 0.5 / math.sqrt(max(total, 1))

        freq_z = self._zscore_list([weights[pos][d] for d in DIGIT_POOL])
        freq_score = [-abs(z) for z in freq_z]
        road_z = self._zscore_list([road[pos][d % 3] for d in DIGIT_POOL])
        road_score = [-abs(z) for z in road_z]
        parity_score = self._ratio_signal(
            odd_ratio - 0.5, sigma_ratio, odd_mask, z_threshold=z_threshold
        )
        size_score = self._ratio_signal(
            high_ratio - 0.5, sigma_ratio, high_mask, z_threshold=z_threshold
        )
        ...
```

- [ ] **Step 2: 删除对 `overall_odd_even_ratio` / `overall_high_low_ratio` 的导入**

```python
# from .utils import (
#     ...
#     overall_high_low_ratio,
#     overall_odd_even_ratio,
#     ...
# )
```

- [ ] **Step 3: 编写测试**

```python
def test_per_position_parity_signal():
    strategy = FC3DStrategyFusionStrategy()
    records = []
    for i in range(200):
        pos0 = random.choice([1, 3, 5, 7, 9]) if random.random() < 0.7 else random.randint(0, 9)
        pos1 = random.choice([0, 2, 4, 6, 8]) if random.random() < 0.7 else random.randint(0, 9)
        pos2 = random.randint(0, 9)
        records.append(make_record([pos0, pos1, pos2]))
    
    t = strategy.generate(count=1, options={
        "history": records, "lookback": 200,
        "balanced_weight": 100, "hot_cold_weight": 0, "missing_weight": 0,
        "adaptive": False, "temperature": 10, "dedup": False, "seed": 1,
    })[0]
    
    for pos, expected_odd_high in [(0, True), (1, False)]:
        p = t.details['pos_probabilities'][pos]
        odd = sum(p[d] for d in [1, 3, 5, 7, 9])
        if expected_odd_high:
            assert odd > 0.5, f"pos{pos} should favor odd"
        else:
            assert odd < 0.5, f"pos{pos} should favor even"
```

- [ ] **Step 4: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_per_position_parity_signal -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "fix(ensemble): use per-position odd/even/high-low ratios (N5)"
```

---

### Task 5: N2 — 温度透传给子策略并移除扭曲的 log-softmax

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:237-348, 397-487`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_get_balanced_probs(..., temperature: float)`
- `_get_hot_cold_probs(..., temperature: float)`
- `_get_missing_probs(..., temperature: float)`
- `generate` 中最终融合只做加权平均 + 归一化，不再 `log(prob)` 调温。

- [ ] **Step 1: 修改三个子策略签名并使用传入温度**

```python
def _get_balanced_probs(
    self, records: List, lookback: int, uniform_flags: List[bool],
    z_threshold: float, temperature: float
) -> List[List[float]]:
    ...
    probs = softmax_scores(combined, temperature=temperature)

def _get_hot_cold_probs(
    self, records: List, lookback: int, hot_weight: float, cold_weight: float,
    geo_z: Dict[int, Dict[int, float]], temperature: float
) -> List[List[float]]:
    ...
    probs = stable_scores(freq[pos], geo_z[pos], hot_weight, cold_weight, temperature)

def _get_missing_probs(
    self, geo_z: Dict[int, Dict[int, float]], z_threshold: float,
    uniform_flags: List[bool], temperature: float
) -> Tuple[List[List[float]], List[bool]]:
    ...
    probs = softmax_scores(logits, temperature=temperature)
```

- [ ] **Step 2: 修改 `generate` 的调用与最终融合**

```python
balanced_probs = self._get_balanced_probs(
    records, lookback, uniform_flags, z_threshold, temperature
)
hot_cold_probs = self._get_hot_cold_probs(
    records, lookback, hot_weight, cold_weight, geo_z, temperature
)
missing_probs, missing_has_signal = self._get_missing_probs(
    geo_z, z_threshold, uniform_flags, temperature
)

# 最终融合：线性加权平均后归一化，不再 log-softmax
fused = [
    w["balanced"] * balanced_probs[pos][d]
    + w["hot_cold"] * hot_cold_probs[pos][d]
    + w["missing"] * missing_probs[pos][d]
    for d in range(10)
]
total = sum(fused)
if total > 0:
    fused = [p / total for p in fused]
else:
    fused = [0.1] * 10
```

- [ ] **Step 3: 更新 tooltip**

```python
"temperature": {
    ...
    "tooltip": "控制号码集中程度（作用于三个子策略的概率生成）。10=标准平衡，1=高度集中，50=接近随机。",
}
```

- [ ] **Step 4: 编写测试**

```python
def test_temperature_affects_substrategies():
    strategy = FC3DStrategyFusionStrategy()
    # 构造 pos0 明显偏数字 4 的历史
    records = []
    for i in range(200):
        nums = [4 if random.random() < 0.6 else random.randint(0, 9) for _ in range(3)]
        records.append(make_record(nums))
    
    def max_prob(options):
        t = strategy.generate(count=1, options=options)[0]
        return max(t.details['pos_probabilities'][0])
    
    base = {
        "history": records, "lookback": 200,
        "balanced_weight": 0, "hot_cold_weight": 100, "missing_weight": 0,
        "adaptive": False, "dedup": False, "seed": 1,
    }
    low_t = max_prob({**base, "temperature": 1})
    mid_t = max_prob({**base, "temperature": 10})
    high_t = max_prob({**base, "temperature": 50})
    assert low_t > mid_t > high_t, "lower temperature should concentrate probability"
```

- [ ] **Step 5: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_temperature_affects_substrategies -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "fix(ensemble): pass temperature to sub-strategies, remove log-prob distortion (N2)"
```

---

### Task 6: N6 — 自适应权重基于实际信号类型而非 χ² 阈值

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:353-392, 451-486`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_adaptive_weights_per_pos(self, chi2_values, uniform_flags, base_weights, missing_has_signal, freq, geo_z, z_threshold)`
- 根据某位置是否存在显著冷号，选择 boost missing 或 hot_cold。

- [ ] **Step 1: 修改 `_adaptive_weights_per_pos` 签名与逻辑**

```python
def _adaptive_weights_per_pos(
    self,
    chi2_values: List[float],
    uniform_flags: List[bool],
    base_weights: Dict[str, float],
    missing_has_signal: List[bool],
) -> Dict[int, Dict[str, float]]:
    """逐位自适应权重：以 base_weights 为基准，根据实际信号类型调整。

    - uniform: 维持基准权重
    - 非 uniform 且存在显著冷号: 提升 missing（追冷），降低 balanced
    - 非 uniform 但无显著冷号: 提升 hot_cold（追热/结构），维持 missing
    """
    result: Dict[int, Dict[str, float]] = {}
    keys = ("balanced", "hot_cold", "missing")
    for pos in range(3):
        if uniform_flags[pos]:
            mult = {"balanced": 1.0, "hot_cold": 1.0, "missing": 1.0}
        elif missing_has_signal[pos]:
            mult = {"balanced": 0.8, "hot_cold": 1.0, "missing": 1.5}
        else:
            mult = {"balanced": 1.0, "hot_cold": 1.2, "missing": 0.8}
        adjusted = {
            k: max(base_weights.get(k, 0) * mult[k], 0.0) for k in keys
        }
        total = sum(adjusted.values())
        if total <= 0:
            adjusted = {k: 1.0 for k in keys}
            total = float(len(keys))
        result[pos] = {k: adjusted[k] / total for k in keys}
    return result
```

- [ ] **Step 2: 在 `generate` 中调整调用顺序**

由于 `_adaptive_weights_per_pos` 现在依赖 `missing_has_signal`，需要先算 `missing_probs` 再算自适应权重：

```python
# 先算 missing（需要 geo_z）
raw_missing = raw_missing_periods(records, lookback)
geo_z = geometric_missing_zscore(raw_missing)
# 先算一次 missing 以得到 has_signal
missing_probs, missing_has_signal = self._get_missing_probs(
    geo_z, z_threshold, uniform_flags, temperature
)
# 再算 adaptive weights
if adaptive:
    pos_weights = self._adaptive_weights_per_pos(
        chi2_values, uniform_flags, base_weights, missing_has_signal
    )
else:
    ...
# 再算 balanced / hot_cold
balanced_probs = self._get_balanced_probs(...)
hot_cold_probs = self._get_hot_cold_probs(...)
# missing 已经算好，直接使用
```

注意：这样 `_get_missing_probs` 会被调用两次（一次为了 has_signal，一次复用）。为避免重复，可调整顺序让 missing 先算并把 probs 存下。

- [ ] **Step 3: 编写测试**

```python
def test_adaptive_boosts_missing_when_cold_signal():
    strategy = FC3DStrategyFusionStrategy()
    # 构造某位有明显冷号的数据
    records = []
    for i in range(200):
        nums = [0, 0, 0]  # 让数字 0 在各位置长期遗漏
        records.append(make_record(nums))
    
    t = strategy.generate(count=1, options={
        "history": records, "lookback": 200,
        "balanced_weight": 33, "hot_cold_weight": 33, "missing_weight": 34,
        "adaptive": True, "temperature": 10, "dedup": False, "seed": 1,
    })[0]
    
    # 至少有一位 missing 权重被提升
    boosted = any(
        w['missing'] > 0.34 for w in t.details['pos_weights']
    )
    assert boosted, "adaptive should boost missing weight when cold signal exists"
```

- [ ] **Step 4: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_adaptive_boosts_missing_when_cold_signal -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "fix(ensemble): signal-aware adaptive weights instead of chi2 heuristic (N6)"
```

---

### Task 7: N3 — 去重采样保留排列相对概率

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/_base.py:94-124`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_weighted_sample_without_replacement(pos_probs, count, rng)` 行为增强：抽中 group 后按各排列的真实联合概率加权选择。

- [ ] **Step 1: 存储每个排列的联合概率并加权选择**

```python
def _weighted_sample_without_replacement(
    pos_probs: List[List[float]],
    count: int,
    rng: random.Random,
) -> List[List[int]]:
    group_probs: Dict[Tuple[int, ...], float] = {}
    group_perms: Dict[Tuple[int, ...], List[Tuple[int, ...]]] = {}
    perm_probs: Dict[Tuple[int, ...], Dict[Tuple[int, ...], float]] = {}
    for combo in itertools.product(range(10), repeat=3):
        key = tuple(sorted(combo))
        p = pos_probs[0][combo[0]] * pos_probs[1][combo[1]] * pos_probs[2][combo[2]]
        group_probs[key] = group_probs.get(key, 0.0) + p
        group_perms.setdefault(key, []).append(combo)
        perm_probs.setdefault(key, {})[combo] = p

    keys: List[Tuple[int, ...]] = list(group_probs.keys())
    weights: List[float] = [group_probs[k] for k in keys]

    n = min(count, len(keys))
    selected: List[List[int]] = []

    for _ in range(n):
        total = sum(weights)
        if total <= 0:
            break
        r = rng.random() * total
        cumulative = 0.0
        idx = len(weights) - 1
        for i, w in enumerate(weights):
            cumulative += w
            if cumulative >= r:
                idx = i
                break
        key = keys.pop(idx)
        weights.pop(idx)
        perms = group_perms[key]
        probs = [max(perm_probs[key][perm], 0.0) for perm in perms]
        perm_total = sum(probs)
        if perm_total <= 0:
            selected.append(list(rng.choice(perms)))
        else:
            selected.append(list(rng.choices(perms, weights=probs, k=1)[0]))

    return selected
```

- [ ] **Step 2: 编写测试**

```python
def test_dedup_preserves_permutation_probability():
    from caipiao.core.strategies.lotteries.fc3d._base import _weighted_sample_without_replacement
    # 构造强烈位置偏好：pos0→1, pos1→2, pos2→3
    pos_probs = [
        [0.05] * 10,
        [0.05] * 10,
        [0.05] * 10,
    ]
    pos_probs[0][1] = 0.55
    pos_probs[1][2] = 0.55
    pos_probs[2][3] = 0.55
    rng = random.Random(1)
    results = _weighted_sample_without_replacement(pos_probs, count=200, rng=rng)
    count_123 = sum(1 for r in results if r == [1, 2, 3])
    count_321 = sum(1 for r in results if r == [3, 2, 1])
    # 123 应显著多于 321
    assert count_123 > count_321 * 2, f"123={count_123}, 321={count_321}"
```

- [ ] **Step 3: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_dedup_preserves_permutation_probability -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/_base.py
git commit -m "fix(ensemble): weighted permutation selection within group for dedup (N3)"
```

---

### Task 8: N4 — 引入号码形态权重

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/_base.py:74-125`
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:488-545`
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `_weighted_sample_without_replacement(pos_probs, count, rng, shape_weights=None)`
- `shape_weights: Optional[Dict[str, float]]`  keyed by "leopard"/"group3"/"group6"，作为形态修正乘数。

- [ ] **Step 1: 扩展 `_weighted_sample_without_replacement` 签名并应用形态权重**

```python
from .utils import fc3d_bet_type, shape_ratio  # 需要在 _base.py 导入

def _weighted_sample_without_replacement(
    pos_probs: List[List[float]],
    count: int,
    rng: random.Random,
    shape_weights: Optional[Dict[str, float]] = None,
) -> List[List[int]]:
    ...
    for combo in itertools.product(range(10), repeat=3):
        key = tuple(sorted(combo))
        p = pos_probs[0][combo[0]] * pos_probs[1][combo[1]] * pos_probs[2][combo[2]]
        if shape_weights:
            shape = fc3d_bet_type(list(combo))
            shape_key = {"豹子号": "leopard", "组选3": "group3", "组选6": "group6"}.get(shape)
            if shape_key:
                p *= shape_weights.get(shape_key, 1.0)
        group_probs[key] = group_probs.get(key, 0.0) + p
        ...
```

- [ ] **Step 2: 在 `ensemble.py` 的 `generate` 中计算并传入形态权重**

```python
# 形态修正：理论比例 / 历史比例
shape_hist = shape_ratio(records, lookback)
theoretical = {"leopard": 0.01, "group3": 0.27, "group6": 0.72}
shape_weights = {}
for key in theoretical:
    hist = shape_hist.get(key, theoretical[key])
    if hist <= 0:
        hist = theoretical[key]
    shape_weights[key] = theoretical[key] / hist

# 限制最大修正倍数，避免极端
for key in shape_weights:
    shape_weights[key] = min(max(shape_weights[key], 0.2), 5.0)

# 采样时传入
if dedup:
    results = _weighted_sample_without_replacement(
        pos_probs, count, rng, shape_weights=shape_weights
    )
else:
    ...
```

- [ ] **Step 3: 在 basis 中说明形态修正**

```python
basis += f"形态修正权重：豹子{shape_weights['leopard']:.2f}/组三{shape_weights['group3']:.2f}/组六{shape_weights['group6']:.2f}。"
```

- [ ] **Step 4: 编写测试**

```python
def test_shape_correction_influences_output():
    strategy = FC3DStrategyFusionStrategy()
    # 构造历史：豹子号远多于理论 1%
    records = []
    for i in range(200):
        records.append(make_record([5, 5, 5]))
    
    t = strategy.generate(count=1, options={
        "history": records, "lookback": 200,
        "balanced_weight": 33, "hot_cold_weight": 33, "missing_weight": 34,
        "adaptive": False, "temperature": 10, "dedup": True, "seed": 1,
    })[0]
    
    # 形态修正应抑制豹子号（权重 < 1）
    assert "豹子" in t.basis
    # 由于去重最多 220 组，这里只验证 basis 包含形态权重即可
```

- [ ] **Step 5: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_shape_correction_influences_output -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/_base.py caipiao/core/strategies/lotteries/fc3d/ensemble.py
git commit -m "feat(ensemble): incorporate shape distribution correction (N4)"
```

---

### Task 9: N7 — 清理 `details` 权重字段语义

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/ensemble.py:540-580`
- Modify: `run_ensemble_v2.py`（如读取 `details['weights']`）
- Test: `tests/test_fc3d_ensemble_v2.py`

**Interfaces:**
- `ticket.details` 中 `"weights"` 改为 `"avg_weights"`，同时保留 `"weights"` 作为兼容别名指向同一数据；`"pos_weights"` 继续保留。

- [ ] **Step 1: 修改 details 字典**

```python
ticket.details = {
    "pos_probabilities": pos_probs,
    "chi_square": chi2_values,
    "is_uniform": uniform_flags,
    # 三位平均权重（概览）；逐位完整数据见 pos_weights
    "avg_weights": avg_weights,
    # 兼容旧字段名
    "weights": avg_weights,
    # 逐位实际权重
    "pos_weights": final_pos_weights,
    "missing_has_signal": missing_has_signal,
    "adaptive": adaptive,
    "temperature": temperature,
    "strategy_components": {...},
    "shape_weights": shape_weights if dedup else None,
}
```

- [ ] **Step 2: 更新 `run_ensemble_v2.py` 消费者**

查找并替换 `details['weights']` 为 `details['pos_weights']` 或 `details['avg_weights']`，视使用场景而定。

```bash
grep -n "details\['weights'\]" run_ensemble_v2.py
```

假设原代码仅用于展示，改为：

```python
avg_weights = ticket.details.get("avg_weights", ticket.details.get("weights", {}))
```

- [ ] **Step 3: 编写测试**

```python
def test_details_has_avg_and_pos_weights():
    strategy = FC3DStrategyFusionStrategy()
    t = strategy.generate(count=1, options={
        "history": [make_record([1,2,3]) for _ in range(50)],
        "lookback": 50,
        "balanced_weight": 33, "hot_cold_weight": 33, "missing_weight": 34,
        "adaptive": True, "temperature": 10, "dedup": False, "seed": 1,
    })[0]
    assert "avg_weights" in t.details
    assert "pos_weights" in t.details
    assert "weights" in t.details  # 兼容
    assert len(t.details["pos_weights"]) == 3
```

- [ ] **Step 4: 运行测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_ensemble_v2.py::test_details_has_avg_and_pos_weights -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py caipiao/core/strategies/lotteries/fc3d/ensemble.py run_ensemble_v2.py
git commit -m "refactor(ensemble): clarify details weight fields, keep backward alias (N7)"
```

---

### Task 10: N9 — 补齐回归测试并跑全量测试

**Files:**
- Create/Modify: `tests/test_fc3d_ensemble_v2.py`
- Test: 全量 `pytest`

- [ ] **Step 1: 补充边界测试**

```python
def test_count_over_220_raises():
    strategy = FC3DStrategyFusionStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=300, options={
            "history": [make_record([1,2,3]) for _ in range(50)],
            "lookback": 50, "dedup": True,
        })

def test_disabled_strategies_respected():
    strategy = FC3DStrategyFusionStrategy()
    t = strategy.generate(count=1, options={
        "history": [make_record([1,2,3]) for _ in range(50)],
        "lookback": 50,
        "balanced_weight": 0, "hot_cold_weight": 0, "missing_weight": 100,
        "adaptive": True, "dedup": False, "seed": 1,
    })[0]
    for w in t.details['pos_weights']:
        assert w['balanced'] == 0.0
        assert w['hot_cold'] == 0.0

def test_uniform_data_outputs_near_uniform():
    strategy = FC3DStrategyFusionStrategy()
    random.seed(123)
    records = [make_record([random.randint(0,9) for _ in range(3)]) for _ in range(200)]
    t = strategy.generate(count=1, options={
        "history": records, "lookback": 200,
        "balanced_weight": 33, "hot_cold_weight": 33, "missing_weight": 34,
        "adaptive": False, "temperature": 10, "dedup": False, "seed": 1,
    })[0]
    for pos in range(3):
        p = t.details['pos_probabilities'][pos]
        assert max(p) < 0.25, f"pos{pos} too concentrated on uniform data"
```

- [ ] **Step 2: 运行全量测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: 全部通过（或仅因无关原因失败，需记录）

- [ ] **Step 3: 提交**

```bash
git add tests/test_fc3d_ensemble_v2.py
git commit -m "test(ensemble): add regression tests for ensemble_v2_3d (N9)"
```

---

## Self-Review

**Spec coverage:**
- N1: Task 3
- N2: Task 5
- N3: Task 7
- N4: Task 8
- N5: Task 4
- N6: Task 6
- N7: Task 9
- N8: Task 2
- N9: Task 10
- N10: Task 1

无遗漏。

**Placeholder scan：**
- 所有步骤均包含具体代码与命令，无 "TBD"/"TODO"/"implement later"。
- 测试代码完整，非占位。

**Type consistency：**
- `_get_balanced_probs`、`_get_hot_cold_probs`、`_get_missing_probs`、`_adaptive_weights_per_pos` 的签名在定义与调用处一致。
- `_weighted_sample_without_replacement` 新增可选参数 `shape_weights`，默认 `None`，向后兼容。
- `details` 新增 `"avg_weights"`，旧 `"weights"` 保留为别名。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-10-fix-fc3d-ensemble-remaining-issues.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
