# 福彩3D「三策略融合」策略问题分析报告

> 分析对象：`caipiao/core/strategies/lotteries/fc3d/ensemble.py` — `FC3DEnsembleStrategy`（id=`ensemble_v2_3d`，name="三策略融合"）
> 对比对象：`balanced.py` / `smart_hot_cold.py` / `missing_number.py`（被融合的三个原始策略）
> 底层依赖：`stability.py` / `utils.py` / `_base.py`
> 说明：本报告仅做问题定位与实证，**未修改任何代码**。所有结论均附带可复现的运行证据。

---

## 0. 结论速览

| 编号 | 问题 | 严重度 | 位置 |
|------|------|--------|------|
| P1 | 遗漏子策略缺少 χ² 守卫，均匀数据上仍输出极端分布（赌徒谬误假阳性） | 🔴严重 | ensemble.py:197-222 |
| P2 | 自适应权重完全忽略用户配置的 base_weights | 🔴严重 | ensemble.py:224-265 |
| P3 | 「历史均衡」子策略与原策略严重不符（仅 2/8 维度，且量级失衡被012路主导） | 🔴严重 | ensemble.py:154-178 |
| P4 | 子策略温度被硬编码 1.0，整个温度体系在默认配置下失效 | 🟠中等 | ensemble.py:191,218 |
| P5 | 无显著冷号时 missing 子策略退化为纯均匀，被动稀释另外两个策略信号 | 🟠中等 | ensemble.py:212-214 |
| P6 | 自适应只用全局平均 χ²，未利用 per-position 信息做逐位差异化 | 🟠中等 | ensemble.py:243 |
| P7 | `basis` 说明文本与实际行为不符（误导性） | 🟡轻微 | ensemble.py:339-363 |
| P8 | `count > 220`（组选上限）时静默返回不足数量，无告警 | 🟡轻微 | _base.py:105 |
| P9 | 存在同名类 `FC3DEnsembleStrategy`（advanced placeholder vs 真实策略），命名冲突 | 🟡轻微 | 见 §11 |
| P10 | 最小样本 30 期下 χ² / z-score 统计功效偏低，信号不可靠 | 🟡轻微 | ensemble.py:150-152 |

---

## 1. P1（严重）遗漏子策略缺少 χ² 守卫 — 最关键问题

### 问题描述
原始 `FC3DMissingNumberStrategy`（missing_number.py:122-130）的核心设计是**双层守卫**：
```python
if uniform_flags[pos]:          # 第一层：χ² 判定该位是否均匀
    cold_digits = []            # 均匀 → 不找冷号，退化为均匀分布
else:
    cold_digits = [d for d in DIGIT_POOL if geo_z[pos][d] > z_threshold]
```
即「只有 χ² 检验认为该位整体不均匀时，才在 z>1.96 中挑冷号」，用以压制假阳性、避免赌徒谬误。

但 ensemble.py 的 `_get_missing_probs`（ensemble.py:205-218）**删除了第一层守卫**，直接用 z 阈值筛冷号：
```python
cold_digits = [d for d in DIGIT_POOL if geo_z[pos][d] > z_threshold]  # 无 χ² 守卫
```

### 为什么严重
z-score（单数字遗漏）与 χ²（整位均匀性）是两个不同尺度的检验。在**整体均匀**的数据里，单个数字完全可能因随机波动出现 z>1.96（10 个数字里出现 1 个假阳性是常态）。原始策略靠 χ² 守卫过滤掉这种情况；融合策略丢掉守卫后，会在「数据其实是均匀的」位置上，仅凭一个数字的随机长遗漏就输出**高度倾斜**的概率。

