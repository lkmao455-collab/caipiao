# 双色球“共识约束策略”设计文档

## 1. 目标与范围

本项目为现有双色球（SSQ）生成策略新增一个**综合性策略**，命名为 **共识约束策略（Consensus Constraint Strategy）**。该策略：

- **保留所有原有策略不变**，与原策略保持完全隔离，互不干扰。
- 融合现有统计/数学类策略的优点，通过**固定顺序的约束流水线**生成号码。
- 每个计算步骤都基于可解释的数学原理（频率统计、概率分布、贝叶斯推断、马尔可夫链、相关性等）。
- **所有可调参数均暴露在 UI 上**，代码中不使用任何字面常量作为默认行为。
- 在相同历史数据、相同 UI 参数、相同随机种子的情况下，**输出结果完全一致**；若不一致，则说明存在未暴露的参数或隐式状态。
- 提供**一键推荐参数**功能，并生成 HTML 报告，解释每个参数的数学原理和推荐依据。

**不包含的范围**：

- 不修改任何现有策略的代码或行为。
- 不包含机器学习类策略（XGBoost、LSTM、Transformer 等），以保证可解释性和结果确定性。
- 不承诺提高中奖概率；策略仅为基于历史统计的号码筛选工具。

## 2. 策略命名

- **中文名**：共识约束策略
- **英文名**：Consensus Constraint Strategy
- **策略 ID**：`consensus_constraint`

由于该策略依赖历史数据，必须将其 ID 前缀加入 `caipiao/core/strategies/factory.py` 中 `needs_history()` 的前缀列表，这样 UI、回测、参数组等上层逻辑才能自动注入历史开奖数据。

命名含义：候选号码必须通过多层数学约束的“共识”——既要符合统计先验，又要通过硬约束过滤，还要在概率精排中得分足够高，最终才能被选中。

## 3. 总体架构

新策略 `SSQConsensusConstraintStrategy` 继承自 `GenerationStrategy`，内部维护一条**固定顺序、不可调整**的数学约束流水线。所有子策略都在新策略内部**重新实例化**，与 UI 中其他策略实例完全隔离；新策略只通过 `get_config_schema()` 暴露参数，不依赖任何全局缓存、模型文件或隐式状态。

流水线包含以下阶段：

1. **统计先验建模**：基于历史数据，用多种统计视角（冷热号、遗漏号、智能加权等）计算红球、蓝球的初始概率分布。
2. **候选集生成**：按初始概率生成可配置数量的候选组合（候选池）。
3. **硬约束过滤**：依次施加奇偶比、大小比、和值范围、必含/排除号码等约束。
4. **概率精排**：用贝叶斯、马尔可夫、趋势、周期、相关性等模型计算每个剩余候选的综合得分。
5. **冲突回退**：若硬约束导致候选池为空，按逆序自动放宽约束并记录原因。
6. **确定性抽样**：使用用户指定的随机种子，从最终候选池中无放回抽样出指定数量的号码组合。

## 4. 子策略执行顺序与分工

为符合“顺序过滤/约束叠加”和“可解释”的原则，流水线固定为以下 6 个阶段，顺序不可调整（不在 UI 上暴露顺序参数，避免隐藏变量）：

| 阶段 | 使用的子策略 | 作用 |
|------|-------------|------|
| 1. 统计先验建模 | `stats`、`smart_hot_cold`、`hot_cold`、`missing_number` | 计算初始红球/蓝球概率分布 |
| 2. 候选集生成 | `random`（按阶段 1 的概率） | 生成大量候选组合 |
| 3. 硬约束过滤 | `odd_even`、`balanced`、`exclude_include` | 过滤不符合约束的组合 |
| 4. 概率精排 | `bayesian`、`markov`、`trend`、`periodic`、`correlation` | 为剩余候选打分 |
| 5. 冲突回退 | — | 自动放宽最后应用的约束，直到候选池非空 |
| 6. 确定性抽样 | — | 按全局 seed 从最终候选池抽样 |

**隔离措施**：每个子策略对象都在 `SSQConsensusConstraintStrategy` 内部新建，不读取/写入任何全局缓存；所有需要的状态都通过 `options` 传入。

## 5. UI 参数暴露方案

为做到“所有参数都在 UI 上、代码中无常量”，`get_config_schema()` 按流水线阶段分组暴露全部可调参数。参数名前加阶段前缀，避免冲突，例如 `stats_lookback`、`bayesian_alpha`。

