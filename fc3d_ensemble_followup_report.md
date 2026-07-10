# 福彩3D「三策略融合」策略复审报告（第二轮）

> 分析对象：`caipiao/core/strategies/lotteries/fc3d/ensemble.py`（上轮已修复 P1–P10）
> 本轮目标：复审修复后的实现，定位**遗留问题**与**上轮修复新引入的回归**
> 说明：本报告**未修改任何代码**，所有结论均附实证证据（临时脚本运行结果）。

---

## 0. 背景与结论速览

上轮修复了 P1–P10（遗漏守卫、自适应权重、balanced 量级、温度、count 上限等），209 项测试通过、10 项验证脚本全 PASS。但本轮逐行复审 + 实证发现：**上轮 P3 修复（用 z-score 归一化 balanced 子策略）引入了一个新的严重回归**，另有 2 个中等问题与若干轻微/设计问题。

| 编号 | 问题 | 严重度 | 是否上轮引入 |
|------|------|--------|--------------|
| **R3** | balanced 子策略 z-score 归一化放大噪声，均匀数据下输出极端分布（max≈0.5） | 🔴严重 | ✅上轮 P3 引入的回归 |
| **R1** | `_reallocate_missing_weight` 在用户禁用 balanced/hot_cold 时强行启用它们 | 🟠中等 | ✅上轮 P5 引入 |
| **R2** | `details["weights"]` 只存 pos0，三位权重不同时误导消费者 | 🟠中等 | ✅上轮 P6 引入 |
| R4 | raw_missing/geo_z 在 hot_cold 与 missing 重复计算；频率统计重复 | 🟡轻微 | 遗留 |
| R5 | `_adaptive_weights_per_pos` 阈值 20/30 是魔数，与 χ² 临界值关系不严谨 | 🟡轻微 | 遗留 |
| R6 | 温度调节 `max(p,1e-10)` clamp 在低温+极端概率时失真 | 🟡轻微 | 遗留 |
| R7 | balanced 频率趋中（反热号）与 hot_cold（追热号）方向相反，融合时部分抵消 | 🟢设计权衡 | — |
| R8 | balanced 奇偶/大小用整体比例套各位，且奇偶×大小叠加产生四象限过度分组 | 🟡轻微 | ✅上轮 P3 引入 |

> 最关键的是 **R3**：它让 balanced 子策略在最常见的「均匀数据」场景下输出与预期截然相反的极端分布。这是上轮为修 P3（量级失衡）而采用的「z-score 归一化」方案的固有缺陷。

---

## 1. R3（严重）balanced 子策略 z-score 归一化放大噪声 — 上轮 P3 回归

### 问题描述
上轮 P3 为消除 freq(≈0.1) 与 road(≈0.33) 的量级失衡，把 balanced 改为「4 维各自 z-score 标准化后等权相加再 softmax」：
```python
freq_score  = [-abs(z) for z in zscore(freq)]     # 频率趋中
road_score  = [-abs(z) for z in zscore(road)]     # 012路趋中
parity_score = zscore([±odd_dev ...])              # 奇偶延续
size_score   = zscore([±high_dev ...])             # 大小延续
combined = freq + road + parity + size
probs = softmax(combined, T=1.0)
```

### 数学缺陷
`parity_raw` / `size_raw` 是**二元信号**（偶数取 +odd_dev，奇数取 -odd_dev，共 10 个值只有 2 种）。对二元信号做 z-score 标准化 `(x-mean)/std` 后，结果恒为 **±常数**（约 ±0.95），**与原始偏差 odd_dev 的大小无关**——无论 odd_dev=0.001（纯噪声）还是 0.2（强偏离），z-score 后都是 ±0.95。

即 z-score **丢失了「偏差有多显著」的信息，把任何微小噪声都放大成 O(1) 的强 logit**。

### 实证（2000 期纯随机均匀数据）
```
均匀数据: odd_ratio=0.4867 (odd_dev=-0.013, 噪声)  high_ratio=0.5067 (high_dev=+0.007, 噪声)
parity_score = [+0.95, -0.95, +0.95, -0.95, ...]   ← 0.013 的噪声被放大成 ±0.95!
size_score   = [-0.95, -0.95, ..., +0.95, +0.95]   ← 同理
combined     = [-1.52, -3.23, -1.18, -2.85, -1.61, -0.9, 0.38, -3.58, 0.71, -0.96]

_get_balanced_probs 输出:
  pos0: max=0.397  min=0.005  spread=0.392
  pos1: max=0.490  min=0.0014 spread=0.489
  pos2: max=0.521  min=0.003  spread=0.518
对照: 只用 freq+road(去掉 parity/size): spread=0.139
      含 parity+size:               spread=0.392   ← 放大近 3 倍
```
在**纯随机均匀数据**上，balanced 子策略竟把某些数字概率抬到 0.5、压到 0.001。而原 `FC3DBalancedStrategy` 在 `all_uniform` 时会退化为纯随机（balanced.py:248-270）。两者行为完全相反。

