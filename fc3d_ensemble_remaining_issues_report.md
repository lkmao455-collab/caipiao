# 福彩3D「三策略融合」策略遗留问题分析报告（第三轮）

> 分析对象：`caipiao/core/strategies/lotteries/fc3d/ensemble.py` — `FC3DEnsembleStrategy`（id=`ensemble_v2_3d`，name="三策略融合"）
> 前提：前两轮报告（`fc3d_ensemble_issues_report.md` 的 P1–P10、`fc3d_ensemble_followup_report.md` 的 R1–R8）所定位的问题已修复或部分修复。
> 本轮目标：**在前两轮修复的基础上，继续定位仍未解决或新暴露的问题**，仅做分析，不修改代码。
> 说明：所有结论均基于对当前代码的静态分析，部分问题附带临时验证脚本结果。

---

## 0. 结论速览

| 编号 | 问题 | 严重度 | 位置 |
|------|------|--------|------|
| N1 | `_ratio_signal` 硬编码 `z_threshold=2.0`，用户配置的 z 阈值不影响历史均衡子策略的奇偶/大小门控 | 🔴严重 | ensemble.py:188,275-280 |
| N2 | 子策略内部温度全部锁死 `1.0`，配置温度只作用于融合后；`log(prob)` 温度实现会扭曲分布尾部 | 🔴严重 | ensemble.py:287,307,345,479-480 |
| N3 | 去重采样按 `sorted tuple` 聚合后均匀选排列，破坏逐位概率模型的位置信息 | 🔴严重 | _base.py:96-100,123 |
| N4 | 模型只建模逐位独立概率，未利用号码形态（组三/组六/豹子）分布 | 🟠中等 | ensemble.py 整体架构 |
| N5 | 奇偶/大小信号使用三位合并的整体比例，粒度偏粗，无法反映逐位差异 | 🟠中等 | ensemble.py:251-257,275-280 |
| N6 | 自适应权重乘数是缺乏统计依据的启发式映射 | 🟠中等 | ensemble.py:366-392 |
| N7 | `details["weights"]` 仍是三位平均，字段语义未与旧消费者彻底切割 | 🟡轻微 | ensemble.py:550-555,569-572 |
| N8 | 同名类 `FC3DEnsembleStrategy` 的命名冲突仅通过别名部分缓解，未彻底消除 | 🟡轻微 | ensemble.py:588，advanced/lotteries/fc3d/ensemble.py |
| N9 | 缺少针对 ensemble 策略的专项单元测试，回归风险高 | 🟡轻微 | tests/ 目录 |
| N10 | `_zscore_list` 使用样本标准差并在 std 极小时返回全 0，可能丢失弱信号 | 🟢设计细节 | ensemble.py:170-181 |

---

## 1. N1（严重）`_ratio_signal` 硬编码 z 阈值，用户配置对 balanced 子策略失效

### 问题描述

`get_config_schema` 向用户暴露了一个统一的 `z_threshold` 配置项（默认 196，即 1.96；范围 100–300，对应 z=1.0–3.0），并在 tooltip 中说明：

> "统计显著性阈值。196=95%置信(z>1.96)，258=99%置信(z>2.58)。"

但代码里，这个配置项**只传给了 `_get_missing_probs`**（line 459），而 `_get_balanced_probs` 中用于奇偶/大小显著性门控的 `_ratio_signal` **硬编码了 `z_threshold=2.0`**：

```python
# ensemble.py:184-190
@staticmethod
def _ratio_signal(
    dev: float,
    sigma: float,
    positive_mask: List[bool],
    z_threshold: float = 2.0,   # ← 硬编码，未使用配置值
    max_gain: float = 3.0,
) -> List[float]:
```

调用处（ensemble.py:275-280）也没有把用户配置的 `z_threshold` 传入：

```python
parity_score = self._ratio_signal(
    odd_ratio - 0.5, sigma_ratio, odd_mask
)
size_score = self._ratio_signal(
    high_ratio - 0.5, sigma_ratio, high_mask
)
```

### 为什么严重

这是**配置项的静默失效**：用户调整 `z_threshold` 时期望影响整个策略的统计显著性门控，但实际上只影响遗漏号追踪分支。balanced 子策略的奇偶/大小信号仍然按固定 z=2.0 门控，用户对此毫不知情。

