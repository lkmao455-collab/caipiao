# 全彩种生成策略与 ML 底层隔离重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `caipiao/core/strategies/` 与 `caipiao/ml/` 按彩种彻底隔离，消除一个类服务多个彩种、一个文件包含多种策略的代码污染，同时保持 `build_strategies` / `needs_history` / `is_ml_strategy` 接口与策略 ID / 名称 / schema 不变。

**Architecture:** 新增按彩种组织的目录 `core/strategies/lotteries/{key}/` 与 `ml/lotteries/{key}/`；引入 `registry.py` 与 `factory.py` 作为唯一入口；公共工具下沉到 `common/` 但只包含真正可复用的基础设施；同一彩种内每个策略也是独立类。

**Tech Stack:** Python 3.10+, pytest, numpy, scikit-learn, xgboost, lightgbm, catboost (按需), PySide6 (UI 不改，只验证)。

## Global Constraints

- 策略 ID 必须保持现状（如 `random`、`odd_even`、`hot_cold`、`balanced`、`stats`、`ml_xgboost`、`xgboost_3d`、`random_forest` 等）。
- 策略 `metadata.name` 与 `metadata.description` 保持现状。
- `get_config_schema()` 的字段名、类型、默认值保持现状（允许新增字段，禁止删除/重命名已有字段）。
- `build_strategies(profile)` / `needs_history(strategy_id)` / `is_ml_strategy(strategy_id)` 的签名与语义不变。
- `GenerationStrategy.generate(count, options)` 返回 `List[Ticket]` 不变。
- 所有迁移必须伴随测试；每阶段完成后运行 `python -m pytest tests/ -q` 必须保持当前通过数不下降。
- 不改动 `LotteryProfile`、`NumberGroup`、`Ticket`、`DrawRecord`、`GenerationEngine` 的核心接口。
- 每次任务完成后必须 `git commit`；禁止一次提交包含多个不相关改动。
- 实施前必须保证工作区干净（当前未提交的修复需先提交/暂存）。

---

## 文件结构映射

### 重构后结构

```
caipiao/core/strategies/
├── __init__.py              # 只导出 build_strategies, needs_history, is_ml_strategy
├── registry.py              # 彩种 -> 策略类列表
├── factory.py               # 入口函数实现
├── common/                  # 真正公共的工具（无策略逻辑）
│   ├── __init__.py
│   ├── records.py           # _records_from_options 等
│   ├── rng.py               # 确定性随机种子
│   └── validators.py        # 通用参数校验辅助
└── lotteries/               # 按彩种隔离
    ├── __init__.py
    ├── ssq/                 # 双色球
    │   ├── __init__.py
    │   ├── random.py
    │   ├── odd_even.py
    │   ├── hot_cold.py
    │   ├── exclude_include.py
    │   ├── smart_hot_cold.py
    │   ├── missing_number.py
    │   ├── balanced.py
    │   ├── stats.py
    │   └── ml/
    │       ├── __init__.py
    │       ├── xgboost.py
    │       ├── lightgbm.py
    │       ├── catboost.py
    │       ├── lstm.py
    │       └── hybrid.py
    ├── fc3d/                # 福彩3D
    │   ├── __init__.py
    │   ├── utils.py         # 从 fc3d_utils.py 迁移
    │   ├── stability.py     # 从 fc3d_stability.py 迁移
    │   ├── random.py
    │   ├── odd_even.py
    │   ├── hot_cold.py
    │   ├── exclude_include.py
    │   ├── smart_hot_cold.py
    │   ├── missing_number.py
    │   ├── balanced.py
    │   └── ml/
    │       ├── __init__.py
    │       ├── xgboost.py
    │       ├── lightgbm.py
    │       └── catboost.py
    ├── qlc/                 # 七乐彩
    ├── kl8/                 # 快乐8
    ├── dlt/                 # 大乐透
    ├── pl3/                 # 排列3
    ├── pl5/                 # 排列5
    └── qxc/                 # 七星彩

caipiao/core/strategies/advanced/
├── __init__.py
├── common/                  # 高级策略公共接口/工具
│   ├── __init__.py
│   └── base.py              # 仅含真正通用辅助（概率归一化、加权采样）
└── lotteries/
    ├── __init__.py
    ├── ssq/
    │   ├── __init__.py
    │   ├── random_forest.py
    │   ├── bayesian.py
    │   ├── markov.py
    │   ├── trend.py
    │   ├── periodic.py
    │   ├── ensemble.py
    │   ├── correlation.py
    │   └── transformer.py
    └── fc3d/
        └── (reserved)

caipiao/ml/
├── __init__.py
├── common/                  # 真正公共基础设施
│   ├── __init__.py
│   ├── model_store.py       # 模型路径、指纹、查找（从现有迁移）
│   └── base.py              # 后端工厂、通用保存加载
└── lotteries/               # 按彩种隔离
    ├── __init__.py
    ├── ssq/
    │   ├── __init__.py
    │   ├── features.py      # SSQ 特征工程
    │   ├── predictor.py     # SSQ 预测器
    │   └── models/
    │       ├── __init__.py
    │       ├── xgboost.py
    │       ├── lightgbm.py
    │       ├── catboost.py
    │       ├── random_forest.py
    │       ├── lstm.py
    │       └── transformer.py
    ├── fc3d/
    │   ├── __init__.py
    │   ├── features.py
    │   ├── predictor.py
    │   └── models/
    │       ├── __init__.py
    │       ├── xgboost.py
    │       ├── lightgbm.py
    │       └── catboost.py
    └── ... (其他彩种预留)
```

### 待删除的旧文件

- `caipiao/core/strategies/generic.py`
- `caipiao/core/strategies/fc3d.py`
- `caipiao/core/strategies/fc3d_utils.py`
- `caipiao/core/strategies/fc3d_stability.py`
- `caipiao/core/strategies/random_strategy.py`
- `caipiao/core/strategies/odd_even_strategy.py`
- `caipiao/core/strategies/hot_cold_strategy.py`
- `caipiao/core/strategies/exclude_include_strategy.py`
- `caipiao/core/strategies/smart_hot_cold_strategy.py`
- `caipiao/core/strategies/missing_number_strategy.py`
- `caipiao/core/strategies/balanced_strategy.py`
- `caipiao/core/strategies/stats_strategy.py`
- `caipiao/core/strategies/ml_strategy.py`
- `caipiao/core/strategies/xgboost_strategy.py`
- `caipiao/core/strategies/lightgbm_strategy.py`
- `caipiao/core/strategies/catboost_strategy.py`
- `caipiao/core/strategies/lstm_strategy.py`
- `caipiao/core/strategies/hybrid_strategy.py`
- `caipiao/core/strategies/advanced/base.py`
- `caipiao/core/strategies/advanced/random_forest_strategy.py`
- `caipiao/core/strategies/advanced/bayesian_strategy.py`
- `caipiao/core/strategies/advanced/markov_strategy.py`
- `caipiao/core/strategies/advanced/trend_strategy.py`
- `caipiao/core/strategies/advanced/periodic_strategy.py`
- `caipiao/core/strategies/advanced/ensemble_strategy.py`
- `caipiao/core/strategies/advanced/correlation_strategy.py`
- `caipiao/core/strategies/advanced/transformer_strategy.py`
- `caipiao/ml/generic_predictor.py`
- `caipiao/ml/generic_features.py`
- `caipiao/ml/generic_model.py`

> 删除操作放在最后阶段统一执行，避免实施过程中破坏导入。

---

## 前置任务

### Task 0: 清理工作区

**Files:**
- 工作区全部文件

**Interfaces:**
- 无

- [ ] **Step 1: 查看当前 git 状态**

Run: `git status --short`
Expected: 了解当前未提交改动。

- [ ] **Step 2: 提交或暂存现有改动**

如果当前未提交的是上一阶段修复内容且已通过测试，执行：

```bash
git add -A
git commit -m "chore: commit prior fixes before isolation refactor"
```

如果其中包含不应提交的临时文件（如 PDF 报告），先排除：

```bash
git add caipiao/ tests/
git commit -m "chore: commit prior code fixes before isolation refactor"
```

- [ ] **Step 3: 确认工作区干净**

Run: `git status --short`
Expected: 仅剩余不应跟踪的临时文件或空。

---

## Phase 1: 目录骨架与公共工具

### Task 1: 创建新目录结构

**Files:**
- Create directories only

**Interfaces:**
- 无

- [ ] **Step 1: 创建目录树**

Run:

```bash
mkdir -p caipiao/core/strategies/common
mkdir -p caipiao/core/strategies/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}
mkdir -p caipiao/core/strategies/advanced/common
mkdir -p caipiao/core/strategies/advanced/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}
mkdir -p caipiao/ml/common
mkdir -p caipiao/ml/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}
mkdir -p caipiao/ml/lotteries/ssq/models
mkdir -p caipiao/ml/lotteries/fc3d/models
```

- [ ] **Step 2: 为所有新增目录添加 `__init__.py`**

Run:

