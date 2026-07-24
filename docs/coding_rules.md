# Coding Rules

## SOLID

- **S**ingle Responsibility: 每个类/函数只做一件事
- **O**pen/Closed: 通过 `GenerationStrategy` ABC 扩展，不修改引擎
- **L**iskov Substitution: 所有策略子类可互换使用
- **I**nterface Segregation: `GenerationStrategy` 仅要求 `metadata` + `generate`
- **D**ependency Inversion: 引擎依赖抽象策略，不依赖具体实现

## KISS

- 优先使用简单实现，避免过度设计
- 一个函数不超过 50 行
- 一个类不超过 300 行

## DRY

- 彩种差异通过 `LotteryProfile` + `NumberGroup` 配置化，不重复写 if-else
- 共用逻辑提取到 `common/` 模块
- 禁止复制已有逻辑，必须调用现有能力

## Clean Architecture

- 依赖方向: UI → Core → Data/ML/Persistence
- `core/profile.py` 不依赖任何上层模块（防循环引用）
- 数据模型（Ticket/DrawRecord）是纯数据类，无业务逻辑

## Error Handling

- 网络请求: `_get_with_retry` 自动重试 3 次，指数退避
- 数据解析: `ValueError/IndexError` 静默跳过单行，不中断整体
- UI 操作: `QMessageBox` 提示用户，不弹异常
- 模型训练: 失败时记录日志，不崩溃

## Logging

- 使用标准 `logging` 模块
- 模块级 `logger = logging.getLogger(__name__)`
- INFO: 关键业务事件（数据更新、模型保存）
- WARNING: 可恢复问题（过滤后候选不足）
- ERROR: 不可恢复错误
- DEBUG: 详细调试信息

## Thread Safety

- UI 操作只在主线程
- 后台任务通过 `QThread` + 信号/槽通信
- `closeEvent` 中等待所有线程结束，超时后 terminate

## Code Style

- Python 3.12+，使用 `from __future__ import annotations`
- 类型注解: 所有公共方法必须有类型注解
- 命名: snake_case 函数/变量，PascalCase 类
- 文件编码: UTF-8
- 禁止: 伪代码、TODO 代替实现、硬编码魔法数字
