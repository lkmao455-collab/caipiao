# Task Harness — Continuous Task System

## Active Tasks

### T1: Harness 建立
- [x] T1.1: 工程扫描与分析
- [x] T1.2: 创建 docs/ 目录
- [x] T1.3: architecture.md
- [x] T1.4: coding_rules.md
- [x] T1.5: api_design.md
- [x] T1.6: module_design.md
- [x] T1.7: risk.md
- [x] T1.8: todo.md
- [x] T1.9: roadmap.md
- [x] T1.10: coding_style.md
- [x] T1.11: test_plan.md
- [x] T1.12: deployment.md
- [x] T1.13: project_memory.md
- [x] T1.14: task_harness.md (本文件)
- [x] T1.15: bug_tracker.md

### T2: 代码质量提升
- [x] T2.1: 消除 FC3D/QLC 过滤逻辑重复 (提取 _filter_by_history 通用函数)
- [x] T2.2: 类型注解审计
  - Union[X, Y, None] → X | Y | None (Python 3.10+ 语法)
  - 添加 NextPeriodInfo TypedDict
  - 移除 Union import (使用新语法)
- [x] T2.3: 异常处理分层审查
  - data/repository.py: Exception → (OSError, json.JSONDecodeError, ValueError, KeyError)
  - 确认各层异常处理符合规范:
    - Core: raise ValueError (验证错误)
    - Data: 具体异常类型 (文件/解析/数据)
    - Persistence: 具体异常类型 (文件/类型转换)
    - UI: except Exception (最后防线)

### T3: 测试覆盖
- [x] T3.1: core 层单元测试补全 (115 tests, all passing)
- [x] T3.2: data 层集成测试 (56 tests, all passing)
- [x] T3.3: ML 层模型测试 (62 tests, all passing - 已有)
- [x] T3.4: 端到端生成流程测试 (20 tests, all passing)

### T4: 功能增强
- [x] T4.1: 增量模型训练
  - ml/features.py: 添加 build_incremental_features()
  - ml/model.py: fit() 支持 incremental 参数
  - ml/predictor.py: 添加 train_incremental() 方法
  - ml/common/model_store.py: 添加 needs_incremental_update()
  - ui/workers.py: TrainModelThread 支持 incremental/new_count
  - ui/main_window.py: 自动判断增量/全量训练
- [x] T4.2: 数据导出 Excel (openpyxl, 带样式/冻结首行/自动列宽)
- [x] T4.3: 自定义过滤规则 UI
  - 设置页添加双色球/福彩3D/七乐彩过滤配置
  - 支持: 比较期数、重合上限、和值范围、蓝球禁止相同
  - 保存/恢复设置

### T5: 文档完善
- [x] T5.1: 用户使用手册 (更新 help.md，添加 Excel 导出说明)
- [x] T5.2: API 自动生成（Sphinx）
  - 创建 docs/api/ 目录结构
  - conf.py: autodoc+viewcode+napoleon, RTD theme
  - index.rst + 模块索引文件
  - 每个模块的 .rst autodoc 文件
- [x] T5.3: 开发者贡献指南 (CONTRIBUTING.md)

## Completed Tasks

- [x] T0.1: 多彩种统一架构
- [x] T0.2: 策略模式 + 插件系统
- [x] T0.3: ML 模型集成
- [x] T0.4: 历史回测
- [x] T0.5: 经验策略过滤

## Rules

1. 每完成一个子任务，标记 [x] 并更新状态
2. 新任务自动加入 Backlog
3. 不能因为一个任务结束而停止整个开发
4. 每次回复必须继续下一个最合理的任务
