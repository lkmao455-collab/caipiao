# 参数组功能设计文档

## 1. 概述

### 目标
在「一键找最优策略和参数」扫描结果的基础上，让用户可以把排名靠前的多个策略（每个策略携带自己的最优参数）保存为一个**参数组**；之后用户可以在主窗口中选择一个参数组，自由决定启用/禁用组内的哪些策略，并据此生成最新一期号码。

### 使用场景
1. 用户在「批量历史回测」对话框点击「一键找最优策略和参数」。
2. 扫描完成后，用户看到完整排名，点击「保存为参数组」。
3. 用户选择取前几名（默认前 3 名）、填写名称或使用自动生成名称，点击保存。
4. 以后用户切换到主窗口的「参数组」标签页，选择该参数组。
5. 用户勾选想用的策略（可关闭表现不佳的策略），点击「生成号码」。
6. 每个启用的策略独立生成设置注数，最终汇总展示在同一结果区。

## 2. 需求确认

| 需求点 | 确认结果 |
|---|---|
| 参数组是什么 | 扫描排名中的前 N 个策略，每个策略保留其最优参数 |
| 生成时多策略如何组合 | 每个启用的策略独立生成全部注数，结果汇总展示 |
| 保存范围 | 按当前彩种分开保存 |
| 实现方案 | 独立模型 + 存储层 + UI 面板 |
| 生成逻辑 | 复用主窗口现有生成流程（含历史数据注入、ML 自动训练），顺序执行 |

## 3. 数据模型

### 3.1 StrategyParameterItem

单个策略参数条目，对应扫描排名中的一行。

```python
@dataclass
class StrategyParameterItem:
    strategy_id: str              # 策略唯一标识，如 "xgboost"
    strategy_name: str            # 策略中文名，如 "XGBoost 智能分析"
    param_name: str | None        # 被优化的参数名，如 "history_count"
    param_value: int | None       # 最优参数值，如 300
    enabled: bool = True          # 在参数组中是否默认启用
    metrics: dict = field(default_factory=dict)
    # metrics 包含：
    #   - total_fixed_prize: int   固定奖金合计
    #   - hit_count: int           中奖次数
    #   - total_rounds: int        回测期数
    #   - first_ticket_hit_count: int  首注中奖次数
    #   - total_cost: int          总花费
```

### 3.2 ParameterGroup

一个完整的参数组。

```python
@dataclass
class ParameterGroup:
    id: str                       # 唯一标识，uuid4
    name: str                     # 用户命名或自动生成名称
    profile_key: str              # 所属彩种，如 "ssq"
    created_at: str               # ISO 格式创建时间
    scan_context: dict            # 扫描时的上下文，便于追溯
    # scan_context 包含：
    #   - start_date: str          回测起始日期
    #   - end_date: str            回测结束日期
    #   - tickets_per_round: int   每期注数
    #   - generated_from_scan: bool 是否来自一键扫描
    items: List[StrategyParameterItem]
```

## 4. 持久化

### 4.1 存储位置

按彩种分别存储在应用数据目录下：

```
.caipiao/
  param_groups/
    ssq.json
    3d.json
    qlc.json
    ...
```

### 4.2 ParameterGroupStore

```python
class ParameterGroupStore:
    def __init__(self, data_dir: Path) -> None: ...

    def path_for(self, profile_key: str) -> Path: ...

    def load_all(self, profile_key: str) -> List[ParameterGroup]: ...

    def save(self, group: ParameterGroup) -> None: ...

    def delete(self, profile_key: str, group_id: str) -> bool: ...

    def rename(self, profile_key: str, group_id: str, new_name: str) -> bool: ...

    def get(self, profile_key: str, group_id: str) -> ParameterGroup | None: ...
```

### 4.3 序列化格式

JSON，可直接由 `dataclasses.asdict()` 序列化，反序列化时做字段兼容（未来新增字段不报错）。

## 5. UI 组件与流程

### 5.1 ParameterGroupSaveDialog（新增）

在「一键找最优策略和参数」扫描完成后弹出，或在批量回测对话框中点击「保存为参数组」后弹出。

界面元素：
- 参数组名称输入框（默认自动生成，如 `最优组_2026-07-05_前3策略`）
- 取前几名：QSpinBox，范围 1-10，默认 3
- 名称预览/自动命名规则说明
- 保存 / 取消 按钮
- 简要展示即将保存的策略列表（名称 + 参数 + 指标）

行为：
- 根据选择的 `top_n` 从扫描结果 `all_results` 中取前 N 个非失败结果。
- 自动生成名称包含日期与策略数量。
- 用户可覆盖名称。
- 点击保存后通过 `ParameterGroupStore` 写入磁盘，对话框关闭。

### 5.2 ParameterGroupPanel（新增）

主窗口新增「参数组」标签页的核心组件。

界面元素：
- 已保存参数组下拉列表 / QListWidget
- 刷新按钮
- 删除 / 重命名 按钮
- 当前参数组详情区：显示每个条目的策略名、参数、回测指标、启用复选框
- 「全选」/「全不选」按钮
- 生成数量：复用主窗口的 `count_spin` 或面板内独立 SpinBox（建议复用主窗口）
- 「使用参数组生成号码」按钮
- 提示信息：当前彩种无参数组时显示占位文本

行为：
- 切换彩种时自动加载对应参数组列表。
- 选择参数组后展示条目详情。
- 用户勾选/取消勾选策略条目，仅影响本次生成。
- 点击生成后，收集所有 `enabled=True` 的条目，交给主窗口执行生成。

