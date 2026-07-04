# 一键找最优策略和参数功能设计

## 背景

在已实现“一键找最优期数”的基础上，用户希望进一步扩展：不仅优化当前策略的参数，而是在所有使用历史记录的策略中找出**最优策略**及其**最优参数**。这样用户只需点击一次按钮，即可获得全局最优的号码生成配置。

当前项目支持多种基于历史数据的生成策略：冷热号分析、智能冷热号、遗漏号追踪、历史均衡，以及 XGBoost/LightGBM/CatBoost 机器学习策略。不同策略依赖不同的“使用期数”参数，且不同策略在同一历史数据上的表现可能差异很大。

## 目标

1. 在批量历史回测对话框保留已有的“一键找最优期数”按钮。
2. 新增“一键找最优策略和参数”按钮。
3. 扫描所有 `needs_history=True` 的策略及其可调参数。
4. 按固定奖金合计最高选出全局最优的 `(策略, 参数名, 参数值)` 组合。
5. 自动将最优策略和参数写回策略面板。
6. 在界面显示扫描摘要，不强制二次确认。

## 非目标

- 本期不扫描无历史依赖的策略（如完全随机、奇偶均衡、排除/必含）。
- 本期不改变“一键找最优期数”的行为。
- 本期不支持用户自定义扫描策略列表或优化目标（后续可扩展）。
- 扫描完成后不自动重新运行完整批量回测。

## 设计

### 1. 界面入口

位置：`BatchBacktestDialog` 控制行（`caipiao/ui/components/batch_backtest_dialog.py`）。

在“一键找最优期数”按钮右侧新增按钮：

- 文本：`一键找最优策略和参数`
- 点击：`_run_optimal_strategy_scan()`
- 状态：
  - 扫描中禁用 `run_btn`、`stop_btn`、两个优化按钮。
  - 扫描过程中支持中断。

### 2. 候选策略与参数

扫描范围由 `caipiao.core.strategies.generic.needs_history(strategy_id)` 决定。当前覆盖：

| 策略 id 前缀 | 是否有可调期数参数 | 参数名 | 扫描范围 |
|---|---|---|---|
| `hot_cold` | 否 | — | 使用全部历史记录，仅跑 1 次 |
| `smart_hot_cold` | 是 | `lookback` | 20, 50, 80, 100, 150, 200, 300 |
| `missing_number` | 是 | `lookback` | 20, 50, 80, 100, 150, 200, 300 |
| `balanced` | 是 | `lookback` | 20, 50, 80, 100, 150, 200, 300 |
| `xgboost` | 是 | `history_count` | 100, 200, 300, 500, 800, 1000, -1 |
| `lightgbm` | 是 | `history_count` | 100, 200, 300, 500, 800, 1000, -1 |
| `catboost` | 是 | `history_count` | 100, 200, 300, 500, 800, 1000, -1 |

通用彩种策略（如 `smart_hot_cold_3d`、`xgboost_kl8`）通过 `startswith` 匹配前缀自动纳入。

`hot_cold` 策略没有独立期数参数，作为“使用全部历史记录”的基准参与扫描，只跑一次默认参数。

### 3. 扫描线程

新增 `caipiao/ui/optimal_strategy_scan_thread.py`：

```python
class OptimalStrategyScanThread(QThread):
    progress = Signal(int, int)            # 当前完成策略数, 总策略数
    status_message = Signal(str)         # 过程状态文本
    result_ready = Signal(object, object) # StrategyScanResult | None, error | None
```

输入：

- `engine`: `GenerationEngine`
- `profile`
- `data_repository`
- `start_date`, `end_date`
- `tickets_per_round`
- `base_options`: 策略面板当前其他参数（不含 strategy_id、lookback/history_count）。
- `plugin_dir`

执行：

1. 从 `engine.list_strategies()` 获取所有策略。
2. 过滤出 `needs_history(strategy.metadata.id)` 为 `True` 的策略。
3. 对每个候选策略：
   - 调用 `resolve_optimal_param(strategy_id)`。
   - 若返回参数名和取值列表，复用 `OptimalPeriodScanThread` 的内部扫描逻辑（或提取为独立函数）对该策略的每个参数值运行回测。
   - 若返回 `None`（如 `hot_cold`），只跑一次默认参数。
