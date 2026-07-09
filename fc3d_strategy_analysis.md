# 福彩3D号码生成策略分析报告

## 一、主要问题概述

### 1. 高级策略全部为占位实现（严重问题）

在 `caipiao/core/strategies/advanced/lotteries/fc3d/` 目录下，**8个高级策略全部是空壳实现**：

| 策略文件 | 策略ID | 状态 |
|---------|--------|------|
| `markov.py` | `markov_3d` | 占位（抛出异常） |
| `bayesian.py` | `bayesian_3d` | 占位（抛出异常） |
| `trend.py` | `trend_3d` | 占位（抛出异常） |
| `ensemble.py` | `ensemble_3d` | 占位（抛出异常） |
| `periodic.py` | `periodic_3d` | 占位（抛出异常） |
| `correlation.py` | `correlation_3d` | 占位（抛出异常） |
| `random_forest.py` | `random_forest_3d` | 占位（抛出异常） |
| `transformer.py` | `transformer_3d` | 占位（抛出异常） |

**问题代码** (`_base.py:30`)：
```python
def generate(self, count=1, options=None):
    raise UnsupportedLotteryError(
        f"{self.metadata.name} 暂不支持 福彩3D 彩种"
    )
```

### 2. 注册表与实际功能不匹配

`registry.py` 第180-198行将这8个占位策略注册到了策略注册表中：
```python
"3d": [
    ...
    fc3d_random_forest.FC3DRandomForestStrategy,
    fc3d_bayesian.FC3DBayesianStrategy,
    fc3d_markov.FC3DMarkovStrategy,
    fc3d_trend.FC3DTrendStrategy,
    fc3d_periodic.FC3DPeriodicStrategy,
    fc3d_ensemble.FC3DEnsembleStrategy,
    fc3d_correlation.FC3DCorrelationStrategy,
    fc3d_transformer.FC3DTransformerStrategy,
],
```

用户可以选择这些策略，但调用时会抛出异常。

### 3. 高级策略基类设计缺陷

`FC3DAdvancedStrategy` 基类的 `validate_options` 被重写为空操作：
```python
def validate_options(self, options: Dict[str, Any]) -> None:
    """占位策略不需要历史数据校验。"""
```

这导致：
- 不验证历史数据是否充足
- 不验证参数合法性
- 用户可能在无数据时触发错误

---

## 二、具体策略代码问题

### 1. `balanced.py` - 历史均衡策略

**问题**：`score` 函数中的权重计算逻辑有缺陷

```python
# 第120行
weight_score = -sum(weights[pos][candidate[pos]] for pos in range(3)) / (max_weight or 1)
```

- `weight_score` 为负值，表示"权重越高越好"
- 但 `max_weight = lookback * len(DIGIT_POOL)` 是理论最大值
- 实际权重分布不均匀，导致评分标准不稳定

**建议**：使用归一化权重或概率作为评分标准。

### 2. `hot_cold.py` - 冷热号分析策略

**问题**：`mixed` 模式的逻辑有误

```python
# 第86行
scores = {d: max(norm[d], 1.0 - norm[d]) for d in range(10)}
```

- 当 `norm[d] = 0.6` 时，`max(0.6, 0.4) = 0.6`（选热号）
- 当 `norm[d] = 0.4` 时，`max(0.4, 0.6) = 0.6`（也选热号）
- 实际上 `mixed` 模式总是偏向热号，违背了"冷热混合"的初衷

**建议**：`mixed` 模式应该随机选择热号或冷号，而不是取最大值。

### 3. `smart_hot_cold.py` - 智能冷热号策略

**问题**：去重逻辑冗余

```python
# 第83-105行
seen: set = set()
max_attempts = count * 50 if dedup else 1
for _ in range(count):
    for attempt in range(max_attempts):
        result = [...]
        key = tuple(sorted(result))
        if not dedup or key not in seen:
            if dedup:
                seen.add(key)
            break
    else:
        for _ in range(200):
            result = [...]
            if not dedup or tuple(sorted(result)) not in seen:
                if dedup:
                    seen.add(tuple(sorted(result)))
                break
```

