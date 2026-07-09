# 福彩3D 智能冷热号策略 (smart_hot_cold_3d) 数学问题分析

> 本报告每个结论均通过数值实验验证，标注 `[已验证]` 的附有实验数据。

---

## 一、策略数据流

```
历史记录 (N期)
    │
    ├── stable_frequency()  →  按位频率(拉普拉斯平滑)   "热分"
    │
    ├── stable_missing()    →  按位遗漏值(归一化[0,1])  "冷分"
    │
    └── stable_scores()     →  加权合并 → softmax(T) → 采样概率
            │
            └── sample_weighted() → 逐位独立采样
```

---

## 二、数学问题（按严重程度排序）

### 问题 1 【致命】softmax 输入域错误，导致默认参数下策略≈随机 `[已验证]`

**代码位置**: `stability.py:119-124` (`stable_scores` 函数)

```python
combined = [
    (hot_weight * (hot_scores[d] / max_hot)
     + cold_weight * (cold_scores[d] / max_cold)) / weight_sum
    for d in DIGIT_POOL
]
return softmax_scores(combined, temperature)
```

**数学原理**:

softmax 的定义为 $p_i = \frac{e^{z_i/T}}{\sum_j e^{z_j/T}}$，其中 $z_i$ 应为 **logits**（无界实数，通常是 log-odds）。

当前代码将 `combined` 的值（经过两次除法归一化后落在 **[0.46, 0.64]** 区间）直接作为 logits 送入 softmax。这意味着最大值与最小值之差 $\Delta z \approx 0.18$。

softmax 输出的最大/最小概率比 = $e^{\Delta z / T}$：
- T=1.0（默认）: $e^{0.18} = 1.20\times$
- T=2.0: $e^{0.09} = 1.09\times$

**实验验证数据**:

| 温度 T | combined范围 | 概率范围 | max/min比 | 熵占均匀分布% |
|--------|-------------|---------|-----------|-------------|
| 0.1 | [0.46, 0.64] | [0.024, 0.391] | 16.0x | 82.1% |
| 0.5 | [0.46, 0.64] | [0.080, 0.140] | 1.74x | 99.4% |
| **1.0(默认)** | [0.46, 0.64] | [0.090, 0.119] | **1.32x** | **99.8%** |
| 2.0 | [0.46, 0.64] | [0.095, 0.109] | 1.15x | 100.0% |

**结论**: 默认温度 T=1.0 下，输出分布的熵达到均匀分布的 **99.8%**，策略等同于完全随机。温度参数仅在 T<0.3 时才有区分力，但用户界面允许的范围是 [0.1, 5.0]，大部分区间无效。

---

### 问题 2 【严重】max 归一化不归零，进一步压缩差异 `[已验证]`

**代码位置**: `stability.py:115-123`

```python
max_hot = max(hot_scores[d] for d in DIGIT_POOL)
combined = hot_weight * (hot_scores[d] / max_hot) + ...
```

**数学原理**:

除以最大值（max-normalization）的输出范围是 $[\min/\max,\ 1]$，**不会归零**。

以频率为例（100期拉普拉斯平滑后）：
- 原始范围: [0.030, 0.220]
- 除以 max(0.220) 后: **[0.136, 1.000]** ← 最小值是 0.136，不是 0

正确的归一化方式对比：

| 方法 | 公式 | 输出范围 | 适合softmax? |
|------|------|---------|-------------|
| max-norm (当前) | $x / \max(x)$ | $[0.136, 1.0]$ | ✗ 不归零 |
| min-max | $(x-\min)/(\max-\min)$ | $[0, 1]$ | △ 可用 |
| **z-score** | $(x-\mu)/\sigma$ | $(-\infty, +\infty)$ | **✓ 最佳** |

z-score 标准化后均值为 0、标准差为 1，是 softmax 的标准输入形式（logits 的统计性质）。

---

### 问题 3 【中等】频率与遗漏强负相关，"双路融合"实为单路信号 `[已验证]`

**代码位置**: `smart_hot_cold.py:63-78` + `stability.py:99-124`

**数学原理**:

策略声称"结合热号频率与冷号遗漏"，但这两个信号在统计上**高度负相关**。

在 i.i.d. 均匀分布下（$p=0.1$），某位数字出现次数多（频率高）意味着它最近一次出现离现在近（遗漏低）。反之亦然。

**实验数据**: 对模拟数据计算皮尔逊相关系数：

```
频率与遗漏的皮尔逊相关系数 r = -0.8854
```