当用户把 `z_threshold` 调到 2.58（更严格）以期降低噪声时，balanced 的奇偶/大小门控仍按 2.0 放行；当用户调到 1.5（更宽松）以捕捉更弱的信号时，balanced 仍按 2.0 拦截。配置项的语义被撕裂。

### 建议修复方向

将用户配置的 `z_threshold` 透传给 `_ratio_signal`，保持策略内统计门控的一致性：

```python
parity_score = self._ratio_signal(
    odd_ratio - 0.5, sigma_ratio, odd_mask, z_threshold=z_threshold
)
```

---

## 2. N2（严重）子策略温度全部锁死，融合后温度实现扭曲分布

### 问题描述

#### 2.1 子策略温度被硬编码

三个子策略的概率生成全部使用 `temperature=1.0`：

- `_get_balanced_probs`: `softmax_scores(combined, temperature=1.0)`（line 287）
- `_get_hot_cold_probs`: `stable_scores(..., temperature=1.0)`（line 307）
- `_get_missing_probs`: `softmax_scores(logits, temperature=1.0)`（line 345）

这意味着配置项 `temperature`（默认 10，代码里除以 10 得 1.0）**只在最终融合后的概率上生效**，三个原始子策略各自的温度调节能力完全丢失。

原始策略中：
- `smart_hot_cold.py` 默认温度 1.0，但用户可调；
- `missing_number.py` 默认温度 0.5（更集中）；
- `balanced.py` 默认温度 1.0，但用户可调。

在 ensemble 中，这些差异被抹平，子策略的"个性"被削弱。

#### 2.2 融合后温度的数学实现不合理

当前实现（line 479-480）：

```python
logits = [math.log(max(p, 1e-12)) for p in fused]
fused = softmax_scores(logits, temperature)
```

`fused` 已经是三个概率分布加权平均后的概率向量（非 logits）。对其取对数再 softmax，本质上是做概率的幂变换：

```
p_i' ∝ p_i^(1/T)
```

这种温度化虽然能改变分布集中度，但存在两个问题：

1. **非线性扭曲**：它把子策略输出的概率当作能量值处理，而不是在子策略的原始得分（logits）上调节。当子策略概率已经接近 0 时，`log(p)` 会落到非常负的区域，再经过 softmax 会把原本接近 0 的概率相对抬升。
2. **`max(p, 1e-12)` clamp**：概率低于 1e-12 时被截断。在低温（T<1）且分布高度集中的场景下，多个数字的概率可能低于 1e-12，clamp 会扭曲尾部分布。

### 实证

在 pos0 明显偏向数字 4 的数据上（200 期），改变 config `temperature`：

```
T=0.1 (config 1):  pos0 max=0.8902, spread=0.8902
T=1.0 (config 10): pos0 max=0.4720, spread=0.4720
T=5.0 (config 50): pos0 max=0.2045, spread=0.1703
```

温度确实能改变集中度，但它是通过 `log(prob)` 实现的；子策略内部仍然是固定 T=1.0。

### 建议修复方向

1. 把配置温度透传给三个子策略，让温度在 logits 层面生效；
2. 或者在融合前用温度分别调节各子策略的概率，再平均；
3. 如果坚持只在融合后调温，应避免 `log(prob)` 截断，可改用 `p^(1/T)` 直接幂变换并归一化，数学上更透明。

---

## 3. N3（严重）去重采样破坏逐位概率的位置信息

### 问题描述

`_weighted_sample_without_replacement`（`_base.py:74-125`）按 `sorted tuple` 把直选组合聚合成组选：

```python
for combo in itertools.product(range(10), repeat=3):
    key = tuple(sorted(combo))
    p = pos_probs[0][combo[0]] * pos_probs[1][combo[1]] * pos_probs[2][combo[2]]
    group_probs[key] = group_probs.get(key, 0.0) + p
    group_perms.setdefault(key, []).append(combo)
```

然后在抽中某个 group 后，**均匀随机选择一个排列**（line 123）：

```python
selected.append(list(rng.choice(perms)))
```

这意味着：对于同一个数字集合 `{a,b,c}`，模型预测 `P(123)=0.5` 和 `P(321)=0.1` 时，去重后它们被合并为 `P({1,2,3})=0.6`，再被均匀拆成 `P(123)=P(321)=0.3`。模型对具体位置的判断被完全抹平。