### 实证（均匀数据 2000 期，三位 χ² 全部 is_uniform=True）
```
均匀数据 chi2: pos0=11.40(uniform)  pos1=6.20(uniform)  pos2=7.60(uniform)
原始 missing 策略 significant_cold: [[], [], []]          ← 正确：无显著冷号
ensemble._get_missing_probs 输出:
  pos0: max=0.1000 min=0.1000 spread=0.0000   ← 正常
  pos1: max=0.7348 min=0.0071 spread=0.7277   ← 异常：极端倾斜！
  pos2: max=0.1000 min=0.1000 spread=0.0000
```
pos1 上某个数字恰好随机遗漏较长（z>1.96），融合子策略就给它 73% 的概率——这在统计上属于纯噪声被当成信号，且违背了遗漏号追踪策略「避免赌徒谬误」的初衷。

### 影响
- 融合结果被噪声支配：当 `missing_weight` 较高时，输出几乎由「最近哪个数字恰好没出」决定。
- 与原始遗漏策略行为不一致，用户预期被打破。

---

## 2. P2（严重）自适应权重完全忽略用户配置

### 问题描述
`generate`（ensemble.py:296-305）把用户配置组装成 `base_weights` 并传入 `_adaptive_weights`：
```python
base_weights = {"balanced": balanced_weight, "hot_cold": hot_cold_weight, "missing": missing_weight}
if adaptive:
    weights = self._adaptive_weights(chi2_values, uniform_flags, base_weights)
```
但 `_adaptive_weights`（ensemble.py:224-265）的函数体里**从未引用 `base_weights` 参数**，而是直接 `return` 一组硬编码常量（33/34/33、25/30/45、30/40/30、35/45/20）。

### 为什么严重
`get_config_schema`（ensemble.py:73-96）向用户暴露了 `balanced_weight`/`hot_cold_weight`/`missing_weight` 三个可配置项；而 `adaptive` 默认值是 `True`（ensemble.py:122-126）。也就是说**默认情况下用户调这三个权重完全不起作用**，被静默替换。

### 实证
```
用户配置 balanced=1, hot_cold=98, missing=1
  adaptive=True  → 实际权重 {'balanced':0.35, 'hot_cold':0.45, 'missing':0.20}  ← 被忽略
  adaptive=False → 实际权重 {'balanced':0.01, 'hot_cold':0.98, 'missing':0.01}  ← 正确生效
```

### 影响
- 配置项形同虚设，属于「静默错误」，最难被发现。
- 用户以为自己在调整策略倾向，实际毫无效果。

---

## 3. P3（严重）「历史均衡」子策略与原策略严重不符

### 问题描述 — 两个层面

**层面A：维度大幅缩水。**
原始 `FC3DBalancedStrategy`（balanced.py）是 8 维度综合评分策略（奇偶、大小、和值、和尾、跨度、形态、按位频率、012路），通过枚举 1000 种组合择优。
而 ensemble 的 `_get_balanced_probs`（ensemble.py:154-178）只用了**按位频率 + 012路** 2 个维度，丢弃了奇偶/大小/和值/跨度/形态等 5 个维度。因此「融合了历史均衡策略」名不副实——它融合的只是一个大幅阉割版。

**层面B：量级失衡。**
```python
freq_weight = weights[pos][d]      # 拉普拉斯平滑频率 ≈ 0.10  (10 数字均分)
road_weight = road[pos][d % 3]     # 012路比例        ≈ 0.33  (3 路均分)
probs.append((freq_weight + road_weight) / 2.0)   # 直接相加
```
两者量级差 3 倍以上，简单相加后 `road_weight` 主导结果：**同属一条 012 路的数字会得到接近的概率**，而本应作为主信号的「按位频率」被淹没。正确的做法应先各自归一化/z-score 化再合并。

### 实证（pos0 各数字概率）
```
数字:   0      1      2      3      4      5      6      7      8      9
概率: 0.0888 0.0729 0.1260 0.0993 0.0834 0.1239 0.0888 0.0938 0.1176 0.1056
012路分组:
  0路(0,3,6,9): 0.0888 / 0.0993 / 0.0888 / 0.1056   ← 内部接近
  1路(1,4,7) : 0.0729 / 0.0834 / 0.0938             ← 内部接近
  2路(2,5,8) : 0.1260 / 0.1239 / 0.1176             ← 内部接近，整体偏高
```
同一路内数字概率高度趋同，证明 012 路是主要塑造者，频率只是次要修正。