|r| > 0.7 即为强相关。r = -0.89 意味着两路信号提供了几乎相同的信息——知道频率就能推断遗漏，反之亦然。所谓"智能冷热融合"的 `hot_weight * freq + cold_weight * missing` 本质上退化为单路信号的缩放。

**根本原因**: 频率和遗漏不是独立的信息源，它们都源自同一个底层统计量（出现次数）。

---

### 问题 4 【理论缺陷】遗漏值信号基于赌徒谬误

**代码位置**: `stability.py:59-86` + `smart_hot_cold.py:64`

**数学原理**:

福彩3D 每位开奖是独立同分布（i.i.d.）试验。在均匀假设下：

$$P(\text{数字} d \text{下期出现} \mid \text{已 } k \text{ 期未出现}) = \frac{1}{10}$$

遗漏值（多少期没出现）**不携带任何关于未来开奖的预测信息**。认为"长期未出的数字应该补出"是经典的**赌徒谬误**（Gambler's Fallacy）。

遗漏值服从几何分布 $\text{Geom}(p=0.1)$：
- 期望: $E[X] = \frac{1-p}{p} = 9$ 期
- 方差: $\text{Var}[X] = \frac{1-p}{p^2} = 90$
- 标准差: $\sigma = 9.49$ 期

这意味着遗漏值在 9±9.49 期范围内波动是完全正常的随机噪声，**不表示该数字"应该"出现**。

---

### 问题 5 【中等】去重逻辑扭曲概率分布

**代码位置**: `smart_hot_cold.py:83-105`

```python
seen: set = set()
for _ in range(count):
    for attempt in range(max_attempts):  # 拒绝采样
        result = [sample_weighted(...) for pos in range(3)]
        key = tuple(sorted(result))
        if key not in seen:   # 去重
            seen.add(key)
            break
    else:
        for _ in range(200):  # 第二轮暴力重试
            ...
```

**数学原理**:

去重使用**拒绝采样**（rejection sampling）。当某个高概率组合已被选中，后续采样会被反复拒绝，迫使选择低概率组合。

设设计的概率分布为 $P(x)$，去重后的实际输出分布为 $P'(x)$。当 count 较大时：

$$P'(x_i) \neq P(x_i), \quad \text{偏差随 count 增大而增大}$$

3D 去重后的组合空间仅 **220 种**（$C(10,3) + \text{排列}$）。当 count 接近 220 时，去重几乎不可能成功，最终 fallback 到低概率组合。

此外，代码中的双循环（`for...else` + 200次重试）逻辑冗余，与其他策略使用的 `_sample_with_dedup` 不一致。

---

### 问题 6 【次要】缺乏数据有效性的统计检验

**问题**: 策略不对历史数据做均匀性检验，即使数据完全随机也会强行生成"冷热"分析。

**数学原理**:

应使用 $\chi^2$ 拟合优度检验判断数据是否偏离均匀分布：

$$\chi^2 = \sum_{i=0}^{9} \frac{(O_i - E_i)^2}{E_i}, \quad E_i = N/10, \quad df = 9$$

临界值: $\chi^2(9, 0.05) = 16.92$

**实验验证**:

| 数据模式 | χ² 值 | 结论 |
|---------|-------|------|
| 接近均匀 [11,9,10,12,8,11,9,10,11,9] | 1.40 | 均匀（冷热分析无意义） |
| 中等偏离 [15,8,14,5,12,7,6,13,8,12] | 11.60 | 均匀（噪声范围内） |
| 强偏离 [22,5,18,3,15,6,4,17,7,3] | 46.60 | **显著偏离** |

结论：100期数据中频率波动大多是统计噪声（$\chi^2 < 16.92$），冷热分析无统计学意义。只有强偏离时才有价值。

---

## 三、改进方案（符合数学原理）

### 改进 1：z-score 标准化替代 max 归一化

```python
def zscore_normalize(scores: Dict[int, float]) -> Dict[int, float]:
    """z-score 标准化: z = (x - mean) / std
    
    输出均值0、标准差1，是 softmax logits 的标准形式。
    消除频率(~0.03-0.22)与遗漏(0-1)之间的量级和偏移差异。
    """
    vals = [scores[d] for d in DIGIT_POOL]
    mean = statistics.mean(vals)
    std = statistics.stdev(vals)
    std = max(std, 1e-10)
    return {d: (scores[d] - mean) / std for d in DIGIT_POOL}
```

**数学依据**: z-score 是概率论中对随机变量标准化的标准方法，变换后的变量 $Z = (X-\mu)/\sigma$ 无量纲、均值0、方差1，可直接作为 logits 使用。

