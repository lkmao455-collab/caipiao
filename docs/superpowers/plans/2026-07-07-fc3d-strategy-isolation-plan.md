# 福彩3D策略独立与按位优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将福彩3D的全部生成策略从 `generic.py` 中独立出来，放入专属模块 `caipiao/core/strategies/fc3d.py` 与工具模块 `fc3d_utils.py`，并针对3D按位、可重复特性优化历史均衡策略，确保其它彩种策略改动不再影响3D。

**Architecture:** 新增 `fc3d_utils.py` 提供3D专用统计函数；新增 `fc3d.py` 实现10个3D专属策略类；改造 `generic.py` 的 `build_strategies()` 对 `profile.key == "3d"` 路由到3D模块；保持策略ID/名称/schema不变，UI与回测无需改动。

**Tech Stack:** Python 3.10+, random, itertools, pytest

## Global Constraints

- 策略ID必须保持不变：`random_3d`、`odd_even_3d`、`hot_cold_3d`、`exclude_include_3d`、`smart_hot_cold_3d`、`missing_number_3d`、`balanced_3d`、`xgboost_3d`、`lightgbm_3d`、`catboost_3d`。
- 策略中文名称和 `get_config_schema()` 字段名/类型/默认值与现有通用版一致。
- `build_strategies()`、`needs_history()`、`is_ml_strategy()` 的签名与行为不变。
- 3D按位结果必须保留原始顺序，禁止 `sorted()`。
- 所有新增/修改代码必须有对应测试覆盖。
- 不改动双色球老策略、不改动其它通用彩种策略实现、不改动 `LotteryProfile`。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `caipiao/core/strategies/fc3d_utils.py` | 3D专用统计工具：按位频率、和尾、跨度、012路、形态比例、平滑权重 |
| `caipiao/core/strategies/fc3d.py` | 10个3D专属策略类 + `build_fc3d_strategies()` |
| `caipiao/core/strategies/generic.py` | 删除3D相关实现，`build_strategies()` 增加3D路由 |
| `tests/test_fc3d_utils.py` | `fc3d_utils.py` 单元测试 |
| `tests/test_fc3d_strategies.py` | 3D策略综合测试 |

---

### Task 1: 3D统计工具函数

**Files:**
- Create: `caipiao/core/strategies/fc3d_utils.py`
- Test: `tests/test_fc3d_utils.py`

**Interfaces:**
- Produces:
  - `positional_frequency(records, lookback=None) -> Dict[int, Dict[int, int]]`
  - `positional_weights(records, lookback=100, smoothing=1.0) -> Dict[int, List[float]]`
  - `sum_tail_statistics(records, lookback=100) -> Dict[str, float]`
  - `span_statistics(records, lookback=100) -> Dict[str, float]`
  - `road_012_statistics(records, lookback=100) -> Dict[int, List[float]]`
  - `shape_ratio(records, lookback=100) -> Dict[str, float]`
  - `fc3d_bet_type(numbers: List[int]) -> str`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_fc3d_utils.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.data.models import DrawRecord
from caipiao.core.strategies.fc3d_utils import (
    positional_frequency,
    positional_weights,
    sum_tail_statistics,
    span_statistics,
    road_012_statistics,
    shape_ratio,
    fc3d_bet_type,
)


def make_records():
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(30)
    ]


def test_positional_frequency():
    records = make_records()
    freq = positional_frequency(records, lookback=10)
    assert 0 in freq and 1 in freq and 2 in freq
    # 第 0 位最近 10 期是 20,21,...,29 的 mod 10，即 0,1,2,...,9,0
    assert sum(freq[0].values()) == 10


def test_positional_weights_smoothing():
    records = make_records()
    weights = positional_weights(records, lookback=10, smoothing=1.0)
    assert len(weights) == 3
    assert len(weights[0]) == 10
    assert all(w > 0 for w in weights[0])


def test_sum_tail_statistics():
    records = make_records()
    stats = sum_tail_statistics(records, lookback=10)
    assert "min" in stats and "max" in stats and "avg" in stats


def test_span_statistics():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 2, 3]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [0, 5, 9]}),
    ]
    stats = span_statistics(records)
    assert stats["avg"] == (2 + 9) / 2


def test_road_012_statistics():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [0, 1, 2]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [3, 4, 5]}),
    ]
    stats = road_012_statistics(records)
    assert len(stats) == 3  # 3个位置
    for pos_stats in stats.values():
        assert sum(pos_stats) == pytest.approx(1.0)


def test_shape_ratio():
    records = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [1, 1, 1]}),  # 豹子
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [1, 1, 2]}),  # 组三
        DrawRecord("2024003", datetime(2024, 1, 3), profile="3d", groups={"pos": [1, 2, 3]}),  # 组六
    ]
    ratio = shape_ratio(records)
    assert ratio["leopard"] == pytest.approx(1 / 3)
    assert ratio["group3"] == pytest.approx(1 / 3)
    assert ratio["group6"] == pytest.approx(1 / 3)