```bash
touch caipiao/core/strategies/common/__init__.py
touch caipiao/core/strategies/lotteries/__init__.py
touch caipiao/core/strategies/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}/__init__.py
touch caipiao/core/strategies/advanced/common/__init__.py
touch caipiao/core/strategies/advanced/lotteries/__init__.py
touch caipiao/core/strategies/advanced/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}/__init__.py
touch caipiao/ml/common/__init__.py
touch caipiao/ml/lotteries/__init__.py
touch caipiao/ml/lotteries/{ssq,fc3d,qlc,kl8,dlt,pl3,pl5,qxc}/__init__.py
touch caipiao/ml/lotteries/{ssq,fc3d}/models/__init__.py
```

- [ ] **Step 3: 提交目录骨架**

```bash
git add caipiao/core/strategies/common caipiao/core/strategies/lotteries caipiao/core/strategies/advanced/common caipiao/core/strategies/advanced/lotteries caipiao/ml/common caipiao/ml/lotteries
git commit -m "chore: create per-lottery strategy and ml directory skeleton"
```

---

### Task 2: 公共工具模块

**Files:**
- Create: `caipiao/core/strategies/common/records.py`
- Create: `caipiao/core/strategies/common/rng.py`
- Create: `caipiao/core/strategies/common/validators.py`
- Test: `tests/test_strategy_common.py`

**Interfaces:**
- Produces:
  - `records_from_options(options: Dict[str, Any]) -> List[DrawRecord]`
  - `make_rng(options: Dict[str, Any]) -> random.Random`
  - `make_rng(options: Dict[str, Any], seed: Optional[int]) -> random.Random`
  - `validate_odd_count(options, pick) -> None`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_strategy_common.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import FC3D, SSQ
from caipiao.core.strategies.common.records import records_from_options
from caipiao.core.strategies.common.rng import make_rng
from caipiao.core.strategies.common.validators import validate_odd_count
from caipiao.core.ticket import Ticket
from caipiao.data.models import DrawRecord


def make_ticket_3d(numbers):
    return Ticket(profile=FC3D, groups={"pos": numbers})


def test_records_from_options_accepts_draw_records():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
    ]
    assert records_from_options({"history": records}) == records


def test_records_from_options_accepts_tickets():
    tickets = [make_ticket_3d([1, 2, 3])]
    result = records_from_options({"history": tickets})
    assert len(result) == 1
    assert result[0].profile.key == "3d"
    assert result[0].groups["pos"] == [1, 2, 3]


def test_records_from_options_empty():
    assert records_from_options({}) == []
    assert records_from_options({"history": None}) == []


def test_make_rng_with_seed():
    rng1 = make_rng({"seed": 42})
    rng2 = make_rng({"seed": 42})
    assert rng1.randint(0, 100) == rng2.randint(0, 100)


def test_make_rng_without_seed():
    rng = make_rng({})
    assert isinstance(rng.randint(0, 100), int)


def test_validate_odd_count_valid():
    validate_odd_count({"odd_count": 3}, 6)


def test_validate_odd_count_invalid():
    with pytest.raises(ValueError):
        validate_odd_count({"odd_count": 7}, 6)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_strategy_common.py -v`
Expected: 7 FAIL（模块未定义）

- [ ] **Step 3: 实现公共工具模块**

```python
# caipiao/core/strategies/common/records.py
"""历史记录标准化工具."""

from __future__ import annotations

from typing import Any, Dict, List

from ....data.models import DrawRecord


def records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    """从 options['history'] 提取 DrawRecord 列表。"""
    history = options.get("history") or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records
```

```python
# caipiao/core/strategies/common/rng.py
"""随机数生成器工具."""

from __future__ import annotations

import random
from typing import Any, Dict, Optional


def make_rng(options: Dict[str, Any], seed: Optional[int] = None) -> random.Random:
    """根据 options 或显式 seed 创建 Random 实例。"""
    effective_seed = seed if seed is not None else options.get("seed")
    return random.Random(effective_seed) if effective_seed is not None else random.Random()
```

```python
# caipiao/core/strategies/common/validators.py
"""通用参数校验辅助."""

from __future__ import annotations

from typing import Any, Dict


def validate_odd_count(options: Dict[str, Any], pick: int) -> None:
    """校验奇数个数参数。"""
    odd_count = options.get("odd_count", pick // 2)
    if not isinstance(odd_count, int) or not (0 <= odd_count <= pick):
        raise ValueError(f"奇数个数必须是 0-{pick} 的整数")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_strategy_common.py -v`
Expected: 7 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/common tests/test_strategy_common.py
git commit -m "feat: add common utilities for strategy isolation"
```

---

### Task 3: 策略注册表与工厂入口

**Files:**
- Create: `caipiao/core/strategies/registry.py`
- Create: `caipiao/core/strategies/factory.py`
- Modify: `caipiao/core/strategies/__init__.py`
- Test: `tests/test_strategy_factory.py`

**Interfaces:**
- Produces:
  - `STRATEGY_REGISTRY: Dict[str, List[Type[GenerationStrategy]]]`
  - `build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]`
  - `needs_history(strategy_id: str) -> bool`
  - `is_ml_strategy(strategy_id: str) -> bool`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_strategy_factory.py
import pytest

from caipiao.core.profile import get_profile, profile_keys
from caipiao.core.strategies import build_strategies, is_ml_strategy, needs_history


EXPECTED_IDS = {
    "ssq": {
        "random", "odd_even", "hot_cold", "exclude_include", "smart_hot_cold",
        "missing_number", "balanced", "stats", "ml_xgboost", "ml_lightgbm", "ml_catboost",
        "random_forest", "bayesian", "markov", "trend", "periodic", "ensemble",
        "correlation", "transformer",
    },
    "3d": {
        "random_3d", "odd_even_3d", "hot_cold_3d", "exclude_include_3d",
        "smart_hot_cold_3d", "missing_number_3d", "balanced_3d",
        "xgboost_3d", "lightgbm_3d", "catboost_3d",
    },
    "qlc": {
        "random_qlc", "odd_even_qlc", "hot_cold_qlc", "exclude_include_qlc",
        "smart_hot_cold_qlc", "missing_number_qlc", "balanced_qlc",
        "xgboost_qlc", "lightgbm_qlc", "catboost_qlc",
    },
    "kl8": {
        "random_kl8", "odd_even_kl8", "hot_cold_kl8", "exclude_include_kl8",
        "smart_hot_cold_kl8", "missing_number_kl8", "balanced_kl8",
        "xgboost_kl8", "lightgbm_kl8", "catboost_kl8",
    },
    "dlt": {
        "random_dlt", "odd_even_dlt", "hot_cold_dlt", "exclude_include_dlt",
        "smart_hot_cold_dlt", "missing_number_dlt", "balanced_dlt",
        "xgboost_dlt", "lightgbm_dlt", "catboost_dlt",
    },
    "pl3": {
        "random_pl3", "odd_even_pl3", "hot_cold_pl3", "exclude_include_pl3",
        "smart_hot_cold_pl3", "missing_number_pl3", "balanced_pl3",
        "xgboost_pl3", "lightgbm_pl3", "catboost_pl3",
    },
    "pl5": {
        "random_pl5", "odd_even_pl5", "hot_cold_pl5", "exclude_include_pl5",
        "smart_hot_cold_pl5", "missing_number_pl5", "balanced_pl5",
        "xgboost_pl5", "lightgbm_pl5", "catboost_pl5",
    },
    "qxc": {
        "random_qxc", "odd_even_qxc", "hot_cold_qxc", "exclude_include_qxc",
        "smart_hot_cold_qxc", "missing_number_qxc", "balanced_qxc",
        "xgboost_qxc", "lightgbm_qxc", "catboost_qxc",
    },
}


@pytest.mark.parametrize("key", profile_keys())
def test_build_strategies_returns_expected_ids(key):
    profile = get_profile(key)
    strategies = build_strategies(profile)
    ids = {s.metadata.id for s in strategies}
    assert ids == EXPECTED_IDS[key], f"{key}: got {ids}"


def test_needs_history_prefixes():
    assert needs_history("hot_cold_3d") is True
    assert needs_history("balanced") is True
    assert needs_history("random") is False
    assert needs_history("xgboost_3d") is True
    assert needs_history("random_forest") is True


def test_is_ml_strategy_prefixes():
    assert is_ml_strategy("ml_xgboost") is True
    assert is_ml_strategy("xgboost_3d") is True
    assert is_ml_strategy("lightgbm_kl8") is True
    assert is_ml_strategy("random_forest") is True
    assert is_ml_strategy("ensemble") is True
    assert is_ml_strategy("random") is False
    assert is_ml_strategy("balanced") is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_strategy_factory.py -v`
Expected: 11 FAIL（新模块未定义）

- [ ] **Step 3: 实现注册表与工厂**

```python
# caipiao/core/strategies/registry.py
"""策略注册表：按彩种管理所有生成策略类。"""

from __future__ import annotations

from typing import Dict, List, Type

from .lotteries.fc3d import balanced as fc3d_balanced
from .lotteries.fc3d import exclude_include as fc3d_exclude_include
from .lotteries.fc3d import hot_cold as fc3d_hot_cold
from .lotteries.fc3d import missing_number as fc3d_missing_number
from .lotteries.fc3d import odd_even as fc3d_odd_even
from .lotteries.fc3d import random as fc3d_random
from .lotteries.fc3d import smart_hot_cold as fc3d_smart_hot_cold
from .lotteries.fc3d.ml import catboost as fc3d_catboost
from .lotteries.fc3d.ml import lightgbm as fc3d_lightgbm
from .lotteries.fc3d.ml import xgboost as fc3d_xgboost
from .lotteries.ssq import balanced as ssq_balanced
from .lotteries.ssq import exclude_include as ssq_exclude_include
from .lotteries.ssq import hot_cold as ssq_hot_cold
from .lotteries.ssq import missing_number as ssq_missing_number
from .lotteries.ssq import odd_even as ssq_odd_even
from .lotteries.ssq import random as ssq_random
from .lotteries.ssq import smart_hot_cold as ssq_smart_hot_cold
from .lotteries.ssq import stats as ssq_stats
from .lotteries.ssq.ml import catboost as ssq_catboost
from .lotteries.ssq.ml import hybrid as ssq_hybrid
from .lotteries.ssq.ml import lightgbm as ssq_lightgbm
from .lotteries.ssq.ml import lstm as ssq_lstm
from .lotteries.ssq.ml import xgboost as ssq_xgboost
from .strategy import GenerationStrategy

# 当前阶段仅注册 ssq 与 3d；其余彩种在 Phase 2 完成后补齐。
STRATEGY_REGISTRY: Dict[str, List[Type[GenerationStrategy]]] = {
    "ssq": [
        ssq_random.SSQRandomStrategy,
        ssq_odd_even.SSQOddEvenStrategy,
        ssq_hot_cold.SSQHotColdStrategy,
        ssq_exclude_include.SSQExcludeIncludeStrategy,
        ssq_smart_hot_cold.SSQSmartHotColdStrategy,
        ssq_missing_number.SSQMissingNumberStrategy,
        ssq_balanced.SSQBalancedStrategy,
        ssq_stats.SSQStatsStrategy,
        ssq_xgboost.SSQXGBoostStrategy,
        ssq_lightgbm.SSQLightGBMStrategy,
        ssq_catboost.SSQCatBoostStrategy,
        ssq_lstm.SSQLSTMStrategy,
        ssq_hybrid.SSQHybridStrategy,
    ],
    "3d": [
        fc3d_random.FC3DRandomStrategy,
        fc3d_odd_even.FC3DOddEvenStrategy,
        fc3d_hot_cold.FC3DHotColdStrategy,
        fc3d_exclude_include.FC3DExcludeIncludeStrategy,
        fc3d_smart_hot_cold.FC3DSmartHotColdStrategy,
        fc3d_missing_number.FC3DMissingNumberStrategy,
        fc3d_balanced.FC3DBalancedStrategy,
        fc3d_xgboost.FC3DXGBoostStrategy,
        fc3d_lightgbm.FC3DLightGBMStrategy,
        fc3d_catboost.FC3DCatBoostStrategy,
    ],
}
```

```python
# caipiao/core/strategies/factory.py
"""策略工厂入口。"""

from __future__ import annotations

from typing import List

from ..profile import LotteryProfile
from .registry import STRATEGY_REGISTRY
from .strategy import GenerationStrategy


def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]:
    """为指定彩种生成全部策略实例。"""
    classes = STRATEGY_REGISTRY.get(profile.key)
    if classes is None:
        raise ValueError(f"未注册彩种 {profile.key} 的策略")
    return [cls() for cls in classes]


