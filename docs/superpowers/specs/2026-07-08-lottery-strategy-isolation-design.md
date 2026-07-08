# 全彩种生成策略与 ML 底层隔离重构设计

## 背景

当前项目里，多个彩种的生成策略存在严重的代码共享与交叉污染：

- `caipiao/core/strategies/generic.py` 中一个 `_GenericBase` 同时服务福彩3D、七乐彩、快乐8、大乐透、排列3/5、七星彩；修改某彩种逻辑时极易破坏其他彩种。
- 双色球老策略（`random_strategy.py`、`hot_cold_strategy.py` 等）与通用策略的实现方式不一致，部分策略硬编码红球 1-33、蓝球 1-16。
- `caipiao/ml/` 下的 `generic_predictor.py`、`generic_features.py`、`generic_model.py` 虽然接收 `LotteryProfile`，但所有彩种共用同一份特征工程与模型训练代码，特征变更会同时影响所有彩种。
- `caipiao/core/strategies/advanced/` 中的高级策略通过 `_AdvancedBase` 的 `if self._is_ssq() / _is_3d()` 分支来兼容多个彩种，一个类里塞入多套逻辑。

这种“一个类服务多个彩种”的结构，是代码互相污染、测试回归困难的根源。

## 目标

1. **彩种隔离**：每个彩种拥有独立的策略目录，不同彩种之间不共享策略类。
2. **策略隔离**：同一彩种内，不同生成策略也各自为独立类，禁止一个类通过 mode/backend/profile 分支同时表达多种策略。
3. **ML 底层隔离**：特征工程、预测器、模型训练按彩种隔离，不同彩种可独立演进特征与模型结构。
4. **入口稳定**：`build_strategies(profile)`、`needs_history(strategy_id)`、`is_ml_strategy(strategy_id)` 的签名与语义不变，UI/回测/参数锁定层无需改动。
5. **测试保障**：每个彩种、每个策略都有独立测试，全量回归测试确保行为不退化。

## 非目标

- 不改动 `LotteryProfile`、`NumberGroup`、`Ticket`、`DrawRecord` 的核心数据模型（只改消费侧）。
- 不改动 `GenerationEngine` 的注册/生成机制。
- 不重新设计 UI；只保证 UI 通过现有接口拿到的策略集合与 schema 不变。
- 本次不追求模型预测效果提升，只保证重构后行为一致、结构隔离。

## 设计

### 1. 目录结构

```
caipiao/core/strategies/
├── __init__.py              # 仅导出 public API（build_strategies, needs_history, is_ml_strategy）
├── registry.py              # 策略注册表：按 profile.key 管理策略类列表
├── factory.py               # build_strategies / needs_history / is_ml_strategy 实现
├── common/                  # 公共工具（无策略逻辑，只放可安全复用的工具）
│   ├── __init__.py
│   ├── base.py              # LotteryStrategy 基类（可选，提供 _records_from_options / _make_rng 等）
│   ├── records.py           # 历史记录标准化
│   ├── rng.py               # 确定性随机种子
│   └── validators.py        # 通用参数校验
├── lotteries/               # 按彩种隔离
│   ├── __init__.py
│   ├── ssq/                 # 双色球
│   │   ├── __init__.py
│   │   ├── random.py
│   │   ├── odd_even.py
│   │   ├── hot_cold.py
│   │   ├── exclude_include.py
│   │   ├── smart_hot_cold.py
│   │   ├── missing_number.py
│   │   ├── balanced.py
│   │   ├── stats.py
│   │   └── ml/              # SSQ 专属 ML 策略
│   │       ├── xgboost.py
│   │       ├── lightgbm.py
│   │       ├── catboost.py
│   │       ├── lstm.py
│   │       └── hybrid.py
│   ├── fc3d/                # 福彩3D（从现有 fc3d.py / fc3d_utils.py 迁移）
│   │   ├── __init__.py
│   │   ├── utils.py
│   │   ├── random.py
│   │   ├── odd_even.py
│   │   ├── hot_cold.py
│   │   ├── exclude_include.py
│   │   ├── smart_hot_cold.py
│   │   ├── missing_number.py
│   │   ├── balanced.py
│   │   └── ml/
│   │       ├── xgboost.py
│   │       ├── lightgbm.py
│   │       └── catboost.py
│   ├── qlc/                 # 七乐彩
│   ├── kl8/                 # 快乐8
│   ├── dlt/                 # 大乐透
│   ├── pl3/                 # 排列3
│   ├── pl5/                 # 排列5
│   └── qxc/                 # 七星彩
└── advanced/                # 高级策略同样按彩种隔离
    ├── common/              # 高级策略公共抽象（只含接口与通用工具，不含具体生成逻辑）
    └── lotteries/
        ├── ssq/
        ├── fc3d/
        └── ...
```

ML 底层：

