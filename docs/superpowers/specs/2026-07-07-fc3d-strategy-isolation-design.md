# 福彩3D策略独立与按位优化设计

## 背景

当前所有非双色球彩种共用 `caipiao/core/strategies/generic.py` 中的通用策略：`GenericRandomStrategy`、`GenericOddEvenStrategy`、`GenericHotColdStrategy`、`GenericExcludeIncludeStrategy`、`GenericSmartHotColdStrategy`、`GenericMissingNumberStrategy`、`GenericBalancedStrategy`、`GenericXGBoostStrategy`、`GenericLightGBMStrategy`、`GenericCatBoostStrategy`。

福彩3D（`profile.key == "3d"`）是**按位、可重复**的数位型彩种：3位数字，每位0-9，顺序决定中奖结果。通用策略为了兼容多种彩种，在3D上存在明显问题：

- 号码生成后会 `sorted()`，破坏百位/十位/个位的顺序语义。
- 统计时只使用整体频率，未利用按位冷热信息。
- 评分维度只有奇偶、大小、和值，缺少跨度、和尾、012路、组三/组六/豹子等3D核心指标。

同时，3D逻辑与七乐彩、快乐8、大乐透等混在一起，未来修改通用策略时极易意外破坏3D行为。

## 目标

1. 将福彩3D的全部生成策略独立到专属模块，与通用策略彻底解耦。
2. 在独立模块内针对3D的按位、可重复特性进行优化。
3. 保持对外的策略ID、名称、配置schema不变，确保UI、回测、最优参数扫描等上层调用无需修改。
4. 保持 `build_strategies()`、`needs_history()`、`is_ml_strategy()` 的接口不变。

## 非目标

- 不改双色球专属的老策略（`caipiao/core/strategies/*.py` 中的 `RandomStrategy`、`BalancedStrategy` 等）。
- 不改动通用彩种（七乐彩、快乐8、大乐透、排列3/5、七星彩）的策略实现。
- 不改动 `LotteryProfile` 和 `NumberGroup` 的定义。
- 本次不引入新的机器学习模型结构，ML策略复用现有 `GenericMLPredictor`。

## 设计

### 1. 文件结构

新增专属模块：

```
caipiao/core/strategies/
├── __init__.py
├── generic.py              # 保留通用彩种策略（3D相关代码删除）
├── fc3d.py                 # 新增：福彩3D专属策略
└── fc3d_utils.py           # 新增：3D统计工具函数
```

测试：

```
tests/
├── test_lottery_unified.py # 保留现有3D通用测试
└── test_fc3d_strategies.py # 新增：3D专属策略详细测试
```

### 2. 3D统计工具 `fc3d_utils.py`

提供纯函数，供所有3D策略共享：

| 函数 | 作用 |
|---|---|
| `positional_frequency(records, lookback)` | 返回 `{0: {0: n, ...}, 1: {...}, 2: {...}}` 按位频率 |
| `sum_tail_statistics(records, lookback)` | 和尾（和值 mod 10）统计 |
| `span_statistics(records, lookback)` | 跨度（最大-最小）统计 |
| `road_012_statistics(records, lookback)` | 012路（mod 3）统计，返回每位各路比例 |
| `shape_ratio(records, lookback)` | 组三/组六/豹子历史比例 |
| `positional_weights(records, lookback, smoothing=1.0)` | 带拉普拉斯平滑的按位权重 |

### 3. 3D专属策略类 `fc3d.py`

全部继承 `GenerationStrategy`，与 `generic.py` 中的 `_GenericBase` 解耦。

| 类名 | 策略ID | 策略名 | 说明 |
|---|---|---|---|
| `FC3DRandomStrategy` | `random_3d` | 完全随机 | 每位独立随机0-9 |
| `FC3DOddEvenStrategy` | `odd_even_3d` | 奇偶均衡 | 默认让每位独立接近历史奇偶比例，也可配置整体奇数个数 |
| `FC3DHotColdStrategy` | `hot_cold_3d` | 冷热号分析 | 按位频率选热/冷/混合 |
| `FC3DExcludeIncludeStrategy` | `exclude_include_3d` | 排除/必含 | 支持按位必含/排除 |
| `FC3DSmartHotColdStrategy` | `smart_hot_cold_3d` | 智能冷热号 | 按位综合频率与遗漏 |
| `FC3DMissingNumberStrategy` | `missing_number_3d` | 遗漏号追踪 | 按位高遗漏优先 |
| `FC3DBalancedStrategy` | `balanced_3d` | 历史均衡 | **核心优化**，见下文 |
| `FC3DXGBoostStrategy` | `xgboost_3d` | XGBoost智能分析 | 独立类但内部复用 `GenericMLPredictor`，隔离未来 generic ML 改动 |
| `FC3DLightGBMStrategy` | `lightgbm_3d` | LightGBM智能分析 | 同上 |
| `FC3DCatBoostStrategy` | `catboost_3d` | CatBoost智能分析 | 同上 |