### 连带影响（R8）
parity 与 size 叠加后，数字被「奇偶 × 大小」分成 4 个象限：
- 偶且大（6,8）：parity+size 双正 → 强抬升
- 奇且小（1,3）：parity+size 双负 → 强压低
- 偶且小 / 奇且大：相互抵消
这种四象限分组在均匀数据上是**纯伪信号**。此外奇偶/大小用的是 `overall_*_ratio`（三位合并的整体比例）套用到每个位置，粒度也偏粗。

### 为什么上轮验证脚本没发现
上轮 P3 验证只检查了 `0 < min < max < 0.5`（输出落在合理区间），没有用**均匀数据**检验「是否接近均匀」。`max<0.5` 通过了，但 0.5 本身对均匀数据已是严重偏离（应为 0.1）。验证用例不够严格。

---

## 2. R1（中等）遗漏弃权重强行启用用户禁用的策略 — 上轮 P5 引入

### 问题描述
`_reallocate_missing_weight`（ensemble.py:181-198）在遗漏无信号时，把 missing 权重再分配给 balanced/hot_cold。但当用户**明确禁用** balanced 和 hot_cold（权重=0）时，`other_sum==0`，进入 else 分支**强行均分**：
```python
else:
    for o in others:
        w[o] = pool / len(others)   # 强行给 balanced/hot_cold 各 50%
```

### 实证
```
用户配置: balanced=0, hot_cold=0, missing=100 (只想用遗漏号)
均匀数据(missing 无信号):
  pos0/1/2 实际权重: {'balanced':0.5, 'hot_cold':0.5, 'missing':0.0}
  >> 违背用户意图: True
```
用户明确禁用 balanced/hot_cold，系统却因遗漏无信号而强行各赋 50%、把 missing 清零。这违背了 config schema 对 `*_weight min=0` 的承诺（用户有权禁用某策略）。

### 合理行为
当 other_sum==0（其它策略都被禁用）时，应**尊重禁用**：要么保留 missing 权重（即不弃权，该位用 missing 的均匀分布），要么让该位整体退化为均匀分布并明示，而非借用被禁用的策略。

---

## 3. R2（中等）`details["weights"]` 只存 pos0，三位差异化时误导 — 上轮 P6 引入

### 问题描述
上轮 P6 把权重改为 per-position 后，为兼容旧消费者保留了 `details["weights"]`，但只存第 1 位（ensemble.py:517）：
```python
"weights": final_pos_weights[0],   # 兼容旧访问（第1位权重）
"pos_weights": final_pos_weights,  # 逐位实际权重
```
而 per-position 自适应 + 遗漏弃权重会让三位权重**显著不同**。

### 实证（realistic 数据，adaptive=True）
```
details['weights'](旧字段) = {'balanced':0.493, 'hot_cold':0.507, 'missing':0.000}   ← 只是 pos0
pos_weights[0] = {'balanced':0.493, 'hot_cold':0.507, 'missing':0.000}  (missing无信号→已清零)
pos_weights[1] = {'balanced':0.329, 'hot_cold':0.441, 'missing':0.230}  (missing有信号)
pos_weights[2] = {'balanced':0.493, 'hot_cold':0.507, 'missing':0.000}
三位权重完全相同: False
```
消费者 `run_ensemble_v2.py:172` 读 `details['weights']` 显示「权重分配」，会误以为「遗漏=0%」是全局的，实际 pos1 遗漏=23%。`basis` 文本已正确显示逐位权重，但 `details` 旧字段与 basis 不一致，构成误导陷阱。

### 建议
旧字段应改为「全部三位的列表」或明确标注其仅代表 pos0；或直接弃用旧字段、让消费者迁移到 `pos_weights`。

---

## 4. R4（轻微）重复计算

- `_get_hot_cold_probs`（ensemble.py:256-257）与 `_get_missing_probs`（ensemble.py:284-285）各自独立调用 `raw_missing_periods` + `geometric_missing_zscore`（相同 records/lookback），重复 O(lookback) 计算。
- χ² 检验用的 `positional_frequency`（ensemble.py:383）与 balanced 用的 `positional_weights`（ensemble.py:216）都基于同一段历史的按位频率统计，可共享。
- 性能影响：lookback=100 时可忽略，但属代码质量问题，建议在 `generate` 顶部算一次后传入各子策略。

---

## 5. R5（轻微）自适应阈值是魔数

