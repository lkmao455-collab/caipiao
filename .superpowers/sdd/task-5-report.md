# Task 5 Report: 迁移 SSQ 其余基础策略

## 1. Status

完成。已将 6 个剩余 SSQ 基础策略从旧文件迁移到 `caipiao/core/strategies/lotteries/ssq/` 下的对应模块，并补充了覆盖全部 8 个 SSQ 基础策略的测试。

迁移的策略：

| 新文件 | 类 | ID | 源旧文件 |
|---|---|---|---|
| `hot_cold.py` | `SSQHotColdStrategy` | `hot_cold` | `caipiao/core/strategies/hot_cold_strategy.py` |
| `exclude_include.py` | `SSQExcludeIncludeStrategy` | `exclude_include` | `caipiao/core/strategies/exclude_include_strategy.py` |
| `smart_hot_cold.py` | `SSQSmartHotColdStrategy` | `smart_hot_cold` | `caipiao/core/strategies/smart_hot_cold_strategy.py` |
| `missing_number.py` | `SSQMissingNumberStrategy` | `missing_number` | `caipiao/core/strategies/missing_number_strategy.py` |
| `balanced.py` | `SSQBalancedStrategy` | `balanced` | `caipiao/core/strategies/balanced_strategy.py` |
| `stats.py` | `SSQStatsStrategy` | `stats` | `caipiao/core/strategies/stats_strategy.py` |

主要适配点：

- 类名统一改为 `SSQ*` 前缀。
- 删除占位类中的 `is_history_needed` 等未使用属性。
- 使用 `from ....profile import SSQ` 与 `Ticket(profile=SSQ, groups={"red": ..., "blue": [...]})` 构造投注单。
- 使用 `from ...common.records import records_from_options` 统一历史记录归一化。
- 保持 `metadata.id`、`metadata.name`、`get_config_schema` 字段名与旧实现一致。
- 旧策略文件按要求保留，未删除。

## 2. Commands Run

```bash
venv/Scripts/python -m pytest tests/test_ssq_strategies.py -v
venv/Scripts/python -m pytest tests/test_strategy_factory.py tests/test_strategy_common.py -v
venv/Scripts/python -c "from caipiao.core.strategies.registry import STRATEGY_REGISTRY; print([s().metadata.id for s in STRATEGY_REGISTRY['ssq']])"
git add caipiao/core/strategies/lotteries/ssq/ tests/test_ssq_strategies.py caipiao/core/strategies/registry.py
git commit -m "feat: isolate remaining ssq basic strategies"
```

## 3. Test Results

### `tests/test_ssq_strategies.py`

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- E:\caipiao\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0
collected 7 items

tests/test_ssq_strategies.py::test_ssq_random_metadata PASSED            [ 14%]
tests/test_ssq_strategies.py::test_ssq_random_generates_valid_tickets PASSED [ 28%]
tests/test_ssq_strategies.py::test_ssq_random_seed_reproducible PASSED   [ 42%]
tests/test_ssq_strategies.py::test_ssq_odd_even_metadata PASSED          [ 57%]
tests/test_ssq_strategies.py::test_ssq_odd_even_respects_count PASSED    [ 71%]
tests/test_ssq_strategies.py::test_build_strategies_includes_ssq PASSED  [ 85%]
tests/test_ssq_strategies.py::test_ssq_all_basic_strategies_generate_valid_tickets PASSED [100%]

============================== 7 passed in 0.44s ==============================
```

### `tests/test_strategy_factory.py` + `tests/test_strategy_common.py`

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- E:\caipiao\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0
collected 11 items

tests/test_strategy_factory.py::test_build_strategies_returns_expected_ids[ssq] PASSED [  9%]
tests/test_strategy_factory.py::test_build_strategies_returns_expected_ids[3d] PASSED [ 18%]
tests/test_strategy_factory.py::test_needs_history_prefixes PASSED       [ 27%]
tests/test_strategy_factory.py::test_is_ml_strategy_prefixes PASSED      [ 36%]
tests/test_strategy_common.py::test_records_from_options_accepts_draw_records PASSED [ 45%]
tests/test_strategy_common.py::test_records_from_options_accepts_tickets PASSED [ 54%]
tests/test_strategy_common.py::test_records_from_options_empty PASSED    [ 63%]
tests/test_strategy_common.py::test_make_rng_with_seed PASSED            [ 72%]
tests/test_strategy_common.py::test_make_rng_without_seed PASSED         [ 81%]
tests/test_strategy_common.py::test_validate_odd_count_valid PASSED      [ 90%]
tests/test_strategy_common.py::test_validate_odd_count_invalid PASSED    [100%]

============================== 11 passed in 0.37s ==============================
```

