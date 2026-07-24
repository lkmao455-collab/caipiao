# Module Design

## core/profile.py — 彩种档案

**职责**: 定义所有彩种的号码结构、数据源、开奖周期。

**关键类**:
- `NumberGroup`: 一个号码组（如红球 1-33 选 6）
- `LotteryProfile`: 一个彩种的完整档案
- `PROFILES`: 全局注册表 `{key: profile}`

**扩展方式**: 新增彩种只需在 `profile.py` 中添加一个 `LotteryProfile` 实例并注册到 `PROFILES`。

## core/strategy.py — 策略接口

**职责**: 定义生成策略的抽象接口。

**设计**: 纯抽象基类，无实现。所有策略必须继承 `GenerationStrategy` 并实现 `metadata` 和 `generate`。

## core/engine.py — 生成引擎

**职责**: 策略注册/调用 + 号码过滤。

**过滤体系**:
- SSQ: 红球重合过滤 + 蓝球去重
- FC3D: 和值范围 + 多集合交集重合过滤
- QLC: 和值范围 + 集合交集重合过滤

**自适应放大**: 过滤前估算通过率，自适应放大候选数量，确保过滤后候选充足。

## core/strategies/ — 内置策略

**组织方式**: `lotteries/{彩种}/` 按彩种子目录组织。

**共享逻辑**: `common/` 子目录存放跨彩种共用的工具（如 validators）。

**工厂模式**: `factory.py` 负责按 profile key 创建策略实例。

## data/ — 数据层

**数据流**:
```
Fetcher (网络) → Repository (JSON) → Analyzer (统计)
```

**统一模型**: `DrawRecord` 通过 `groups` 字典表达任意彩种的一期开奖。

## ml/ — 机器学习

**架构**:
```
Features (特征工程)
    ↓
Model (XGBoost/LightGBM/CatBoost)
    ↓
Predictor (高层接口: train → predict → recommend)
```

**缓存**: 模型文件 + 元数据指纹，数据变化时自动重训。

## persistence/ — 持久化

| Store | 存储方式 | 用途 |
|-------|---------|------|
| AppSettings | QSettings | 应用配置 |
| HistoryManager | JSON | 生成历史 |
| BacktestDB | SQLite | 回测结果 |
| ParameterGroupStore | JSON | 参数组 |
| OptimalParamStore | JSON | 最优参数锁定 |

## ui/ — 界面

**标签页架构**: MainWindow 使用 QTabWidget，6 个标签页：
1. 生成号码（策略选择 + 结果展示）
2. 历史记录
3. 开奖数据（更新/统计/模型训练）
4. 插件管理
5. 设置
6. 参数组

**线程模型**: 所有耗时操作（网络/训练/生成）在 QThread 中执行，通过信号/槽更新 UI。