4. 对每个策略，按原 `total_fixed_prize → hit_count → 参数值较小者` 选出该策略的最优参数。
5. 汇总所有策略的最优结果，按全局标准排序：
   1. `total_fixed_prize` 最高
   2. 相同则 `hit_count` 最高
   3. 仍相同则策略 id 字典序较小（保证确定性）
6. 返回 `StrategyScanResult`：

```python
@dataclass
class StrategyScanResult:
    optimal_strategy_id: str
    optimal_strategy_name: str
    param_name: Optional[str]
    optimal_value: Optional[int]
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[str, Optional[int], BatchBacktestResult]]
    interrupted: bool = False
```

### 4. 复用与重构

- 将 `OptimalPeriodScanThread` 中对“单一策略多参数扫描”的逻辑提取为独立函数 `_scan_param_values(...)`，供 `OptimalPeriodScanThread` 和 `OptimalStrategyScanThread` 共同调用。
- `OptimalStrategyScanThread` 对每种策略调用该函数，避免代码重复。
- 两个线程共享 `RoundBacktestContext`、`RoundTask`、`worker_round_backtest`、`merge_round_results`。

### 5. 对话框回调

`_run_optimal_strategy_scan()` 流程：

1. 校验日期区间。
2. 校验历史数据至少 100 期（因为所有候选策略都需要历史数据）。
3. 禁用按钮、清空日志、显示进度条。
4. 启动 `OptimalStrategyScanThread`。
5. 进度更新到 `status_text` 和 `progress`。
6. 完成后：
   - 若出错：`QMessageBox.critical`。
   - 否则：
     - 调用 `strategy_panel.set_strategy_id(best_strategy_id)`。
     - 若 `param_name` 不为 `None`，调用 `strategy_panel.set_options({param_name: optimal_value})`。
     - 在 `summary_label` 显示最优结果。
     - 在 `status_text` 追加所有策略-参数结果排名。
7. 恢复按钮状态。

### 6. 错误处理

- 单个策略失败：记录错误，不影响其他策略。
- 单个策略的某个参数失败：按 `OptimalPeriodScanThread` 的失败隔离逻辑处理，该策略仍可能选出其他成功参数。
- 全部策略均失败：返回错误，提示“没有可成功的策略组合”。
- 用户中断：保留已收集结果，返回当前最优（若有），并在日志标注“已中断”。

### 7. UI 状态

- 批量回测运行期间禁用两个优化按钮。
- 参数扫描运行期间禁用批量回测按钮和策略扫描按钮。
- 策略扫描运行期间禁用批量回测按钮和参数扫描按钮。
- 停止按钮可同时中断批量回测线程或策略扫描线程。

### 8. 测试

新增 `tests/test_optimal_strategy_scan.py`：

1. `test_resolve_history_strategies`：验证能正确识别 `needs_history` 策略。
2. `test_strategy_scan_finds_best`：用模拟数据验证能找出固定奖金最高的策略+参数。
3. `test_strategy_scan_skips_failed_strategy`：某个策略失败不影响整体扫描。
4. `test_strategy_scan_applies_best_to_panel`：验证扫描后策略面板被正确更新。
5. `test_strategy_scan_includes_hot_cold`：验证 `hot_cold` 策略作为无参数策略参与扫描。

## 扩展预留

- `OptimalStrategyScanThread` 的候选策略过滤条件后续可配置（如排除 ML 策略以加速）。
- 优化目标后续可扩展为 `hit_count`、`profit`、`first_ticket_hit_count` 等。
- 结果表格展示可在后续方案中基于 `StrategyScanResult.all_results` 渲染。

## 风险

- 扫描策略数和参数取值数的乘积可能很大，ML 策略尤为耗时。需在 UI 中明确提示。
- 当前未对策略扫描设置并发上限，仍使用 `_normalize_max_workers` 控制。
- 不同策略的 `base_options` 不完全通用（如 `hot_weight` 只适用于 `smart_hot_cold`），扫描时会自动忽略不适用于某策略的选项。