def needs_history(strategy_id: str) -> bool:
    """判断策略是否需要历史开奖数据。"""
    for key in (
        "hot_cold", "smart_hot_cold", "missing_number", "balanced",
        "stats", "xgboost", "lightgbm", "catboost", "ml_",
        "lstm", "hybrid", "random_forest", "bayesian", "markov",
        "trend", "periodic", "ensemble", "correlation", "transformer",
    ):
        if strategy_id.startswith(key):
            return True
    return False


def is_ml_strategy(strategy_id: str) -> bool:
    """判断策略是否为机器学习策略。"""
    return (
        strategy_id.startswith("xgboost_")
        or strategy_id.startswith("lightgbm_")
        or strategy_id.startswith("catboost_")
        or strategy_id.startswith("ml_")
        or strategy_id.startswith("random_forest")
        or strategy_id.startswith("ensemble")
        or strategy_id.startswith("lstm")
        or strategy_id.startswith("hybrid")
        or strategy_id.startswith("transformer")
    )
```

```python
# caipiao/core/strategies/__init__.py
"""策略包公共入口。"""

from .factory import build_strategies, is_ml_strategy, needs_history

__all__ = ["build_strategies", "needs_history", "is_ml_strategy"]
```

- [ ] **Step 4: 运行测试确认失败（预期：导入错误）**

Run: `python -m pytest tests/test_strategy_factory.py -v`
Expected: ImportError（因为 lottery 子模块尚未实现）

- [ ] **Step 5: 提交骨架**

```bash
git add caipiao/core/strategies/registry.py caipiao/core/strategies/factory.py caipiao/core/strategies/__init__.py tests/test_strategy_factory.py
git commit -m "feat: add strategy registry and factory entry points"
```

---

## Phase 2: 按彩种拆分基础策略

### Task 4: 迁移 SSQ 基础策略（代表：Random + OddEven）

**Files:**
- Create: `caipiao/core/strategies/lotteries/ssq/random.py`
- Create: `caipiao/core/strategies/lotteries/ssq/odd_even.py`
- Create: `caipiao/core/strategies/lotteries/ssq/__init__.py`
- Test: `tests/test_ssq_strategies.py`

**Interfaces:**
- Produces:
  - `SSQRandomStrategy` (id=`random`, name=`完全随机`)
  - `SSQOddEvenStrategy` (id=`odd_even`, name=`奇偶均衡`)

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_ssq_strategies.py
import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies
from caipiao.core.strategies.lotteries.ssq.odd_even import SSQOddEvenStrategy
from caipiao.core.strategies.lotteries.ssq.random import SSQRandomStrategy


def test_ssq_random_metadata():
    s = SSQRandomStrategy()
    assert s.metadata.id == "random"
    assert s.metadata.name == "完全随机"


def test_ssq_random_generates_valid_tickets():
    s = SSQRandomStrategy()
    tickets = s.generate(count=5)
    assert len(tickets) == 5
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1
        assert all(1 <= n <= 33 for n in t.groups["red"])
        assert 1 <= t.groups["blue"][0] <= 16


def test_ssq_random_seed_reproducible():
    s = SSQRandomStrategy()
    t1 = s.generate(count=1, options={"seed": 42})[0]
    t2 = s.generate(count=1, options={"seed": 42})[0]
    assert t1.groups == t2.groups


def test_ssq_odd_even_metadata():
    s = SSQOddEvenStrategy()
    assert s.metadata.id == "odd_even"
    assert s.metadata.name == "奇偶均衡"


def test_ssq_odd_even_respects_count():
    s = SSQOddEvenStrategy()
    tickets = s.generate(count=5, options={"odd_count": 2})
    for t in tickets:
        odd = sum(1 for n in t.groups["red"] if n % 2 == 1)
        assert odd == 2


def test_build_strategies_includes_ssq():
    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "random" in ids
    assert "odd_even" in ids
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_ssq_strategies.py -v`
Expected: 6 FAIL

- [ ] **Step 3: 实现 SSQ Random 策略**

```python
# caipiao/core/strategies/lotteries/ssq/random.py
"""双色球完全随机策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket


class SSQRandomStrategy(GenerationStrategy):
    """完全随机生成投注单."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random",
            name="完全随机",
            description="从 33 个红球和 16 个蓝球中完全随机抽取。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
                "tooltip": "固定随机种子可使每次生成的号码相同，便于重复实验。留空则完全随机。",
            }
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        seed = options.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("随机种子必须是整数")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        basis = "完全随机策略：从 33 个红球和 16 个蓝球中等概率随机抽取。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(range(1, 34), 6))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
```

- [ ] **Step 4: 实现 SSQ OddEven 策略**

```python
# caipiao/core/strategies/lotteries/ssq/odd_even.py
"""双色球奇偶均衡策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.validators import validate_odd_count


class SSQOddEvenStrategy(GenerationStrategy):
    """尽量保持红球奇偶比均衡（默认 3:3，可配置）."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even",
            name="奇偶均衡",
            description="控制红球中奇数和偶数的比例，默认 3:3。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": 3,
                "min": 0,
                "max": 6,
                "tooltip": "指定红球中奇数的个数（0~6），偶数个数自动为 6 减该值。默认 3 个奇数符合历史统计规律。",
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
                "tooltip": "固定随机种子可使每次生成的号码相同，便于重复实验。留空则完全随机。",
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        validate_odd_count(options, 6)

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        odd_count = int(options.get("odd_count", 3))
        even_count = 6 - odd_count
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        odd_reds = [i for i in range(1, 34) if i % 2 == 1]
        even_reds = [i for i in range(1, 34) if i % 2 == 0]
        basis = f"奇偶均衡策略：红球中强制包含 {odd_count} 个奇数、{even_count} 个偶数，其余号码随机补充。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            if odd_count > len(odd_reds) or even_count > len(even_reds):
                raise ValueError("奇偶数量超出可选范围")
            reds = sorted(rng.sample(odd_reds, odd_count) + rng.sample(even_reds, even_count))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
```

