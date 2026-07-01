# 双色球号码生成器

基于 Python + PySide6 的双色球（福利彩票）号码自动生成软件，采用模块化、插件化架构，具备良好的可扩展性。

## 功能特性

- **多种生成策略**
  - 完全随机
  - 奇偶均衡
  - 冷热号分析（基于历史记录）
  - 排除/必含号码
  - 智能冷热号（基于官方历史数据）
  - 遗漏号追踪（基于官方历史数据）
  - 历史均衡（奇偶/大小/和值）
  - **XGBoost 智能分析**（基于机器学习预测号码概率）
  - 可通过插件扩展更多策略

- **号码展示**
  - 红球/蓝球图形化展示
  - 紧凑文本格式，支持一键复制

- **历史记录**
  - 自动生成历史保存
  - 导出 CSV / TXT
  - 导入 JSON
  - 打印历史记录
  - 清空历史

- **打印功能**
  - 打印当前生成结果
  - 打印历史记录
  - 自动排版为带红蓝球样式的 HTML 表格
  - 打印失败时只提示一次，支持“不再提示”
  - 提供导出 PDF 功能，绕过打印机驱动问题

- **插件系统**
  - 动态加载自定义策略插件
  - 支持类自动发现或 `register_strategies(engine)` 函数

- **官方开奖数据**
  - 一键从网络抓取全部历史开奖数据（2003 年至今）
  - 使用与 `getssq` 相同的数据源：`http://data.17500.cn/ssq_asc.txt`
  - 同时支持 500.com、中彩网作为备选数据源
  - 本地 JSON 持久化存储，**无网络也能正常使用**
  - 启动时自动检查并更新最新一期数据（可关闭）
  - 实时统计分析：热号、冷号、遗漏值、奇偶比、大小比、和值、连号率
  - 支持仅获取最新一期

- **XGBoost 机器学习**
  - 基于历史开奖数据训练 XGBoost 二分类模型
  - 预测每个红球/蓝球下一期出现的概率
  - 支持概率加权采样 + 多样性增强
  - 训练前自动联网拉取最新一期数据，训练全程弹出模态进度窗口，阻止训练期间的误操作
  - 模型按时间戳命名缓存（`xgboost_lookback{lookback}_{时间戳}.pkl`），保留历史版本，首次训练约 10-20 秒
  - 生成时自动校验模型是否与当前数据匹配，数据更新后会先重新训练再生成
  - 可在“开奖数据”页手动训练或删除模型

- **设置持久化**
  - 默认注数
  - 深色/浅色主题
  - 最后使用策略
  - 插件目录

- **炫酷图标"
  - 自动生成双色球主题 ICO/PNG 图标
  - 用作窗口图标和任务栏图标
  - 支持重新生成：`.\venv\Scripts\python.exe scripts\generate_icon.py`

## 项目结构

```
caipiao/
├── caipiao/
│   ├── core/               # 核心模型与策略接口
│   │   ├── ball.py         # 球的定义
│   │   ├── ticket.py       # 投注单
│   │   ├── strategy.py     # 策略抽象接口
│   │   ├── engine.py       # 生成引擎
│   │   └── strategies/     # 内置策略
│   ├── data/               # 官方开奖数据获取与分析
│   │   ├── fetcher.py      # 网络抓取
│   │   ├── repository.py   # 本地存储
│   │   ├── analyzer.py     # 统计分析
│   │   └── models.py       # 数据模型
│   ├── ml/                 # 机器学习模块
│   │   ├── features.py     # 特征工程
│   │   ├── model.py        # XGBoost 模型
│   │   └── predictor.py    # 预测推荐
│   ├── plugins/            # 插件系统
│   ├── persistence/        # 历史记录与设置
│   ├── utils/              # 工具函数
│   └── ui/                 # Qt 界面
├── plugins/                # 自定义插件目录（运行时）
├── tests/                  # 单元测试
├── main.py                 # 启动脚本
└── requirements.txt
```

## 快速开始

### 方式一：使用批处理脚本（推荐 Windows 用户）

```bat
:: 首次运行前，创建虚拟环境并安装依赖
create_venv.bat

:: 运行程序
run.bat
```

### 方式二：手动运行

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境（Windows）
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行程序
python main.py
```

## 自定义策略插件示例

在 `plugins/` 目录下创建 Python 文件，例如 `plugins/my_strategy.py`：

```python
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket
import random

class MyStrategy(GenerationStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="my_strategy",
            name="我的策略",
            description="这是一个自定义策略示例",
        )

    def generate(self, count=1, options=None):
        tickets = []
        for _ in range(count):
            reds = sorted(random.sample(range(1, 34), 6))
            blue = random.choice([1, 8, 16])
            tickets.append(Ticket(reds, blue, strategy_name=self.metadata.name))
        return tickets
```

然后在程序的“插件管理”标签页点击“重新加载插件”即可。

## 测试

```bash
python -m pytest tests/
```

## 免责声明

本软件仅用于学习、娱乐和号码生成参考，不保证中奖。请理性购彩，量力而行。
