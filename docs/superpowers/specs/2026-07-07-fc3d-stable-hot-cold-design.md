# 福彩3D 智能冷热号稳定化与最优参数固定设计文档

## 1. 背景与问题

当前福彩3D策略中，基于历史数据的生成策略（冷热号分析、智能冷热号、遗漏号追踪、历史均衡）存在以下稳定性问题：

1. **评分敏感**：`FC3DSmartHotColdStrategy` 使用 `max_freq` 和 `max_missing` 做最大值归一化，历史数据稍有变动就会导致所有数字的冷热评分剧烈 rescale。
2. **采样离散**：`FC3DHotColdStrategy` 和 `FC3DMissingNumberStrategy` 先选出固定候选池，再在池内均匀随机抽取，池子边缘的排序 tie 会让概率分布出现跳变。
3. **随机种子默认缺失**：当用户不填 seed 时，每次生成都不同，无法保证「前后一致」。
4. **一键扫描维度单一**：`OptimalStrategyScanThread` 仅扫描 `lookback` / `history_count`，没有针对热冷权重、候选池大小等关键参数寻优。
5. **最优参数无法固定**：扫描结果只能以「参数组」形式保存，策略本身的默认参数仍会被下次扫描覆盖，缺乏「锁定」机制。

## 2. 目标

- 让福彩3D各历史类策略在**相同历史 + 相同种子**下输出完全可复现。
- 让各策略的生成概率对历史数据的**小幅度更新**保持平滑，不剧烈跳变。
- 扩展「一键找最优策略和参数」，支持**多参数网格扫描**。
- 提供**参数锁定**与**配置持久化**，把最优参数固定下来并在启动时自动加载。
- 引入**交叉验证稳定性指标**，优先推荐「高收益 + 高稳定」的参数组合。

## 3. 非目标

- 不保证中奖率提升（彩票本身随机）。
- 不改动双色球、大乐透等其他彩种策略。
- 不做需要重新训练模型架构的 ML 改造。
- 不强制所有策略输出相同号码（允许策略间保持差异化）。

## 4. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                     UI 层 (PySide6)                          │
│  StrategyPanel ── ParameterGroupPanel ── OptimalScanDialog   │
│         ▲                ▲                    │              │
└─────────┼────────────────┼────────────────────┼──────────────┘
          │                │                    │
          │                │         ┌──────────▼──────────┐
          │                │         │ OptimalStrategyScan │
          │                │         │    Thread           │
          │                │         └──────────┬──────────┘
          │                │                    │
          │                │    ┌───────────────▼────────────┐
          │                │    │   OptimalParamStore        │
          │                │    │  (optimal_params.json)     │
          │                │    └───────────────┬────────────┘
          │                │                    │
          │         ┌──────▼──────┐             │
          │         │ ParameterGroup│ ◄─────────┘
          │         │    Store      │
          │         └───────────────┘
          │