def test_fc3d_bet_type():
    assert fc3d_bet_type([1, 1, 1]) == "豹子号"
    assert fc3d_bet_type([1, 1, 2]) == "组选3"
    assert fc3d_bet_type([1, 2, 3]) == "组选6"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_utils.py -v`
Expected: 8 FAIL（`caipiao.core.strategies.fc3d_utils` 未定义）

- [ ] **Step 3: 实现统计工具函数**

```python
# caipiao/core/strategies/fc3d_utils.py
"""福彩3D专用统计工具函数."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from ..data.models import DrawRecord


POSITION_COUNT = 3
DIGIT_POOL = list(range(10))


def _slice_records(records: List[DrawRecord], lookback: Optional[int]) -> List[DrawRecord]:
    sorted_records = sorted(records, key=lambda r: r.draw_date)
    if lookback is None or lookback >= len(sorted_records):
        return sorted_records
    if lookback <= 0:
        return []
    return sorted_records[-lookback:]


def positional_frequency(
    records: List[DrawRecord], lookback: Optional[int] = None
) -> Dict[int, Dict[int, int]]:
    """返回按位频率：{position: {digit: count}}。"""
    sliced = _slice_records(records, lookback)
    result: Dict[int, Counter] = {i: Counter() for i in range(POSITION_COUNT)}
    for record in sliced:
        nums = record.groups.get("pos", [])
        for idx, n in enumerate(nums[:POSITION_COUNT]):
            if n in DIGIT_POOL:
                result[idx][n] += 1
    return {idx: dict(counter) for idx, counter in result.items()}


def positional_weights(
    records: List[DrawRecord], lookback: int = 100, smoothing: float = 1.0
) -> Dict[int, List[float]]:
    """带拉普拉斯平滑的按位权重。"""
    freq = positional_frequency(records, lookback)
    weights: Dict[int, List[float]] = {}
    for pos in range(POSITION_COUNT):
        pos_freq = freq.get(pos, {})
        total = sum(pos_freq.values()) + smoothing * len(DIGIT_POOL)
        weights[pos] = [
            (pos_freq.get(d, 0) + smoothing) / total for d in DIGIT_POOL
        ]
    return weights


def sum_tail_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """和尾（和值 mod 10）统计。"""
    sliced = _slice_records(records, lookback)
    tails = [sum(r.groups.get("pos", [])[:POSITION_COUNT]) % 10 for r in sliced]
    if not tails:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    tails.sort()
    n = len(tails)
    median = tails[n // 2] if n % 2 else (tails[n // 2 - 1] + tails[n // 2]) / 2
    return {"min": min(tails), "max": max(tails), "avg": sum(tails) / n, "median": median}


def span_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """跨度（最大-最小）统计。"""
    sliced = _slice_records(records, lookback)
    spans = []
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        if nums:
            spans.append(max(nums) - min(nums))
    if not spans:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    spans.sort()
    n = len(spans)
    median = spans[n // 2] if n % 2 else (spans[n // 2 - 1] + spans[n // 2]) / 2
    return {"min": min(spans), "max": max(spans), "avg": sum(spans) / n, "median": median}


def road_012_statistics(
    records: List[DrawRecord], lookback: int = 100
) -> Dict[int, List[float]]:
    """每位012路（mod 3）比例：{position: [p0, p1, p2]}。"""
    sliced = _slice_records(records, lookback)
    counts: Dict[int, List[int]] = {i: [0, 0, 0] for i in range(POSITION_COUNT)}
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        for idx, n in enumerate(nums):
            counts[idx][n % 3] += 1
    result: Dict[int, List[float]] = {}
    for pos, cnts in counts.items():
        total = sum(cnts)
        result[pos] = [c / total if total else 1 / 3 for c in cnts]
    return result


def fc3d_bet_type(numbers: List[int]) -> str:
    """判断3D号码形态：豹子号、组选3、组选6。"""
    if len(numbers) != POSITION_COUNT:
        return "未知"
    unique = len(set(numbers))
    if unique == 1:
        return "豹子号"
    if unique == 2:
        return "组选3"
    return "组选6"


def shape_ratio(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """历史形态比例：豹子/组三/组六。"""
    sliced = _slice_records(records, lookback)
    total = len(sliced)
    if total == 0:
        return {"leopard": 1 / 3, "group3": 1 / 3, "group6": 1 / 3}
    counts = {"leopard": 0, "group3": 0, "group6": 0}
    for record in sliced:
        nums = record.groups.get("pos", [])[:POSITION_COUNT]
        bet_type = fc3d_bet_type(nums)
        if bet_type == "豹子号":
            counts["leopard"] += 1
        elif bet_type == "组选3":
            counts["group3"] += 1
        else:
            counts["group6"] += 1
    return {k: v / total for k, v in counts.items()}


def overall_odd_even_ratio(records: List[DrawRecord], lookback: int = 100) -> Tuple[float, float]:
    """整体奇偶比例（3D 9个数字中奇数判定）。"""
    sliced = _slice_records(records, lookback)
    odd = even = 0
    for record in sliced:
        for n in record.groups.get("pos", [])[:POSITION_COUNT]:
            if n % 2 == 1:
                odd += 1
            else:
                even += 1
    total = odd + even
    if total == 0:
        return 0.5, 0.5
    return odd / total, even / total


def overall_high_low_ratio(
    records: List[DrawRecord], lookback: int = 100, border: int = 5
) -> Tuple[float, float]:
    """整体大小比例，>= border 为大号。"""
    sliced = _slice_records(records, lookback)
    high = low = 0
    for record in sliced:
        for n in record.groups.get("pos", [])[:POSITION_COUNT]:
            if n >= border:
                high += 1
            else:
                low += 1
    total = high + low
    if total == 0:
        return 0.5, 0.5
    return high / total, low / total


def sum_statistics(records: List[DrawRecord], lookback: int = 100) -> Dict[str, float]:
    """和值统计。"""
    sliced = _slice_records(records, lookback)
    sums = [sum(r.groups.get("pos", [])[:POSITION_COUNT]) for r in sliced]
    if not sums:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    sums.sort()
    n = len(sums)
    median = sums[n // 2] if n % 2 else (sums[n // 2 - 1] + sums[n // 2]) / 2
    return {"min": min(sums), "max": max(sums), "avg": sum(sums) / n, "median": median}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_utils.py -v`
Expected: 8 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d_utils.py tests/test_fc3d_utils.py
git commit -m "feat: add 3D-specific statistical utilities"
```

---

### Task 2: 3D基础策略

**Files:**
- Create: `caipiao/core/strategies/fc3d.py`（初始版本，后续任务继续追加）
- Test: `tests/test_fc3d_strategies.py`（初始版本）

**Interfaces:**
- Produces:
  - `FC3DRandomStrategy` (id=`random_3d`)
  - `FC3DOddEvenStrategy` (id=`odd_even_3d`)
  - `FC3DExcludeIncludeStrategy` (id=`exclude_include_3d`)

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_fc3d_strategies.py
from datetime import datetime, timedelta

import pytest

from caipiao.core.profile import get_profile
from caipiao.core.strategies.fc3d import (
    FC3DRandomStrategy,
    FC3DOddEvenStrategy,
    FC3DExcludeIncludeStrategy,
)
from caipiao.data.models import DrawRecord


def make_history(n=30):
    return [
        DrawRecord(
            f"2024{i:03d}",
            datetime(2024, 1, 1) + timedelta(days=i),
            profile="3d",
            groups={"pos": [(i + j) % 10 for j in range(3)]},
        )
        for i in range(n)
    ]


def test_random_3d_generates_three_digits():
    strategy = FC3DRandomStrategy()
    tickets = strategy.generate(count=5)
    assert len(tickets) == 5
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_random_3d_seed_reproducible():
    strategy = FC3DRandomStrategy()
    t1 = strategy.generate(count=1, options={"seed": 42})[0].groups["pos"]
    t2 = strategy.generate(count=1, options={"seed": 42})[0].groups["pos"]
    assert t1 == t2


def test_odd_even_3d_respects_overall_count():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"odd_count": 2})
    for t in tickets:
        odd = sum(1 for n in t.groups["pos"] if n % 2 == 1)
        assert odd == 2


def test_odd_even_3d_positional_mode():
    strategy = FC3DOddEvenStrategy()
    tickets = strategy.generate(count=5, options={"positional": [1, 0, 1]})
    for t in tickets:
        assert t.groups["pos"][0] % 2 == 1
        assert t.groups["pos"][1] % 2 == 0
        assert t.groups["pos"][2] % 2 == 1


def test_exclude_include_3d_positional():
    strategy = FC3DExcludeIncludeStrategy()
    tickets = strategy.generate(
        count=5,
        options={
            "include_pos": [[1], [], [5]],
            "exclude_pos": [[], [2, 3], []],
        },
    )
    for t in tickets:
        assert t.groups["pos"][0] == 1
        assert t.groups["pos"][1] not in (2, 3)
        assert t.groups["pos"][2] == 5


def test_exclude_include_3d_no_sort():
    strategy = FC3DExcludeIncludeStrategy()
    ticket = strategy.generate(
        count=1,
        options={"include_pos": [[9], [], [0]]},
    )[0]
    assert ticket.groups["pos"] == [9, 1, 0]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 6 FAIL

- [ ] **Step 3: 实现基础策略**

```python
# caipiao/core/strategies/fc3d.py（初始部分）
"""福彩3D专属生成策略."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ..profile import get_profile
from ..strategy import GenerationStrategy, StrategyMetadata
from ..ticket import Ticket
from ...data.models import DrawRecord