### 5.1 全局/流水线参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `seed` | int | 统一随机种子（必填），保证可复现 |
| `candidate_count` | int | 候选池大小，例如 50000~200000 |
| `relaxation_order` | choice | 冲突时放宽顺序，可选 `reverse`（逆序自动放宽，默认）或 `strict`（不放宽，直接报错） |
| `predict_date` | date（可选） | 周期分析使用的预测日期；不填则使用历史最后一条 `draw_date` + 1 天。若 UI 当前不支持 date 类型，可用 `str`（ISO 格式，如 `2026-07-10`）实现，同样暴露为 UI 参数 |
| `blue_sampling_mode` | choice | 蓝球抽样方式：`uniform`（均匀随机）或 `weighted`（按阶段 1 蓝球概率加权），默认 `weighted` |

### 5.2 阶段 1：统计先验建模参数

| 参数名 | 来源策略 | 说明 |
|--------|----------|------|
| `stats_enabled` | stats | 是否启用统一统计分析 |
| `stats_mode` | stats | hot / cold / mixed / smart / missing |
| `stats_lookback` | stats | 回看期数 |
| `stats_hot_weight` | stats | smart 模式下热号权重 |
| `stats_cold_weight` | stats | smart 模式下冷号权重 |
| `stats_pool_size` | stats | missing 模式下候选池大小 |
| `stats_weight` | stats | 在统计先验融合中的相对权重 |
| `smart_hot_cold_enabled` | smart_hot_cold | 是否启用智能冷热 |
| `smart_hot_cold_lookback` | smart_hot_cold | 统计期数 |
| `smart_hot_cold_hot_weight` | smart_hot_cold | 热号权重 |
| `smart_hot_cold_cold_weight` | smart_hot_cold | 冷号权重 |
| `smart_hot_cold_weight` | smart_hot_cold | 在统计先验融合中的相对权重 |
| `hot_cold_enabled` | hot_cold | 是否启用冷热号分析 |
| `hot_cold_mode` | hot_cold | hot / cold / mixed |
| `hot_cold_weight` | hot_cold | 在统计先验融合中的相对权重 |
| `missing_number_enabled` | missing_number | 是否启用遗漏号追踪 |
| `missing_number_lookback` | missing_number | 统计期数 |
| `missing_number_pool_size` | missing_number | 候选池大小 |
| `missing_number_weight` | missing_number | 在统计先验融合中的相对权重 |

阶段 1 的最终概率分布为各启用策略概率向量的**加权算术平均**：

```
P_initial = Σ(P_strategy_i × weight_i) / Σ(weight_i)
```

**适配说明**：现有部分策略（如 `hot_cold`、`missing_number`）原始输出的是“候选池”而非概率向量。在新策略中，会先将这些候选池转换为概率向量（池内号码等概率、池外号码概率为 0），再参与加权平均。所有转换规则都必须是确定性的，并写入实现代码与 HTML 报告中。

### 5.3 阶段 3：硬约束参数

| 参数名 | 来源策略 | 说明 |
|--------|----------|------|
| `odd_even_enabled` | odd_even | 是否启用奇偶约束 |
| `odd_count` | odd_even | 红球中奇数个数（0~6） |
| `balanced_enabled` | balanced | 是否启用历史均衡约束 |
| `balanced_lookback` | balanced | 统计历史分布的期数 |
| `sum_min` | balanced | 红球和值下限 |
| `sum_max` | balanced | 红球和值上限 |
| `target_odd` | balanced | 目标奇数个数 |
| `target_high` | balanced | 目标大号（≥17）个数 |
| `exclude_include_enabled` | exclude_include | 是否启用包含/排除 |
| `include_red` | exclude_include | 必含红球列表 |
| `exclude_red` | exclude_include | 排除红球列表 |
| `exclude_blue` | exclude_include | 排除蓝球列表 |

### 5.4 阶段 4：概率精排参数

| 参数名 | 来源策略 | 说明 |
|--------|----------|------|
| `bayesian_enabled` | bayesian | 是否启用贝叶斯推断 |
| `bayesian_prior_weight` | bayesian | 先验权重（0~100） |
| `bayesian_lookback` | bayesian | 观测窗口期数 |
| `bayesian_alpha` | bayesian | 先验强度 |
| `markov_enabled` | markov | 是否启用马尔可夫链 |
| `markov_order` | markov | 马尔可夫链阶数（1/2/3） |
| `markov_lookback` | markov | 预测融合窗口 |
| `markov_transition_weight` | markov | 转移概率融合权重（替代原代码中硬编码的 0.7/0.3） |
| `trend_enabled` | trend | 是否启用趋势分析 |
| `trend_window_size` | trend | 趋势窗口大小 |
| `trend_weight` | trend | 趋势权重（0~100） |
| `periodic_enabled` | periodic | 是否启用周期性分析 |
| `periodic_week_weight` | periodic | 周周期权重 |
| `periodic_month_weight` | periodic | 月周期权重 |
| `periodic_quarter_weight` | periodic | 季度周期权重 |
| `correlation_enabled` | correlation | 是否启用相关性挖掘 |
| `correlation_min_support` | correlation | 最小支持度（0~100） |
| `correlation_weight` | correlation | 相关性权重（0~100） |