### Registry 校验

```bash
venv/Scripts/python -c "from caipiao.core.strategies.registry import STRATEGY_REGISTRY; print([s().metadata.id for s in STRATEGY_REGISTRY['ssq']])"
```

输出：

```
['random', 'odd_even', 'hot_cold', 'exclude_include', 'smart_hot_cold', 'missing_number', 'balanced', 'stats', ...]
```

全部 8 个 SSQ 基础策略均已注册。

## 4. Commits Made

```
1f01740 feat: isolate remaining ssq basic strategies
```

提交文件：

- `caipiao/core/strategies/lotteries/ssq/balanced.py`
- `caipiao/core/strategies/lotteries/ssq/exclude_include.py`
- `caipiao/core/strategies/lotteries/ssq/hot_cold.py`
- `caipiao/core/strategies/lotteries/ssq/missing_number.py`
- `caipiao/core/strategies/lotteries/ssq/smart_hot_cold.py`
- `caipiao/core/strategies/lotteries/ssq/stats.py`
- `tests/test_ssq_strategies.py`

`caipiao/core/strategies/registry.py` 在任务开始前已包含全部 8 个基础策略，因此无实际变更未进入提交。

## 5. Concerns

1. **旧文件仍被多处导入导致部分测试无法收集**：`caipiao/core/backtest_worker.py`、`tests/test_core.py`、`tests/test_batch_backtest_integration.py`、`tests/test_optimal_strategy_scan.py` 等仍尝试 `from caipiao.core.strategies import BalancedStrategy / HotColdStrategy / RandomStrategy / ...`，但 `caipiao/core/strategies/__init__.py` 已不再导出这些旧类，导致以下测试在收集阶段报错：
   - `tests/test_batch_backtest_integration.py`
   - `tests/test_batch_backtest_worker.py`
   - `tests/test_core.py`
   - `tests/test_optimal_period_scan.py`
   - `tests/test_optimal_strategy_scan.py`
   - `tests/test_parameter_group_dialog.py`
   - `tests/test_stability_validator.py`
   - `tests/test_strategy_panel.py`

   这些问题与本次 Task 5 的迁移范围无关，属于策略隔离重构的后续清理工作（Task 8 删除旧文件并统一调用新路径时会一并处理）。本次任务按要求未删除旧文件，也未修改这些跨模块导入。

2. **`SSQStatsStrategy.metadata.name` 与占位类不同**：占位类使用 `"统计特征"`，旧实现为 `"统计分析"`。按“保持旧实现语义不变”的原则，本次迁移恢复为 `"统计分析"`。

3. **行尾换行警告**：Git 提示多个新文件 LF 将被替换为 CRLF，这是 Windows 环境下的正常 core.autocrlf 行为，不影响代码功能。

---

## Fix Report

### Status
完成。已删除 `caipiao/core/strategies/lotteries/ssq/stats.py` 中未使用的 `import numpy as np`，测试全部通过并已提交。

### Commands Run

```bash
venv/Scripts/python -m pytest tests/test_ssq_strategies.py -v
git add caipiao/core/strategies/lotteries/ssq/stats.py
git commit -m "fix: remove unused numpy import in ssq stats strategy"
```

### Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- E:\caipiao\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0

tests/test_ssq_strategies.py::test_ssq_random_metadata PASSED            [ 14%]
tests/test_ssq_strategies.py::test_ssq_random_generates_valid_tickets PASSED [ 28%]
tests/test_ssq_strategies.py::test_ssq_random_seed_reproducible PASSED   [ 42%]
tests/test_ssq_strategies.py::test_ssq_odd_even_metadata PASSED          [ 57%]
tests/test_ssq_strategies.py::test_ssq_odd_even_respects_count PASSED    [ 71%]
tests/test_ssq_strategies.py::test_build_strategies_includes_ssq PASSED  [ 85%]
tests/test_ssq_strategies.py::test_ssq_all_basic_strategies_generate_valid_tickets PASSED [100%]