FC3D_PROFILE = get_profile("3d")


def _records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    history = options.get("history", []) or []
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


def _make_rng(options: Dict[str, Any]) -> random.Random:
    seed = options.get("seed")
    return random.Random(seed) if seed is not None else random.Random()


class FC3DRandomStrategy(GenerationStrategy):
    """3D完全随机：每位独立0-9。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="random_3d",
            name="完全随机",
            description="在福彩3D的百、十、个位上分别独立随机生成0-9数字。",
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
        rng = _make_rng(options)
        basis = "完全随机策略：百、十、个位分别独立随机生成0-9数字。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"
        tickets: List[Ticket] = []
        for _ in range(count):
            groups = {"pos": [rng.randint(0, 9) for _ in range(3)]}
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups=groups, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DOddEvenStrategy(GenerationStrategy):
    """3D奇偶均衡：控制整体奇数个数或按位奇偶。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="odd_even_3d",
            name="奇偶均衡",
            description="控制福彩3D号码中奇数和偶数的比例。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "odd_count": {
                "type": "int",
                "label": "奇数个数",
                "default": 1,
                "min": 0,
                "max": 3,
            },
            "positional": {
                "type": "list_int",
                "label": "按位奇偶（可选）",
                "default": [],
                "min": 0,
                "max": 1,
                "tooltip": "长度为3的列表，1表示奇数，0表示偶数，空则使用整体奇数个数。",
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
        positional = options.get("positional", [])
        if positional and len(positional) != 3:
            raise ValueError("按位奇偶必须提供3个值")
        if positional and any(p not in (0, 1) for p in positional):
            raise ValueError("按位奇偶值必须是0或1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        positional = options.get("positional", [])
        odd_count = int(options.get("odd_count", 1))

        odd_pool = [1, 3, 5, 7, 9]
        even_pool = [0, 2, 4, 6, 8]

        if positional:
            basis = f"奇偶均衡策略：按位控制奇偶为 {positional}。"
        else:
            basis = f"奇偶均衡策略：整体包含 {odd_count} 个奇数、{3 - odd_count} 个偶数。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            if positional:
                result = [
                    rng.choice(odd_pool if p == 1 else even_pool)
                    for p in positional
                ]
            else:
                result = sorted(rng.sample(odd_pool, odd_count) + rng.sample(even_pool, 3 - odd_count))
                # 整体模式仍排序以保持与原通用策略行为一致；按位模式保留顺序
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DExcludeIncludeStrategy(GenerationStrategy):
    """3D排除/必含：支持按位必含/排除。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exclude_include_3d",
            name="排除/必含",
            description="排除不想要的号码，或强制包含某些幸运号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "include_pos": {
                "type": "list_int_list",
                "label": "必含 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组必含数字，空列表表示不约束。",
            },
            "exclude_pos": {
                "type": "list_int_list",
                "label": "排除 号码",
                "default": [[], [], []],
                "tooltip": "每位可指定一组排除数字，空列表表示不约束。",
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
        for key in ("include_pos", "exclude_pos"):
            value = options.get(key, [[], [], []])
            if len(value) != 3:
                raise ValueError(f"{key} 必须提供3个位置的列表")
            for idx, nums in enumerate(value):
                if not all(0 <= n <= 9 for n in nums):
                    raise ValueError(f"{key} 第{idx}位包含越界号码")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        include_pos = options.get("include_pos", [[], [], []])
        exclude_pos = options.get("exclude_pos", [[], [], [])

        basis_parts = ["排除/必含策略："]
        for idx in range(3):
            inc = set(include_pos[idx])
            exc = set(exclude_pos[idx])
            if inc:
                basis_parts.append(f"第{idx+1}位必含 {sorted(inc)}；")
            if exc:
                basis_parts.append(f"第{idx+1}位排除 {sorted(exc)}；")
        basis = " ".join(basis_parts) + "其余位在可用范围内随机。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for idx in range(3):
                include = set(include_pos[idx])
                exclude = set(exclude_pos[idx])
                if include:
                    chosen = rng.choice(list(include))
                else:
                    pool = [n for n in range(10) if n not in exclude]
                    chosen = rng.choice(pool)
                result.append(chosen)
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 6 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d.py tests/test_fc3d_strategies.py
git commit -m "feat: add 3D random, odd-even, and exclude-include strategies"
```

---

### Task 3: 3D冷热相关策略

**Files:**
- Modify: `caipiao/core/strategies/fc3d.py`（追加类）
- Test: `tests/test_fc3d_strategies.py`（追加测试）

**Interfaces:**
- Produces:
  - `FC3DHotColdStrategy` (id=`hot_cold_3d`)
  - `FC3DSmartHotColdStrategy` (id=`smart_hot_cold_3d`)
  - `FC3DMissingNumberStrategy` (id=`missing_number_3d`)

- [ ] **Step 1: 编写失败测试**

```python
# 追加到 tests/test_fc3d_strategies.py
from caipiao.core.strategies.fc3d import (
    FC3DHotColdStrategy,
    FC3DSmartHotColdStrategy,
    FC3DMissingNumberStrategy,
)
from caipiao.data.analyzer import DrawAnalyzer


def test_hot_cold_3d_generates_valid():
    strategy = FC3DHotColdStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"mode": "hot", "history": history})
    assert len(tickets) == 3
    for t in tickets:
        assert len(t.groups["pos"]) == 3


def test_smart_hot_cold_3d_uses_history():
    strategy = FC3DSmartHotColdStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3


def test_missing_number_3d_generates_valid():
    strategy = FC3DMissingNumberStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3


def test_hot_cold_3d_seed_reproducible():
    strategy = FC3DHotColdStrategy()
    history = make_history(50)
    opts = {"mode": "hot", "history": history, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    assert t1 == t2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_strategies.py::test_hot_cold_3d_generates_valid tests/test_fc3d_strategies.py::test_smart_hot_cold_3d_uses_history tests/test_fc3d_strategies.py::test_missing_number_3d_generates_valid tests/test_fc3d_strategies.py::test_hot_cold_3d_seed_reproducible -v`
Expected: 4 FAIL

- [ ] **Step 3: 实现冷热相关策略**

```python
# 追加到 caipiao/core/strategies/fc3d.py
from collections import Counter

from ...data.analyzer import DrawAnalyzer
from .fc3d_utils import positional_frequency, positional_weights


class FC3DHotColdStrategy(GenerationStrategy):
    """3D冷热号分析：基于按位历史频率。"""

    is_history_needed = True

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="hot_cold_3d",
            name="冷热号分析",
            description="基于历史记录统计每位数字出现频率，优先选择热号或冷号。",
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
        if not options.get("history"):
            raise ValueError("冷热号分析策略需要历史开奖数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        mode = options.get("mode", "mixed")
        records = _records_from_options(options)

        freq = positional_frequency(records)
        tickets: List[Ticket] = []
        basis = f"冷热号分析策略：{mode} 模式，基于按位历史频率抽取号码。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        for _ in range(count):
            result = []
            for pos in range(3):
                pos_freq = freq.get(pos, {})
                ranked = sorted(range(10), key=lambda d: pos_freq.get(d, 0), reverse=True)
                if mode == "hot":
                    pool = ranked[:5]
                elif mode == "cold":
                    pool = ranked[-5:]
                else:
                    pool = ranked[:2] + ranked[-2:]
                result.append(rng.choice(pool))
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DSmartHotColdStrategy(GenerationStrategy):
    """3D智能冷热号：综合按位频率与遗漏值。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="smart_hot_cold_3d",
            name="智能冷热号",
            description="结合历史数据中的按位热号频率与冷号遗漏值加权生成。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "hot_weight": {"type": "int", "label": "热号权重", "default": 60, "min": 0, "max": 100},
            "cold_weight": {"type": "int", "label": "冷号权重", "default": 40, "min": 0, "max": 100},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "seed": {
                "type": "int",
                "label": "随机种子（可选）",
                "default": None,
                "min": 0,
                "max": 999999999,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 20:
            raise ValueError("智能冷热号策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        hot_weight = int(options.get("hot_weight", 60))
        cold_weight = int(options.get("cold_weight", 40))
        lookback = int(options.get("lookback", 100))

        analyzer = DrawAnalyzer(records, FC3D_PROFILE)
        freq = analyzer.frequency("pos")
        max_freq = max(freq.values()) if freq else 1
        missing = dict(analyzer.missing("pos", lookback))
        max_missing = max(missing.values()) if missing else 1

        basis = (
            f"智能冷热号策略：综合最近 {lookback} 期按位热号频率（权重 {hot_weight}）"
            f"与冷号遗漏值（权重 {cold_weight}）加权评分后抽取号码。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for pos in range(3):
                pos_records = [r.groups["pos"][pos] for r in records[-lookback:] if len(r.groups.get("pos", [])) > pos]
                pos_freq = Counter(pos_records)
                pos_missing = {}
                for idx, n in enumerate(reversed(pos_records)):
                    if n not in pos_missing:
                        pos_missing[n] = idx
                for d in range(10):
                    pos_missing.setdefault(d, len(pos_records))

                scores = []
                for d in range(10):
                    hot_score = hot_weight * (pos_freq.get(d, 0) / max_freq)
                    cold_score = cold_weight * (pos_missing[d] / max_missing)
                    scores.append(max(0.1, hot_score + cold_score))
                result.append(rng.choices(range(10), weights=scores, k=1)[0])
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets


class FC3DMissingNumberStrategy(GenerationStrategy):
    """3D遗漏号追踪：按位优先选择高遗漏号码。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="missing_number_3d",
            name="遗漏号追踪",
            description="选择近期按位遗漏值较高的号码，适合追冷号。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 50, "min": 10, "max": 10000},
            "pool_size": {
                "type": "int",
                "label": "候选池大小",
                "default": 5,
                "min": 1,
                "max": 10,
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
        if len(options.get("history", [])) < 20:
            raise ValueError("遗漏号追踪策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 50))
        pool_size = int(options.get("pool_size", 5))

        analyzer = DrawAnalyzer(records, FC3D_PROFILE)

        basis = f"遗漏号追踪策略：基于最近 {lookback} 期，按位从高遗漏值候选池抽取号码。"
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        tickets: List[Ticket] = []
        for _ in range(count):
            result = []
            for pos in range(3):
                pos_records = [r.groups["pos"][pos] for r in records[-lookback:] if len(r.groups.get("pos", [])) > pos]
                missing: Dict[int, int] = {d: lookback for d in range(10)}
                for idx, n in enumerate(reversed(pos_records)):
                    if missing[n] == lookback:
                        missing[n] = idx
                pool = [d for d, _ in sorted(missing.items(), key=lambda x: x[1], reverse=True)[:pool_size]]
                result.append(rng.choice(pool))
            tickets.append(
                Ticket(profile=FC3D_PROFILE, groups={"pos": result}, strategy_name=self.metadata.name, basis=basis)
            )
        return tickets
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 10 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d.py tests/test_fc3d_strategies.py
git commit -m "feat: add 3D hot-cold, smart-hot-cold, and missing-number strategies"
```

---

### Task 4: 3D历史均衡策略（核心优化）

**Files:**
- Modify: `caipiao/core/strategies/fc3d.py`（追加 `FC3DBalancedStrategy`）
- Test: `tests/test_fc3d_strategies.py`（追加测试）

**Interfaces:**
- Produces: `FC3DBalancedStrategy` (id=`balanced_3d`)
- Consumes: `fc3d_utils` functions

- [ ] **Step 1: 编写失败测试**

```python
# 追加到 tests/test_fc3d_strategies.py
from caipiao.core.strategies.fc3d import FC3DBalancedStrategy


def test_balanced_3d_generates_valid():
    strategy = FC3DBalancedStrategy()
    history = make_history(50)
    tickets = strategy.generate(count=3, options={"history": history, "lookback": 30})
    assert len(tickets) == 3
    for t in tickets:
        assert len(t.groups["pos"]) == 3
        assert all(0 <= n <= 9 for n in t.groups["pos"])


def test_balanced_3d_respects_order():
    """历史均衡结果应保留百十位的原始顺序，不应被排序。"""
    strategy = FC3DBalancedStrategy()
    history = [
        DrawRecord("2024001", datetime(2024, 1, 1), profile="3d", groups={"pos": [9, 0, 1]}),
        DrawRecord("2024002", datetime(2024, 1, 2), profile="3d", groups={"pos": [9, 0, 1]}),
    ]
    # 使用枚举模式 + 固定种子确保确定性
    ticket = strategy.generate(
        count=1,
        options={"history": history, "lookback": 10, "seed": 1, "use_enumeration": True},
    )[0]
    assert ticket.groups["pos"] == [9, 0, 1]


def test_balanced_3d_enumeration_finds_best():
    strategy = FC3DBalancedStrategy()
    history = make_history(30)
    # 记录中全是 [i, i+1, i+2] mod 10，最优应接近这种模式
    tickets = strategy.generate(
        count=1,
        options={"history": history, "lookback": 30, "use_enumeration": True},
    )
    assert len(tickets) == 1


def test_balanced_3d_seed_reproducible():
    strategy = FC3DBalancedStrategy()
    history = make_history(50)
    opts = {"history": history, "lookback": 30, "seed": 42}
    t1 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    t2 = strategy.generate(count=1, options=opts)[0].groups["pos"]
    assert t1 == t2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_strategies.py::test_balanced_3d_generates_valid tests/test_fc3d_strategies.py::test_balanced_3d_respects_order tests/test_fc3d_strategies.py::test_balanced_3d_enumeration_finds_best tests/test_fc3d_strategies.py::test_balanced_3d_seed_reproducible -v`
Expected: 4 FAIL

- [ ] **Step 3: 实现历史均衡策略**

```python
# 追加到 caipiao/core/strategies/fc3d.py
import itertools

from .fc3d_utils import (
    fc3d_bet_type,
    overall_high_low_ratio,
    overall_odd_even_ratio,
    positional_weights,
    shape_ratio,
    span_statistics,
    sum_statistics,
    sum_tail_statistics,
)


class FC3DBalancedStrategy(GenerationStrategy):
    """3D历史均衡：按位统计，保留顺序，支持枚举择优。"""

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="balanced_3d",
            name="历史均衡",
            description="根据历史数据的按位频率、奇偶、大小、跨度、和尾、012路和形态生成均衡号码。",
            configurable=True,
        )

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "history": {"type": "history", "label": "历史记录", "default": []},
            "lookback": {"type": "int", "label": "统计期数", "default": 100, "min": 10, "max": 10000},
            "max_attempts": {"type": "int", "label": "最大尝试次数", "default": 1000, "min": 100, "max": 10000},
            "use_enumeration": {
                "type": "bool",
                "label": "使用枚举择优",
                "default": True,
                "tooltip": "3D仅1000种组合，枚举可找到评分最高且确定性的结果。",
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
        if len(options.get("history", [])) < 20:
            raise ValueError("历史均衡策略需要至少 20 期历史数据")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        rng = _make_rng(options)
        records = _records_from_options(options)
        lookback = int(options.get("lookback", 100))
        max_attempts = int(options.get("max_attempts", 1000))
        use_enumeration = bool(options.get("use_enumeration", True))

        odd_ratio, _ = overall_odd_even_ratio(records, lookback)
        high_ratio, _ = overall_high_low_ratio(records, lookback)
        sum_stats = sum_statistics(records, lookback)
        avg_sum = sum_stats["avg"]
        std_sum = (sum_stats["max"] - sum_stats["min"]) / 6.0 or 1.0
        sum_min = max(avg_sum - 1.5 * std_sum, sum_stats["min"])
        sum_max = min(avg_sum + 1.5 * std_sum, sum_stats["max"])
        tail_avg = sum_tail_statistics(records, lookback)["avg"]
        span_avg = span_statistics(records, lookback)["avg"]
        shape = shape_ratio(records, lookback)
        target_odd = round(3 * odd_ratio)
        target_high = round(3 * high_ratio)
        weights = positional_weights(records, lookback, smoothing=1.0)

        basis = (
            f"历史均衡策略：基于最近 {lookback} 期，"
            f"使3D号码的按位频率、奇偶、大小、和值、跨度、和尾、012路和形态接近历史平均。"
        )
        seed = options.get("seed")
        if seed is not None:
            basis += f" 随机种子：{seed}。"

        def score(candidate: List[int]) -> float:
            odd_count = sum(1 for n in candidate if n % 2 == 1)
            high_count = sum(1 for n in candidate if n >= 5)
            total = sum(candidate)
            tail = total % 10
            span = max(candidate) - min(candidate)
            shape_type = fc3d_bet_type(candidate)
            shape_score = 0.0
            if shape_type == "豹子号":
                shape_score = 1 - shape["leopard"]
            elif shape_type == "组选3":
                shape_score = 1 - shape["group3"]
            else:
                shape_score = 1 - shape["group6"]

            return (
                abs(odd_count - target_odd)
                + abs(high_count - target_high)
                + abs(total - avg_sum) / 10.0
                + abs(tail - tail_avg) / 5.0
                + abs(span - span_avg) / 5.0
                + shape_score
            )

        def sample_one() -> List[int]:
            return [rng.choices(range(10), weights=weights[pos], k=1)[0] for pos in range(3)]

        tickets: List[Ticket] = []
        for _ in range(count):
            best_candidate: Optional[List[int]] = None
            best_score = float("inf")

            if use_enumeration:
                candidates = [list(c) for c in itertools.product(range(10), repeat=3)]
                if seed is not None:
                    rng.shuffle(candidates)
                for candidate in candidates:
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
                    if best_score <= 0.01:
                        break
            else:
                for _ in range(max_attempts):
                    candidate = sample_one()
                    s = score(candidate)
                    if s < best_score:
                        best_score = s
                        best_candidate = candidate
                    if best_score <= 0.5:
                        break

            if best_candidate is None:
                best_candidate = sample_one()

            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups={"pos": best_candidate},
                    strategy_name=self.metadata.name,
                    basis=basis,
                )
            )
        return tickets
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 14 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d.py tests/test_fc3d_strategies.py
git commit -m "feat: add 3D balanced strategy with positional enumeration"
```

---

### Task 5: 3D ML策略包装器

**Files:**
- Modify: `caipiao/core/strategies/fc3d.py`（追加ML类）
- Test: `tests/test_fc3d_strategies.py`（追加测试）

**Interfaces:**
- Produces:
  - `FC3DXGBoostStrategy` (id=`xgboost_3d`, `is_ml=True`)
  - `FC3DLightGBMStrategy` (id=`lightgbm_3d`, `is_ml=True`)
  - `FC3DCatBoostStrategy` (id=`catboost_3d`, `is_ml=True`)
- Consumes: `GenericMLPredictor`, `compute_lookback`, `find_current_model`, `new_model_path`

- [ ] **Step 1: 编写失败测试**

```python
# 追加到 tests/test_fc3d_strategies.py
from caipiao.core.strategies.fc3d import (
    FC3DXGBoostStrategy,
    FC3DLightGBMStrategy,
    FC3DCatBoostStrategy,
)


@pytest.mark.parametrize("strategy_cls", [FC3DXGBoostStrategy, FC3DLightGBMStrategy, FC3DCatBoostStrategy])
def test_ml_3d_strategy_generates_valid(strategy_cls):
    strategy = strategy_cls()
    assert strategy.is_ml
    history = make_history(120)
    tickets = strategy.generate(count=1, options={"history": history, "history_count": 100})
    assert len(tickets) == 1
    assert len(tickets[0].groups["pos"]) == 3
    assert all(0 <= n <= 9 for n in tickets[0].groups["pos"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_strategies.py::test_ml_3d_strategy_generates_valid -v`
Expected: 3 FAIL

- [ ] **Step 3: 实现ML策略包装器**

```python
# 追加到 caipiao/core/strategies/fc3d.py
import numpy as np

from ...ml.generic_predictor import GenericMLPredictor
from ...ml.model_store import compute_lookback, find_current_model, new_model_path


class _FC3DMLStrategy(GenerationStrategy):
    _backend: str = "xgboost"

    @property
    def is_ml(self) -> bool:
        return True

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "diversity_boost": {
                "type": "int",
                "label": "多样性增强 (0-10)",
                "default": 3,
                "min": 0,
                "max": 10,
            },
            "history": {"type": "history", "label": "历史记录", "default": []},
            "history_count": {
                "type": "int",
                "label": "使用历史记录期数",
                "default": -1,
                "min": -1,
                "max": 10000,
            },
        }

    def validate_options(self, options: Dict[str, Any]) -> None:
        if len(options.get("history", [])) < 100:
            raise ValueError(f"{self.metadata.name} 策略需要至少 100 期历史数据")
        history_count = options.get("history_count", -1)
        if not isinstance(history_count, int) or history_count < -1:
            raise ValueError("使用历史记录期数必须大于等于 -1")

    def generate(
        self, count: int = 1, options: Optional[Dict[str, Any]] = None
    ) -> List[Ticket]:
        options = options or {}
        records = _records_from_options(options)
        diversity = int(options.get("diversity_boost", 3)) / 10.0

        history_count = options.get("history_count", -1)
        if isinstance(history_count, int) and history_count > 0 and len(records) > history_count:
            records = records[-history_count:]

        lookback = compute_lookback(len(records))
        if self._backend == "xgboost":
            prefix = FC3D_PROFILE.xgboost_prefix()
        elif self._backend == "lightgbm":
            prefix = FC3D_PROFILE.lightgbm_prefix()
        else:
            prefix = FC3D_PROFILE.catboost_prefix()

        model_path = (
            find_current_model(records, lookback, prefix=prefix, options=options)
            or new_model_path(records, lookback, prefix=prefix, options=options)
        )

        predictor = GenericMLPredictor(
            records, profile=FC3D_PROFILE, lookback=lookback, model_path=model_path, backend=self._backend
        )
        if not predictor.is_ready():
            predictor.train()

        proba = predictor.predict()
        proba_lists = {}
        for k, v in proba.items():
            if v.ndim == 1:
                proba_lists[k] = [round(float(p), 4) for p in v]
            else:
                proba_lists[k] = [[round(float(x), 4) for x in row] for row in v]

        details = {
            "lookback": lookback,
            "diversity_boost": int(diversity * 10),
            "probabilities": proba_lists,
            "model_name": self._backend.upper(),
        }
        basis = (
            f"{self.metadata.name}：基于最近 {len(records)} 期历史数据训练模型，"
            f"特征回看期数 {lookback}，按预测概率加权采样。"
        )

        group_picks = {"pos": 3}
        tickets: List[Ticket] = []
        seed = 42
        for i in range(count):
            np_rng = np.random.RandomState(seed + i)
            rec_groups = predictor.recommend(group_picks=group_picks, diversity_boost=diversity, rng=np_rng)
            tickets.append(
                Ticket(
                    profile=FC3D_PROFILE,
                    groups=rec_groups,
                    strategy_name=self.metadata.name,
                    basis=basis,
                    details=details,
                )
            )
        return tickets


class FC3DXGBoostStrategy(_FC3DMLStrategy):
    _backend = "xgboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="xgboost_3d",
            name="XGBoost 智能分析",
            description="基于 XGBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


class FC3DLightGBMStrategy(_FC3DMLStrategy):
    _backend = "lightgbm"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="lightgbm_3d",
            name="LightGBM 智能分析",
            description="基于 LightGBM 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


class FC3DCatBoostStrategy(_FC3DMLStrategy):
    _backend = "catboost"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="catboost_3d",
            name="CatBoost 智能分析",
            description="基于 CatBoost 模型分析历史数据，生成概率优先的号码组合。",
            configurable=True,
        )


def build_fc3d_strategies(profile) -> List[GenerationStrategy]:
    return [
        FC3DRandomStrategy(),
        FC3DOddEvenStrategy(),
        FC3DHotColdStrategy(),
        FC3DExcludeIncludeStrategy(),
        FC3DSmartHotColdStrategy(),
        FC3DMissingNumberStrategy(),
        FC3DBalancedStrategy(),
        FC3DXGBoostStrategy(),
        FC3DLightGBMStrategy(),
        FC3DCatBoostStrategy(),
    ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 17 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/strategies/fc3d.py tests/test_fc3d_strategies.py
git commit -m "feat: add 3D ML strategy wrappers"
```

---

### Task 6: build_strategies路由改造

**Files:**
- Modify: `caipiao/core/strategies/generic.py`

**Interfaces:**
- Consumes: `build_fc3d_strategies` from `fc3d`
- Produces: `build_strategies()` 对3D路由

- [ ] **Step 1: 编写失败测试**

```python
# 追加到 tests/test_fc3d_strategies.py
from caipiao.core.strategies.generic import build_strategies, needs_history, is_ml_strategy


def test_build_strategies_3d_uses_fc3d_classes():
    profile = get_profile("3d")
    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    assert "random_3d" in strategies
    assert "balanced_3d" in strategies
    assert "xgboost_3d" in strategies
    # 确认是3D专属类，不是通用类
    from caipiao.core.strategies.fc3d import FC3DBalancedStrategy
    assert isinstance(strategies["balanced_3d"], FC3DBalancedStrategy)


def test_needs_history_and_is_ml_3d_unchanged():
    assert needs_history("balanced_3d")
    assert needs_history("xgboost_3d")
    assert is_ml_strategy("xgboost_3d")
    assert is_ml_strategy("lightgbm_3d")
    assert is_ml_strategy("catboost_3d")
    assert not needs_history("random_3d")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_fc3d_strategies.py::test_build_strategies_3d_uses_fc3d_classes tests/test_fc3d_strategies.py::test_needs_history_and_is_ml_3d_unchanged -v`
Expected: 2 FAIL（`FC3DBalancedStrategy` import 可能成功但 build_strategies 仍返回通用类）

- [ ] **Step 3: 修改 generic.py 的 build_strategies**

```python
# caipiao/core/strategies/generic.py
# 在 build_strategies 函数开头添加3D路由

def build_strategies(profile: LotteryProfile) -> List[GenerationStrategy]:
    """为指定彩种生成全部通用策略实例。"""
    if profile.key == "3d":
        from .fc3d import build_fc3d_strategies
        return build_fc3d_strategies(profile)

    base = [cls(profile) for cls in _GENERIC_STRATEGY_CLASSES]
    ...
```

- [ ] **Step 4: 验证 generic.py 中不再包含3D专属逻辑**

检查 `generic.py` 中 `GenericBalancedStrategy` 等类是否仍保留非3D逻辑。保留通用彩种逻辑，但确保：
- 通用策略的 `generate` 不再处理 `profile.key == "3d"` 的特殊分支（原本就没有，但确认无残留）。
- 测试 `test_generic_random_3d` 仍然通过。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py tests/test_lottery_unified.py::test_generic_random_3d tests/test_lottery_unified.py::test_generic_predictor_recommend_3d -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/strategies/generic.py tests/test_fc3d_strategies.py
git commit -m "feat: route 3D strategies through dedicated fc3d module"
```

---

### Task 7: 综合测试与边界情况

**Files:**
- Test: `tests/test_fc3d_strategies.py`

- [ ] **Step 1: 追加边界测试**

```python
# 追加到 tests/test_fc3d_strategies.py


def test_all_3d_strategies_respect_count():
    profile = get_profile("3d")
    from caipiao.core.strategies.generic import build_strategies

    strategies = {s.metadata.id: s for s in build_strategies(profile)}
    history = make_history(120)
    for sid, strategy in strategies.items():
        options = {}
        if needs_history(sid):
            options["history"] = history
        tickets = strategy.generate(count=5, options=options)
        assert len(tickets) == 5, sid
        for t in tickets:
            assert len(t.groups["pos"]) == 3, sid
            assert all(0 <= n <= 9 for n in t.groups["pos"]), sid


def test_balanced_3d_no_history_raises():
    strategy = FC3DBalancedStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=1, options={"history": []})


def test_ml_3d_insufficient_history_raises():
    strategy = FC3DXGBoostStrategy()
    with pytest.raises(ValueError):
        strategy.generate(count=1, options={"history": make_history(50)})
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_fc3d_strategies.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_fc3d_strategies.py
git commit -m "test: add 3D strategy boundary tests"
```

---

### Task 8: 全量回归测试

**Files:**
- 全部修改的文件

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest tests/ -q --tb=short`
Expected: 全部 PASS（或只有与本次改动无关的既有失败）

- [ ] **Step 2: 重点检查相关测试**

Run:
```bash
python -m pytest tests/test_lottery_unified.py tests/test_core.py tests/test_optimal_period_scan.py tests/test_optimal_strategy_scan.py tests/test_fc3d_utils.py tests/test_fc3d_strategies.py -v
```
Expected: 全部 PASS

- [ ] **Step 3: 检查未提交改动**

Run: `git status`
Expected: 只有新增/修改的目标文件

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: isolate and optimize FC3D strategies into dedicated module"
```

---

## Self-Review Checklist

- **Spec coverage**: 设计文档中所有要求均已对应到任务。
  - 独立模块 ✅ Task 1-5
  - build_strategies路由 ✅ Task 6
  - 按位优化/枚举 ✅ Task 4
  - 保持ID/schema不变 ✅ 各Task中已说明
  - 测试覆盖 ✅ Task 1, 4, 7, 8
- **Placeholder scan**: 无 TBD/TODO/"实现 later"。
- **Type consistency**:
  - `positional_frequency` 返回 `Dict[int, Dict[int, int]]`，与 `fc3d_utils.py` 实现一致。
  - `build_fc3d_strategies` 返回 `List[GenerationStrategy]`，与 `build_strategies` 一致。
  - ML策略 `is_ml` 为 True，与 `is_ml_strategy()` 前缀识别兼容。
- **Ambiguity check**: 已明确 `use_enumeration` 默认 True，保留顺序；`odd_even` 整体模式仍排序以兼容旧行为，按位模式保留顺序。

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-07-fc3d-strategy-isolation-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