- 内层循环逻辑复杂，可读性差
- `else` 分支中的额外200次尝试没有注释说明
- 与其他策略的 `_sample_with_dedup` 不一致

### 4. `odd_even.py` - 奇偶均衡策略

**问题**：未处理历史数据

```python
def generate(self, count=1, options=None):
    rng = _make_rng(options, [], None, self.metadata.id)  # 空历史
    ...
```

- 不使用历史数据进行统计
- 纯随机生成，无法体现"均衡"策略的价值

### 5. `exclude_include.py` - 排除/必含策略

**问题**：去重逻辑与其他策略不一致

```python
results = _sample_with_dedup(sample_one, count, dedup)
```

- 使用了 `_sample_with_dedup`，但该函数的 `max_attempts` 计算有误
- `max_attempts = count * 50 if dedup else 1` 中的 `count` 是总数而非单次数

### 6. `ml/base.py` - ML策略基类

**问题**：`group_picks` 硬编码

```python
group_picks = {"pos": 3}  # 第125行
```

- 没有从配置中获取
- 无法支持可变数量的预测

---

## 三、工具函数问题

### 1. `stability.py`

**问题**：`deterministic_seed` 的种子生成逻辑

```python
def deterministic_seed(options, history, lookback=None, strategy_id=""):
    seed = options.get("seed")
    if seed is not None:
        return int(seed)
    h = _history_content_hash(history, lookback)
    raw = hashlib.sha256(f"{strategy_id}:{h}".encode("utf-8")).hexdigest()
    return int(raw, 16) % (2**31)
```

- 当 `history` 为空时，`h` 是固定值，导致所有策略生成相同种子
- 不同策略使用相同历史数据时，种子可能相同

### 2. `utils.py`

**问题**：`shape_ratio` 的默认值不合理

```python
def shape_ratio(records, lookback=100):
    if total == 0:
        return {"leopard": 1/3, "group3": 1/3, "group6": 1/3}  # 均匀分布
```

- 实际开奖中，豹子号概率远低于1/3
- 应该使用更合理的默认值（如 1/10, 3/10, 6/10）

---

## 四、设计层面问题

### 1. 缺乏回测验证
- 没有看到针对3D策略的回测脚本
- 无法量化评估策略效果

### 2. 参数默认值不合理
- 多个策略的 `lookback` 默认100期
- 3D每天开奖，100期约3个月，可能不够反映长期规律

### 3. 缺乏策略组合机制
- 用户只能选择单一策略
- 没有策略组合或投票机制

### 4. ML策略缺乏解释性
- ML策略只输出概率，不解释为什么推荐某个号码
- 用户无法理解决策依据

---

## 五、修复建议

### 优先级1：移除或实现占位策略

有两个选择：
1. **移除占位策略**：从注册表中删除这8个策略
2. **实现策略**：为每个策略编写实际逻辑

### 优先级2：修复已知Bug

1. 修复 `hot_cold.py` 的 `mixed` 模式逻辑
2. 修复 `balanced.py` 的权重评分计算
3. 统一去重逻辑

### 优先级3：增强功能

1. 添加策略回测验证
2. 实现策略组合机制
3. 增加ML策略的可解释性

---

## 六、当前可用策略总结

| 策略 | 可用性 | 说明 |
|-----|--------|------|
| `random_3d` | ✅ | 完全随机，基准策略 |
| `odd_even_3d` | ✅ | 奇偶均衡，简单有效 |
| `hot_cold_3d` | ⚠️ | 冷热号，mixed模式有bug |
| `exclude_include_3d` | ✅ | 排除/必含，用户友好 |
| `smart_hot_cold_3d` | ⚠️ | 智能冷热，逻辑冗余 |
| `missing_number_3d` | ✅ | 遗漏号追踪 |
| `balanced_3d` | ⚠️ | 历史均衡，评分逻辑需优化 |
| `xgboost_3d` | ✅ | ML策略，需要训练数据 |
| `lightgbm_3d` | ✅ | ML策略，需要训练数据 |
| `catboost_3d` | ✅ | ML策略，需要训练数据 |
| 其他8个高级策略 | ❌ | 占位实现，不可用 |
