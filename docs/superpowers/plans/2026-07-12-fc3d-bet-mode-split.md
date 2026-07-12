# 福彩3D 直选/组选投注方式分配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 福彩3D 生成号码时按 1:1 比例分配直选/组选投注方式（奇数时组选多一张），中奖判定、奖金、展示与回测全部按投注方式区分。

**Architecture:** 在 `GenerationEngine.generate` 出口对 fc3d tickets 统一后处理，把投注方式写入 `ticket.details["bet_mode"]`；`core/prize.py` 的 `_fc3d_prize` 按 `bet_mode` 分支判定；三处回测调用方改传 `ticket.details`；主界面展示、PDF 导出、概率面板读取同一字段，并修复 UI 对 3D 有序号码的强制排序。

**Tech Stack:** Python 3.10+，pytest，PySide6（仅 UI 任务涉及），无新增依赖。

## Global Constraints

- fc3d 彩种 profile key 是 `"3d"`（`calculate_prize` 以 `profile_key == "3d"` 分支）。
- 投注方式取值固定为 `"直选"` / `"组选"`，存于 `ticket.details["bet_mode"]`。
- 奖金：直选 1040、组选3 346、组选6 173；每注成本 2 元不变。
- 分配规则：N 张票，组选 `ceil(N/2)` 张、直选 `floor(N/2)` 张；前 `ceil(N/2)` 张标组选，其余标直选；组选区内豹子号改标直选且不补位。
- 历史数据无 `bet_mode` 字段时，中奖判定必须保持现有行为（向后兼容）。
- 不修改任何策略的号码生成逻辑本身；不改形态权重（`shape_weights`）。
- 测试命令统一使用项目 venv：`venv/Scripts/python -m pytest ...`（Windows）。

## File Structure

- `caipiao/core/strategies/lotteries/fc3d/utils.py` — 新增 `assign_fc3d_bet_modes()`（分配逻辑，唯一事实来源）。
- `caipiao/core/engine.py` — `GenerationEngine.generate` 增加 fc3d 后处理钩子。
- `caipiao/core/prize.py` — `_fc3d_prize` 按 `bet_mode` 分支；`calculate_prize` 增加可选 `details` 参数。
- `caipiao/ui/components/backtest_dialog.py`、`caipiao/core/backtest_worker.py`、`scripts/run_30day_all_strategies.py` — 调用 `calculate_prize` 时传 `ticket.details`。
- `caipiao/ui/main_window.py` — 展示标签、概率面板期望收益、可编辑列表排序修复。
- `tests/test_fc3d_bet_mode.py` — 新增，覆盖分配、判定、概率面板。

---

### Task 1: 分配函数 `assign_fc3d_bet_modes` 与 engine 钩子

**Files:**
- Modify: `caipiao/core/strategies/lotteries/fc3d/utils.py`（文件末尾追加函数）
- Modify: `caipiao/core/engine.py:41-53`
- Test: `tests/test_fc3d_bet_mode.py`（新建）

**Interfaces:**
- Produces: `assign_fc3d_bet_modes(tickets: List[Ticket]) -> List[Ticket]` — 就地写入 `ticket.details["bet_mode"]`（`"直选"`/`"组选"`），返回同一列表。
- Produces: `GenerationEngine.generate(...)` 对 profile key 为 `"3d"` 的 tickets 自动完成分配。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_fc3d_bet_mode.py`：

```python
"""福彩3D 直选/组选投注方式分配与判定测试。"""

from __future__ import annotations

from typing import List, Optional

from caipiao.core.engine import GenerationEngine
from caipiao.core.strategies.lotteries.fc3d.utils import assign_fc3d_bet_modes
from caipiao.core.strategy import GenerationStrategy, StrategyMetadata
from caipiao.core.ticket import Ticket


def _ticket(nums: List[int]) -> Ticket:
    return Ticket(profile="3d", groups={"pos": nums})