┌─────────▼───────────────────────────────────────────────────┐
│                   核心策略层                                  │
│  FC3DHotColdStrategy / SmartHotColdStrategy /                │
│  MissingNumberStrategy / BalancedStrategy / Random / OddEven │
│         ▲                                                     │
│  ┌──────┴──────────┐                                          │
│  │ FC3DStrategyStabilizer                                     │
│  │  - stable_frequency()                                      │
│  │  - stable_missing()                                        │
│  │  - stable_scores()                                         │
│  │  - deterministic_seed()                                    │
│  └──────────────────┘                                         │
│         ▲                                                     │
│  ┌──────┴──────────┐                                          │
│  │ StabilityValidator                                         │
│  │  - cross_validate_params()                                 │
│  │  - stability_score()                                       │
│  └──────────────────┘                                         │
└───────────────────────────────────────────────────────────────┘
```

## 5. 组件设计

### 5.1 FC3DStrategyStabilizer（新增 `caipiao/core/strategies/fc3d_stability.py`）

统一提供稳定的统计工具，被所有福彩3D历史类策略调用。

| 函数 | 职责 |
|------|------|
| `stable_frequency(records, lookback, smoothing=1.0)` | 拉普拉斯平滑后的按位频率，避免 0 概率和离群最大值影响。 |
| `stable_missing(records, lookback, cap=None)` | 计算按位遗漏值，超过 cap 的部分截断，降低极端遗漏的冲击。 |
| `stable_scores(hot_scores, cold_scores, hot_weight, cold_weight, temperature=1.0)` | 先分别 min-max 归一化到 `[0,1]`，加权求和后再做 softmax 转概率。 |
| `deterministic_seed(options, history_hash=None)` | 若用户未提供 seed，则根据「策略 ID + lookback 内历史数据内容的 hash」派生一个确定性 seed，保证相同历史可复现。 |
| `sample_weighted(rng, values, probabilities)` | 包装 `rng.choices`，并对概率做极小值兜底，避免权重全 0。 |

**关键稳定性改进**：
- 不再使用全局 `max_freq` / `max_missing` 直接除，而是对每位分别 min-max 归一化，再用 softmax 输出概率分布。
- 拉普拉斯平滑保证即使某数字在 lookback 内未出现，也保留非 0 概率。
- 遗漏值 cap 防止某数字长期未出时获得压倒性权重。

### 5.2 策略改造

#### FC3DHotColdStrategy
- 使用 `stable_frequency(..., smoothing=1.0)`。
- `mode` 仍然决定排序方向：`hot` 按频率降序、`cold` 按频率升序、`mixed` 同时考虑频率高低两端。
- 不再只选前 5 / 后 5 / 前 2 + 后 2 做均匀抽取，而是对全部 10 个数字按排序后的 rank 做 softmax 概率分布加权采样。
- 新增 `temperature` 可调参数（默认 1.0）：温度越低，概率越集中在排名靠前的数字；温度越高，分布越接近均匀。

#### FC3DSmartHotColdStrategy
- 使用 `stable_frequency` + `stable_missing`。
- 冷热评分通过 `stable_scores(...)` 合并为概率分布。
- `hot_weight`、`cold_weight`、`lookback`、`temperature` 均参与一键扫描。
- 默认 seed 通过 `deterministic_seed` 派生。

#### FC3DMissingNumberStrategy
- 使用 `stable_missing(..., cap=lookback)`。
- 保留 `pool_size` 作为「考虑的候选数量」，但不再在池内均匀随机抽取；改为按遗漏值对池内数字做 softmax 加权采样。
- `lookback`、`pool_size`、`temperature` 参与扫描。

#### FC3DBalancedStrategy
- 已在枚举模式下确定性强，主要优化 `weight_score` 的缩放系数，使其对历史变化的敏感度降低。
- `lookback`、`max_attempts` 参与扫描。

#### FC3DRandomStrategy / FC3DOddEvenStrategy
- 不依赖历史，但统一使用 `deterministic_seed` 在 seed 缺失时提供可复现性。

### 5.3 多参数网格扫描（改造 `caipiao/ui/optimal_period_config.py`）

新增 `STRATEGY_PARAM_GRID`：

```python
STRATEGY_PARAM_GRID: dict[str, dict[str, list]] = {
    "smart_hot_cold_3d": {
        "lookback": [30, 50, 80, 100, 150],
        "hot_weight": [30, 50, 70, 90],
        "cold_weight": [10, 30, 50, 70],
        "temperature": [0.5, 1.0, 1.5],
    },
    "missing_number_3d": {
        "lookback": [30, 50, 80, 100],
        "pool_size": [3, 5, 7],
        "temperature": [0.5, 1.0, 1.5],
    },
    "balanced_3d": {
        "lookback": [50, 80, 100, 150],
        "max_attempts": [500, 1000, 2000],
    },
    "hot_cold_3d": {
        "mode": ["hot", "cold", "mixed"],
        "temperature": [0.5, 1.0, 1.5],
    },
    "xgboost_3d": {"history_count": [100, 200, 300, 500, -1]},
    "lightgbm_3d": {"history_count": [100, 200, 300, 500, -1]},
    "catboost_3d": {"history_count": [100, 200, 300, 500, -1]},
}
```

`resolve_optimal_param` 扩展为返回完整网格，扫描线程使用笛卡尔积遍历。

### 5.4 参数锁定与持久化（新增 `caipiao/persistence/optimal_param_store.py`）

数据模型：

```python
@dataclass
class LockedParameter:
    strategy_id: str
    param_name: str
    param_value: Any
    source: str  # "scan", "user", "default"
    locked_at: str
    stability_score: float
    cv_mean_prize: float
    cv_std_prize: float

@dataclass
class OptimalParamsConfig:
    profile_key: str
    locked: list[LockedParameter]
    last_scan_at: str | None
```

存储文件：`<app_data_dir>/optimal_params/<profile_key>.json`，与 `parameter_group_store` 的 `<app_data_dir>/param_groups/<profile_key>.json` 保持一致。

行为：
- 启动时加载，覆盖对应策略 `config_schema` 的 `default` 值。
- 扫描时，已被锁定的参数从网格中排除；其余参数继续扫描。
- 扫描完成弹窗提示用户哪些新参数建议锁定，用户确认后写入持久化。
- UI 上锁图标表示已锁定参数，双击或右键可解锁。

### 5.5 交叉验证稳定层（新增 `caipiao/core/strategies/stability_validator.py`）

```python
def cross_validate_params(
    strategy_id: str,
    records: list[DrawRecord],
    param_grid: dict[str, list],
    n_folds: int = 3,
    tickets_per_round: int = 5,
) -> list[CrossValidationResult]:
    ...

def stability_score(cv_results: list[RoundResult]) -> float:
    """返回 0~1 的稳定性分数，1 表示最稳定。基于 CV 收益的变异系数。"""
    ...