- [ ] **Step 5: 更新 SSQ __init__.py**

```python
# caipiao/core/strategies/lotteries/ssq/__init__.py
"""双色球生成策略."""

from .balanced import SSQBalancedStrategy
from .exclude_include import SSQExcludeIncludeStrategy
from .hot_cold import SSQHotColdStrategy
from .missing_number import SSQMissingNumberStrategy
from .odd_even import SSQOddEvenStrategy
from .random import SSQRandomStrategy
from .smart_hot_cold import SSQSmartHotColdStrategy
from .stats import SSQStatsStrategy

__all__ = [
    "SSQRandomStrategy",
    "SSQOddEvenStrategy",
    "SSQHotColdStrategy",
    "SSQExcludeIncludeStrategy",
    "SSQSmartHotColdStrategy",
    "SSQMissingNumberStrategy",
    "SSQBalancedStrategy",
    "SSQStatsStrategy",
]
```

> 注意：此时 `balanced.py` 等尚未创建，`__init__.py` 可先只导出已实现的 random/odd_even，后续任务再补齐导入。但为了避免注册表导入失败，建议 Task 4 只注册 random 和 odd_even，其余 SSQ 策略在后续任务中逐步加入注册表。

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_ssq_strategies.py -v`
Expected: 6 PASS

- [ ] **Step 7: 提交**

```bash
git add caipiao/core/strategies/lotteries/ssq/random.py caipiao/core/strategies/lotteries/ssq/odd_even.py caipiao/core/strategies/lotteries/ssq/__init__.py tests/test_ssq_strategies.py
git commit -m "feat: isolate ssq random and odd-even strategies"
```

---

### Task 5: 迁移 SSQ 其余基础策略

**Files:**
- Create: `caipiao/core/strategies/lotteries/ssq/hot_cold.py`
- Create: `caipiao/core/strategies/lotteries/ssq/exclude_include.py`
- Create: `caipiao/core/strategies/lotteries/ssq/smart_hot_cold.py`
- Create: `caipiao/core/strategies/lotteries/ssq/missing_number.py`
- Create: `caipiao/core/strategies/lotteries/ssq/balanced.py`
- Create: `caipiao/core/strategies/lotteries/ssq/stats.py`
- Modify: `caipiao/core/strategies/lotteries/ssq/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Test: extend `tests/test_ssq_strategies.py`

**Interfaces:**
- Produces:
  - `SSQHotColdStrategy` (id=`hot_cold`)
  - `SSQExcludeIncludeStrategy` (id=`exclude_include`)
  - `SSQSmartHotColdStrategy` (id=`smart_hot_cold`)
  - `SSQMissingNumberStrategy` (id=`missing_number`)
  - `SSQBalancedStrategy` (id=`balanced`)
  - `SSQStatsStrategy` (id=`stats`)

- [ ] **Step 1: 编写失败测试（覆盖全部 SSQ 基础策略）**

在 `tests/test_ssq_strategies.py` 追加：

```python
from datetime import datetime

from caipiao.data.models import DrawRecord


def make_ssq_history(n=50):
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i),
            red_balls=sorted(__import__("random").sample(range(1, 34), 6)),
            blue_ball=(i % 16) + 1,
        )
        for i in range(n)
    ]


def test_ssq_all_basic_strategies_generate_valid_tickets():
    from caipiao.core.strategies.lotteries.ssq import (
        SSQBalancedStrategy,
        SSQExcludeIncludeStrategy,
        SSQHotColdStrategy,
        SSQMissingNumberStrategy,
        SSQSmartHotColdStrategy,
        SSQStatsStrategy,
    )

    history = make_ssq_history(50)
    strategies = [
        SSQHotColdStrategy(),
        SSQSmartHotColdStrategy(),
        SSQMissingNumberStrategy(),
        SSQBalancedStrategy(),
        SSQStatsStrategy(),
    ]
    for s in strategies:
        tickets = s.generate(count=2, options={"history": history})
        assert len(tickets) == 2
        for t in tickets:
            assert t.profile.key == "ssq"
            assert len(t.groups["red"]) == 6
            assert len(t.groups["blue"]) == 1

    s = SSQExcludeIncludeStrategy()
    tickets = s.generate(count=2, options={"include_red": [1, 2, 3]})
    for t in tickets:
        assert {1, 2, 3} <= set(t.groups["red"])
```

- [ ] **Step 2: 迁移策略代码**

将现有 `hot_cold_strategy.py`、`exclude_include_strategy.py`、`smart_hot_cold_strategy.py`、`missing_number_strategy.py`、`balanced_strategy.py`、`stats_strategy.py` 的内容复制到新文件，并做以下适配：

1. 类名改为 `SSQHotColdStrategy` 等。
2. 删除原文件中的 `is_history_needed` 等未使用属性（如果存在）。
3. 导入 `from ....profile import SSQ` 并用 `Ticket(profile=SSQ, groups={...})` 替代旧构造。
4. 使用 `from ...common.records import records_from_options` 替换内部 `_to_draw_records`。
5. 保持 `metadata`、`get_config_schema`、`validate_options`、`generate` 的语义与字段名不变。

例如 `SSQHotColdStrategy` 的核心差异：

```python
# caipiao/core/strategies/lotteries/ssq/hot_cold.py
from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Optional

from ....profile import SSQ
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ...common.records import records_from_options


class SSQHotColdStrategy(GenerationStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold",
            name="冷热号分析",
            description="基于历史记录统计出现频率，优先选择热号或冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "label": "模式",
                "choices": ["hot", "cold", "mixed"],
                "default": "mixed",
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        mode = options.get("mode", "mixed")
        if mode not in ("hot", "cold", "mixed"):
            raise ValueError("mode 必须是 hot、cold 或 mixed")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        mode = options.get("mode", "mixed")
        records = records_from_options(options)
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        red_counter: Counter = Counter()
        for record in records:
            red_counter.update(record.groups.get("red", []))

        all_reds = list(range(1, 34))
        if not red_counter:
            ranked_reds = all_reds[:]
            rng.shuffle(ranked_reds)
        else:
            ranked_reds = sorted(all_reds, key=lambda n: red_counter.get(n, 0), reverse=True)

        if mode == "hot":
            pool = ranked_reds[:16]
        elif mode == "cold":
            pool = ranked_reds[-16:]
        else:
            pool = ranked_reds[:8] + ranked_reds[-8:]

        basis = f"冷热号分析策略：基于历史记录统计频率后选取候选池。注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            reds = sorted(rng.sample(pool, 6))
            blue = rng.randint(1, 16)
            tickets.append(
                Ticket(
                    profile=SSQ,
                    groups={"red": reds, "blue": [blue]},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
```

其余 5 个策略按相同模式迁移（文件名/类名不同，逻辑保持原实现）。

- [ ] **Step 3: 更新 SSQ __init__.py 和 registry.py**

`caipiao/core/strategies/lotteries/ssq/__init__.py` 导入全部 8 个基础策略类。

`caipiao/core/strategies/registry.py` 的 SSQ 列表补齐全部 8 个基础策略。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_ssq_strategies.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/lotteries/ssq/ tests/test_ssq_strategies.py caipiao/core/strategies/registry.py
git commit -m "feat: isolate remaining ssq basic strategies"
```

---

### Task 6: 迁移 FC3D 策略到新目录

**Files:**
- Create: `caipiao/core/strategies/lotteries/fc3d/utils.py`（从 `fc3d_utils.py` 复制）
- Create: `caipiao/core/strategies/lotteries/fc3d/stability.py`（从 `fc3d_stability.py` 复制）
- Create: `caipiao/core/strategies/lotteries/fc3d/random.py` 等 7 个文件
- Create: `caipiao/core/strategies/lotteries/fc3d/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Test: `tests/test_fc3d_strategies.py`（已存在，更新导入路径）

**Interfaces:**
- Produces:
  - `FC3DRandomStrategy`, `FC3DOddEvenStrategy`, `FC3DHotColdStrategy`,
    `FC3DExcludeIncludeStrategy`, `FC3DSmartHotColdStrategy`,
    `FC3DMissingNumberStrategy`, `FC3DBalancedStrategy`

- [ ] **Step 1: 复制工具模块与稳定性模块**

将 `caipiao/core/strategies/fc3d_utils.py` 完整复制到 `caipiao/core/strategies/lotteries/fc3d/utils.py`。
将 `caipiao/core/strategies/fc3d_stability.py` 完整复制到 `caipiao/core/strategies/lotteries/fc3d/stability.py`。

- [ ] **Step 2: 拆分策略类**

