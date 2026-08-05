# WORK_NEXT

未完成任务清单，按优先级排列。执行时从序号 1 开始依次推进。

## 1. 提升测试覆盖率至 80% (完成核心层，UI 层待定)

- 现状：整体 53%（17873 行 / 8439 行未覆盖），核心 69%（4002 行 / 1257 行未覆盖）。
- 已完成：ML 模型 (MarkovChainModel, RandomForest, XGBoost, Transformer/LSTM - 条件跳过)、fc3d/utils、pl3/pl5/qxc/kl8 balanced 策略、stability_validator、共享 _base.py 模块。
- 重点拉低文件示例：
  - UI: `workers.py` 20%、`loss_plot.py` 0%、`draw_analysis_dialog.py` 7%、`main_window.py` 49%、`chart_utils.py` 18%、`batch_backtest_dialog.py` 6%
  - Core: `lstm_strategy.py` 0% (PyTorch 未安装，测试跳过)、`pl3/pl5/qxc/_base.py` 64%
  - ML: `red_lstm.py` 0% (跳过)、`transformer_model.py` 16% (跳过)
- 目标：优先补齐 core 层剩余模块 (_base.py 共享函数)，再补 UI 关键文件。对应 `docs/todo.md:20`、`docs/roadmap.md:20`。

## 2. 代码质量优化 (核心层完成，UI 层已完成)

- 对应 `docs/roadmap.md:21`（Phase 3 未勾选项）。
- 已完成：核心层主要 Ruff 问题修复；UI 层 86 个 Ruff 问题（原扫描 86 项，重构中已修 12 项，剩余 74 项本次已修复）已全部清零，覆盖 datetime 时区（统一 `datetime.now(timezone.utc).astimezone()` 约定）、盲目异常捕获（补 `logger` 记录）、未定义名称（补 `typing` 导入 + 修复 `resolved` 真实 bug）、代码简化（UP031/C401/ISC004/SIM102/118/113/FURB192/RUF012/S112/F841）。`ruff_output.txt` 已重新生成为全绿。
- UI 层 lint 已无阻塞项。

## 3. Phase 5 远期规划

- 对应 `docs/roadmap.md:31-34`：
  - Web 版本（FastAPI + Vue）
  - 多用户支持
  - API 开放平台
  - 实时数据推送

## 4. 提交未挂起的改动 (已完成)

- 已提交：`2281cac` refactor: 提交进行中的重构与 UI 代码质量修复（169 文件，+5737/−4518）。
- 范围：进行中的核心/策略/数据/UI 层重构 + UI 层 Ruff 清零（第 2 项）+ 新增测试（tests/core、tests/ml、tests/test_dialogs 等）。
- 未纳入：`ruff_output.txt`（ruff 扫描瞬时产物，每次重跑会重新生成）。
- 未 push（远端提交需另行确认）。

## 附注：文档同步

- `docs/roadmap.md` 的 Phase 4 与 `docs/todo.md` 不同步：Phase 4（增量训练、多期联合预测、自定义过滤、Excel 导出、Transformer/TabNet）实际已完成但 roadmap 未勾选，需更新。