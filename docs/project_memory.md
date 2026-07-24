# Project Memory

## Key Facts

- **Project**: 彩票号码生成器 (Lottery Number Generator)
- **Language**: Python 3.12
- **GUI**: PySide6 (Qt6)
- **Entry**: `main.py` → `caipiao.app.run()`
- **Data Source**: 17500.cn (纯文本 *_asc.txt)
- **Storage**: JSON 本地文件 + SQLite (回测)

## Architecture Decisions

1. **多彩种统一**: `LotteryProfile` + `NumberGroup` 抽象，不为每种彩种写独立代码
2. **策略模式**: 所有策略继承 `GenerationStrategy`，引擎通过 ID 调用
3. **插件化**: `PluginManager` 支持运行时加载自定义策略
4. **本地优先**: 数据 JSON 缓存，离线可用
5. **后台线程**: 耗时操作在 QThread，信号/槽通信

## Conventions

- 文件编码: UTF-8
- 类型注解: 所有公共方法
- 日志: `logging.getLogger(__name__)`
- 导入: `from __future__ import annotations`
- 相对导入: 包内使用 `from ..module import X`

## Gotchas

- `core/profile.py` 不依赖任何上层模块（防循环引用）
- Ticket/DrawRecord 保留双色球旧接口（向后兼容）
- SSQ 过滤使用集合交集，FC3D 使用多集合交集（处理重复号码）
- QLC 通过率用采样估算（全枚举 203 万组合不现实）
- 模型缓存通过数据指纹（record_count + last_issue）判断有效性

## File Locations

- 主入口: `main.py`
- 应用入口: `caipiao/app.py`
- 主窗口: `caipiao/ui/main_window.py`
- 策略注册: `caipiao/core/strategies/registry.py`
- 策略工厂: `caipiao/core/strategies/factory.py`
- 数据获取: `caipiao/data/fetcher.py`
- 数据存储: `caipiao/data/repository.py`
- ML 预测: `caipiao/ml/predictor.py`