将 `caipiao/core/strategies/fc3d.py` 中的每个类拆分到独立文件：
- `caipiao/core/strategies/lotteries/fc3d/random.py`
- `caipiao/core/strategies/lotteries/fc3d/odd_even.py`
- `caipiao/core/strategies/lotteries/fc3d/hot_cold.py`
- `caipiao/core/strategies/lotteries/fc3d/exclude_include.py`
- `caipiao/core/strategies/lotteries/fc3d/smart_hot_cold.py`
- `caipiao/core/strategies/lotteries/fc3d/missing_number.py`
- `caipiao/core/strategies/lotteries/fc3d/balanced.py`

每个文件包含一个类，导入做以下调整：
- `from ..profile import get_profile` → `from .....profile import get_profile`
- `from ..strategy import ...` → `from .....strategy import ...`
- `from ..ticket import Ticket` → `from .....ticket import Ticket`
- `from ...data.models import DrawRecord` → `from .....data.models import DrawRecord`
- `from .fc3d_stability import ...` → `from .stability import ...`
- `from .fc3d_utils import ...` → `from .utils import ...`
- `from ...ml.generic_predictor import ...` → `from .....ml.generic_predictor import ...`（Phase 4 再替换）
- `from ...ml.model_store import ...` → `from .....ml.model_store import ...`

- [ ] **Step 3: 创建 FC3D __init__.py**

```python
# caipiao/core/strategies/lotteries/fc3d/__init__.py
"""福彩3D生成策略."""

from .balanced import FC3DBalancedStrategy
from .exclude_include import FC3DExcludeIncludeStrategy
from .hot_cold import FC3DHotColdStrategy
from .missing_number import FC3DMissingNumberStrategy
from .odd_even import FC3DOddEvenStrategy
from .random import FC3DRandomStrategy
from .smart_hot_cold import FC3DSmartHotColdStrategy

__all__ = [
    "FC3DRandomStrategy",
    "FC3DOddEvenStrategy",
    "FC3DHotColdStrategy",
    "FC3DExcludeIncludeStrategy",
    "FC3DSmartHotColdStrategy",
    "FC3DMissingNumberStrategy",
    "FC3DBalancedStrategy",
]
```

- [ ] **Step 4: 更新 registry.py 使用新路径**

将 `registry.py` 中 FC3D 的导入从旧 `.fc3d` 改为 `.lotteries.fc3d.*`。

- [ ] **Step 5: 更新现有测试导入**

修改 `tests/test_fc3d_strategies.py` 中所有 `from caipiao.core.strategies.fc3d import ...` 为 `from caipiao.core.strategies.lotteries.fc3d import ...`。
修改 `from caipiao.core.strategies.fc3d_utils import ...` 为 `from caipiao.core.strategies.lotteries.fc3d.utils import ...`。

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py tests/test_fc3d_utils.py tests/test_strategy_factory.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add caipiao/core/strategies/lotteries/fc3d/ caipiao/core/strategies/registry.py tests/test_fc3d_strategies.py tests/test_fc3d_utils.py
git commit -m "refactor: move fc3d strategies into per-lottery package"
```

---

### Task 7: 创建通用彩种（QLC/KL8/DLT/PL3/PL5/QXC）基础策略

**Files:**
- Create per-lottery directories/files for 6 lotteries × 7 strategies
- Modify: `caipiao/core/strategies/registry.py`
- Test: `tests/test_other_lottery_strategies.py`

**Interfaces:**
- Produces per lottery:
  - `Random`, `OddEven`, `HotCold`, `ExcludeInclude`, `SmartHotCold`, `MissingNumber`, `Balanced`

- [ ] **Step 1: 建立迁移模式**

每个通用彩种策略类复制自原 `generic.py` 中的对应类，但：
1. 类名带彩种前缀，如 `QLCRandomStrategy`。
2. 硬编码 `self.profile = QLC` 等，不再接收 `profile` 参数。
3. 删除 `_GenericBase` 继承，改为继承 `GenerationStrategy`。
4. 使用 `from .....profile import QLC` 等导入。
5. 使用 `from ...common.records import records_from_options`。
6. `metadata.id` 保持 `random_qlc` 等。

- [ ] **Step 2: 迁移七乐彩(QLC)示例**

```python
# caipiao/core/strategies/lotteries/qlc/random.py
"""七乐彩完全随机策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ....profile import QLC
from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket


class QLCRandomStrategy(GenerationStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_qlc",
            name="完全随机",
            description="在七乐彩 1-30 号池中完全随机抽取 7 个基本号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            }
        }

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        seed = options.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        basis = "完全随机策略：在七乐彩 1-30 号池中随机抽取 7 个基本号。"
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            nums = sorted(rng.sample(range(1, 31), 7))
            tickets.append(
                Ticket(profile=QLC, groups={"basic": nums}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
```

其余 QLC 策略从 `generic.py` 复制并修改类名/导入/固定 profile。

- [ ] **Step 3: 批量创建其余彩种策略**

对 KL8、DLT、PL3、PL5、QXC 重复 Step 2。可使用脚本辅助生成骨架，但每个策略逻辑必须人工从 `generic.py` 迁移并审查。

快乐8 注意 `pick_count` 可变；排列3/5/七星彩注意 `positional=True`。

- [ ] **Step 4: 更新 registry.py**

补齐 `STRATEGY_REGISTRY` 的 `qlc`、`kl8`、`dlt`、`pl3`、`pl5`、`qxc` 键。

- [ ] **Step 5: 编写通用彩种回归测试**

```python
# tests/test_other_lottery_strategies.py
import pytest

from caipiao.core.profile import DLT, KL8, PL3, PL5, QLC, QXC, get_profile
from caipiao.core.strategies import build_strategies


@pytest.mark.parametrize("key", ["qlc", "kl8", "dlt", "pl3", "pl5", "qxc"])
def test_all_strategies_generate_valid_tickets(key):
    profile = get_profile(key)
    strategies = build_strategies(profile)
    assert len(strategies) >= 7
    for s in strategies:
        if s.metadata.id.startswith("random"):
            tickets = s.generate(count=2)
        else:
            # 其他策略需要历史数据，用随机生成的记录
            from datetime import datetime

            from caipiao.data.models import DrawRecord

            history = [
                DrawRecord(
                    f"2024{i:03d}",
                    datetime(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                    profile=key,
                    groups={g.key: [g.lo] * g.count for g in profile.pick_groups},
                )
                for i in range(100)
            ]
            tickets = s.generate(count=2, options={"history": history})
        assert len(tickets) == 2
        for t in tickets:
            assert t.profile.key == key
            for g in profile.pick_groups:
                assert g.key in t.groups
                assert len(t.groups[g.key]) >= g.effective_pick_min
```

- [ ] **Step 6: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: 当前通过数不下降

- [ ] **Step 7: 提交**

```bash
git add caipiao/core/strategies/lotteries/{qlc,kl8,dlt,pl3,pl5,qxc}/ caipiao/core/strategies/registry.py tests/test_other_lottery_strategies.py
git commit -m "feat: isolate qlc/kl8/dlt/pl3/pl5/qxc basic strategies"
```

---

### Task 8: 删除旧基础策略文件

**Files:**
- Delete: `caipiao/core/strategies/generic.py`
- Delete: `caipiao/core/strategies/fc3d.py`
- Delete: `caipiao/core/strategies/fc3d_utils.py`
- Delete: `caipiao/core/strategies/fc3d_stability.py`
- Delete: `caipiao/core/strategies/random_strategy.py`
- Delete: `caipiao/core/strategies/odd_even_strategy.py`
- Delete: `caipiao/core/strategies/hot_cold_strategy.py`
- Delete: `caipiao/core/strategies/exclude_include_strategy.py`
- Delete: `caipiao/core/strategies/smart_hot_cold_strategy.py`
- Delete: `caipiao/core/strategies/missing_number_strategy.py`
- Delete: `caipiao/core/strategies/balanced_strategy.py`
- Delete: `caipiao/core/strategies/stats_strategy.py`

- [ ] **Step 1: 删除旧文件**

```bash
git rm caipiao/core/strategies/generic.py
git rm caipiao/core/strategies/fc3d.py
git rm caipiao/core/strategies/fc3d_utils.py
git rm caipiao/core/strategies/fc3d_stability.py
git rm caipiao/core/strategies/random_strategy.py
git rm caipiao/core/strategies/odd_even_strategy.py
git rm caipiao/core/strategies/hot_cold_strategy.py
git rm caipiao/core/strategies/exclude_include_strategy.py
git rm caipiao/core/strategies/smart_hot_cold_strategy.py
git rm caipiao/core/strategies/missing_number_strategy.py
git rm caipiao/core/strategies/balanced_strategy.py
git rm caipiao/core/strategies/stats_strategy.py
```

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git commit -m "chore: remove obsolete shared strategy files"
```

---

## Phase 3: ML 策略隔离

### Task 9: 迁移 SSQ ML 策略

**Files:**
- Create: `caipiao/core/strategies/lotteries/ssq/ml/xgboost.py`
- Create: `caipiao/core/strategies/lotteries/ssq/ml/lightgbm.py`
- Create: `caipiao/core/strategies/lotteries/ssq/ml/catboost.py`
- Create: `caipiao/core/strategies/lotteries/ssq/ml/lstm.py`
- Create: `caipiao/core/strategies/lotteries/ssq/ml/hybrid.py`
- Create: `caipiao/core/strategies/lotteries/ssq/ml/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Delete: `caipiao/core/strategies/ml_strategy.py`
- Delete: `caipiao/core/strategies/xgboost_strategy.py`
- Delete: `caipiao/core/strategies/lightgbm_strategy.py`
- Delete: `caipiao/core/strategies/catboost_strategy.py`
- Delete: `caipiao/core/strategies/lstm_strategy.py`
- Delete: `caipiao/core/strategies/hybrid_strategy.py`
- Test: `tests/test_ssq_ml_strategies.py`

**Interfaces:**
- Produces:
  - `SSQXGBoostStrategy` (id=`ml_xgboost`)
  - `SSQLightGBMStrategy` (id=`ml_lightgbm`)
  - `SSQCatBoostStrategy` (id=`ml_catboost`)
  - `SSQLSTMStrategy` (id=`ml_lstm`)
  - `SSQHybridStrategy` (id=`ml_hybrid`)

- [ ] **Step 1: 创建 ML 策略基类或独立类**

SSQ 的 ML 策略当前由 `ml_strategy.py` 统一通过 `backend` 参数切换。隔离后，每个后端一个独立类，但可共享一个私有基类：

```python
# caipiao/core/strategies/lotteries/ssq/ml/base.py
"""SSQ ML 策略公共逻辑（文件私有）."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from .....data.models import DrawRecord
from .....ml.model_store import compute_lookback, find_current_model, new_model_path
from .....ml.predictor import MLPredictor
from ....profile import SSQ
from ....strategy import GenerationStrategy
from ...common.records import records_from_options

