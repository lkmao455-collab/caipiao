# 彩票号码生成器（双色球 / 福彩3D / 大乐透 / 快乐8 / 排列3 / 排列5 / 七乐彩 / 七星彩）

基于 Python + PySide6 的多彩种彩票号码自动生成软件，采用模块化、插件化架构，具备良好的可扩展性。核心支持 8 种彩种，各彩种共享统一的生成策略与回测框架。

## 功能特性

- **简洁高效的生成策略**（每个彩种 2 种核心策略）
  - **智能冷热号**：拉普拉斯平滑频率 + 几何分布 z-score 遗漏检验 + χ² 均匀性检验 + softmax 概率融合 + Gumbel-max 无放回采样
  - **历史均衡**：基于 7 维统计特征（奇偶/大小/和值/三区/连号/覆盖度/邻期重合）生成均衡号码，各维度独立加权评分，分段引导采样保证分散性；蓝球结合频率与遗漏值 z-score 加权

- **机器学习模型**
  - **XGBoost**：顺序生成模型（红球）+ 多输出分类器（蓝球）
  - **LightGBM**：梯度提升框架
  - **CatBoost**：对称梯度提升
  - **Transformer**：基于注意力机制的序列模型（需 PyTorch）
  - **增量训练**：支持模型增量更新，避免全量重训

- **多期联合预测**
  - 预测未来 N 期的号码出现概率
  - 趋势分析：稳定号码、上升趋势号码
  - 综合推荐

- **特征工程自动化管道**
  - 可配置的特征提取器（号码特征、窗口统计、关联性、区间分布、AC值、和值分布、时间特征、滞后特征、滚动统计）
  - 特征重要性分析
  - 特征选择（基于方差）
  - 配置保存/加载

- **回测胜率统计**
  - 各奖级中奖次数统计
  - 总投入/总回报/收益率计算
  - 号码频率分析
  - 热号/冷号检测

- **号码展示**
  - 红球/蓝球图形化展示
  - 紧凑文本格式，支持一键复制
  - 福彩3D 自动标注投注方式：直选 / 组选3 / 组选6 / 豹子号

- **历史记录**
  - 自动生成历史保存
  - 导出 CSV / TXT / Excel
  - 导入 JSON
  - 打印历史记录
  - 清空历史

- **打印与导出**
  - 打印当前生成结果
  - 打印历史记录
  - 自动排版为带彩球样式的 HTML 表格
  - 打印失败时只提示一次，支持"不再提示"
  - 提供导出 PDF 功能，绕过打印机驱动问题
  - PDF 中的概率折线图自适应宽度，避免与号码重叠

- **插件系统**
  - 动态加载自定义策略插件
  - 支持类自动发现或 `register_strategies(engine)` 函数

- **官方开奖数据**
  - 一键从网络抓取全部历史开奖数据
  - 使用 17500.cn 数据源
  - 本地 JSON 持久化存储，**无网络也能正常使用**
  - 启动时自动检查并更新最新一期数据（可在"设置"中关闭）
    - 受「启动时自动检查更新」开关控制：**关闭后启动完全不检查**，进度对话框也不会弹出。
    - 受「检查间隔（天）」控制：仅当距上次更新超过该间隔（默认 1 天）才联网检查，避免频繁请求。
  - 实时统计分析：热号、冷号、遗漏值、奇偶比、大小比、和值、连号率、三区分布
  - 支持仅获取最新一期

- **历史回测**
  - 单期回测：对指定日期进行模拟投注
  - 批量回测：对日期区间逐期回测，自动汇总盈亏
  - 支持生成注数、预测注数最大 **1000 注**

- **自定义过滤规则**
  - 双色球：比较期数、红球重合上限、蓝球禁止相同
  - 福彩3D：启用开关、比较期数、相同号码上限、和值范围
  - 七乐彩：启用开关、比较期数、基本号重合上限、和值范围

- **界面与主题**
  - 深色/浅色主题
  - 全局字体统一使用 **pt** 单位
  - 策略下拉选择框：切换策略时自动显示对应参数面板

- **异步处理**
  - 基于 asyncio 的异步网络请求
  - ThreadPoolExecutor 并发执行
  - 非阻塞 UI 线程

- **性能优化**
  - NumPy 向量化特征提取
  - 特征缓存（LRU）
  - 批量处理
  - 内存优化

- **CI/CD**
  - GitHub Actions 自动化测试
  - 多平台支持（Ubuntu/Windows）
  - 多 Python 版本支持（3.10/3.11/3.12）

- **设置持久化**
  - 默认注数
  - 最后使用策略
  - 插件目录
  - 蓝球去重对比期数（默认 1 期）
  - 各彩种过滤参数

## 项目结构

