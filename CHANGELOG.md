# Changelog

## [2.1.0] - 2026-07-24

### Added

#### New Features
- **Transformer Model**: 基于 Transformer 架构的彩票预测模型，支持 PyTorch
- **Multi-Period Prediction**: 多期联合预测功能，支持趋势分析和稳定号码检测
- **Feature Engineering Pipeline**: 特征工程自动化管道，支持可配置的特征提取器
- **Backtest Statistics**: 号码组合回测胜率统计，支持收益率和中奖率计算
- **Custom Filter Rules UI**: 自定义过滤规则界面（双色球/福彩3D/七乐彩）
- **Excel Export**: 支持导出 Excel 格式，带样式表头和冻结首行
- **Async Workers**: 异步网络请求工作器，替代传统 QThread
- **Performance Optimization**: 性能优化模块，包括向量化特征提取和缓存

#### Improvements
- **Incremental Model Training**: 支持模型增量更新，避免全量重训
- **CI/CD**: GitHub Actions 自动化测试配置
- **Type Annotations**: 统一使用 Python 3.10+ 类型注解语法
- **Exception Handling**: 异常处理分层优化
- **Logging**: 日志格式统一化（中文）

#### Documentation
- **API Documentation**: Sphinx 自动生成 API 文档
- **User Manual**: 更新用户使用手册
- **Contributing Guide**: 开发者贡献指南
- **Code Quality Report**: 代码质量检查报告
- **Architecture Documentation**: 架构设计文档

### Changed
- Refactored FC3D/QLC filter logic (extracted `_filter_by_history` common function)
- Updated README with new features and project structure
- Updated requirements.txt with openpyxl dependency

### Fixed
- Fixed logging language (unified to Chinese)
- Fixed exception handling in data/repository.py

## [2.0.0] - Previous Release

### Features
- Multi-lottery support (SSQ, FC3D, QLC, KL8, DLT, PL3, PL5, QXC)
- Smart hot/cold number strategy
- Historical balance strategy
- XGBoost/LightGBM/CatBoost ML models
- History backtest (single and batch)
- Plugin system
- Dark/light theme
- Boss key
- Parameter group management
- Experience strategy filtering

## [1.0.0] - Initial Release

### Features
- Basic lottery number generation
- History record management
- Print and export functionality