### 为什么严重

三策略融合的核心就是**逐位概率模型**（百位、十位、个位可以有不同的概率分布）。去重模式却把这些位置信息丢弃，把排列视为等价。这与策略设计目标直接冲突。

### 实证

构造数据让 pos0 偏向 1、pos1 偏向 2、pos2 偏向 3，hot_cold 权重 100%：

```
dedup=False (n=1000): 123 出现 26 次，321 出现 3 次
                      → 模型正确预测 123 远更可能
dedup=True  (n=200):  123 与 321 均未命中（因为 220 组去重后覆盖有限）
```

虽然本次小样本未同时命中两者，但代码逻辑决定了：一旦 group `{1,2,3}` 被抽中，`123` 和 `321` 会被等概率选出，与模型原本的 26:3 比例完全不符。

### 建议修复方向

1. 如果必须去重，应保留 group 内各排列的相对概率加权选择，而不是均匀选排列；
2. 或者，去重模式下显式说明"位置特异性会部分丢失"；
3. 最佳方案：提供两种去重语义——"直选去重"（保留位置）与"组选去重"（当前行为）。

---

## 4. N4（中等）未建模号码形态分布

### 问题描述

三策略融合只生成三个独立的逐位概率分布，然后按位置采样。它完全没有建模 3D 号码的**组合形态**：

- 豹子号（如 111）：理论概率 1%
- 组选3（如 112）：理论概率 27%
- 组选6（如 123）：理论概率 72%

而原始 `balanced.py` 策略显式包含 `shape_score`，会根据历史形态比例偏离理论值进行惩罚/奖励。ensemble 把这一维度丢掉了。

### 后果

- 在均匀输入下，ensemble 输出的形态分布确实接近理论值（见下方实证），但这只是"独立采样碰巧得到"，不是策略主动控制的结果；
- 如果历史数据在形态上有显著偏离（例如近期豹子号明显偏少），ensemble **无法调整**输出以 compensate；
- 对于希望根据形态过滤号码的用户，ensemble 无法提供支持。

### 实证（均匀随机历史 200 期，生成 5000 组，dedup=False）

```
豹子号: 1.200% (理论 1%)
组选3:  26.080% (理论 27%)
组选6:  72.720% (理论 72%)
```

均匀输入下结果接近理论，但这不能掩盖策略缺乏形态控制能力的事实。在非均匀形态历史中，偏差无法被纠正。

### 建议修复方向

在采样阶段或评分阶段引入形态约束：
- 方案 A：在 `_weighted_sample_without_replacement` 中按 group 概率加权选择排列时，额外乘以一个形态权重；
- 方案 B：在生成后按形态比例过滤/重采样。

---

## 5. N5（中等）奇偶/大小信号使用整体比例，粒度偏粗

### 问题描述

`_get_balanced_probs` 中的奇偶/大小信号基于**三位合并的整体比例**：

```python
odd_ratio, _ = overall_odd_even_ratio(records, lookback)   # 三位合并
high_ratio, _ = overall_high_low_ratio(records, lookback)  # 三位合并

sigma_ratio = 0.5 / math.sqrt(max(3 * actual_n, 1))        # 假设三位独立同分布

parity_score = self._ratio_signal(
    odd_ratio - 0.5, sigma_ratio, odd_mask
)
size_score = self._ratio_signal(
    high_ratio - 0.5, sigma_ratio, high_mask
)
```

这意味着：
1. 用整体奇偶/大小比例去影响**每个位置**的概率；
2. 如果 pos0 偏奇、pos1 偏偶，整体比例可能接近 0.5，导致 parity_score≈0，两个位置的真实差异被抵消；
3. 如果 pos0、pos1 都偏奇，整体比例显著，parity_score 会给**所有位置**的奇数加分，包括实际上均匀的 pos2。

### 缓解因素

ensemble 同时有逐位频率得分 `freq_score`，它能在一定程度上捕捉逐位偏差。因此当某位有明显频率偏差时，`freq_score` 会主导该位。但当偏差以"形态/组合"方式出现（例如 pos0 奇、pos1 偶、pos2 奇这种结构性偏差）时，整体比例会失效。

### 建议修复方向

改用逐位奇偶/大小比例：

