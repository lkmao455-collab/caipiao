# 福彩3D 直选/组选投注方式分配 设计文档

日期：2026-07-12
状态：已批准

## 背景

福彩3D 实际投注分「直选」（按位顺序完全一致才中奖，奖金 1040 元）和「组选」
（无序匹配即中奖，组选3 奖金 346 元、组选6 奖金 173 元；豹子号无组选玩法）。

当前代码中，fc3d 号码全部以有序三元组（`groups={"pos": [百,十,个]}`）生成，
`fc3d_bet_type()` 只按数字形态返回「豹子号/组选3/组选6」，不存在真正的
「直选/组选投注方式」概念；中奖判定 `core/prize.py:_fc3d_prize` 对所有票统一
先判直选、再按无序匹配判组选奖金。

## 需求

生成号码时按比例分配投注方式：

- 总数量 N 为偶数：一半直选、一半组选；
- 总数量 N 为奇数：组选比直选多一张（组选 `ceil(N/2)`、直选 `floor(N/2)`）。

已确认的决策：

1. **完整投注方式语义**：组选票与开奖号码无序匹配即中奖，按组选3/组选6 对应
   奖金（346/173 元）计算；直选票需顺序完全一致（1040 元）。影响回测、中奖
   统计、概率面板。
2. **所有入口统一生效**：主界面生成、单期回测、批量回测、脚本回测行为一致。
3. **豹子自动转直选**：组选票恰好是豹子号时改标直选，不补位（此时直选可能
   比组选多一张，总数不变）。

## 方案

引擎层统一后处理（对比过策略基类钩子方案：需改 11 处 Ticket 创建点，易漏改，
否决）。

### 1. 数据模型

`ticket.details["bet_mode"]` ∈ `"直选"` / `"组选"`。

- 随 `Ticket.to_dict()` 序列化（`details` 字段已持久化）；
- 历史数据无此字段时，中奖判定保持现有行为（向后兼容）。

### 2. 分配逻辑（生成侧）

插入点：`GenerationEngine.generate()`（`caipiao/core/engine.py:41`）返回前，
当 `self.profile.key == "fc3d"` 时对 tickets 做后处理（新增模块级 helper，
如 `assign_fc3d_bet_modes(tickets)`，放在 `engine.py` 或 `fc3d/utils.py`）：

- 按生成顺序，前 `ceil(N/2)` 张标 `"组选"`，其余标 `"直选"`；
- 标为组选的票若是豹子号（`fc3d_bet_type(nums) == "豹子号"`），改标 `"直选"`；
- 写入 `ticket.details["bet_mode"]`，不改动号码本身。

所有 4 个生成入口（`workers.py:161`、`backtest_worker.py:228`、
`scripts/run_30day_all_strategies.py:81` 及单期回测共享的
`GenerateTicketsThread`）都经过 `engine.generate`，零改动继承。

### 3. 中奖判定（判定侧）

修改 `core/prize.py:_fc3d_prize`（:31-64）：

- `bet_mode == "直选"`：`list(ticket) == list(actual)` → 1040，否则 0；
- `bet_mode == "组选"`：`sorted` 多重集相等即中，组选3 → 346、组选6 → 173
  （即使位置全对也按组选奖金，不发 1040）；豹子号兜底按直选规则；
- 无 `bet_mode`（旧数据）：保持现有逻辑不变。

`calculate_prize` 增加可选 `details: Optional[Dict[str, Any]] = None` 参数，
`_fc3d_prize` 从中取 `bet_mode`。三处调用方手边都有完整 ticket，改传
`ticket.details`：

- `caipiao/ui/components/backtest_dialog.py:397`
- `caipiao/core/backtest_worker.py:263`
- `scripts/run_30day_all_strategies.py:102`

每注成本 2 元不变（`backtest_worker.py:267`）。

### 4. 展示与副作用修正

- 主界面号码列表与 PDF 导出（`_build_print_html`，`main_window.py:2267`）在
  号码旁显示投注方式标签（如 `[直选]`、`[组选6]`，组选票形态后缀来自
  `fc3d_bet_type`）；
- `_calc_fc3d_probability`（`main_window.py:1858`）期望收益按 `bet_mode`
  分别用 1040 / 346 / 173 计算；
- 修复 UI 可编辑列表对 3D 号码强制排序写回的问题（`_on_number_edited`
  `main_window.py:2101`、`_add_custom_number` :2122、`_add_random_number`
  :2168）——`pos` 是有序组（`profile.py:206` positional=True），排序会破坏
  直选位置信息，3D 彩种应保留原始顺序。

### 5. 测试

新增/扩展测试（项目已有 pytest 套件，`tests/`）：

- 分配比例：N=1/2/3/10 时组选 `ceil(N/2)`、直选 `floor(N/2)`；
- 豹子转直选：组选区内的豹子号改标直选且不补位；
- 中奖判定：直选票位置错位不中；组选票无序匹配中 346/173、位置全对也只发
  组选奖金；旧数据（无 `bet_mode`）行为不变；
- `calculate_prize(details=...)` 参数传递。

## 不做的事（YAGNI）

- 不做用户可配置比例（需求固定 1:1）；
- 不改形态权重（`shape_weights`）等与本需求正交的逻辑；
- 不引入新的 Ticket 字段（复用 `details`）。
