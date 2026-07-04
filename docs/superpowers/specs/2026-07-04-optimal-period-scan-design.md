# 一键找最优期数功能设计

## 背景

当前批量历史回测功能允许用户选择策略、设置日期区间和每期注数后逐期回测。部分策略依赖“使用期数”参数：

- 历史统计策略：`smart_hot_cold`、`missing_number`、`balanced` 使用 `lookback`。
- ML 策略：`xgboost`、`lightgbm`、`catboost` 使用 `history_count`。

用户希望一键扫描这些参数的不同取值，找出使中奖额度（固定奖金合计）最高的那一组参数，并自动应用。

## 目标

1. 在批量回测对话框增加“一键找最优期数”按钮。
2. 根据当前策略自动识别可优化参数及其扫描范围。
3. 在后台并行扫描所有参数取值。
4. 扫描完成后，自动将固定奖金合计最高的参数值写回策略面板。
5. 在界面显示扫描摘要，不强制二次确认。

## 非目标

- 本期实现不支持用户自定义扫描范围和优化目标（方案 2 扩展）。
- 本期不自动再次运行完整批量回测。
- 本期不对所有策略优化，仅覆盖带 `lookback` 或 `history_count` 的策略。

## 设计

### 1. 界面入口

位置：`BatchBacktestDialog` 控制行（`caipiao/ui/components/batch_backtest_dialog.py`）。

在“停止回测”按钮右侧新增按钮：

- 文本：`一键找最优期数`
- 点击：`_run_optimal_period_scan()`
- 状态：
  - 扫描中禁用 `run_btn`、`stop_btn`、扫描按钮。
  - 扫描过程中支持中断。

### 2. 参数映射与扫描范围

独立模块 `caipiao/ui/optimal_period_config.py` 维护映射，便于后续方案 2 扩展。

```python
OPTIMAL_PERIOD_RANGES = {
    "lookback": [20, 50, 80, 100, 150, 200, 300],
    "history_count": [100, 200, 300, 500, 800, 1000, -1],
}

STRATEGY_PARAM_MAP = {
    "smart_hot_cold": "lookback",
    "missing_number": "lookback",
    "balanced": "lookback",
    "xgboost": "history_count",
    "lightgbm": "history_count",
    "catboost": "history_count",
    # 通用彩种策略 id 带后缀，使用 startswith 匹配
}
```

识别逻辑：遍历 `STRATEGY_PARAM_MAP` 的 key，若 `strategy_id` 以 key 开头，则使用对应参数名。

### 3. 扫描线程

新增 `caipiao/ui/optimal_period_scan_thread.py`：

```python
class OptimalPeriodScanThread(QThread):
    progress = Signal(int, int)            # 当前完成组数, 总组数
    status_message = Signal(str)         # 过程状态文本
    result_ready = Signal(object, object) # ScanResult | None, error | None
```

输入：

- `engine`: 仅用于兼容，worker 会重建。
- `strategy_id`
- `profile`
- `data_repository`
- `start_date`, `end_date`
- `tickets_per_round`
- `base_options`: 策略面板当前其他参数。
- `param_name`: `lookback` 或 `history_count`。
- `param_values`: 扫描取值列表。
- `plugin_dir`

执行：

1. 获取全部开奖记录，筛选目标日期区间内的记录。
2. 构造 `RoundBacktestContext`（与 `BatchBacktestThread` 一致）。
3. 对 `param_values` 中的每个值：
   - 复制 `base_options`
   - 设置 `param_name=value`
   - 构造 `RoundTask` 列表
   - 复用 `worker_round_backtest` 在 `ProcessPoolExecutor` 中执行
4. 合并每组结果，记录 `(value, BatchBacktestResult)`。
5. 按以下优先级排序找出最优值：
   1. `total_fixed_prize` 最高
   2. 相同则 `hit_count` 最高
   3. 仍相同则取值最小
6. 返回 `ScanResult`：

```python
@dataclass
class ScanResult:
    param_name: str
    optimal_value: int
    optimal_result: BatchBacktestResult
    all_results: List[Tuple[int, BatchBacktestResult]]
```

### 4. 对话框回调

`_run_optimal_period_scan()` 流程：

1. 校验日期区间、策略已选择。
2. 调用 `resolve_optimal_param(strategy_id)`，若返回 `None` 则提示“当前策略不支持”。
3. 校验历史数据是否满足最小需求（至少覆盖最小扫描值，例如 `lookback` 最小 20，ML 最小 100）。
4. 禁用按钮、清空日志、显示进度条。
5. 启动 `OptimalPeriodScanThread`。
6. 进度更新到 `status_text` 和 `progress`。
7. 完成后：
   - 若出错：`QMessageBox.critical`。
   - 否则：
     - 调用 `strategy_panel.set_options({param_name: optimal_value})`。
     - 在 `summary_label` 显示最优结果。
     - 在 `status_text` 追加所有取值排名。
8. 恢复按钮状态。

### 5. 与现有批量回测的关系

- `OptimalPeriodScanThread` 与 `BatchBacktestThread` 共享 `RoundBacktestContext`、`RoundTask`、`worker_round_backtest` 和 `merge_round_results`。
- 不修改 `BatchBacktestThread` 的行为，仅在对话框层增加新线程和入口。
- 扫描完成后，用户仍使用原有“开始批量回测”按钮运行完整回测。

### 6. 错误处理

- 单组参数失败：记录 `BatchBacktestResult.errors`，不影响其他组。
- 全部失败：返回错误，提示“所有参数组合均失败”。
- 用户中断：保留已收集结果，返回当前最优（若有），并在日志标注“已中断”。
- 历史数据不足：在启动前校验，避免跑空。

### 7. 测试

新增 `tests/test_optimal_period_scan.py`：

1. `test_resolve_param_for_smart_hot_cold`：验证策略到参数的映射。
2. `test_scan_thread_finds_optimal_lookback`：用模拟数据验证能找到固定奖金最高的 `lookback`。
3. `test_scan_thread_unsupported_strategy`：不支持的策略返回提示。
4. `test_scan_thread_skips_failed_values`：部分参数失败时其余参数仍正常返回。

## 扩展预留

- `OptimalPeriodConfig` 后续可开放为类，支持用户自定义范围和目标函数。
- `OptimalPeriodScanThread` 可接收 `objective_key` 参数，支持 `total_fixed_prize`、`hit_count`、`first_ticket_hit_count`、`profit` 等目标。
- 结果表格展示可在方案 2 中基于 `ScanResult.all_results` 渲染。

## 风险

- 扫描多组参数会运行多次完整批量回测，耗时较长。ML 策略尤为明显。需在 UI 中明确提示。
- 默认扫描范围较保守，避免运行过慢；用户后续可通过方案 2 自定义。