logger = logging.getLogger(__name__)


class _SSQMLStrategyBase(GenerationStrategy):
    """SSQ ML 策略私有基类，禁止外部直接实例化。"""

    _backend: str = "xgboost"
    _label: str = "XGBoost"
    _id: str = "ml_xgboost"
    is_ml: bool = True

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "diversity_boost": {
                "type": "int",
                "label": "多样性增强 (0-10)",
                "default": 3,
                "min": 0,
                "max": 10,
            },
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 100:
            raise ValueError(f"{self._label} 智能分析策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def _load_predictor(self, options: Dict[str, Any]) -> MLPredictor:
        records = records_from_options(options)
        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]
        lookback = compute_lookback(len(records))

        # 延迟导入模型类
        model_class = self._model_class()
        prefix = model_class.__name__.lower().replace("lottery", "").replace("model", "")
        # 保持原前缀：ml_xgboost 等
        prefix_map = {
            "xgboost": "ml_xgboost",
            "lightgbm": "ml_lightgbm",
            "catboost": "ml_catboost",
            "lstm": "ml_lstm",
            "hybrid": "ml_hybrid",
        }
        prefix = prefix_map.get(self._backend, self._backend)

        model_path = (
            find_current_model(records, lookback, prefix=prefix, options=options)
            or new_model_path(records, lookback, prefix=prefix, options=options)
        )
        predictor = MLPredictor(records, lookback=lookback, model_path=model_path, model_class=model_class)
        if not predictor.is_ready():
            predictor.train()
        return predictor

    def _model_class(self):
        if self._backend == "xgboost":
            from .....ml.model import LotteryXGBoostModel
            return LotteryXGBoostModel
        if self._backend == "lightgbm":
            from .....ml.lgbm_model import LotteryLightGBMModel
            return LotteryLightGBMModel
        if self._backend == "catboost":
            from .....ml.catboost_model import LotteryCatBoostModel
            return LotteryCatBoostModel
        if self._backend == "lstm":
            from .....ml.red_lstm import RedLSTMModel
            return RedLSTMModel
        if self._backend == "hybrid":
            from .....ml.hybrid_model import HybridModel
            return HybridModel
        raise ValueError(f"未知后端: {self._backend}")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        from .....core.ticket import Ticket

        options = options or {}
        predictor = self._load_predictor(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0
        seed = options.get("seed")
        if seed is None:
            seed = int(np.random.randint(0, 2**31))

        red_proba, blue_proba = predictor.predict()
        details = {
            "lookback": predictor.lookback,
            "diversity_boost": int(diversity * 10),
            "red_probabilities": [round(float(p), 4) for p in red_proba],
            "blue_probabilities": [round(float(p), 4) for p in blue_proba],
            "backend": self._backend,
        }
        basis = (
            f"{self._label} 智能分析策略：基于最近 {len(predictor.records)} 期历史数据训练模型，"
            f"特征回看期数 {predictor.lookback}，按预测概率加权采样。"
            f"注意：历史统计规律不能预测独立随机开奖，本策略仅作为号码筛选参考。"
        )

        tickets: List[Ticket] = []
        seen: set = set()
        seed_offset = 0
        while len(tickets) < count and seed_offset < count * 20:
            np_rng = np.random.RandomState(seed + seed_offset)
            reds, blues = predictor.recommend(
                red_count=6, blue_count=1, diversity_boost=diversity, rng=np_rng
            )
            blue = int(blues[0]) if blues else 0
            ticket = Ticket(
                profile=SSQ,
                groups={"red": sorted(reds), "blue": [blue]},
                strategy_name=self.metadata.name,
                basis=basis,
                details=details,
            )
            key = (tuple(sorted(ticket.groups["red"])), ticket.groups["blue"][0])
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)
            seed_offset += 1
        return tickets[:count]
```

- [ ] **Step 2: 实现具体 ML 策略类**

```python
# caipiao/core/strategies/lotteries/ssq/ml/xgboost.py
from __future__ import annotations

from ....strategy import StrategyMetadata
from .base import _SSQMLStrategyBase


class SSQXGBoostStrategy(_SSQMLStrategyBase):
    _backend = "xgboost"
    _label = "XGBoost"
    _id = "ml_xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="ml_xgboost",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
```

同理创建 `lightgbm.py`、`catboost.py`、`lstm.py`、`hybrid.py`。

- [ ] **Step 3: 更新 registry.py 与删除旧文件**

在 `registry.py` 的 SSQ 列表中导入并注册新的 ML 策略类。
删除旧的 `ml_strategy.py`、`xgboost_strategy.py`、`lightgbm_strategy.py`、`catboost_strategy.py`、`lstm_strategy.py`、`hybrid_strategy.py`。

- [ ] **Step 4: 编写回归测试**

```python
# tests/test_ssq_ml_strategies.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies, is_ml_strategy
from caipiao.core.strategies.lotteries.ssq.ml import (
    SSQCatBoostStrategy,
    SSQLightGBMStrategy,
    SSQXGBoostStrategy,
)
from caipiao.data.models import DrawRecord


def make_ssq_history(n=120):
    rng = __import__("random").Random(0)
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=sorted(rng.sample(range(1, 34), 6)),
            blue_ball=rng.randint(1, 16),
        )
        for i in range(n)
    ]


@pytest.mark.parametrize("cls, sid", [
    (SSQXGBoostStrategy, "ml_xgboost"),
    (SSQLightGBMStrategy, "ml_lightgbm"),
    (SSQCatBoostStrategy, "ml_catboost"),
])
def test_ssq_ml_strategy_metadata(cls, sid):
    s = cls()
    assert s.metadata.id == sid
    assert is_ml_strategy(sid) is True


@pytest.mark.parametrize("cls", [SSQXGBoostStrategy, SSQLightGBMStrategy, SSQCatBoostStrategy])
def test_ssq_ml_strategy_generates_valid(cls):
    s = cls()
    history = make_ssq_history(120)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1
```

- [ ] **Step 5: 运行测试**

Run: `python -m pytest tests/test_ssq_ml_strategies.py -v`
Expected: PASS（训练可能较慢，设置合理超时）

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/strategies/lotteries/ssq/ml/ caipiao/core/strategies/registry.py tests/test_ssq_ml_strategies.py
git rm caipiao/core/strategies/ml_strategy.py caipiao/core/strategies/xgboost_strategy.py caipiao/core/strategies/lightgbm_strategy.py caipiao/core/strategies/catboost_strategy.py caipiao/core/strategies/lstm_strategy.py caipiao/core/strategies/hybrid_strategy.py
git commit -m "refactor: isolate ssq ml strategies into per-lottery package"
```

---

### Task 10: 迁移 FC3D ML 策略

**Files:**
- Create: `caipiao/core/strategies/lotteries/fc3d/ml/xgboost.py`
- Create: `caipiao/core/strategies/lotteries/fc3d/ml/lightgbm.py`
- Create: `caipiao/core/strategies/lotteries/fc3d/ml/catboost.py`
- Create: `caipiao/core/strategies/lotteries/fc3d/ml/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Modify: `caipiao/core/strategies/lotteries/fc3d/balanced.py` 等（移除内部 ML 相关导入，改为独立 ml 包）

**Interfaces:**
- Produces:
  - `FC3DXGBoostStrategy` (id=`xgboost_3d`)
  - `FC3DLightGBMStrategy` (id=`lightgbm_3d`)
  - `FC3DCatBoostStrategy` (id=`catboost_3d`)

- [ ] **Step 1: 创建公共基类**

参考 Task 9 的 `_SSQMLStrategyBase`，在 `caipiao/core/strategies/lotteries/fc3d/ml/base.py` 创建 `_FC3DMLStrategyBase`，使用 `GenericMLPredictor`（Phase 4 再替换为 `ml.lotteries.fc3d.predictor`）。

- [ ] **Step 2: 实现具体类**

```python
# caipiao/core/strategies/lotteries/fc3d/ml/xgboost.py
from __future__ import annotations