```
caipiao/ml/
├── __init__.py
├── common/                  # 通用基础设施（文件路径、指纹、lookback 计算等）
│   ├── model_store.py       # 模型存储与查找（保持当前能力，文件名按 prefix 区分）
│   └── base.py              # 后端工厂等真正可复用的代码
└── lotteries/               # 按彩种隔离
    ├── ssq/
    │   ├── features.py      # SSQ 特征工程
    │   ├── predictor.py     # SSQ 预测器
    │   └── models/
    │       ├── xgboost.py
    │       ├── lightgbm.py
    │       ├── catboost.py
    │       ├── random_forest.py
    │       ├── lstm.py
    │       └── transformer.py
    ├── fc3d/
    ├── qlc/
    ├── kl8/
    ├── dlt/
    ├── pl3/
    ├── pl5/
    └── qxc/
```

### 2. 关键接口契约

#### 2.1 工厂入口（必须保持兼容）

```python
# caipiao/core/strategies/factory.py

def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]: ...
def needs_history(strategy_id: str) -> bool: ...
def is_ml_strategy(strategy_id: str) -> bool: ...
```

- `build_strategies` 内部通过 `registry.STRATEGY_REGISTRY[profile.key]` 获取该彩种策略类列表并实例化。
- `needs_history` / `is_ml_strategy` 仍按策略 ID 前缀判断，因此各彩种策略 ID 必须沿用现有命名（如 `random_3d`、`balanced_qlc`、`xgboost_kl8` 等）。

#### 2.2 策略类契约

每个策略类必须：

1. 继承 `GenerationStrategy`。
2. 实现 `metadata` 属性，返回 `StrategyMetadata`。
3. 可选实现 `get_config_schema()` / `validate_options()`。
4. 实现 `generate(count, options) -> List[Ticket]`。
5. 类名和文件路径体现彩种归属，例如 `SSQRandomStrategy`、`FC3DBalancedStrategy`。

**禁止**：一个类通过 `mode`、`backend`、`profile` 分支同时为多个彩种/多种策略服务。

#### 2.3 策略注册表

```python
# caipiao/core/strategies/registry.py

from .lotteries.ssq import random as ssq_random, ...
from .lotteries.fc3d import random as fc3d_random, ...

STRATEGY_REGISTRY: Dict[str, List[Type[GenerationStrategy]]] = {
    "ssq": [
        ssq_random.SSQRandomStrategy,
        ssq_odd_even.SSQOddEvenStrategy,
        ...,
        ssq_ml_xgboost.SSQXGBoostStrategy,
        ...,
        ssq_advanced_random_forest.SSQRandomForestStrategy,
        ...,
    ],
    "3d": [...],
    "qlc": [...],
    "kl8": [...],
    "dlt": [...],
    "pl3": [...],
    "pl5": [...],
    "qxc": [...],
}
```

### 3. 迁移路径

按**架构层次**分 5 个阶段实施（每阶段独立可验证）：

#### 阶段 1：建立新目录骨架与公共工具

- 创建 `caipiao/core/strategies/common/`、`lotteries/`、`advanced/common/` 空包。
- 创建 `caipiao/ml/common/`、`caipiao/ml/lotteries/` 空包。
- 将 `_records_from_options`、`_make_rng`、历史记录标准化等逻辑移入 `common/`。
- 新增 `registry.py` 与 `factory.py`，但此时仍把旧策略类注册进去，保证 `build_strategies` 行为不变。
- 新增回归测试，验证所有彩种在重构前后返回的策略 ID 集合一致。

#### 阶段 2：按彩种拆分基础策略

- 将 `generic.py` 中的策略按彩种迁移到 `lotteries/{key}/` 下独立文件。
- 将双色球老策略（`random_strategy.py`、`hot_cold_strategy.py` 等）迁移到 `lotteries/ssq/`。
- 将 `fc3d.py` / `fc3d_utils.py` 迁移到 `lotteries/fc3d/`。
- 每个新类只服务一个彩种；删除原 `generic.py` 及已迁移的旧文件。
- 更新 `registry.py`，使用新类。
- 为每个彩种新增 `test_{key}_strategies.py`，覆盖生成合法性、schema、种子可复现、needs_history 前缀。

#### 阶段 3：按彩种拆分 ML 策略

- 将 `ml_strategy.py`、`xgboost_strategy.py`、`lightgbm_strategy.py`、`catboost_strategy.py`、`lstm_strategy.py`、`hybrid_strategy.py` 等按彩种拆分。
- 每个彩种的 ML 策略引用自己彩种目录下的 `ml.predictor` / `ml.features`。
- 初始实现可委托给当前通用 ML 底层（`GenericMLPredictor` 已支持任意 profile），但文件与导入路径必须按彩种隔离。

#### 阶段 4：按彩种拆分 ML 底层（分两步）

**4A：文件隔离，行为不变**

- 在 `caipiao/ml/lotteries/{key}/` 下创建 `features.py`、`predictor.py`、`models/`。
- 每个彩种的 `predictor.py` 和 `features.py` 初始实现直接委托给现有的 `GenericMLPredictor` / `generic_features.py`，保证生成结果完全一致。
- 各彩种 ML 策略改为从 `ml.lotteries.{key}.predictor` 导入，从导入层面完成隔离。