```

扫描线程选择最优时，排序键改为：

```python
key = (
    cv_stability_score,      # 高稳定性优先
    cv_mean_fixed_prize,     # 高平均收益
    -cv_std_fixed_prize,     # 低波动
)
```

### 5.6 UI 变更

- `StrategyPanel`：
  - 参数控件旁显示 🔒 图标表示已锁定。
  - 锁定参数只读，解锁后才可编辑。
  - 新增「恢复默认」按钮，可清除该策略的锁定参数。
- `ParameterGroupPanel` / `ParameterGroupSaveDialog`：
  - 显示每个保存项的「稳定性分数」和「CV 收益均值/标准差」。
  - 保存参数组时同步更新 `optimal_params.json`。
- `OptimalStrategyScanThread`：
  - 每完成一个策略，emit 该策略的最优参数、稳定性分数、收益均值。

## 6. 数据流

1. **应用启动**：`OptimalParamStore.load(profile_key)` → 若存在锁定参数，覆盖策略 schema default。
2. **用户打开策略面板**：`StrategyPanel` 读取当前策略 schema，渲染控件并在锁定参数旁显示 🔒。
3. **用户点击「一键找最优策略和参数」**：
   - `OptimalStrategyScanThread` 从 `OptimalParamStore` 读取锁定参数。
   - 对每个策略，构造「未锁定参数」的笛卡尔积网格。
   - 调用 `StabilityValidator.cross_validate_params` 获取每套参数的 CV 结果。
   - 按「稳定性优先、收益高、波动低」选出最优参数。
   - 弹窗提示用户锁定新参数，用户确认后写入 `OptimalParamStore` 并生成 `ParameterGroup`。
4. **用户生成号码**：使用锁定/当前参数 + `deterministic_seed` → 相同历史始终输出一致。
5. **历史数据更新**：已锁定参数不变，未锁定参数仍可在下次扫描中重新优化。

## 7. 错误处理

- 若锁定参数导致扫描无可行网格，弹窗提示用户解锁部分参数。
- 若某套参数在 CV 中全部失败，记录错误并跳过，不影响其他参数。
- 若历史数据不足以做交叉验证（少于 `n_folds * 50` 期），自动降级为单区间回测并给出警告。

## 8. 测试计划

| 测试 | 内容 |
|------|------|
| `test_fc3d_stability.py` | 拉普拉斯平滑、softmax 归一化、确定性种子、遗漏 cap 的单元测试。 |
| `test_fc3d_strategies.py` 扩展 | 验证改造后的策略在相同 seed 下可复现；历史小变动时输出变化可控。 |
| `test_optimal_param_store.py` | 锁定参数的保存、加载、解锁、覆盖 default 行为。 |
| `test_stability_validator.py` | 交叉验证折叠、稳定性分数计算、异常降级。 |
| `test_optimal_strategy_scan.py` 扩展 | 验证锁定参数被排除在扫描外；CV 结果参与排序。 |
| `test_strategy_panel.py` 扩展 | 验证锁定参数在 UI 上只读。 |

## 9. 涉及文件

### 新增
- `caipiao/core/strategies/fc3d_stability.py`
- `caipiao/core/strategies/stability_validator.py`
- `caipiao/persistence/optimal_param_store.py`
- `tests/test_fc3d_stability.py`
- `tests/test_optimal_param_store.py`
- `tests/test_stability_validator.py`
- `docs/superpowers/specs/2026-07-07-fc3d-stable-hot-cold-design.md`

### 修改
- `caipiao/core/strategies/fc3d.py`
- `caipiao/core/strategies/fc3d_utils.py`
- `caipiao/ui/optimal_period_config.py`
- `caipiao/ui/optimal_strategy_scan_thread.py`
- `caipiao/ui/components/strategy_panel.py`
- `caipiao/ui/components/parameter_group_panel.py`
- `caipiao/ui/components/parameter_group_save_dialog.py`
- `tests/test_fc3d_strategies.py`
- `tests/test_fc3d_utils.py`
- `tests/test_optimal_strategy_scan.py`

## 10. 验收标准

- [ ] 相同历史 + 相同 seed，所有福彩3D策略连续生成 10 次结果完全一致。
- [ ] 在历史末尾追加 1 期新数据后，智能冷热号各位置数字的概率分布变化不超过预设阈值（JS 散度 < 0.1）。
- [ ] 「一键找最优策略和参数」支持对 `smart_hot_cold_3d` 扫描 `lookback` / `hot_weight` / `cold_weight` / `temperature`。
- [ ] 扫描结果可保存为锁定参数，`<app_data_dir>/optimal_params/<profile_key>.json` 中可查到对应记录。
- [ ] 重启应用后，锁定参数自动覆盖策略默认值。
- [ ] 参数组面板显示每个保存项的稳定性分数和 CV 收益统计。
- [ ] 所有新增与修改测试通过。

## 11. 未来扩展

- **策略集成融合（Ensemble）**：在参数组基础上，新增一个 `FC3DEnsembleStrategy`，根据各策略的历史回测表现和稳定性分数加权融合生成号码，可进一步降低单一策略的波动。本次设计为其预留了 `StabilityValidator` 和 `OptimalParamStore` 的数据基础，但不在本次实现范围内。