from ....strategy import StrategyMetadata
from .base import _FC3DMLStrategyBase


class FC3DXGBoostStrategy(_FC3DMLStrategyBase):
    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_3d",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
```

同理创建 `lightgbm.py`、`catboost.py`。

- [ ] **Step 3: 从 fc3d.py 移除 ML 类**

删除 `caipiao/core/strategies/lotteries/fc3d/balanced.py` 等文件中内嵌的 ML 相关代码（如果之前拆分时不小心保留）。确保 `fc3d.py` 只剩基础策略。

- [ ] **Step 4: 更新 registry.py**

FC3D 注册表使用新的 ml 模块导入。

- [ ] **Step 5: 运行 FC3D 测试**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/strategies/lotteries/fc3d/ml/ caipiao/core/strategies/registry.py
git commit -m "refactor: isolate fc3d ml strategies"
```

---

### Task 11: 创建通用彩种 ML 策略

**Files:**
- Create: per-lottery ml strategies for QLC/KL8/DLT/PL3/PL5/QXC
- Modify: `caipiao/core/strategies/registry.py`

**Interfaces:**
- Produces per lottery: `XGBoost`, `LightGBM`, `CatBoost` strategies

- [ ] **Step 1: 建立迁移模式**

从原 `generic.py` 中的 `_GenericMLStrategy` 迁移到各彩种独立类：
- 类名带彩种前缀，如 `QLCXGBoostStrategy`。
- `metadata.id` 保持 `xgboost_qlc` 等。
- 内部使用 `GenericMLPredictor`（Phase 4 替换）。
- 固定 `profile = QLC` 等。

- [ ] **Step 2: 实现 QLC 示例**

```python
# caipiao/core/strategies/lotteries/qlc/ml/xgboost.py
from __future__ import annotations

from typing import Any, Dict

from .....profile import QLC
from .....strategy import StrategyMetadata
from .......ml.generic_predictor import GenericMLPredictor
from .......ml.model_store import compute_lookback, find_current_model, new_model_path
from ...common.records import records_from_options
from .base import _QLCMLStrategyBase


class QLCXGBoostStrategy(_QLCMLStrategyBase):
    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_qlc",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )
```

其中 `_QLCMLStrategyBase` 与 `_GenericMLStrategy` 逻辑一致，但固定 `profile = QLC`。

- [ ] **Step 3: 批量创建其余彩种 ML 策略**

对 KL8、DLT、PL3、PL5、QXC 重复 Step 2。

- [ ] **Step 4: 更新 registry.py**

补齐各彩种 ML 策略类。

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/strategies/lotteries/{qlc,kl8,dlt,pl3,pl5,qxc}/ml/ caipiao/core/strategies/registry.py
git commit -m "feat: isolate ml strategies for qlc/kl8/dlt/pl3/pl5/qxc"
```

---

## Phase 4: ML 底层隔离

### Task 12: 迁移 model_store 到 ml.common

**Files:**
- Create: `caipiao/ml/common/model_store.py`
- Modify: `caipiao/ml/model_store.py`
- Test: `tests/test_model_store.py`（已存在，更新导入）

**Interfaces:**
- Produces:
  - `caipiao.ml.common.model_store` 包含所有原有函数

- [ ] **Step 1: 复制 model_store**

将 `caipiao/ml/model_store.py` 完整复制到 `caipiao/ml/common/model_store.py`。

- [ ] **Step 2: 创建兼容别名**

```python
# caipiao/ml/model_store.py
"""模型存储兼容入口，转发到 ml.common.model_store。"""

from __future__ import annotations

from .common.model_store import (
    compute_lookback,
    data_fingerprint,
    find_current_model,
    is_model_current,
    model_dir,
    model_info,
    new_model_path,
)

__all__ = [
    "compute_lookback",
    "data_fingerprint",
    "find_current_model",
    "is_model_current",
    "model_dir",
    "model_info",
    "new_model_path",
]
```

- [ ] **Step 3: 更新测试导入**

如果 `tests/test_model_store.py` 导入的是 `caipiao.ml.model_store`，保持不变；同时新增一条测试验证 `caipiao.ml.common.model_store` 可用。

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_model_store.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/ml/common/model_store.py caipiao/ml/model_store.py tests/test_model_store.py
git commit -m "refactor: move model_store to ml.common with backward compat"
```

---

### Task 13: 创建 SSQ ML 底层

**Files:**
- Create: `caipiao/ml/lotteries/ssq/features.py`
- Create: `caipiao/ml/lotteries/ssq/predictor.py`
- Create: `caipiao/ml/lotteries/ssq/models/__init__.py`
- Create: `caipiao/ml/lotteries/ssq/models/xgboost.py` 等
- Test: `tests/ml/test_ssq_ml.py`

**Interfaces:**
- Produces:
  - `caipiao.ml.lotteries.ssq.features.build_features(records, lookback)`
  - `caipiao.ml.lotteries.ssq.predictor.SSQPredictor`

- [ ] **Step 1: 文件隔离，行为不变**

```python
# caipiao/ml/lotteries/ssq/predictor.py
"""SSQ 专属 ML 预测器（当前委托通用实现，保留隔离边界）."""

from __future__ import annotations

from ....core.profile import SSQ
from ....generic_predictor import GenericMLPredictor


class SSQPredictor(GenericMLPredictor):
    def __init__(self, records, lookback=50, model_path=None, backend="xgboost", temp_dir=None):
        super().__init__(records, profile=SSQ, lookback=lookback, model_path=model_path, backend=backend, temp_dir=temp_dir)
```

```python
# caipiao/ml/lotteries/ssq/features.py
"""SSQ 特征工程（当前委托通用实现）."""

from __future__ import annotations

from ....generic_features import build_features as _build_features
from ....generic_features import build_prediction_features as _build_prediction_features

build_features = _build_features
build_prediction_features = _build_prediction_features
```

- [ ] **Step 2: 更新 SSQ ML 策略引用**

将 `caipiao/core/strategies/lotteries/ssq/ml/base.py` 中的 `from .....ml.predictor import MLPredictor` 改为 `from .....ml.lotteries.ssq.predictor import SSQPredictor as MLPredictor`（保持接口兼容）。

- [ ] **Step 3: 运行测试**

Run: `python -m pytest tests/test_ssq_ml_strategies.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add caipiao/ml/lotteries/ssq/ caipiao/core/strategies/lotteries/ssq/ml/base.py tests/ml/test_ssq_ml.py
git commit -m "refactor: create ssq ml isolation layer"
```

---

### Task 14: 创建 FC3D 与其他彩种 ML 底层

**Files:**
- Create: `caipiao/ml/lotteries/fc3d/features.py`, `predictor.py`
- Create: `caipiao/ml/lotteries/{qlc,kl8,dlt,pl3,pl5,qxc}/features.py`, `predictor.py`
- Modify: corresponding strategy ml base classes

**Interfaces:**
- Produces per lottery: `{Lottery}Predictor`, `build_features`

- [ ] **Step 1: 每个彩种创建 predictor/features**

与 Task 13 类似，每个彩种创建 `predictor.py` 和 `features.py`，内部委托 `GenericMLPredictor` / `generic_features`。

- [ ] **Step 2: 更新策略引用**

各彩种 ML 策略基类改为从 `ml.lotteries.{key}.predictor` 导入。

- [ ] **Step 3: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add caipiao/ml/lotteries/{fc3d,qlc,kl8,dlt,pl3,pl5,qxc}/ caipiao/core/strategies/lotteries/
git commit -m "refactor: create per-lottery ml predictor isolation"
```

---

### Task 15: 下沉通用 ML 代码到 ml.common 并删除 generic_*.py

**Files:**
- Create: `caipiao/ml/common/base.py`
- Modify: `caipiao/ml/lotteries/{ssq,fc3d,...}/predictor.py`
- Delete: `caipiao/ml/generic_predictor.py`
- Delete: `caipiao/ml/generic_features.py`
- Delete: `caipiao/ml/generic_model.py`

**Interfaces:**
- Produces:
  - `caipiao.ml.common.base.LotteryGenericModel`
  - 各彩种 `predictor.py` 不再依赖 `ml.generic_*`

- [ ] **Step 1: 迁移通用模型基类**

将 `caipiao/ml/generic_model.py` 复制到 `caipiao/ml/common/base.py`。

- [ ] **Step 2: 重构 generic_predictor**

将 `GenericMLPredictor` 的核心逻辑保留在 `ml.common` 或下沉到各彩种。简化做法：
- 把 `GenericMLPredictor` 改名为 `BaseMLPredictor` 放入 `ml.common.base`。
- 各彩种 `predictor.py` 继承 `BaseMLPredictor` 并传入对应 profile。

- [ ] **Step 3: 重构 generic_features**

将 `generic_features.py` 中真正通用的特征提取逻辑放入 `ml.common.features`，各彩种 `features.py` 可在此基础上扩展。

- [ ] **Step 4: 删除旧文件**

```bash
git rm caipiao/ml/generic_predictor.py
git rm caipiao/ml/generic_features.py
git rm caipiao/ml/generic_model.py
```

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/ml/common/ caipiao/ml/lotteries/ caipiao/core/strategies/lotteries/
git commit -m "refactor: sink generic ml code into ml.common and per-lottery layers"
```