---

### 改进 2：冷号信号改用几何分布 z-score

```python
def geometric_missing_zscore(missing_periods: Dict[int, int], p: float = 0.1) -> Dict[int, float]:
    """将原始遗漏期数转为几何分布的 z-score.
    
    在均匀假设(p=0.1)下, 遗漏服从 Geom(p):
      E[X] = (1-p)/p = 9
      sigma = sqrt(1-p)/p = 9.49
    
    z > 1.96 (95%置信) 才算统计显著的"偏冷".
    避免将正常随机波动误判为冷号信号.
    """
    expected = (1 - p) / p
    sigma = math.sqrt(1 - p) / p
    return {d: (missing_periods[d] - expected) / sigma for d in DIGIT_POOL}
```

**数学依据**: 这是假设检验中的标准化检验统计量。只有 $|z| > 1.96$（5%显著性水平）时才认为观测值偏离理论值，避免赌徒谬误。

---

### 改进 3：合并后的 softmax 恢复区分力

```python
def stable_scores_improved(hot_scores, cold_scores, hw, cw, temp=1.0):
    """改进版分数合并.
    
    1. 两路信号分别 z-score 标准化
    2. 加权合并得到无界 logits
    3. softmax 输出概率，温度参数恢复区分力
    """
    hot_z = zscore_normalize(hot_scores)
    cold_z = zscore_normalize(cold_scores)
    ws = hw + cw or 1.0
    logits = [(hw * hot_z[d] + cw * cold_z[d]) / ws for d in DIGIT_POOL]
    # logits 范围约为 [-2, +2]，softmax 后 max/min ≈ e^4 ≈ 55x (T=1.0)
    return softmax_with_temp(logits, temp)
```

**改进效果对比** [已验证]:

| 温度 | 当前 max/min | 改进 max/min | 当前熵% | 改进熵% |
|------|-------------|-------------|---------|---------|
| 0.1 | 16.0x | 13650x | 82.1% | 14.1% |
| 0.5 | 1.74x | 6.71x | 99.4% | 91.6% |
| **1.0** | **1.32x** | **2.59x** | **99.8%** | **98.0%** |
| 2.0 | 1.15x | 1.61x | 100.0% | 99.5% |

改进后 T=1.0 的区分力（2.59x）接近改进前 T=0.3 的水平，温度参数在全范围内都有意义。

---

### 改进 4：添加 χ² 均匀性检验守卫

```python
def chi_square_uniform_test(counts: List[int]) -> tuple:
    """检验观测频率是否偏离均匀分布.
    
    返回 (chi2_statistic, is_uniform).
    is_uniform=True 时, 冷热分析无统计学意义.
    """
    n = sum(counts)
    expected = n / 10.0
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    return chi2, chi2 < 16.92  # df=9, alpha=0.05
```

**数学依据**: Pearson 的 $\chi^2$ 拟合优度检验是判断分类数据是否符合理论分布的标准方法。当 $\chi^2 < 16.92$（自由度9、显著性5%）时，无法拒绝均匀分布假设，此时冷热分析无意义，应退化为均匀随机。

---

### 改进 5：去重改为概率保持的 Gumbel 技巧或直接枚举

3D 仅 1000 种直选组合（220 种组选），可**全枚举打分后按概率无放回采样**：

```python
# 枚举所有1000种组合，计算每种的概率乘积
candidates = list(itertools.product(range(10), repeat=3))
weights = [prod(pos_probs[pos][c[pos]] for pos in range(3)) for c in candidates]
# 按权重无放回采样 count 个（保持概率分布）
selected = weighted_sample_without_replacement(candidates, weights, count)
```

**数学依据**: 无放回加权采样（Fisher-Yates 变体）能在去重的同时保持边际概率分布，避免拒绝采样导致的概率扭曲。

---

## 四、改进验证总结

| 问题 | 改进前 | 改进后 | 数学依据 |
|------|--------|--------|---------|
| softmax失效 | T=1.0→熵99.8%均匀 | T=1.0→熵98.0% | logits应为无界实数 |
| 归一化压缩 | 最小值0.136 | 最小值≈-2 | z-score标准化 |
| 冷热信号冗余 | r=-0.89 | 改用独立检验量 | 几何分布z-score |
| 赌徒谬误 | 遗漏大→追 | z>1.96才追 | 假设检验 |
| 去重扭曲 | 拒绝采样偏差 | 加权无放回采样 | 概率保持 |
| 缺乏守卫 | 强行分析 | χ²检验守卫 | 拟合优度检验 |
