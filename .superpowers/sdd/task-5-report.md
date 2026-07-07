# Task 5 Report: 3D ML 策略包装器

## Status

已完成 ✅

## 变更内容

- 在 `caipiao/core/strategies/fc3d.py` 中追加三个 ML 策略包装器：
  - `FC3DXGBoostStrategy`（ID: `xgboost_3d`，`is_ml=True`）
  - `FC3DLightGBMStrategy`（ID: `lightgbm_3d`，`is_ml=True`）
  - `FC3DCatBoostStrategy`（ID: `catboost_3d`，`is_ml=True`）
- 通过内部基类 `_FC3DMLStrategy` 复用 `GenericMLPredictor`、`compute_lookback`、`find_current_model`、`new_model_path`，各后端仅通过 `_backend` 与 `metadata` 区分。
- 追加 `build_fc3d_strategies()` 工厂函数，返回包含上述三个 ML 策略在内的 10 个 3D 策略实例。
- 在 `tests/test_fc3d_strategies.py` 中追加参数化测试：
  - `test_ml_3d_strategy_generates_valid[XGBoost/LightGBM/CatBoost]`

## 运行命令

```bash
venv/Scripts/python -m pytest tests/test_fc3d_strategies.py -v
```

## 测试结果

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- E:\caipiao\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\caipiao
configfile: pytest.ini
plugins: qt-4.5.0
collecting ... collected 21 items

tests/test_fc3d_strategies.py::test_random_3d_generates_three_digits PASSED [  4%]
tests/test_fc3d_strategies.py::test_random_3d_seed_reproducible PASSED   [  9%]
tests/test_fc3d_strategies.py::test_odd_even_3d_respects_overall_count PASSED [ 14%]
tests/test_fc3d_strategies.py::test_odd_even_3d_positional_mode PASSED   [ 19%]
tests/test_fc3d_strategies.py::test_exclude_include_3d_positional PASSED [ 23%]
tests/test_fc3d_strategies.py::test_exclude_include_3d_no_sort PASSED    [ 28%]
tests/test_fc3d_strategies.py::test_exclude_include_3d_empty_pool_raises PASSED [ 33%]
tests/test_fc3d_strategies.py::test_exclude_include_3d_empty_include_with_exclude PASSED [ 38%]
tests/test_fc3d_strategies.py::test_smart_hot_cold_3d_all_digits_in_lookback PASSED [ 42%]
tests/test_fc3d_strategies.py::test_smart_hot_cold_3d_seed_reproducible PASSED [ 47%]
tests/test_fc3d_strategies.py::test_hot_cold_3d_generates_valid PASSED   [ 52%]
tests/test_fc3d_strategies.py::test_hot_cold_3d_seed_reproducible PASSED [ 57%]
tests/test_fc3d_strategies.py::test_smart_hot_cold_3d_uses_history PASSED [ 61%]
tests/test_fc3d_strategies.py::test_missing_number_3d_generates_valid PASSED [ 66%]
tests/test_fc3d_strategies.py::test_balanced_3d_generates_valid PASSED   [ 71%]
tests/test_fc3d_strategies.py::test_balanced_3d_respects_order PASSED    [ 76%]
tests/test_fc3d_strategies.py::test_balanced_3d_enumeration_finds_best PASSED [ 80%]
tests/test_fc3d_strategies.py::test_balanced_3d_seed_reproducible PASSED [ 85%]
tests/test_fc3d_strategies.py::test_ml_3d_strategy_generates_valid[FC3DXGBoostStrategy] PASSED [ 90%]
tests/test_fc3d_strategies.py::test_ml_3d_strategy_generates_valid[FC3DLightGBMStrategy] PASSED [ 95%]
tests/test_fc3d_strategies.py::test_ml_3d_strategy_generates_valid[FC3DCatBoostStrategy] PASSED [100%]

============================= 21 passed in 3.23s ==============================
```

> 注：当前文件共有 21 个测试通过。Brief 中预期 17 个通过，是因为此前任务已在该测试文件中追加了额外测试。

## Commit

- Hash: `e68003aa63447e64ebed29d3e6613de42b08607a`
- Message: `feat: add 3D ML strategy wrappers`

## 关注点

- `is_ml` 使用 `@property` 覆盖基类的类属性，确保批量回测 worker 能正确识别 ML 策略。
- 测试使用 120 期历史记录并指定 `history_count=100`，满足 `validate_options` 对 ≥100 期的校验。
- 模型训练产生的缓存文件会写入应用数据目录，测试运行后已在本地生成；后续如切换 `CAIPIAO_MODEL_DIR` 可隔离缓存。
- 未修改 `caipiao/ml/generic.py`，Task 6 仍可按计划进行。

## 修复记录（Task 5 Review Fixes）

修复 `caipiao/core/strategies/fc3d.py` 中的审查问题：

1. 将 `import numpy as np` 与 ML 相关导入（`GenericMLPredictor`、`compute_lookback`、`find_current_model`、`new_model_path`）从模块中部移到文件顶部导入区。
2. 将 `_FC3DMLStrategy.is_ml` 从 `@property` 改为类属性 `is_ml: bool = True`，支持类级别访问。
3. 保留 `build_fc3d_strategies(profile)` 签名以兼容 Task 6 的通用工厂调用，但增加 `assert profile.key == "3d"` 校验。
4. 为每个 Ticket 使用 `details.copy()`，避免多张彩票共享同一个 `details` 字典。

验证命令：

```bash
venv/Scripts/python -m pytest tests/test_fc3d_strategies.py -v
```

结果：21 passed in 2.66s。

提交信息：`refactor: clean up 3D ML strategy imports and is_ml attr`
