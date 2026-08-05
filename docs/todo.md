# TODO

## In Progress

- [x] 建立 Harness 文档体系

## Backlog

### 功能增强
- [x] 增加更多 ML 模型（如 Transformer、TabNet）
- [x] 增加号码组合回测胜率统计
- [x] 增加多期联合预测
- [x] 增加自定义过滤规则 UI
- [x] 增加开奖数据导出为 Excel

### 技术优化
- [x] 模型训练增量更新（避免全量重训）
- [x] 特征工程自动化管道
- [x] 异步网络请求（替代 QThread）
- [x] 单元测试覆盖率提升至 80%（核心层行覆盖率已达 100%，UI/ML 按约定排除）
- [x] 集成 CI/CD（GitHub Actions）

### 代码质量
- [x] 消除重复代码（FC3D/QLC 过滤逻辑合并）
- [x] 类型注解完善（Union → X | Y | None，添加 TypedDict）
- [x] 日志格式统一化（统一为中文）
- [x] 异常处理分层（UI 层 vs 核心层）

### 文档
- [x] API 文档自动生成（Sphinx）
- [x] 用户使用手册
- [x] 开发者贡献指南

## Completed

- [x] 多彩种统一架构（Profile + NumberGroup）
- [x] 策略模式 + 插件系统
- [x] XGBoost/LightGBM/CatBoost ML 模型
- [x] 历史回测（单期 + 批量）
- [x] 深色/浅色主题
- [x] 老板键
- [x] 参数组管理
- [x] 经验策略过滤（SSQ/FC3D/DLT）
- [x] 数据导出 Excel（openpyxl）
- [x] 消除 FC3D/QLC 过滤逻辑重复
- [x] Core 层单元测试（115 tests）
- [x] Data 层集成测试（56 tests）
- [x] 端到端生成流程测试（20 tests）
- [x] ML 层模型测试（62 tests）
- [x] 模型训练增量更新
- [x] 自定义过滤规则 UI
- [x] API 文档自动生成（Sphinx）