阶段 4 的综合得分计算为各启用模型对候选组合得分的加权平均。具体地，每个模型先输出单个红球的概率向量，再对候选组合中的 6 个红球概率取对数求和（或算术平均），得到该组合的模型得分；最后将各模型得分按权重平均，按从高到低排序候选池。

**蓝球处理**：阶段 4 的概率精排目前仅针对红球；蓝球在最终抽样时从可用蓝球集合中按均匀分布或阶段 1 的蓝球概率抽取（具体方式作为 UI 参数 `blue_sampling_mode` 暴露）。

### 5.5 UI 控件布局

由于参数较多，策略面板将：

- 使用 **QScrollArea / 滚动面板** 承载所有参数控件，避免界面拥挤。
- 按阶段分组显示，使用 `QGroupBox` 分隔“全局参数”、“统计先验”、“硬约束”、“概率精排”。
- 在面板顶部放置“一键推荐参数”按钮。

## 6. 一键推荐参数

新策略增加类方法：

```python
@classmethod
def recommend_parameters(cls, records: List[DrawRecord]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    ...
```

返回两个字典：

- 第一个：推荐参数值，可直接填充到 UI。
- 第二个：每个参数的推荐原因（用于 HTML 报告）。

推荐规则基于历史数据统计特征，示例：

| 参数 | 推荐规则 | 数学/统计依据 |
|------|----------|--------------|
| `stats_lookback` | `min(int(len(records) * 0.8), 5000)` | 使用大部分历史数据，兼顾稳定性与近期性 |
| `odd_count` | `round(6 × historical_odd_ratio)` | 匹配历史奇偶分布的期望 |
| `sum_min` / `sum_max` | `avg_sum ± 1.5 × std_sum` | 覆盖约 86% 的历史和值（切比雪夫/经验规则） |
| `target_high` | `round(6 × historical_high_ratio)` | 匹配历史大小号分布 |
| `trend_window_size` | `max(5, min(30, len(records) // 10))` | 保证窗口内样本量足够 |
| `correlation_min_support` | `max(1, min(10, len(records) // 100))` | 随数据量动态调整支持度阈值 |

所有推荐规则都必须在代码中用数学公式表达，并在 HTML 报告中给出解释。

## 7. HTML 报告

### 7.1 触发方式

在“共识约束策略”参数面板顶部显示“一键推荐参数”按钮。点击后：

1. 调用 `recommend_parameters(records)` 计算推荐值。
2. 自动填充 UI 控件。
3. 生成 HTML 报告。
4. 通过 Qt `QTextBrowser` 弹窗显示报告，同时保存到 `docs/reports/consensus_constraint_<timestamp>.html`。

### 7.2 报告内容

1. **报告头**：策略名、历史数据起止期、历史记录条数、生成时间戳（仅用于展示，不影响生成结果）。
2. **参数解释表**：
   - 参数名
   - 推荐值
   - 数学原理（该参数在流水线中的作用）
   - 推荐依据（基于哪个统计量、公式是什么）
3. **生成详情**：
   - 初始候选池大小（`candidate_count`）
   - 各硬约束过滤后剩余候选数量
   - 被自动放宽的约束及原因
   - 最终候选池大小
   - 最终抽样的号码组合
4. **数学声明**：明确说明彩票开奖是独立随机事件，所有计算仅基于历史统计进行筛选，不保证中奖。

### 7.3 报告模板位置

HTML 模板可内嵌在策略类中（简单的字符串模板），避免额外文件依赖。报告样式使用内联 CSS，保证在不同环境下显示一致。

## 8. 确定性/可复现性保证

要做到“相同 UI 参数下输出一致”，新策略在实现上必须满足：

1. **单一随机源**：整个流水线只使用一个 `seed` 初始化 `random.Random(seed)` 和 `np.random.RandomState(seed)`，并显式传给所有需要随机性的子步骤。不允许使用全局随机状态。
2. **禁止隐式时间**：不使用 `datetime.now()`。周期分析基于历史记录最后一条的 `draw_date` 计算下一个预测日期；若用户指定 `predict_date`，则使用该参数。
3. **确定性的集合操作**：过滤、排序、去重都使用稳定排序；候选组合用有序元组表示，抽样前对候选池按得分+字典序排序。
4. **不依赖外部状态**：不读取模型缓存文件、不依赖线程状态、不依赖全局计数器。
5. **参数完整性检查**：新增单元测试，固定 seed 和历史数据，连续调用 10 次，断言输出完全一致；若不一致则测试失败，提示存在未暴露参数或隐式状态。