```python
# 对每个位置分别计算 odd_ratio[pos], high_ratio[pos]
# sigma_ratio[pos] = 0.5 / sqrt(actual_n)
parity_score = self._ratio_signal(odd_ratio[pos] - 0.5, sigma_ratio[pos], odd_mask)
```

---

## 6. N6（中等）自适应权重乘数是启发式，缺乏统计依据

### 问题描述

`_adaptive_weights_per_pos` 的分档逻辑：

```python
if uniform:
    mult = {"balanced": 1.0, "hot_cold": 1.0, "missing": 1.0}
elif chi2 > CHI2_01:  # >21.67
    mult = {"balanced": 0.8, "hot_cold": 1.0, "missing": 1.5}
else:  # 16.92 ≤ chi2 ≤ 21.67
    mult = {"balanced": 1.0, "hot_cold": 1.2, "missing": 1.0}
```

χ² 检验只能告诉我们"该位是否显著偏离均匀分布"，但**不能告诉我们偏离的类型**：
- 偏离可能是某些数字长期未出（冷号特征）→ 适合 missing；
- 也可能是某些数字近期频繁出现（热号特征）→ 适合 hot_cold；
- 还可能是 012 路、奇偶、大小的结构性偏离 → 适合 balanced。

当前映射把"强偏离"等同于"追冷"，把"中等偏离"等同于"追热"，这是作者的直觉假设，没有经过统计验证。

### 后果

在真实随机数据中，χ² 显著偏离的"原因"是多种多样的。自适应权重可能在某些场景下适得其反：
- 强偏离实际是热号集中 → 提升 missing 权重反而错误；
- 中等偏离实际是冷号特征 → 提升 hot_cold 权重反而错误。

### 建议修复方向

1. 根据具体偏离类型选择策略权重（例如：如果显著冷号多，提升 missing；如果热号集中，提升 hot_cold；如果结构比例失衡，提升 balanced）；
2. 或者将自适应改为更保守的"仅在 uniform 时降低激进策略权重"，避免强假设；
3. 增加回测验证，用历史数据训练/验证这些乘数。

---

## 7. N7（轻微）`details["weights"]` 字段语义仍不清晰

### 问题描述

上一轮 R2 修复后，`details` 现在同时包含：

```python
"weights": avg_weights,      # 三位平均权重
"pos_weights": final_pos_weights,  # 逐位实际权重
```

`avg_weights` 是三位权重的算术平均，用于兼容旧消费者。但字段名 `"weights"` 容易让旧代码误以为它是全局单一权重。当三位权重差异较大时（例如 pos0 missing=0%，pos1 missing=23%），平均权重会掩盖这种差异。

### 建议修复方向

1. 将 `"weights"` 重命名为 `"avg_weights"` 并保留 `"pos_weights"`；
2. 或在 `"weights"` 旁加 `"_note": "三位平均，详见 pos_weights"`；
3. 同步更新 `run_ensemble_v2.py` 等消费者，强制迁移到 `pos_weights`。

---

## 8. N8（轻微）命名冲突未彻底消除

### 问题描述

代码中仍然存在两个 `FC3DEnsembleStrategy`：

| 文件 | id | 行为 |
|------|----|----|
| `core/strategies/lotteries/fc3d/ensemble.py` | `ensemble_v2_3d` | 真实策略 |
| `core/strategies/advanced/lotteries/fc3d/ensemble.py` | `ensemble_3d` | ML 占位，抛异常 |

虽然真实策略模块增加了别名 `FC3DStrategyFusionStrategy`（line 588），但：
1. 类名仍然是 `FC3DEnsembleStrategy`；
2. 测试 `test_other_lottery_advanced_strategies.py:84` 仍引用 advanced 占位类；
3. 新维护者看到两个同名类仍容易混淆。

### 建议修复方向

将真实策略的类名改为 `FC3DStrategyFusionStrategy`，保持 `FC3DEnsembleStrategy` 作为弃用别名；或彻底重命名 advanced 占位类。

---

## 9. N9（轻微）缺少针对 ensemble 的单元测试

### 问题描述

`tests/` 目录下没有专门针对 `ensemble_v2_3d` 的测试文件。仅有的相关引用是：

- `tests/test_strategy_factory.py:17` 在策略列表中注册了 `ensemble_v2_3d`；
- `tests/test_other_lottery_advanced_strategies.py:19,84` 测试的是 advanced 占位类 `ensemble_3d`（会抛异常）。