============================== 7 passed in 0.40s ==============================
```

### Commit Hash

```
73ca3d959d0e49a0d293f43dd881691db5a5190f
```

### Concerns
无。仅删除了未使用的导入，未影响功能。Git 提示的 LF→CRLF 换行警告为 Windows 环境下 core.autocrlf 的正常行为。

---

## Fix Report 2

### Status
完成。已清理 `caipiao/core/strategies/lotteries/ssq/stats.py` 中的未使用导入，并将 `lookback` 参数实际传入智能模式与遗漏模式的红球分析。

具体修改：

1. 删除未使用的 `from collections import Counter` 导入。
2. `_smart_mode` 中 `analyzer.frequency("red", lookback)` 和 `analyzer.missing("red", lookback)` 均传入 `lookback`。
3. `_missing_mode` 中删除未使用的 `freq_red` 与 `freq_blue` 死赋值；同时让红球遗漏分析也使用 `lookback`（此前仅蓝球使用，红球使用默认 50 期），使配置的回看期数对 missing 模式生效。

### Commands Run

```bash
python -m pytest tests/test_ssq_strategies.py -v
git add caipiao/core/strategies/lotteries/ssq/stats.py
git commit -m "fix(ssq): remove unused Counter import, wire lookback in stats strategy"
```

### Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0
collected 7 items

tests/test_ssq_strategies.py::test_ssq_random_metadata PASSED            [ 14%]
tests/test_ssq_strategies.py::test_ssq_random_generates_valid_tickets PASSED [ 28%]
tests/test_ssq_strategies.py::test_ssq_random_seed_reproducible PASSED   [ 42%]
tests/test_ssq_strategies.py::test_ssq_odd_even_metadata PASSED          [ 57%]
tests/test_ssq_strategies.py::test_ssq_odd_even_respects_count PASSED    [ 71%]
tests/test_ssq_strategies.py::test_build_strategies_includes_ssq PASSED  [ 85%]
tests/test_ssq_strategies.py::test_ssq_all_basic_strategies_generate_valid_tickets PASSED [100%]

============================== 7 passed in 0.25s ==============================
```

### Commit Hash

```
69fc47b836e7ef6548a7f48e061286139b76fdea
```

### Concerns
无。测试全部通过；红球遗漏分析现在也受 `lookback` 控制，行为与配置一致。Git 提示的 LF→CRLF 警告为 Windows 环境下 `core.autocrlf` 的正常行为。

---

## Fix Report 3

### Status
完成。已修复 `caipiao/core/strategies/lotteries/ssq/stats.py` 中 `_freq_mode` 与 `_smart_mode` 未将 `lookback` 参数传递给所有 `analyzer.frequency()` 调用的问题，使配置项"回看期数"在所有统计模式下生效。

### Specific Changes

1. `_freq_mode` 现在接收 `options` 参数，并从中读取 `lookback`（默认 100）。
2. `_freq_mode` 中 `analyzer.frequency("red", lookback)` 与 `analyzer.frequency("blue", lookback)` 均传入 `lookback`。
3. `_smart_mode` 中 `analyzer.frequency("blue", lookback)` 也传入 `lookback`。
4. `_freq_mode` 的 `basis` 文案中补充了"回看 {lookback} 期"。
5. `generate` 中调用 `_freq_mode` 时同步传入 `options`。

### Commands Run

```bash
python -m pytest tests/test_ssq_strategies.py -v
git add caipiao/core/strategies/lotteries/ssq/stats.py
git commit -m "fix(ssq): pass lookback to all frequency calls in stats strategy"
```

### Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0
collected 7 items

tests/test_ssq_strategies.py::test_ssq_random_metadata PASSED            [ 14%]
tests/test_ssq_strategies.py::test_ssq_random_generates_valid_tickets PASSED [ 28%]
tests/test_ssq_strategies.py::test_ssq_random_seed_reproducible PASSED   [ 42%]
tests/test_ssq_strategies.py::test_ssq_odd_even_metadata PASSED          [ 57%]
tests/test_ssq_strategies.py::test_ssq_odd_even_respects_count PASSED    [ 71%]
tests/test_ssq_strategies.py::test_build_strategies_includes_ssq PASSED  [ 85%]
tests/test_ssq_strategies.py::test_ssq_all_basic_strategies_generate_valid_tickets PASSED [100%]

============================== 7 passed in 0.23s ==============================
```

### Commit Hash

```
371bce6332b1b1c42ca3e01a7fef7bee71514460
```

### Concerns
无。测试全部通过；所有统计模式下的红球与蓝球频率分析现在均受 `lookback` 控制，行为与配置一致。Git 提示的 LF→CRLF 警告为 Windows 环境下 `core.autocrlf` 的正常行为。