---

## Phase 5: 高级策略隔离

### Task 16: 迁移 SSQ 高级策略

**Files:**
- Create: `caipiao/core/strategies/advanced/common/base.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/random_forest.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/bayesian.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/markov.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/trend.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/periodic.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/ensemble.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/correlation.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/transformer.py`
- Create: `caipiao/core/strategies/advanced/lotteries/ssq/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Delete: old advanced files
- Test: `tests/test_ssq_advanced_strategies.py`

**Interfaces:**
- Produces:
  - `SSQRandomForestStrategy`, `SSQBayesianStrategy`, ..., `SSQTransformerStrategy`

- [ ] **Step 1: 精简高级策略公共基类**

```python
# caipiao/core/strategies/advanced/common/base.py
"""高级策略公共接口（仅含真正通用工具）."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .....data.models import DrawRecord
from ....strategy import GenerationStrategy, StrategyMetadata


class AdvancedStrategy(GenerationStrategy):
    """高级策略基类：只提供历史记录处理和 metadata 模板。"""

    _id: str = ""
    _name: str = ""
    _description: str = ""
    is_ml: bool = False

    def _records_from_options(self, options: Dict[str, Any]) -> List[DrawRecord]:
        from ...common.records import records_from_options
        return records_from_options(options)

    def _get_history(self, options: Dict[str, Any]) -> List[DrawRecord]:
        history = options.get("history", [])
        history_count = options.get("history_count", -1)
        records = self._records_from_options(options)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]
        return records

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id=self._id,
            name=self._name,
            description=self._description,
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        history = options.get("history", [])
        if len(history) < 30:
            raise ValueError(f"{self.metadata.name} 策略需要至少 30 期历史数据")
```

- [ ] **Step 2: 迁移 RandomForest 作为示例**

将 `caipiao/core/strategies/advanced/random_forest_strategy.py` 中 SSQ 相关逻辑提取到 `caipiao/core/strategies/advanced/lotteries/ssq/random_forest.py`，类名 `SSQRandomForestStrategy`，删除 3D/通用分支。

- [ ] **Step 3: 迁移其余高级策略**

同理迁移 bayesian、markov、trend、periodic、ensemble、correlation、transformer。

- [ ] **Step 4: 更新 registry.py 与删除旧文件**

SSQ 注册表使用新的 advanced 模块导入。
删除 `advanced/base.py`、`random_forest_strategy.py` 等旧文件。

- [ ] **Step 5: 编写回归测试**

```python
# tests/test_ssq_advanced_strategies.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import SSQ
from caipiao.core.strategies import build_strategies, is_ml_strategy
from caipiao.core.strategies.advanced.lotteries.ssq.random_forest import SSQRandomForestStrategy
from caipiao.data.models import DrawRecord


def make_ssq_history(n=50):
    rng = __import__("random").Random(0)
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            red_balls=sorted(rng.sample(range(1, 34), 6)),
            blue_ball=rng.randint(1, 16),
        )
        for i in range(n)
    ]


def test_ssq_random_forest_metadata():
    s = SSQRandomForestStrategy()
    assert s.metadata.id == "random_forest"
    assert is_ml_strategy("random_forest") is True


def test_ssq_random_forest_generates_valid():
    s = SSQRandomForestStrategy()
    history = make_ssq_history(50)
    tickets = s.generate(count=2, options={"history": history})
    assert len(tickets) == 2
    for t in tickets:
        assert t.profile.key == "ssq"
        assert len(t.groups["red"]) == 6
        assert len(t.groups["blue"]) == 1


def test_build_strategies_includes_advanced():
    strategies = build_strategies(SSQ)
    ids = {s.metadata.id for s in strategies}
    assert "random_forest" in ids
    assert "transformer" in ids
```

- [ ] **Step 6: 运行测试**

Run: `python -m pytest tests/test_ssq_advanced_strategies.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add caipiao/core/strategies/advanced/ caipiao/core/strategies/registry.py tests/test_ssq_advanced_strategies.py
git rm caipiao/core/strategies/advanced/base.py caipiao/core/strategies/advanced/random_forest_strategy.py caipiao/core/strategies/advanced/bayesian_strategy.py caipiao/core/strategies/advanced/markov_strategy.py caipiao/core/strategies/advanced/trend_strategy.py caipiao/core/strategies/advanced/periodic_strategy.py caipiao/core/strategies/advanced/ensemble_strategy.py caipiao/core/strategies/advanced/correlation_strategy.py caipiao/core/strategies/advanced/transformer_strategy.py
git commit -m "refactor: isolate ssq advanced strategies"
```

---

### Task 17: 创建其他彩种高级策略占位与清理

**Files:**
- Create: placeholder files in `advanced/lotteries/{fc3d,qlc,kl8,dlt,pl3,pl5,qxc}/`
- Modify: `caipiao/core/strategies/advanced/__init__.py`

**Interfaces:**
- 当前其他彩种暂无高级策略需求，保持为空包即可。

- [ ] **Step 1: 更新 advanced __init__.py**

```python
# caipiao/core/strategies/advanced/__init__.py
"""高级预测策略子包（按彩种隔离）."""

from .lotteries.ssq.bayesian import SSQBayesianStrategy
from .lotteries.ssq.correlation import SSQCorrelationMiningStrategy
from .lotteries.ssq.ensemble import SSQEnsembleVotingStrategy
from .lotteries.ssq.markov import SSQMarkovChainStrategy
from .lotteries.ssq.periodic import SSQPeriodicAnalysisStrategy
from .lotteries.ssq.random_forest import SSQRandomForestStrategy
from .lotteries.ssq.trend import SSQTrendAnalysisStrategy
from .lotteries.ssq.transformer import SSQTransformerStrategy

__all__ = [
    "SSQRandomForestStrategy",
    "SSQBayesianStrategy",
    "SSQMarkovChainStrategy",
    "SSQTrendAnalysisStrategy",
    "SSQPeriodicAnalysisStrategy",
    "SSQEnsembleVotingStrategy",
    "SSQCorrelationMiningStrategy",
    "SSQTransformerStrategy",
]
```

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add caipiao/core/strategies/advanced/ caipiao/core/strategies/registry.py
git commit -m "chore: finalize advanced strategy package isolation"
```

---

## 最终回归与收尾

### Task 18: 全量回归测试与清理

**Files:**
- All

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -q`
Expected: 通过数不低于重构前（当前 212 passed, 4 skipped）

- [ ] **Step 2: 检查未引用旧文件**

Run: `git status --short`
确认所有旧策略文件已删除，新文件已纳入版本控制。

- [ ] **Step 3: 运行 smoke test / UI 启动验证**

Run: `python -c "from caipiao.core.strategies import build_strategies; from caipiao.core.profile import list_profiles; [print(p.key, [s.metadata.id for s in build_strategies(p)]) for p in list_profiles()]"`
Expected: 8 个彩种均输出策略 ID 列表，无异常。

- [ ] **Step 4: 提交最终整理**

```bash
git add -A
git commit -m "refactor: complete per-lottery strategy and ml isolation"
```

---

## Self-Review

### 1. Spec coverage

| Spec 要求 | 对应任务 |
|---|---|
| 彩种隔离 | Task 4-7, Task 11, Task 16-17 |
| 策略隔离 | Task 4-7, Task 9-11, Task 16-17 |
| ML 底层隔离 | Task 12-15 |
| 入口稳定 | Task 3 |
| 测试保障 | 每个 Task 都包含测试步骤 |
| ID/名称/schema 不变 | 所有迁移步骤明确说明 |

### 2. Placeholder scan

- 无 "TBD"/"TODO"。
- 无 "add appropriate error handling" 等模糊描述。
- 每个迁移任务都给出了代表代码示例。
- 文件路径和类名全部具体化。

### 3. Type consistency

- `build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]` 全计划一致。
- `GenerationStrategy.generate(count, options) -> List[Ticket]` 全计划一致。
- `SSQRandomStrategy` 等类名与 `metadata.id` 对应关系明确。

### 4. 已知限制

- Task 7/Task 11 涉及大量文件（6 个彩种 × 7 个策略/3 个 ML 策略），实施时可考虑使用脚本生成骨架，但必须人工审查逻辑。
- Phase 4 的 ML 底层下沉可能涉及较多接口调整，如果一次改动过大，可拆分为两次提交：先隔离文件，再下沉通用代码。
- 当前 `ml.predictor.MLPredictor` 与 `ml.model.LotteryXGBoostModel` 等保留不变，仅改变消费侧导入路径；真正重写特征工程/模型结构属于后续优化，不在本次范围。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-lottery-strategy-isolation-plan.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