#### 3.1 历史均衡策略优化

`FC3DBalancedStrategy` 不再使用通用版的整体随机采样+排序，而是：

1. **按位采样**：每位独立使用按位冷热权重 + 拉普拉斯平滑生成候选。
2. **保留顺序**：结果直接是 `[百位, 十位, 个位]`，不再 `sorted()`。
3. **多维评分**：在奇偶、大小、和值基础上增加：
   - 跨度接近历史平均跨度
   - 和尾接近历史平均和尾
   - 012路比例接近历史比例
   - 形态（组三/组六/豹子）接近历史比例
4. **小空间枚举**：3D总组合仅1000种，可安全枚举全部组合并按评分排序取最优，避免 `max_attempts` 随机搜索低效。
5. **可配置项**：保留 `lookback`、`max_attempts`、`seed`；新增 `use_enumeration`（默认True）。

### 4. `build_strategies()` 路由改造

`caipiao/core/strategies/generic.py` 中的 `build_strategies()` 增加分发逻辑：

```python
def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]:
    if profile.key == "3d":
        from .fc3d import build_fc3d_strategies
        return build_fc3d_strategies(profile)
    # 原有通用逻辑保持不变
    ...
```

`needs_history()` 和 `is_ml_strategy()` 仍按策略ID前缀判断，因此3D策略ID沿用原有命名即可自动生效，无需修改。

### 5. 兼容性保证

- 策略ID不变：`random_3d`、`balanced_3d` 等。
- 策略名称不变："完全随机"、"历史均衡" 等。
- `get_config_schema()` 返回的字段名和默认值与通用版保持一致，UI参数面板无需改动。
- `generate(count, options)` 返回 `List[Ticket]`，且 `Ticket.profile` 仍为 `"3d"`。
- `needs_history()` / `is_ml_strategy()` 仍通过前缀识别，逻辑不变。

### 6. 错误处理

- 历史数据不足时，`validate_options()` 抛出与通用策略一致的 `ValueError`。
- 枚举模式下组合空间可控，不会超时；若用户显式关闭枚举且 `max_attempts` 不足，回退到当前最优候选或随机候选。
- 按位频率缺失某位历史数据时，使用拉普拉斯平滑赋予基线权重，避免除零。

### 7. 测试

新增 `tests/test_fc3d_strategies.py`，覆盖：

1. `test_fc3d_strategy_ids_unchanged`：验证 `build_strategies("3d")` 返回的策略ID集合与现在一致。
2. `test_fc3d_random_respects_order`：随机策略生成结果不排序，顺序有意义。
3. `test_fc3d_balanced_positional_weights`：历史均衡策略使用按位权重，每位频率不同则权重不同。
4. `test_fc3d_balanced_no_sort`：历史均衡结果保留原始生成顺序，不是排序后的数字。
5. `test_fc3d_balanced_span_and_tail`：验证评分结果考虑跨度和和尾。
6. `test_fc3d_balanced_enumeration`：枚举模式生成确定性最高评分组合。
7. `test_fc3d_exclude_include_positional`：按位必含/排除生效。
8. `test_fc3d_ml_strategies_ready`：XGBoost/LightGBM/CatBoost 3D策略能正常生成3位号码。
9. `test_fc3d_seed_reproducible`：相同种子下所有策略生成结果一致。
10. `test_fc3d_needs_history_prefix`：`needs_history("balanced_3d")` 仍为 True。

同时保留 `tests/test_lottery_unified.py` 中 `test_generic_random_3d`、`test_generic_predictor_recommend_3d` 等现有测试，确保不回归。

## 扩展预留

- `fc3d_utils.py` 未来可支持更多3D指标（如两码差、和值除3余数、冷热走势图）。
- 若排列3（`pl3`）也需要按位优化，可复用 `fc3d.py` 的多数逻辑，只需调整 `profile` 和策略ID前缀。
- 历史均衡的枚举模式可作为通用彩种小组合空间（如排列5有10万种组合）的参考，但本次不扩展。

## 风险

- 历史均衡改为枚举后，结果可能与原随机搜索版本差异较大，需要在测试和UI文案中明确说明这是"优化后的按位均衡"。
- 形态统计需要一定数量的历史数据（建议≥30期），数据过少时回退到均匀比例。
- ML策略的thin wrapper虽然逻辑简单，但仍需确保子进程训练、模型路径、参数面板等链路正常。
