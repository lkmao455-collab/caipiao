# 福彩3D「分散随机」策略实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `docs/superpowers/specs/2026-07-10-fc3d-dispersed-random-design.md` 中定义的福彩3D「分散随机」策略，不依赖历史数据，通过局部搜索使输出号码在三维数字空间中尽量分散，并在UI策略列表中可选。

**Architecture：** 新建独立策略文件 `caipiao/core/strategies/lotteries/fc3d/dispersed_random.py`，实现 `FC3DDispersedRandomStrategy` 类；通过注册表自动暴露给UI；使用TDD，先写测试再实现。

**Tech Stack：** Python 3.12、pytest、项目现有 `GenerationStrategy` / `Ticket` / `FC3D_PROFILE`。

## Global Constraints

- 不依赖任何历史数据；`history` 字段完全可选。
- 不引用、不继承任何现有 3D 策略的实现代码（仅使用 `_base.py` 中的 `FC3D_PROFILE` 和 `get_profile` 等基础设施）。
- 策略 ID 为 `dispersed_random_3d`，名称为 `分散随机`。
- 默认 `dedup=True`。
- 所有新增代码必须附带测试。
- 提交前全量测试通过。

---

## File Structure

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `caipiao/core/strategies/lotteries/fc3d/dispersed_random.py` | 策略主实现 | 新建 |
| `caipiao/core/strategies/lotteries/fc3d/__init__.py` | 导出策略类 | 修改 |
| `caipiao/core/strategies/registry.py` | 注册到 3D 策略列表 | 修改 |
| `tests/test_fc3d_dispersed_random.py` | 单元测试 | 新建 |

---

### Task 1: 实现 FC3DDispersedRandomStrategy

**Files:**
- Create: `caipiao/core/strategies/lotteries/fc3d/dispersed_random.py`
- Test: `tests/test_fc3d_dispersed_random.py`（临时 smoke test，本任务用）

**Interfaces:**
- Consumes: `FC3D_PROFILE`, `GenerationStrategy`, `StrategyMetadata`, `Ticket`
- Produces: `FC3DDispersedRandomStrategy.generate(count, options) -> List[Ticket]`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_fc3d_dispersed_random.py
def test_dispersed_random_strategy_exists():
    from caipiao.core.strategies.lotteries.fc3d.dispersed_random import FC3DDispersedRandomStrategy
    strategy = FC3DDispersedRandomStrategy()
    assert strategy.metadata.id == "dispersed_random_3d"
    tickets = strategy.generate(count=5, options={})
    assert len(tickets) == 5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_dispersed_random.py::test_dispersed_random_strategy_exists -v