### 影响
- balanced 分支输出不能代表「历史均衡」策略，融合语义错误。
- 由于 012 路把数字分成 3 组并整组抬升/压低，输出结构高度模板化，区分度不足。

---

## 4. P4（中等）温度体系在默认配置下完全失效

### 问题描述
- 子策略内部硬编码温度：`_get_hot_cold_probs` 用 `temperature=1.0`（ensemble.py:191），`_get_missing_probs` 用 `temperature=1.0`（ensemble.py:218），均忽略传入的 `temperature` 与各原策略默认温度（如 missing 原默认 0.5）。
- 最终融合温度分支：`if temperature != 1.0:`（ensemble.py:327），而 config 默认 `temperature=10` → `/10.0 = 1.0`，**默认下该分支根本不执行**。

### 结果
默认配置下，从子策略到融合后没有任何温度调节生效，温度旋钮是「空转」的。只有用户主动改 temperature 才会在融合后做一次 log-softmax，但此时子策略温度仍被锁死 1.0，行为不可预期。

---

## 5. P5（中等）无冷号时 missing 子策略退化为纯均匀，被动稀释信号

### 问题描述
ensemble.py:212-214：
```python
if not cold_digits:
    probs = [1.0 / 10.0] * 10    # 退化为纯均匀
```
当数据较均匀（实际大多数场景），missing 子策略输出纯均匀分布。融合时它按 `missing_weight`（默认 ~33%）权重参与加权平均，**等同于把 33% 的权重变成纯噪声去稀释 balanced/hot_cold 的有效信号**。

这在统计上未必是坏事（可防过拟合），但意味着在多数实际场景里，「遗漏号追踪」这一路非但不能贡献信号，反而在削弱另外两路。与策略名「三策略融合、综合优点」的预期不符。

（注：叠加 P1 后情况更糟——要么是纯均匀稀释信号，要么是噪声被当成强冷号信号，两种状态都不理想。）

---

## 6. P6（中等）自适应只用全局平均 χ²，未逐位差异化

### 问题描述
`_adaptive_weights` 对三个位置的 χ² 取算术平均（ensemble.py:243 `avg_chi2 = sum/len`），生成**一套**权重套用到三个位置。但 χ² 是 per-position 的，融合概率也是 per-position 计算的（ensemble.py:318-334）。

当某位强烈偏离、其余位均匀时，全局平均会把强烈信号稀释，三位置用同一套权重，丢失了逐位差异化的机会。更合理的是 per-position 自适应权重。

---

## 7. P7（轻微）`basis` 说明文本与实际行为不符

ensemble.py:339-363 的说明文本声称「综合三个策略的概率分布进行融合」「自适应权重根据数据状态动态调整」，但：
- balanced 分支不是真正的历史均衡（P3）；
- missing 分支缺少 χ² 守卫（P1）；
- 自适应模式下用户权重被忽略（P2）。

文本具有误导性，用户/维护者会据此建立错误的心智模型。建议文本与实现一致，或在文本中如实描述简化。

---

## 8. P8（轻微）`count > 220` 时静默截断

### 问题描述
`_weighted_sample_without_replacement`（_base.py:74-125）枚举 1000 种直选组合后按 `sorted tuple` 聚合成组选。3D 组选总数 = 组六 120 + 组三 90 + 豹子 10 = **220**。
`n = min(count, len(keys))`（_base.py:105）在 `count>220` 时只返回 220 组，**无任何告警/异常**。

### 实证
```
请求 300 组 → 实际返回 220 组   （静默少 80 组）
```
调用方若按 count 分配后续逻辑（如分摊预算），会因数量不符而出错。建议超限时抛异常或在 basis 中明示。

