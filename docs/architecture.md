# Architecture

## Overview

彩票号码生成器是一个基于 Python + PySide6 (Qt6) 的桌面应用，采用分层架构设计，支持 8 种彩种的号码生成、历史分析、机器学习预测和回测。

## Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│                    UI Layer (PySide6)                 │
│  MainWindow → StrategyPanel / ResultArea / DataTable  │
└───────────┬─────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────┐
│                  Core Layer                           │
│  GenerationEngine → GenerationStrategy (ABC)         │
│  Ticket / Ball / LotteryProfile / NumberGroup         │
└──────┬────────────┬──────────────┬──────────────────┘
       │            │              │
┌──────▼──────┐ ┌───▼──────┐ ┌────▼─────────────┐
│  Data Layer │ │ ML Layer │ │ Persistence Layer │
│  Fetcher    │ │ Predictor│ │ Settings          │
│  Repository │ │ Models   │ │ HistoryManager    │
│  Analyzer   │ │ Features │ │ BacktestDB        │
│  Models     │ │          │ │ ParamGroupStore   │
└─────────────┘ └──────────┘ └──────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│              Infrastructure                          │
│  PluginManager / Utils / Network (requests)          │
└─────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **多彩种统一模型**: `LotteryProfile` + `NumberGroup` 抽象任意彩种的号码结构，上层代码彩种无关
2. **策略模式**: 所有生成策略继承 `GenerationStrategy` ABC，通过 `GenerationEngine` 注册/调用
3. **插件化**: `PluginManager` 支持运行时动态加载自定义策略
4. **本地优先**: 开奖数据本地 JSON 存储，无网络也可运行
5. **后台线程**: 网络请求、模型训练均在 `QThread` 中执行，不阻塞 UI

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `core/profile.py` | 彩种档案定义（号码组、号池、开奖周期） |
| `core/ticket.py` | 投注单数据模型（多彩种统一） |
| `core/strategy.py` | 策略抽象接口 |
| `core/engine.py` | 生成引擎 + 历史过滤（SSQ/3D/QLC） |
| `core/strategies/` | 内置策略实现（按彩种组织） |
| `data/fetcher.py` | 网络抓取开奖数据（17500.cn） |
| `data/repository.py` | 本地 JSON 存储与查询 |
| `data/analyzer.py` | 统计分析（频率/热冷/遗漏/奇偶/和值） |
| `data/models.py` | DrawRecord 数据模型 |
| `ml/predictor.py` | ML 预测器高层接口 |
| `ml/model.py` | XGBoost 模型封装 |
| `ml/lgbm_model.py` | LightGBM 模型封装 |
| `ml/catboost_model.py` | CatBoost 模型封装 |
| `ml/features.py` | 特征工程 |
| `persistence/settings.py` | 应用设置（QSettings） |
| `persistence/history.py` | 生成历史管理 |
| `persistence/backtest_db.py` | 回测结果 SQLite 存储 |
| `plugins/plugin_manager.py` | 插件加载与管理 |
| `ui/main_window.py` | 主窗口（标签页架构） |
| `ui/workers.py` | 后台线程（fetch/train/generate） |
