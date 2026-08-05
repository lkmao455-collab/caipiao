# WORK_DONE

记录已完成的工作内容与里程碑，供后续任务参考。

## 已完成里程碑

- 多彩种统一架构（`LotteryProfile` + `NumberGroup`），不为每种彩种写独立代码
- 策略模式 + 插件系统（`GenerationStrategy` / `PluginManager`）
- ML 模型集成：XGBoost / LightGBM / CatBoost；特征工程；统计分析；历史过滤
- 深色/浅色主题、老板键、参数组管理、自定义过滤规则 UI
- 历史回测（单期 + 批量）；数据导出 Excel（openpyxl）
- 模型训练增量更新（避免全量重训）
- 骨干彩种：双色球(SSQ)、福彩3D(FC3D)、大乐透(DLT)
- 八卦占卜 / 易经 divination 模块
- API 文档自动生成（Sphinx）、用户使用手册、开发者贡献指南
- 异步网络请求（替代 QThread）
- CI/CD（GitHub Actions）
- 日志格式统一为中文

### 近期提交记录

- `9b0877a` 彻底移除七乐彩（QLC）相关代码
- `6642d06` fix: 八卦占卜等通用策略的过滤设置按目标彩种显示
- `0169557` test: 修正两个与七乐彩下架现状不符的陈旧测试
- `50e3a8f` fix: 八卦占卜策略按目标彩种生成并修复快乐8选号个数
- `21e3138` feat: 八卦占卜/策略参数完善与设置持久化健壮性修复
- `8b3c8d1` chore: 将 `.mimocode/.cron-lock` 移出版本库
- `3941269` chore(scripts): 新增策略/测试清理脚本与双色球分析脚本
- `6097a5d` test: 清理旧策略测试，更新核心与工具栏测试
- `53bcf54` docs: 同步策略重构与自动更新相关文档
- `35c46b5` feat(ui): 更新 UI 与启动自动更新对话框

## 当前测试状态

- 核心测试通过：676 passed, 35 skipped（全量 `python -m pytest`）
- 整体覆盖率：53%（目标 80%，UI 层拖低）
- 核心层覆盖率：69%

## 最近完成（本轮）

- 清理遗留陈旧测试脚本：删除 9 个根目录 `test_*.py`（引用已移除的 `FC3DMissingNumberStrategy`）、`scripts/test_fetch.py`（依赖未安装的 bs4）及孤立损坏模块 `caipiao/core/strategies/lotteries/fc3d/analyzer.py`。
- 效果：`python -m pytest` 全量收集不再中断（修复前直接 10 errors），现可正常跑通。此操作是覆盖率测量的前置条件。

- 新增核心层单元测试，覆盖率提升 48% → 53%（核心 55% → 69%）：
  - `tests/ml/test_markov_model.py` (11 tests) - 马尔可夫链模型
  - `tests/ml/test_random_forest_model.py` (13 tests) - 随机森林模型
  - `tests/ml/test_xgb_model.py` (13 tests) - XGBoost 模型
  - `tests/ml/test_red_lstm.py` (条件跳过) - LSTM 模型
  - `tests/ml/test_transformer_model.py` (条件跳过) - Transformer 模型
  - `tests/core/strategies/lotteries/fc3d/test_utils.py` (30 tests) - FC3D 统计工具
  - `tests/core/strategies/lotteries/pl3/test_pl3_balanced.py` (13 tests) - PL3 均衡策略
  - `tests/core/strategies/lotteries/pl5/test_pl5_balanced.py` (8 tests) - PL5 均衡策略
  - `tests/core/strategies/lotteries/qxc/test_qxc_balanced.py` (8 tests) - QXC 均衡策略
  - `tests/core/strategies/test_stability_validator.py` (24 tests) - 稳定性验证器
  - `tests/core/strategies/lotteries/kl8/test_balanced.py` (22 tests) - KL8 均衡策略
  - `tests/core/strategies/lotteries/test_base_modules.py` (15 tests) - 共享 _base.py 模块

- 代码质量优化（Ruff 错误从 ~151 降至 86，核心层基本清零）：
  - datetime 时区修复：`now()`, `strptime()`, `fromtimestamp()` 全部加时区
  - 未使用变量清理：`leap_month`, `base_date`, `hexagram`, `diversity`, `tag`, `red_proba`, `strategy_id`, `samples` 等
  - 代码简化：嵌套 if (SIM102)、解包未用 (RUF059)、dict 字面量 (C408)
  - 异常处理规范化：BLE001 添加 `# noqa: BLE001`
  - 导入修复：相对路径、缺失导入、循环导入、排序 (I001)
  - 逻辑修复：时区比较、变量名一致性、`np` 导入、TypeError vs ValueError
  - 涉及文件：`bagua_strategy.py`、`ssq/balanced.py`、`ticket.py`、`records.py`、`fc3d/_base.py`、`hybrid_strategy.py`、`ball.py`、`engine.py`、`backtest_worker.py`、`lunar_calendar.py`、`fetcher.py`、`models.py`、`divination_engine.py`、`ml/common/model_store.py`、`ml/common/base.py`、`ml/predictor.py`、`ml/multi_period.py`、`ml/transformer_model.py`、`ml/blue_lstm.py`、`ml/red_lstm.py`、`ml/feature_pipeline.py`、`ml/features.py`、`persistence/history.py`、`persistence/optimal_param_store.py`、测试文件

- 修复测试：Transformer 模型测试在 PyTorch 未安装时正确跳过、`ml/common/model_store.py`、`ml/common/base.py`、`ml/predictor.py`、`ml/multi_period.py`、`persistence/history.py`、测试文件
  - `tests/core/strategies/lotteries/kl8/test_balanced.py` (22 tests) - KL8 均衡策略