这意味着：
- P1–P10、R1–R8 的修复依赖于临时验证脚本，没有沉淀为持续集成测试；
- 未来对 ensemble 的改动（尤其是 `_adaptive_weights_per_pos`、`_ratio_signal` 等）很容易回归；
- 用户配置的边界情况（如 `balanced=0, hot_cold=0, missing=100`、超大会 `count` 等）没有被测试覆盖。

### 建议修复方向

新增 `tests/test_fc3d_ensemble_v2.py`，覆盖：
- 均匀数据下输出接近均匀；
- 各配置项实际生效（尤其是 `z_threshold`、`temperature`、`adaptive`）；
- 禁用策略时的权重行为；
- `count > 220` 抛异常；
- `details["pos_weights"]` 正确反映逐位差异。

---

## 10. N10（设计细节）`_zscore_list` 使用样本标准差并存在全零回退

### 问题描述

```python
@staticmethod
def _zscore_list(vals: List[float]) -> List[float]:
    mean = statistics.mean(vals)
    std = statistics.stdev(vals)   # 样本标准差 (n-1)
    if std < 1e-10:
        return [0.0] * len(vals)
    return [(v - mean) / std for v in vals]
```

- 对 10 个数字做 z-score 时使用样本标准差（除以 n-1），而非总体标准差（除以 n）。差异约 5%，虽小但概念不一致。
- 当标准差极小时返回全 0，这会把原本存在的微弱信号完全丢弃。虽然避免了数值不稳定，但也让策略在"几乎均匀"数据上完全退化为均匀。

### 建议修复方向

1. 统一使用总体标准差（与 `stability.py` 中的 `_zscore_normalize` 行为一致）；
2. 在全零回退前，判断是否是真正意义上的"无差异"，避免过度平滑。

---

## 11. 问题优先级总结

```
N1 (z_threshold 硬编码) ──→ 配置项静默失效，用户无法通过 UI 控制 balanced 门控
N2 (温度系统)          ──→ 子策略温度丢失，融合后温度实现数学上扭曲分布
N3 (去重破坏位置信息)   ──→ 与策略核心设计目标冲突，dedup=True 时输出失真
N4 (无形态建模)        ──→ 丢失组合层面特征，无法纠正形态偏离
N5 (整体奇偶/大小)      ──→ 粒度偏粗，跨位置偏差会抵消或错误传播
N6 (自适应 heuristic)  ──→ 缺乏统计依据，可能适得其反
N7-N10                 ──→ 可维护性、测试、命名、数值细节
```

**当前最应优先处理的是 N1 和 N3**：
- N1 是明确的配置不一致 bug；
- N3 是架构级问题，直接影响去重模式下的输出质量。

---

## 12. 修复建议汇总（仅建议，待确认后再改代码）

| 编号 | 建议 |
|------|------|
| N1 | 将用户配置的 `z_threshold` 透传给 `_ratio_signal` |
| N2 | 子策略接收配置温度并在 logits 层面调温；或改用更透明的幂变换实现 |
| N3 | 去重采样保留 group 内排列的相对概率，或提供"直选去重"与"组选去重"两种语义 |
| N4 | 引入形态评分/权重，参考 `balanced.py` 的 `shape_score` |
| N5 | 改用逐位奇偶/大小比例 |
| N6 | 根据具体偏离类型（热/冷/结构）动态选择策略权重，或保守降低激进策略 |
| N7 | 重命名/标注 `"weights"` 字段，推动消费者迁移到 `"pos_weights"` |
| N8 | 重命名真实策略类为 `FC3DStrategyFusionStrategy`，消除同名冲突 |
| N9 | 新增 `tests/test_fc3d_ensemble_v2.py` 专项测试 |
| N10 | 统一使用总体标准差，谨慎处理全零回退 |

---

## 附：验证脚本

临时验证脚本存放于 `C:\Users\ADMINI~1\AppData\Local\Temp\verify_ensemble_new*.py`（共 3 个），运行方式：

```bash
E:/caipiao/venv/Scripts/python.exe /tmp/verify_ensemble_new2.py
E:/caipiao/venv/Scripts/python.exe /tmp/verify_ensemble_new3.py
```

脚本覆盖了 N1、N2、N3、N4、N9 的实证，结果与本报告一致。未修改项目任何代码。