### 5.3 BatchBacktestDialog 改造

在 `_on_strategy_scan_finished` 中：
- 汇总区新增「保存为参数组」按钮。
- 点击后实例化 `ParameterGroupSaveDialog`，传入 `StrategyScanResult`。
- 保存成功后提示用户。

### 5.4 MainWindow 改造

- 在 `_setup_ui` 中新增「参数组」标签页，嵌入 `ParameterGroupPanel`。
- 为面板提供信号/槽连接：
  - 面板请求生成时，主窗口按顺序为每个启用条目调用生成逻辑，汇总结果后统一展示。
- 切换彩种时刷新面板。

## 6. 生成逻辑

### 6.1 入口

`ParameterGroupPanel` 在用户点击「使用参数组生成号码」后发射信号：

```python
request_generate = Signal(list)  # List[StrategyParameterItem]
```

`MainWindow` 连接该信号到 `_generate_from_parameter_group(items)`。

### 6.2 顺序生成

为避免多线程并行训练多个 ML 模型带来的复杂性和资源竞争，采用**顺序生成**：

1. 校验至少有一个启用条目。
2. 对每个启用条目：
   - 构造 `options = {item.param_name: item.param_value}`（若 param_name 为空则无此参数）。
   - 复用主窗口的 `_generate` 等价逻辑（注入历史数据、ML 模型自动训练、异步等待）。
   - 每完成一个策略，把生成的 tickets 追加到结果列表。
3. 所有策略完成后，调用 `_display_results` 展示合并后的 tickets。
4. 每注的 `strategy_name` / `basis` 标注来自哪个策略。

### 6.3 与现有逻辑的复用

提取一个内部辅助方法 `_generate_single_strategy(strategy_id, options)`：
- 处理历史数据注入。
- 处理 ML 模型训练异步回调。
- 返回 tickets 或错误。

原 `_generate` 可部分重构为调用此辅助方法，但保持现有单策略入口不变。

### 6.4 结果展示

- 所有 tickets 显示在同一结果区。
- 文本行格式：`序号. 紧凑号码  [策略名]`。
- 可视化行使用 `TicketRowWidget` 正常渲染。
- 目标期号信息以第一个 ticket 的 `details` 为准。

## 7. 错误处理

| 场景 | 处理方式 |
|---|---|
| 策略已不存在（插件被卸载） | 跳过该条目，生成结束后提示用户 |
| 参数 schema 已变化 | 使用条目中的参数值尝试生成；若校验失败，提示并跳过 |
| 没有启用任何策略 | 生成前直接提示「请至少启用一个策略」 |
| 历史数据不足 | 按现有逻辑弹出警告，跳过该策略，继续下一个 |
| ML 模型训练失败 | 按现有逻辑提示错误，跳过该策略，继续下一个 |
| 参数组文件损坏 | 加载时捕获异常，清空列表并提示用户 |

## 8. 测试策略

### 8.1 单元测试

- `tests/test_parameter_group_model.py`
  - `StrategyParameterItem` / `ParameterGroup` 创建、序列化、反序列化。
  - 缺失字段的向后兼容。
- `tests/test_parameter_group_store.py`
  - 保存、加载、删除、重命名。
  - 损坏文件的处理。

### 8.2 UI 集成测试

- `tests/test_parameter_group_dialog.py`
  - 保存对话框生成正确的 `ParameterGroup`。
  - 自动命名规则。
- `tests/test_parameter_group_panel.py`（如可行，使用 QtBot）
  - 勾选/取消勾选条目。
  - 空列表状态。

### 8.3 生成流程测试

- 使用 mock engine 验证 `_generate_from_parameter_group` 对每个启用条目调用生成。
- 验证多个策略生成的 tickets 被正确汇总。

## 9. 文件变更清单

### 新增文件
- `caipiao/core/parameter_group.py` — 数据模型
- `caipiao/persistence/parameter_group_store.py` — 持久化
- `caipiao/ui/components/parameter_group_save_dialog.py` — 保存对话框
- `caipiao/ui/components/parameter_group_panel.py` — 主窗口参数组面板
- `tests/test_parameter_group_model.py`
- `tests/test_parameter_group_store.py`
- `tests/test_parameter_group_dialog.py`

### 修改文件
- `caipiao/ui/components/batch_backtest_dialog.py`
  - `_on_strategy_scan_finished` 中新增「保存为参数组」按钮及槽函数。
- `caipiao/ui/main_window.py`
  - 新增「参数组」标签页。
  - 新增 `_generate_from_parameter_group` 方法。
  - 可能提取/复用现有生成逻辑。
- `caipiao/ui/strategy_panel.py`（可能不需要改动）
- `caipiao/persistence/settings.py`（可能不需要改动）

## 10. 风险与注意事项

1. **ML 策略训练时间**：参数组包含多个 ML 策略时，顺序训练可能耗时较长。后续可考虑增加进度提示。
2. **结果数量**：若参数组有 5 个策略，每个生成 5 注，则最终展示 25 注。需要在 UI 上明确告知用户。
3. **彩种隔离**：参数组严格按 `profile_key` 隔离，切换彩种后只显示当前彩种参数组。
4. **插件策略**：保存参数组时记录 `strategy_id` 和 `strategy_name`；若插件被卸载，生成时按 `strategy_id` 找不到策略则跳过。

## 11. 未来可扩展

- 参数组导入/导出为 JSON 文件，便于备份和分享。
- 为每个条目增加权重，支持加权投票生成精选号码。
- 参数组一键回测，验证保存的参数组在历史区间上的表现。