## 9. 冲突回退

当硬约束叠加后候选池为空时，按以下规则自动回退，直到候选池非空：

1. **记录冲突点**：记录是哪一层约束导致候选池为空。
2. **逆序放宽**：按约束应用顺序的逆序，逐步放宽最后应用的约束：
   - 首先放宽 `balanced` 的和值范围（每次扩大 ±10%）。
   - 其次放宽 `odd_even` 的奇数个数（允许 ±1 偏差）。
   - 最后放宽 `exclude_include`（优先减少排除数量，不触碰必含号码）。
3. **报告到 basis**：最终输出的 `basis` 字段中说明哪些约束被放宽以及原因，保证可追溯。
4. **硬底线**：若放宽到仅剩 `include_red` 都无法满足，则抛出明确错误提示用户调整参数。

## 10. 文件结构

新增/修改的文件清单：

1. **`caipiao/core/strategies/advanced/lotteries/ssq/consensus_constraint.py`**
   - 新策略 `SSQConsensusConstraintStrategy` 的实现。
   - 包含流水线、参数 schema、`recommend_parameters()`、HTML 报告生成。

2. **`caipiao/core/strategies/registry.py`**
   - 在 `STRATEGY_REGISTRY["ssq"]` 中注册 `SSQConsensusConstraintStrategy`。

3. **`caipiao/core/strategies/factory.py`**
   - 将 `consensus_constraint` 加入 `needs_history()` 的前缀列表，确保上层能自动注入历史数据。
   - 在 `register_builtin_strategies()` 中实例化并注册新策略。

4. **`caipiao/ui/components/strategy_panel.py`**
   - 扩展策略面板，支持策略自定义操作按钮。
   - 当检测到策略实现了 `recommend_parameters()` 方法时，自动显示“一键推荐参数”按钮。

5. **`tests/test_ssq_consensus_constraint.py`**
   - 覆盖元数据、生成有效性、确定性、参数推荐、冲突回退、HTML 报告、隔离性、参数暴露完整性等测试。

6. **`docs/reports/` 目录**
   - 运行时生成的 HTML 报告保存位置（目录不存在则自动创建）。

## 11. 测试策略

新增测试文件 `tests/test_ssq_consensus_constraint.py` 覆盖：

1. **元数据测试**：策略 ID 为 `consensus_constraint`，名称正确，`configurable=True`。
2. **生成有效性测试**：生成结果符合双色球规则（6 红 + 1 蓝，红球不重复，范围正确）。
3. **确定性测试**：固定 seed、history、全部参数，连续调用 10 次，断言输出完全一致。
4. **参数推荐测试**：`recommend_parameters()` 返回的选项通过 `validate_options()`，且每个推荐值都有非空原因。
5. **冲突回退测试**：设置无法同时满足的约束（如排除过多号码 + 和值范围极窄），验证策略能自动放宽并返回结果，且 `basis` 中记录了放宽信息。
6. **HTML 报告测试**：调用报告生成方法，验证文件存在、包含参数解释表和生成详情。
7. **隔离性测试**：
   - 同时实例化新策略与一个原策略（如 `SSQBalancedStrategy`）。
   - 先调用原策略生成号码，再调用新策略生成号码。
   - 验证：新策略的输出不受原策略调用影响；反之亦然。两个策略实例不共享任何可写状态。
8. **参数暴露完整性测试**：遍历 `get_config_schema()` 返回的 key，确保 `generate()` 中没有使用未在 schema 中出现的字面常量（通过代码审查或运行时 mock 验证）。

## 12. 风险与限制

1. **参数数量庞大**：UI 上会有数十个参数。通过分组和滚动面板缓解，但仍需用户理解。
2. **候选池大小与性能**：`candidate_count` 过大（如 > 20 万）会增加内存和计算开销。默认值建议 5 万，UI 上给出合理范围。
3. **“推荐参数”并非最优**：推荐仅基于历史统计特征，不做回测优化，不保证中奖。
4. **与原策略行为差异**：新策略是独立实现，即使复用了原策略的数学思想，输出也与原策略不同。
5. **周期分析的日期依赖**：若历史数据为空且用户未指定 `predict_date`，策略无法运行，需给出明确错误。

## 13. 后续步骤

本设计文档经用户确认后，将使用 `writing-plans` 技能制定详细实现计划，然后按 plan 执行编码、测试和验证。