**4B：通用代码下沉，彩种定制上浮**

- 将 `generic_features.py`、`generic_model.py`、`generic_predictor.py` 中真正通用的部分（如模型保存加载、指纹计算、后端工厂）下放到 `ml.common/`。
- 把与彩种特征相关、未来可能定制化的部分（如窗口统计、标签构造）保留在各 `ml/lotteries/{key}/` 中。
- 最终删除 `generic_*.py`。

#### 阶段 5：按彩种拆分高级策略

- 将 `advanced/base.py` 精简为只含真正公共工具/接口。
- 把 `advanced/random_forest_strategy.py`、`bayesian_strategy.py` 等按彩种迁移到 `advanced/lotteries/{key}/`。
- 删除 `_AdvancedBase` 中的 `if _is_ssq() / _is_3d()` 分支，每个彩种拥有自己的 `_compute_probabilities` 实现。

### 4. 兼容性说明

- **策略 ID 不变**：为了 `OptimalParamStore`（以 `(profile_key, strategy_id)` 为键）和 `needs_history` / `is_ml_strategy` 前缀判断继续工作，所有策略 ID 保持现有值。
- **策略名称不变**：UI 下拉框展示的是 `metadata.name`，保持原名称。
- **Schema 字段名不变**：基础参数（`history`、`lookback`、`seed`、`odd_count` 等）保持原字段名，避免 UI 参数面板与历史锁定参数失效。
- **破坏性改动**：
  - 文件路径、类名、导入路径会变化；外部代码直接 `from caipiao.core.strategies.xxx import ...` 会失效（但 UI 只通过 `build_strategies` 使用策略，不受影响）。
  - 部分重复/废弃的类会被删除。

### 5. 错误处理

- 注册表缺失某个彩种时，`build_strategies` 抛出 `ValueError`，而不是默默回退到双色球。
- 各彩种策略内部校验保持原逻辑：历史数据不足抛 `ValueError`、参数越界抛 `ValueError`。
- ML 模型训练失败时由该彩种的 `predictor.py` 捕获并转换为可理解的异常，不污染其他彩种。

### 6. 测试策略

新增/保留以下测试：

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_strategy_factory.py` | 所有彩种 `build_strategies` 返回 ID 集合、needs_history、is_ml_strategy |
| `tests/test_ssq_strategies.py` | 双色球全部策略生成合法性、schema、种子、历史过滤 |
| `tests/test_fc3d_strategies.py` | 3D 全部策略生成合法性、按位顺序、schema |
| `tests/test_qlc_strategies.py` | 七乐彩策略 |
| `tests/test_kl8_strategies.py` | 快乐8 策略（含可变 pick_count） |
| `tests/test_dlt_strategies.py` | 大乐透策略 |
| `tests/test_pl3_strategies.py` | 排列3 策略 |
| `tests/test_pl5_strategies.py` | 排列5 策略 |
| `tests/test_qxc_strategies.py` | 七星彩策略 |
| `tests/ml/test_ssq_ml.py` | SSQ ML 训练/预测/推荐链路 |
| `tests/ml/test_fc3d_ml.py` | 3D ML 链路 |
| `tests/test_model_store.py` | 模型存储查找（已存在，需更新导入） |

全量回归：`python -m pytest tests/ -q`，目标保持当前 212 passed / 4 skipped 以上。

### 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 文件迁移导致导入循环 | 高 | 公共工具只依赖 `profile/models/ticket/strategy` 等底层；策略类内部再依赖公共工具 |
| 策略 ID 或 schema 变化导致历史锁定参数失效 | 中 | 保持 ID、名称、schema 字段名不变 |
| ML 模型路径/指纹变化导致重复训练 | 中 | `model_store.py` 保持通用，文件名 prefix 仍使用 `profile.model_prefix` |
| 阶段合并后回归测试发现大量失败 | 高 | 严格按阶段实施，每阶段跑全量测试后再进入下一阶段 |
| 高级策略拆分后代码重复增加 | 低 | 允许适度重复以换取隔离；公共辅助函数可放入 `advanced/common` |

## 扩展预留

- 新增彩种时，只需在 `lotteries/` 与 `ml/lotteries/` 下新增同名目录并注册到 `registry.py`。
- 未来某个彩种需要替换特征工程时，只改其 `ml/lotteries/{key}/features.py`，不影响其他彩种。
- `advanced/common` 可进一步抽象为插件式的高级策略模板，但本次不引入。

## 待用户确认

1. 是否接受按上述 5 阶段分阶段实施？
2. 是否同意保持策略 ID / 名称 / schema 字段名不变，仅改变文件/类结构？
3. 是否接受阶段 4 中 ML 底层先“文件隔离但实现委托通用代码”，再逐步下沉到各彩种？
4. 是否需要优先处理某些彩种（如双色球、3D、快乐8）？