```

Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 实现策略类**

```python
# caipiao/core/strategies/lotteries/fc3d/dispersed_random.py
"""福彩3D分散随机策略.

完全随机生成候选号码，并通过局部搜索使输出在三维数字空间中尽量分散。
本模块独立实现，不依赖历史数据，也不复用其他策略的生成逻辑。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from ....strategy import GenerationStrategy, StrategyMetadata
from ....ticket import Ticket
from ._base import FC3D_PROFILE


class FC3DDispersedRandomStrategy(GenerationStrategy):
    """3D分散随机：不依赖历史，通过局部搜索生成空间分散的随机号码."""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="dispersed_random_3d",
            name="分散随机",
            description="完全随机生成候选号码，并通过局部搜索使输出在三维数字空间中尽量分散。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "candidate_multiplier": {
                "type": "int",
                "label": "候选池倍数",
                "default": 50,
                "min": 10,
                "max": 200,
                "tooltip": "候选池大小 = 生成数量 × 倍数。倍数越大，局部搜索空间越大，分散性越好。",
            },
            "max_iterations": {
                "type": "int",
                "label": "最大迭代次数",
                "default": 100,
                "min": 10,
                "max": 1000,
                "tooltip": "局部搜索最大轮数。",
            },
            "dedup": {
                "type": "bool",
                "label": "号码去重",
                "default": True,
                "tooltip": "开启后去除号码集合重复，例如123和132视为相同号码。",
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
        # 本策略不需要历史数据
        pass

    @staticmethod
    def _euclidean_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    @staticmethod
    def _min_pairwise_distance(selected: List[Tuple[int, int, int]]) -> float:
        n = len(selected)
        if n < 2:
            return float("inf")
        min_dist = float("inf")
        for i in range(n):
            for j in range(i + 1, n):
                d = FC3DDispersedRandomStrategy._euclidean_distance(selected[i], selected[j])
                if d < min_dist:
                    min_dist = d
        return min_dist

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        self.validate_options(options)

        candidate_multiplier = int(options.get("candidate_multiplier", 50))
        max_iterations = int(options.get("max_iterations", 100))
        dedup = bool(options.get("dedup", True))
        seed = options.get("seed")

        rng = random.Random(seed) if seed is not None else random.Random()

        # 1. 生成候选池
        pool_size = max(count * candidate_multiplier, count * 2)
        candidates: List[Tuple[int, int, int]] = [
            (rng.randint(0, 9), rng.randint(0, 9), rng.randint(0, 9))
            for _ in range(pool_size)
        ]

        # 2. 去重（按组选 sorted tuple）
        if dedup:
            seen: Set[Tuple[int, int, int]] = set()
            unique: List[Tuple[int, int, int]] = []
            for nums in candidates:
                key = tuple(sorted(nums))
                if key not in seen:
                    seen.add(key)
                    unique.append(nums)
            candidates = unique
            if len(candidates) < count:
                raise ValueError(
                    f"去重后候选池不足（{len(candidates)} < {count}），"
                    f"请降低生成数量、增大 candidate_multiplier 或关闭去重。"
                )
            # 去重模式下总数不能超过 220（组选上限）
            if count > 220:
                raise ValueError(
                    "去重模式下最多生成 220 组（3D组选组合上限）。"
                )

        # 3. Greedy Farthest Point 初始化
        selected: List[Tuple[int, int, int]] = [candidates[0]]
        remaining = candidates[1:]

        while len(selected) < count and remaining:
            best_idx = 0
            best_min_dist = -1.0
            for idx, cand in enumerate(remaining):
                min_dist = min(
                    self._euclidean_distance(cand, s) for s in selected
                )
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = idx
            selected.append(remaining.pop(best_idx))

        # 4. 局部搜索：单次交换优化最小 pairwise 距离
        current_min = self._min_pairwise_distance(selected)
        for _ in range(max_iterations):
            improved = False
            for sel_idx in range(len(selected)):
                for cand_idx, cand in enumerate(remaining):
                    # 尝试交换
                    original = selected[sel_idx]
                    selected[sel_idx] = cand
                    new_min = self._min_pairwise_distance(selected)
                    if new_min > current_min:
                        # 接受交换
                        remaining[cand_idx] = original
                        current_min = new_min
                        improved = True
                        break
                    else:
                        selected[sel_idx] = original
                if improved:
                    break
            if not improved:
                break

        # 5. 构建 basis 与 Ticket
        basis = (
            f"分散随机策略：生成 {count} 注，候选池倍数={candidate_multiplier}，"
            f"最大迭代={max_iterations}，去重={dedup}。"
        )
        if seed is not None:
            basis += f" 随机种子：{seed}。"
        basis += "基于局部搜索使号码在三维数字空间中尽量分散。"

        tickets: List[Ticket] = []
        for nums in selected:
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": list(nums)},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
```

- [ ] **Step 4: 运行测试确认通过**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_dispersed_random.py::test_dispersed_random_strategy_exists -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_fc3d_dispersed_random.py caipiao/core/strategies/lotteries/fc3d/dispersed_random.py
git commit -m "feat(fc3d): add dispersed random strategy"
```

---

### Task 2: 注册策略到 UI

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/__init__.py`
- Modify: `caipiao/core/strategies/registry.py`
- Test: `tests/test_strategy_factory.py`

**Interfaces:**
- Consumes: `FC3DDispersedRandomStrategy`
- Produces: 注册表 `3d` 列表中包含 `dispersed_random_3d`

- [ ] **Step 1: 导出策略类**

```python
# caipiao/core/strategies/lotteries/fc3d/__init__.py
from .dispersed_random import FC3DDispersedRandomStrategy

__all__ = [
    # ... 保留原有项 ...
    "FC3DDispersedRandomStrategy",
]
```

- [ ] **Step 2: 注册到策略表**

```python
# caipiao/core/strategies/registry.py
from .lotteries.fc3d import dispersed_random as fc3d_dispersed_random

STRATEGY_REGISTRY["3d"] = [
    # ... 保留原有项 ...
    fc3d_dispersed_random.FC3DDispersedRandomStrategy,
]
```

- [ ] **Step 3: 更新工厂测试预期**

```python
# tests/test_strategy_factory.py 中 3d 期望 ID 列表加入 "dispersed_random_3d"
"3d": {
    "random_3d", "odd_even_3d", "hot_cold_3d", "exclude_include_3d",
    "smart_hot_cold_3d", "missing_number_3d", "balanced_3d",
    "ensemble_v2_3d", "dispersed_random_3d",  # 新增
    # ... 其他 ID ...
}
```

- [ ] **Step 4: 运行注册表测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_strategy_factory.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/lotteries/fc3d/__init__.py caipiao/core/strategies/registry.py tests/test_strategy_factory.py
git commit -m "feat(fc3d): register dispersed random strategy in UI"
```

---

### Task 3: 完善分散随机策略单元测试

**Files:**
- Create/Modify: `tests/test_fc3d_dispersed_random.py`

**Interfaces:**
- Consumes: `FC3DDispersedRandomStrategy.generate(count, options)`

- [ ] **Step 1: 编写完整测试**

```python
# tests/test_fc3d_dispersed_random.py
from __future__ import annotations

import pytest

from caipiao.core.strategies.lotteries.fc3d.dispersed_random import (
    FC3DDispersedRandomStrategy,
)


@pytest.fixture
def strategy():
    return FC3DDispersedRandomStrategy()


def test_metadata(strategy):
    assert strategy.metadata.id == "dispersed_random_3d"
    assert strategy.metadata.name == "分散随机"


def test_generate_without_history(strategy):
    tickets = strategy.generate(count=20, options={})
    assert len(tickets) == 20
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_dedup_removes_group_duplicates(strategy):
    tickets = strategy.generate(count=50, options={"dedup": True, "seed": 1})
    keys = {tuple(sorted(t.groups["pos"])) for t in tickets}
    assert len(keys) == len(tickets)


def test_dedup_allows_more_than_220_raises(strategy):
    with pytest.raises(ValueError):
        strategy.generate(count=300, options={"dedup": True})


def test_seed_deterministic(strategy):
    t1 = strategy.generate(count=20, options={"seed": 42})
    t2 = strategy.generate(count=20, options={"seed": 42})
    assert [t.groups["pos"] for t in t1] == [t.groups["pos"] for t in t2]


def test_dispersion_positive(strategy):
    tickets = strategy.generate(count=20, options={"seed": 123})
    nums = [tuple(t.groups["pos"]) for t in tickets]
    min_dist = float("inf")
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            d = FC3DDispersedRandomStrategy._euclidean_distance(nums[i], nums[j])
            if d < min_dist:
                min_dist = d
    assert min_dist > 0
```

- [ ] **Step 2: 运行全部新增测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/test_fc3d_dispersed_random.py -v
```

Expected: 6 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_fc3d_dispersed_random.py
git commit -m "test(fc3d): add dispersed random strategy tests"
```

---

### Task 4: 全量回归测试

**Files:**
- All existing tests

- [ ] **Step 1: 运行全量测试**

```bash
E:/caipiao/venv/Scripts/python.exe -m pytest tests/ -q
```

- [ ] **Step 2: 确认结果**

Expected: 全绿（例如 `586 passed, 4 skipped` 或更多，无 failure）

- [ ] **Step 3: 提交（如无变更则跳过）**

若全量测试未触发代码修改，本任务无需额外提交。

---

## Self-Review

**Spec coverage：**
- 独立策略文件：Task 1
- 不依赖历史：`validate_options` 为空，生成时不读取 history：Task 1
- 局部搜索 + 欧氏距离：Task 1
- 配置项 candidate_multiplier / max_iterations / dedup / seed：Task 1
- UI 注册：Task 2
- 测试：Task 3

无遗漏。

**Placeholder scan：**
- 无 "TBD" / "TODO" / "implement later"。
- 所有代码块完整，包含实际实现。

**Type consistency：**
- `FC3DDispersedRandomStrategy.generate(count, options)` 签名与 `GenerationStrategy` 一致。
- 注册表中使用的类名与 `__init__.py` 导出一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-10-fc3d-dispersed-random.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