```
caipiao/
├── caipiao/
│   ├── core/               # 核心模型与策略接口
│   │   ├── ball.py         # 球的定义
│   │   ├── ticket.py       # 投注单
│   │   ├── strategy.py     # 策略抽象接口
│   │   ├── engine.py       # 生成引擎 + 号码过滤
│   │   ├── prize.py        # 奖金计算
│   │   ├── backtest_stats.py # 回测统计
│   │   └── strategies/     # 内置策略
│   │       └── lotteries/  # 按彩种组织
│   │           ├── ssq/    # 双色球（智能冷热号 + 历史均衡）
│   │           ├── fc3d/   # 福彩3D
│   │           ├── dlt/    # 大乐透
│   │           ├── kl8/    # 快乐8
│   │           ├── pl3/    # 排列3
│   │           ├── pl5/    # 排列5
│   │           ├── qlc/    # 七乐彩
│   │           └── qxc/    # 七星彩
│   ├── data/               # 官方开奖数据获取与分析
│   │   ├── fetcher.py      # 网络抓取
│   │   ├── repository.py   # 本地存储
│   │   ├── analyzer.py     # 统计分析
│   │   └── models.py       # 数据模型
│   ├── ml/                 # 机器学习模块
│   │   ├── features.py     # 特征工程
│   │   ├── model.py        # XGBoost 模型
│   │   ├── lgbm_model.py   # LightGBM 模型
│   │   ├── catboost_model.py # CatBoost 模型
│   │   ├── transformer_model.py # Transformer 模型
│   │   ├── predictor.py    # 预测器
│   │   ├── feature_pipeline.py # 特征工程管道
│   │   ├── multi_period.py # 多期联合预测
│   │   └── optimization.py # 性能优化
│   ├── plugins/            # 插件系统
│   ├── persistence/        # 历史记录与设置
│   ├── utils/              # 工具函数
│   └── ui/                 # Qt 界面
│       ├── async_workers.py # 异步工作器
│       └── workers.py      # 工作线程
├── plugins/                # 自定义插件目录（运行时）
├── tests/                  # 单元测试
├── docs/                   # 项目文档
├── .github/workflows/      # CI/CD 配置
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

## 策略说明

### 智能冷热号策略

数学原理：
1. **热号信号**：拉普拉斯平滑后的出现频率概率
2. **冷号信号**：原始遗漏期数 → 几何分布 z-score（红球 p=1/33，蓝球 p=1/16）
3. **χ² 均匀性检验**：判断红球/蓝球频率是否显著偏离均匀分布
4. **z-score 标准化 + 温度控制 softmax**：融合热分和冷分
5. **Gumbel-max 无放回采样**：保持概率分布形状

### 历史均衡策略

控制维度：
- **奇偶比**：目标奇数个数（基于历史比例）
- **大小比**：目标大号个数（17-33 为大号）
- **和值范围**：基于历史标准差计算合理区间
- **连号模式**：匹配历史连号对数频率
- **三区分布**：1-11 / 12-22 / 23-33 三个区间的号码数量
- **蓝球**：结合频率与遗漏值 z-score 加权，支持奇偶/大小控制

快乐8 历史均衡策略（增强版）额外维度：
- **覆盖度**：号码在 8 个分段中的覆盖比例，保证全局分散性
- **邻期重合**：与上期号码重合数接近历史平均
- **频率引导采样**：基于拉普拉斯平滑频率分段采样，替代纯随机
- **χ² 均匀性检验**：判断当前分布是否显著偏离均匀，指导采样策略

### 号码过滤

- **红球重合过滤**：与最近 N 期开奖号码比较，超过重合上限则淘汰
- **蓝球去重过滤**：与最近 1 期（可配置）开奖蓝球比较，相同则淘汰

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

然后在程序的"插件管理"标签页点击"重新加载插件"即可。

## 多期联合预测

```python
from caipiao.ml.predictor import MLPredictor
from caipiao.ml.multi_period import predict_multi_period, format_multi_period_report

# 创建预测器（需要已训练的模型）
predictor = MLPredictor(records, lookback=50)

# 多期预测
result = predict_multi_period(predictor, periods=5)

# 获取稳定号码
stable = result.get_stable_numbers()

# 获取上升趋势号码
rising = result.get_rising_numbers()

# 打印报告
print(format_multi_period_report(result))
```

## 特征工程管道

```python
from caipiao.ml.feature_pipeline import FeaturePipeline, FeatureConfig

# 创建特征管道
config = FeatureConfig(
    lookback=50,
    use_number_features=True,
    use_window_stats=True,
    use_lag_features=True,
)
pipeline = FeaturePipeline(config)

# 构建特征
X, y_red, y_blue = pipeline.build_features(records)

# 特征重要性分析
importance = pipeline.analyze_feature_importance(X, y_red[:, 0], top_n=10)

# 保存配置
pipeline.save_config("feature_config.json")
```

## 回测统计

```python
from caipiao.core.backtest_stats import run_backtest, format_backtest_report

# 运行回测
stats = run_backtest(
    tickets_by_period={"2024001": [ticket1, ticket2]},
    draw_records={"2024001": draw_record},
    profile_key="ssq",
)

# 打印报告
print(format_backtest_report(stats))

# 获取统计信息
print(f"收益率: {stats.roi:.2%}")
print(f"中奖率: {stats.win_rate:.2%}")
```

## 测试

```bash
# 运行全部测试
python -m pytest tests/

# 运行指定测试
python -m pytest tests/test_core_ticket.py -v

# 带覆盖率
python -m pytest tests/ --cov=caipiao.core --cov=caipiao.data
```

## 贡献

请参考 [CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解如何贡献代码。

## 免责声明

本软件仅用于学习、娱乐和号码生成参考，不保证中奖。彩票开奖是独立随机事件，历史统计规律不能预测未来开奖。请理性购彩，量力而行。