def _modes(tickets: List[Ticket]) -> List[str]:
    return [t.details["bet_mode"] for t in tickets]


class TestAssignFc3dBetModes:
    def test_even_split(self):
        tickets = [_ticket([1, 2, 3]) for _ in range(10)]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选"] * 5 + ["直选"] * 5

    def test_odd_split_group_has_one_more(self):
        tickets = [_ticket([1, 2, 3]) for _ in range(3)]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选", "组选", "直选"]

    def test_single_ticket_is_group(self):
        tickets = [_ticket([1, 2, 3])]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["组选"]

    def test_leopard_in_group_zone_becomes_zhixuan(self):
        # N=3：前 2 张为组选区；第 1 张是豹子号 → 转直选，不补位
        tickets = [_ticket([6, 6, 6]), _ticket([1, 2, 3]), _ticket([4, 5, 6])]
        assign_fc3d_bet_modes(tickets)
        assert _modes(tickets) == ["直选", "组选", "直选"]

    def test_empty_list(self):
        assert assign_fc3d_bet_modes([]) == []


class _Dummy3dStrategy(GenerationStrategy):
    def __init__(self, tickets: List[Ticket]) -> None:
        self._tickets = tickets

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(id="dummy-3d", name="dummy", description="")

    def generate(self, count: int = 1, options: Optional[dict] = None) -> List[Ticket]:
        return self._tickets


class TestEngineHook:
    def test_engine_assigns_bet_modes_for_3d(self):
        engine = GenerationEngine()
        engine.register(_Dummy3dStrategy([_ticket([1, 2, 3]) for _ in range(4)]))
        tickets = engine.generate("dummy-3d", count=4)
        assert _modes(tickets) == ["组选", "组选", "直选", "直选"]

    def test_engine_leaves_ssq_untouched(self):
        engine = GenerationEngine()
        ssq = [Ticket(red_balls=[1, 2, 3, 4, 5, 6], blue_ball=7) for _ in range(2)]
        engine.register(_Dummy3dStrategy(ssq))
        tickets = engine.generate("dummy-3d", count=2)
        assert all("bet_mode" not in t.details for t in tickets)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py -v`
Expected: FAIL（`ImportError: cannot import name 'assign_fc3d_bet_modes'`）

- [ ] **Step 3: 实现分配函数**

在 `caipiao/core/strategies/lotteries/fc3d/utils.py` 末尾追加：

```python
def assign_fc3d_bet_modes(tickets: list) -> list:
    """按 1:1 比例为3D投注单分配直选/组选投注方式（就地修改 details）。

    规则：
    - 总数 N：组选 ceil(N/2) 张、直选 floor(N/2) 张；
    - 按生成顺序，前 ceil(N/2) 张标 "组选"，其余标 "直选"；
    - 组选区内的豹子号自动改标 "直选"（不补位，直选可能多一张）。

    投注方式写入 ``ticket.details["bet_mode"]``，取值 "直选" / "组选"，
    供中奖判定（core.prize._fc3d_prize）与界面展示使用。
    """
    n = len(tickets)
    zu_count = (n + 1) // 2
    for i, ticket in enumerate(tickets):
        nums = ticket.groups.get("pos", [])
        if i < zu_count and fc3d_bet_type(nums) != "豹子号":
            ticket.details["bet_mode"] = "组选"
        else:
            ticket.details["bet_mode"] = "直选"
    return tickets
