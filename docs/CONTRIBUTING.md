# 贡献指南

感谢你对彩票号码生成器项目的关注！本文档将帮助你快速上手开发。

## 快速开始

### 环境准备

```bash
# 1. 克隆仓库
git clone <repo-url>
cd caipiao

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行测试
python -m pytest tests/ -v
```

### 项目结构

```
caipiao/
├── caipiao/              # Python 包
│   ├── core/             # 核心模型（策略、引擎、Ticket）
│   ├── data/             # 数据层（获取、存储、分析）
│   ├── ml/               # 机器学习（XGBoost/LightGBM/CatBoost）
│   ├── persistence/      # 持久化（设置、历史、回测）
│   ├── plugins/          # 插件系统
│   ├── ui/               # PySide6 界面
│   └── utils/            # 工具函数
├── tests/                # 测试
├── docs/                 # 文档
├── scripts/              # 辅助脚本
└── main.py               # 启动入口
```

## 开发流程

### 1. 理解需求

- 明确要解决的问题
- 如果需求不清晰，先做合理假设并说明

### 2. 编写代码

- 代码必须完整、可运行
- 不允许只给片段（除非明确要求）
- 遵循 SOLID、KISS、DRY 原则

### 3. 测试验证

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行指定测试
python -m pytest tests/test_core_ticket.py -v

# 带覆盖率
python -m pytest tests/ --cov=caipiao --cov-report=html
```

### 4. 提交代码

```bash
# 提交信息格式
feat(module): 新功能描述
fix(module): 修复描述
refactor(module): 重构描述
docs(module): 文档描述
test(module): 测试描述
```

## 代码规范

### 命名

| 元素 | 规范 | 示例 |
|------|------|------|
| 包/模块 | snake_case | `data.fetcher` |
| 类 | PascalCase | `DrawAnalyzer` |
| 函数/方法 | snake_case | `fetch_all()` |
| 变量 | snake_case | `red_balls` |
| 常量 | UPPER_SNAKE | `FC3D_FILTER_SAFETY` |
| 私有 | 前缀下划线 | `_records` |

### 类型注解

```python
# 所有公共方法必须有类型注解
def fetch_all(self) -> List[DrawRecord]: ...

# 使用 Optional 表示可选
def get_latest(self) -> Optional[DrawRecord]: ...
```

### 文档字符串

```python
def frequency(self, group_key: str, last_n: Optional[int] = None) -> Dict[int, int]:
    """返回指定号码组的出现频率."""
```

## 添加新彩种

1. 在 `core/profile.py` 中添加 `LotteryProfile` 实例
2. 在 `PROFILES` 字典中注册
3. 在 `data/fetcher.py` 中添加解析器 `_parse_xxx`
4. 在 `core/strategies/lotteries/` 下创建策略目录
5. 在 `core/strategies/registry.py` 中注册策略
6. 添加测试

## 添加新策略

1. 继承 `GenerationStrategy` ABC
2. 实现 `metadata` 属性和 `generate` 方法
3. 在 `core/strategies/registry.py` 中注册
4. 添加测试

## 运行现有测试

```bash
# 快速测试（跳过慢测试）
python -m pytest tests/ -m "not slow"

# 只运行新增测试
python -m pytest tests/test_core_ticket.py tests/test_core_profile.py tests/test_core_engine.py -v
```

## 文档

- `docs/architecture.md` - 架构设计
- `docs/api_design.md` - API 设计
- `docs/coding_rules.md` - 编码规范
- `docs/help.md` - 用户帮助文档