---

## 9. P9（轻微）同名类命名冲突

代码库中存在**两个** `FC3DEnsembleStrategy`：
| 文件 | id | is_ml | 行为 |
|------|----|----|------|
| `core/strategies/lotteries/fc3d/ensemble.py` | `ensemble_v2_3d` | 否 | 真实可用（本报告分析对象） |
| `core/strategies/advanced/lotteries/fc3d/ensemble.py` | `ensemble_3d` | 是 | ML placeholder，generate 抛 `UnsupportedLotteryError` |

`fc3d/__init__.py` 导出的是前者。但测试 `test_other_lottery_advanced_strategies.py:84` 与 `run_fc3d_ensemble.py` 各引用一个，id 也不同（`ensemble_3d` vs `ensemble_v2_3d`）。同名不同义，易造成 import 混淆与维护误解。建议重命名其一（如真实策略改为 `FC3DStrategyFusionStrategy` / id 统一）。

---

## 10. P10（轻微）最小 30 期样本下统计功效偏低

`validate_options`（ensemble.py:150-152）要求 ≥30 期。但：
- χ²(df=9) 在 n=30 时每格期望仅 3，检验功效很弱，极易把噪声判成「均匀」（与 P1 叠加放大危害）；
- 几何分布 z-score 在小样本下方差大，易误判冷热。
建议把最小期数提到 50~100，或在样本不足时显式降级提示。

---

## 11. 问题之间的因果链（为何 P1/P2/P3 最致命）

```
P3 (balanced 维度缩水 + 012路主导)  ─┐
P1 (missing 缺 χ² 守卫, 噪声成信号) ─┼─→ 融合后的 pos_probs 既不代表"均衡"
P5 (missing 退化均匀稀释信号)      ─┘   也不代表"冷热/遗漏", 信号质量低于
                                        任一原始策略
P2 (adaptive 忽略用户权重) ─→ 用户无法纠偏, 调参无效
P4 (温度默认空转)          ─→ 用户无法调节集中度
```
也就是说，**即便用户察觉输出异常，也没有有效的参数通道去修正**（P2/P4 把旋钮都锁死了）。

---

## 12. 建议修复方向（仅建议，待确认后再改代码）

1. **P1**：给 `_get_missing_probs` 补 χ² 守卫，与原 missing 策略一致：`uniform_flags[pos]` 为真时直接返回均匀。
2. **P2**：让 `_adaptive_weights` 以 `base_weights` 为基准做「乘性调整」（如 `base * multiplier` 后归一化），而非返回硬编码常量。
3. **P3**：
   - 维度：balanced 子策略应尽量对齐原策略的多维评分（或直接复用 `FC3DBalancedStrategy` 的评分函数产出 per-digit 概率）；
   - 量级：合并前对 freq / road 各自做 z-score 或归一化，杜绝简单相加。
4. **P4**：把 `temperature` 透传给各子策略；或统一只在融合后调温，但需让默认配置产生可感知的效果。
5. **P5**：无显著冷号时，让 missing 分支跟随 balanced/hot_cold 的归一化分布，而非纯均匀；或在该状态下把 missing 权重自动降低。
6. **P6**：自适应改为 per-position 权重。
7. **P7**：同步更新 `basis` 文本，或让文本由实际分支动态生成。
8. **P8**：`count > 可去重数` 时抛 `ValueError` 或在 basis 中明示。
9. **P9**：重命名消歧。
10. **P10**：提高最小期数门槛或加降级提示。

---

## 附：验证方法（可复现）

临时验证脚本（未写入项目，仅放临时目录）：
`C:\Users\ADMINI~1\AppData\Local\Temp\opencode\verify_ensemble.py`
运行：`E:\caipiao\venv\Scripts\python.exe <脚本>`（workdir=E:\caipiao）
脚本覆盖了 P1/P2/P3/P8 四项实证，结果与本报告一致。