```

- [ ] **Step 4: 给 engine 加钩子**

修改 `caipiao/core/engine.py:41-53` 的 `generate` 方法：

```python
    def generate(
        self,
        strategy_id: str,
        count: int = 1,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[Ticket]:
        """使用指定策略生成投注单."""
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise ValueError(f"未找到策略: {strategy_id}")
        options = options or {}
        strategy.validate_options(options)
        tickets = strategy.generate(count=count, options=options)
        if tickets and tickets[0].profile.key == "3d":
            from .strategies.lotteries.fc3d.utils import assign_fc3d_bet_modes

            assign_fc3d_bet_modes(tickets)
        return tickets
```

（函数内导入避免 engine 与策略包之间的潜在循环导入。）

- [ ] **Step 5: 运行测试确认通过**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py -v`
Expected: PASS（7 个用例）

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/strategies/lotteries/fc3d/utils.py caipiao/core/engine.py tests/test_fc3d_bet_mode.py
git commit -m "feat(fc3d): 生成时按1:1分配直选/组选投注方式"
```

---

### Task 2: `_fc3d_prize` 按投注方式判定 + `calculate_prize` 增加 `details` 参数

**Files:**
- Modify: `caipiao/core/prize.py:9`（typing 导入）、`:31-64`（`_fc3d_prize`）、`:254-275`（`calculate_prize`）
- Test: `tests/test_fc3d_bet_mode.py`（追加用例）

**Interfaces:**
- Consumes: `ticket.details["bet_mode"]`（Task 1 产出）。
- Produces: `calculate_prize(profile_key, hits, ticket_groups, actual_groups=None, details=None) -> Tuple[str, int | None]` — 新参数可选，旧调用方不受影响。

- [ ] **Step 1: 写失败测试**

在 `tests/test_fc3d_bet_mode.py` 追加：

```python
from caipiao.core.prize import calculate_prize


def _prize(ticket_nums, actual_nums, bet_mode=None):
    details = {"bet_mode": bet_mode} if bet_mode else None
    return calculate_prize(
        "3d",
        {"pos": 0},
        {"pos": ticket_nums},
        {"pos": actual_nums},
        details=details,
    )


class TestFc3dPrizeByBetMode:
    def test_zhixuan_exact_match(self):
        assert _prize([1, 2, 3], [1, 2, 3], "直选") == ("直选", 1040)

    def test_zhixuan_wrong_order_no_prize(self):
        # 直选票顺序不同 → 不中（旧逻辑会发组选6奖金）
        assert _prize([1, 2, 3], [3, 2, 1], "直选") == ("未中奖", 0)

    def test_zuxuan_unordered_match_group6(self):
        assert _prize([1, 2, 3], [3, 2, 1], "组选") == ("组选6", 173)

    def test_zuxuan_unordered_match_group3(self):
        assert _prize([1, 1, 2], [1, 2, 1], "组选") == ("组选3", 346)

    def test_zuxuan_exact_order_still_group_prize(self):
        # 组选票即使位置全对，也只发组选奖金
        assert _prize([1, 2, 3], [1, 2, 3], "组选") == ("组选6", 173)

    def test_zuxuan_mismatch(self):
        assert _prize([1, 2, 3], [4, 5, 6], "组选") == ("未中奖", 0)

    def test_zuxuan_leopard_fallback_zhixuan(self):
        # 豹子号标组选属异常数据，兜底按直选规则
        assert _prize([6, 6, 6], [6, 6, 6], "组选") == ("直选", 1040)

    def test_legacy_without_bet_mode_unchanged(self):
        # 无 bet_mode：保持旧行为（有序全对发直选，无序相同发组选）
        assert _prize([1, 2, 3], [1, 2, 3]) == ("直选", 1040)
        assert _prize([1, 2, 3], [3, 2, 1]) == ("组选6", 173)
        assert _prize([1, 2, 3], [4, 5, 6]) == ("未中奖", 0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py::TestFc3dPrizeByBetMode -v`
Expected: FAIL（`TypeError: calculate_prize() got an unexpected keyword argument 'details'`）

- [ ] **Step 3: 修改 `_fc3d_prize`**

替换 `caipiao/core/prize.py:31-64` 整个函数：

```python
def _fc3d_prize(
    hits: Dict[str, int],
    ticket_groups: Dict[str, List[int]],
    actual_groups: Optional[Dict[str, List[int]]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int | None]:
    """福彩3D奖金：按投注方式（直选/组选）与形态判断。

    - bet_mode == "直选"：3 位数字及顺序与开奖完全相同才中奖（1040）。
    - bet_mode == "组选"：投注号码是开奖号码的任意排列即中奖
      （组选3 → 346，组选6 → 173；位置全对也只发组选奖金）。
    - 无 bet_mode（历史数据）：保持旧逻辑，先判直选再判组选。

    必须有真实开奖号码 ``actual_groups`` 才能判定；否则统一视为未中奖，
    避免只根据投注号码自身特征误发奖金。
    """
    if actual_groups is None:
        return ("未中奖", 0)

    actual = actual_groups.get("pos", [])
    ticket = ticket_groups.get("pos", [])
    if len(actual) != 3 or len(ticket) != 3:
        return ("未中奖", 0)

    bet_mode = (details or {}).get("bet_mode")
    # 组选票不可能是豹子号（生成时已转直选）；异常数据兜底按直选规则
    if bet_mode == "组选" and len(set(ticket)) == 1:
        bet_mode = "直选"

    if bet_mode == "直选":
        if list(actual) == list(ticket):
            return ("直选", 1040)
        return ("未中奖", 0)

    if bet_mode == "组选":
        if sorted(actual) == sorted(ticket):
            unique = len(set(actual))
            if unique == 2:
                return ("组选3", 346)
            if unique == 3:
                return ("组选6", 173)
        return ("未中奖", 0)

    # 无 bet_mode（历史数据）：保持原逻辑
    if list(actual) == list(ticket):
        return ("直选", 1040)

    if sorted(actual) == sorted(ticket):
        unique = len(set(actual))
        if unique == 2:
            return ("组选3", 346)
        if unique == 3:
            return ("组选6", 173)

    return ("未中奖", 0)
```

- [ ] **Step 4: 修改 `calculate_prize` 签名并透传**

`caipiao/core/prize.py:9` 的 typing 导入改为：

```python
from typing import Any, Dict, List, Optional, Tuple
```

`calculate_prize`（:254）签名与 fc3d 分支改为：

```python
def calculate_prize(
    profile_key: str,
    hits: Dict[str, int],
    ticket_groups: Dict[str, List[int]],
    actual_groups: Optional[Dict[str, List[int]]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int | None]:
    """根据彩种、命中数、投注号码与真实开奖号码计算理论奖金。

    Args:
        profile_key: 彩种标识。
        hits: 各号码组命中数。
        ticket_groups: 当前投注号码分组。
        actual_groups: 当期真实开奖号码分组。福彩 3D 的组选/直选判定
            依赖真实号码；其他彩种可省略。
        details: 投注单附加信息（Ticket.details）。福彩 3D 用其中的
            ``bet_mode``（"直选"/"组选"）区分投注方式；缺省保持旧逻辑。

    Returns:
        (奖级描述, 奖金)。奖金为 None 表示浮动奖（如一等奖）。
    """
    if profile_key == "ssq":
        return _ssq_prize(hits)
    if profile_key == "3d":
        return _fc3d_prize(hits, ticket_groups, actual_groups, details)
```

（其余分支保持不变。）

- [ ] **Step 5: 运行测试确认通过**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py -v`
Expected: PASS（全部用例）

- [ ] **Step 6: 提交**

```bash
git add caipiao/core/prize.py tests/test_fc3d_bet_mode.py
git commit -m "feat(fc3d): 中奖判定按直选/组选投注方式区分奖金"
```

---

### Task 3: 三处回测调用方传入 `ticket.details`

**Files:**
- Modify: `caipiao/ui/components/backtest_dialog.py:397-399`
- Modify: `caipiao/core/backtest_worker.py:263-265`
- Modify: `scripts/run_30day_all_strategies.py:102`

**Interfaces:**
- Consumes: `calculate_prize(..., details=None)`（Task 2 产出）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_fc3d_bet_mode.py` 追加（锁定「调用方必须传 details 才生效」这一契约）：

```python
class TestCallersPassDetails:
    def test_details_actually_change_result(self):
        # 同一组号码：传 details 与不改传，结果必须不同
        ticket = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        ticket.details["bet_mode"] = "直选"
        with_details = calculate_prize(
            "3d", {"pos": 0}, ticket.groups, {"pos": [3, 2, 1]},
            details=ticket.details,
        )
        without_details = calculate_prize(
            "3d", {"pos": 0}, ticket.groups, {"pos": [3, 2, 1]},
        )
        assert with_details == ("未中奖", 0)
        assert without_details == ("组选6", 173)
```

同时写一个静态检查测试，防止三处调用方漏传：

```python
    def test_call_sites_pass_details(self):
        import inspect
        import caipiao.core.backtest_worker as bw
        import caipiao.ui.components.backtest_dialog as bd

        for module in (bw, bd):
            src = inspect.getsource(module)
            assert "details=ticket.details" in src, (
                f"{module.__name__} 的 calculate_prize 调用必须传 details=ticket.details"
            )
```

（`scripts/run_30day_all_strategies.py` 不是包模块，无法 import，用 grep 人工核对，见 Step 4。）

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py::TestCallersPassDetails -v`
Expected: FAIL（`test_call_sites_pass_details` 断言失败）

- [ ] **Step 3: 修改三处调用**

`caipiao/ui/components/backtest_dialog.py:397-399`：

```python
            prize_name, prize_amount = calculate_prize(
                self.profile.key, hits, ticket.groups, actual.groups,
                details=ticket.details,
            )
```

`caipiao/core/backtest_worker.py:263-265`：

```python
            prize_name, prize_amount = calculate_prize(
                profile.key, hits, ticket.groups, task.actual.groups,
                details=ticket.details,
            )
```

`scripts/run_30day_all_strategies.py:102`：

```python
                prize_name, prize_amount = calculate_prize(
                    profile.key, hits, ticket.groups, actual.groups,
                    details=ticket.details,
                )
```

- [ ] **Step 4: 运行测试确认通过，并 grep 核对脚本**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py -v`
Expected: PASS

Run: `grep -n "details=ticket.details" scripts/run_30day_all_strategies.py`
Expected: 输出第 102 行附近的匹配

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/components/backtest_dialog.py caipiao/core/backtest_worker.py scripts/run_30day_all_strategies.py tests/test_fc3d_bet_mode.py
git commit -m "feat(fc3d): 回测调用方传入投注方式参与奖金判定"
```

---

### Task 4: 主界面展示标签、概率面板与排序修复

**Files:**
- Modify: `caipiao/ui/main_window.py`
  - `_update_result_text`（:2180-2191）标签逻辑
  - `_build_print_html`（:2280-2282）标签逻辑
  - `_refresh_editable_table`（:2050-2052）取消排序显示
  - `_on_number_edited`（:2099-2102）取消排序写回
  - `_add_custom_number`（:2122）取消排序
  - `_add_random_number`（:2168）取消排序
  - `_calc_fc3d_probability`（:1890-1934）按 `bet_mode` 计算覆盖与期望收益
- Test: `tests/test_fc3d_bet_mode.py`（追加概率面板用例）

**Interfaces:**
- Consumes: `ticket.details["bet_mode"]`（Task 1 产出）。
- Produces: `MainWindow._fc3d_display_label(ticket) -> str`（静态方法）— 直选票返回 `"直选"`；组选票按形态返回 `"组选3"`/`"组选6"`；无 `bet_mode` 返回 `fc3d_bet_type(nums)` 的旧标签。

- [ ] **Step 1: 写失败测试**

在 `tests/test_fc3d_bet_mode.py` 追加：

```python
class TestFc3dProbabilityPanel:
    @staticmethod
    def _make(nums, bet_mode):
        t = Ticket(profile="3d", groups={"pos": nums})
        t.details["bet_mode"] = bet_mode
        return t

    def test_zhixuan_counts_as_single_coverage(self):
        from caipiao.ui.main_window import MainWindow

        tickets = [self._make([1, 2, 3], "直选"), self._make([4, 5, 6], "直选")]
        info = MainWindow._calc_fc3d_probability(tickets)
        assert info["total_coverage"] == 2
        assert info["expected_return"] == round(2 * (1 / 1000 * 1040), 2)
        assert "直选×2" in info["breakdown"]

    def test_zuxuan_keeps_shape_based_coverage(self):
        from caipiao.ui.main_window import MainWindow

        tickets = [self._make([1, 2, 3], "组选"), self._make([1, 1, 2], "组选")]
        info = MainWindow._calc_fc3d_probability(tickets)
        assert info["total_coverage"] == 9  # 6 + 3
        expected = 6 / 1000 * 173 + 3 / 1000 * 346
        assert info["expected_return"] == round(expected, 2)

    def test_display_label(self):
        from caipiao.ui.main_window import MainWindow

        assert MainWindow._fc3d_display_label(self._make([1, 2, 3], "直选")) == "直选"
        assert MainWindow._fc3d_display_label(self._make([1, 2, 3], "组选")) == "组选6"
        assert MainWindow._fc3d_display_label(self._make([1, 1, 2], "组选")) == "组选3"
        legacy = Ticket(profile="3d", groups={"pos": [1, 2, 3]})
        assert MainWindow._fc3d_display_label(legacy) == "组选6"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py::TestFc3dProbabilityPanel -v`
Expected: FAIL（`_fc3d_display_label` 不存在；coverage 断言不符）

- [ ] **Step 3: 新增标签 helper 并改展示**

在 `MainWindow` 中 `_calc_fc3d_probability` 附近新增静态方法：

```python
    @staticmethod
    def _fc3d_display_label(ticket) -> str:
        """3D 号码的展示标签：按投注方式，组选票附带形态（组选3/组选6）。"""
        nums = ticket.groups.get("pos", [])
        bet_mode = ticket.details.get("bet_mode")
        if bet_mode == "直选":
            return "直选"
        if bet_mode == "组选":
            unique = len(set(nums))
            if unique == 2:
                return "组选3"
            if unique == 3:
                return "组选6"
            return "直选"  # 豹子号兜底（生成时已转直选，正常不会到这里）
        return fc3d_bet_type(nums)
```

`_update_result_text`（:2186-2187）改为：

```python
            line = f"{idx:02d}. {ticket.format_compact()}"
            line += f"  [{MainWindow._fc3d_display_label(ticket)}]"
```

`_build_print_html`（:2281-2282）改为：

```python
            if ticket.profile.key == "3d":
                compact += f"  [{MainWindow._fc3d_display_label(ticket)}]"
```

`_refresh_editable_table`（:2050-2052）取消排序显示：

```python
            nums = ticket.groups.get("pos", [])
            # 3D 为按位有序组，保持原始顺序显示（直选位置有意义）
            num_str = "".join(str(n) for n in nums)
            bet_type = MainWindow._fc3d_display_label(ticket)
```

`_on_number_edited`（:2099-2102）改为：

```python
        # 更新ticket（3D 为按位有序组，保持用户输入顺序）
        if 0 <= row < len(self._editable_tickets):
            nums = [int(c) for c in new_num]
            self._editable_tickets[row].groups["pos"] = nums
```

`_add_custom_number`（:2122）改为：

```python
        nums = [int(c) for c in num_str]  # 按位有序，保持输入顺序
```

`_add_random_number`（:2168）改为：

```python
        # 按位有序，保持生成顺序
        from ..core.ticket import Ticket
```

（即删掉 `nums = sorted(nums)` 一行，保留其后代码。）

- [ ] **Step 4: 改 `_calc_fc3d_probability` 按投注方式计算**

将 :1890-1934 的循环与期望收益部分改为：

```python
        count_zhi = 0

        for t in tickets:
            digits = t.groups.get("pos", [])
            if len(digits) != 3:
                continue
            key = tuple(sorted(digits))
            if key in seen_sets:
                continue
            seen_sets.add(key)

            bet_mode = t.details.get("bet_mode")
            unique = len(set(digits))
            if bet_mode == "直选":
                total_coverage += 1
                count_zhi += 1
            elif unique == 3:
                total_coverage += 6
                count_z6 += 1
            elif unique == 2:
                total_coverage += 3
                count_z3 += 1
            else:
                total_coverage += 1
                count_bz += 1

            if has_valid_probs:
                confidence += sum(
                    pos_probs[0][p[0]] * pos_probs[1][p[1]] * pos_probs[2][p[2]]
                    for p in set(permutations(digits))
                )

        abs_p = total_coverage / 1000 * 100

        # 期望收益 = Σ(每种注数 × 中奖概率 × 奖金)，按投注方式区分
        expected_return = (
            count_zhi * (1 / 1000 * MainWindow._FC3D_PRIZE_ZHI)
            + count_z6 * (6 / 1000 * MainWindow._FC3D_PRIZE_Z6)
            + count_z3 * (3 / 1000 * MainWindow._FC3D_PRIZE_Z3)
            + count_bz * (1 / 1000 * MainWindow._FC3D_PRIZE_ZHI)
        )
        total_cost = len(tickets) * MainWindow._FC3D_TICKET_COST
        return_rate = (expected_return / total_cost * 100) if total_cost > 0 else 0.0

        parts = []
        if count_zhi:
            parts.append(f"直选×{count_zhi}")
        if count_z6:
            parts.append(f"组选6×{count_z6}")
        if count_z3:
            parts.append(f"组选3×{count_z3}")
        if count_bz:
            parts.append(f"豹子×{count_bz}")
        breakdown = " ".join(parts) if parts else "无"
```

同时在 :1881 的计数器初始化处加上 `count_zhi = 0`（若 Step 代码未覆盖到该处）。返回 dict 结构不变。

- [ ] **Step 5: 运行测试确认通过**

Run: `venv/Scripts/python -m pytest tests/test_fc3d_bet_mode.py -v`
Expected: PASS（全部用例）

- [ ] **Step 6: 提交**

```bash
git add caipiao/ui/main_window.py tests/test_fc3d_bet_mode.py
git commit -m "feat(fc3d): 界面与PDF展示投注方式，概率面板按投注方式计算，修复3D有序号码排序"
```

---

### Task 5: 全量回归与手动冒烟

**Files:** 无新增修改（回归验证 + 必要时修复）。

- [ ] **Step 1: 全量测试**

Run: `venv/Scripts/python -m pytest tests/ -x -q`
Expected: 全部通过。若有旧测试断言了 fc3d 奖金旧行为（如无序匹配发组选奖金），逐一核对：属于「无 bet_mode 兜底路径」的应仍通过；若失败说明兜底逻辑被破坏，回到 Task 2 修复。

- [ ] **Step 2: 脚本回测冒烟**

Run: `venv/Scripts/python scripts/run_30day_all_strategies.py`（若依赖网络数据则跳过，改跑已有的批量回测集成测试 `venv/Scripts/python -m pytest tests/test_batch_backtest_integration.py -q`）
Expected: 正常结束，无异常。

- [ ] **Step 3: UI 手动冒烟**

Run: `venv/Scripts/python main.py`
操作与预期：
1. 切换到福彩3D，生成 5 注 → 列表前 3 注显示 `[组选6]`/`[组选3]`，后 2 注显示 `[直选]`；
2. 号码顺序与生成时一致（不再被排序）；
3. 手动编辑一注为 `321` → 表格保持 `321` 不变；
4. 导出 PDF → 标签与列表一致；
5. 概率面板 breakdown 出现 `直选×N`。
如有问题，修复后补对应测试。

- [ ] **Step 4: 最终提交（如有修复）**

```bash
git add -A
git commit -m "fix(fc3d): 投注方式功能回归修复"
```