`_adaptive_weights_per_pos`（ensemble.py:333-341）的分档：
```
uniform (χ²<16.92)            → 1/1/1
χ²>30 (强偏离)                → b0.8/h1.0/m1.5
χ²>20 (中等)                  → b1.0/h1.2/m1.0
else 16.92≤χ²≤20 (轻微)       → b1.0/h1.3/m0.7
```
χ²(df=9) 临界值：5%=16.92、1%=21.67。分档阈值 20/30 与临界值关系不严谨（20 介于 5%~1% 之间，30 远超 1%）。且「中等偏离(>20)提升 hot_cold 而非 missing」缺乏统计依据——中等偏离既可能是热号趋势也可能是冷号特征，为何偏好 hot_cold 存疑。建议阈值对齐临界值，或让乘数随 χ² 连续变化而非阶梯。

---

## 6. R6（轻微）温度 clamp 失真

ensemble.py:436 `logits = [math.log(max(p, 1e-10)) for p in fused]`。当融合概率极小（<1e-10）时被 clamp 到 1e-10，低温下会被相对抬升。

实证：`temperature=0.1` 时全局最小概率 `3.57e-12 < 1e-10`，触发 clamp。影响有限（仅在极端低温 + 概率高度集中时），但理论上扭曲了输出分布的尾部。

---

## 7. R7（设计权衡）balanced 与 hot_cold 频率方向相反

balanced 的 freq 维度用 `-abs(z)`（趋中，反对热号），而 hot_cold 用频率追热号。两者在融合时对「频率」的方向相反，会部分抵消。这是「均衡」策略的预期效果（不让单一信号过强），不一定是 bug，但应在文档/tooltip 中说明，避免用户误以为「调高 balanced 权重会增强热号信号」。

---

## 8. 优先级与因果

```
R3 (balanced z-score 放大噪声)
  └─ 均匀数据(最常见场景)下 balanced 输出极端分布
     └─ 融合后整体分布被错误信号扭曲
        └─ 这是当前最影响输出质量的问题，应优先修复

R1 (弃权重强行启用禁用策略) ── 用户极端配置(0/0/100)下违背意图
R2 (details['weights']=pos0) ── 误导消费者，与 basis 文本不一致

R4/R5/R6/R8 ── 质量与精度问题，可批量优化
R7 ── 设计权衡，文档说明即可
```

---

## 9. 修复建议方向（仅建议，待确认后再改代码）

1. **R3（核心）**：balanced 子策略不应在均匀数据上输出极端分布。可选方案：
   - **(推荐)** 给 balanced 加 χ² 守卫：该位 `uniform_flags[pos]` 为真时直接返回均匀分布（与原 balanced 策略一致），从源头消除噪声放大；
   - 或：parity/size 不用 z-score，改用原始 `odd_dev/high_dev` 作为弱 logit（小偏差→小logit→接近均匀），并用 χ² 或 `|dev|` 做显著性 gating；
   - 或：对 parity/size 信号乘以一个「显著性系数」（如 `max(0, |odd_dev| - 噪声带)/噪声带`），只在偏离超噪声时才注入。
   - 建议三者结合：χ² 守卫 + 显著性 gating，最稳健。

2. **R1**：`_reallocate_missing_weight` 的 else 分支改为尊重禁用——`other_sum==0` 时不借用禁用策略，保留 missing 权重（该位用 missing 的均匀分布），并在 basis 注明「该位无显著信号」。

3. **R2**：`details["weights"]` 改为三位列表（与 `pos_weights` 一致）或加 `"_note": "pos0 only"` 字段；同时让 `run_ensemble_v2.py` 等消费者迁移到 `pos_weights`。

4. **R4**：在 `generate` 顶部统一计算 `raw_missing/geo_z/positional_frequency` 一次，传入各子策略。

5. **R5**：自适应乘数对齐 χ² 临界值（如 16.92/21.67），或改为 `mult = f(χ²)` 连续函数。

6. **R6**：温度 clamp 改为 `max(p, eps)` 配合「先减去 max(logits) 再 clamp」或在 clamp 前过滤零概率，减少尾部失真。

7. **R8**：随 R3 一并处理（奇偶/大小改用显著性 gating 后，四象限过度分组自然消失）。

---

## 附：验证与诊断方法（可复现）

- `Temp\opencode\verify_ensemble_v2.py`：覆盖 R1/R2/R3/R6 实证
- `Temp\opencode\diag_r3.py`：R3 根因诊断（各维度得分分解）
- 运行：`E:\caipiao\venv\Scripts\python.exe <脚本>`（workdir=E:\caipiao）
- 上轮的 10 项验证脚本（`verify_ensemble.py`）仍全部 PASS，但其中 P3 用例（`max<0.5`）不足以发现 R3——需要补「均匀数据下 spread 应≈0」的断言。
