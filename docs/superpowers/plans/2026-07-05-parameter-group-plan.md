# 参数组功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现「一键找最优策略和参数」结果保存为参数组、在主窗口参数组标签页中选择并自由启用/禁用组内策略生成最新一期号码的功能。

**Architecture:** 新增 `ParameterGroup` 数据模型与 `ParameterGroupStore` 持久化层；新增保存对话框和主窗口参数组面板；复用主窗口现有生成逻辑（历史数据注入、ML 自动训练）对参数组中每个启用策略顺序生成并汇总结果。

**Tech Stack:** Python 3.10+, PySide6, dataclasses, JSON, pytest-qt（可选）

## Global Constraints

- 参数组按彩种隔离，文件存储在 `.caipiao/param_groups/<profile_key>.json`。
- 生成时每个启用的策略独立生成完整注数，结果汇总展示。
- 顺序生成，不并行训练多个 ML 模型。
- 每注必须标注来自哪个策略（`strategy_name` / `basis`）。
- 保持现有单策略生成入口行为不变。
- 所有新增代码需有对应单元测试。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `caipiao/core/parameter_group.py` | `StrategyParameterItem`、`ParameterGroup` 数据模型与序列化 |
| `caipiao/persistence/parameter_group_store.py` | 参数组按彩种 JSON 持久化：增删改查、重命名 |
| `caipiao/ui/components/parameter_group_save_dialog.py` | 一键扫描后保存参数组的对话框 |
| `caipiao/ui/components/parameter_group_panel.py` | 主窗口参数组标签页：列表、详情、启用勾选、生成 |
| `caipiao/ui/components/batch_backtest_dialog.py` | 扫描完成后新增「保存为参数组」按钮 |
| `caipiao/ui/main_window.py` | 新增参数组标签页、顺序生成逻辑、结果汇总 |
| `tests/test_parameter_group_model.py` | 数据模型序列化测试 |
| `tests/test_parameter_group_store.py` | 持久化存储测试 |
| `tests/test_parameter_group_dialog.py` | 保存对话框行为测试 |

---

### Task 1: 参数组数据模型

**Files:**
- Create: `caipiao/core/parameter_group.py`
- Test: `tests/test_parameter_group_model.py`

**Interfaces:**
- Produces: `StrategyParameterItem`, `ParameterGroup`, `parameter_group_to_dict`, `parameter_group_from_dict`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_parameter_group_model.py
from caipiao.core.parameter_group import (
    StrategyParameterItem,
    ParameterGroup,
    parameter_group_to_dict,
    parameter_group_from_dict,
)


def test_create_parameter_group():
    item = StrategyParameterItem(
        strategy_id="xgboost",
        strategy_name="XGBoost 智能分析",
        param_name="history_count",
        param_value=300,
        enabled=True,
        metrics={"total_fixed_prize": 100, "hit_count": 5},
    )
    group = ParameterGroup(
        id="g1",
        name="测试组",
        profile_key="ssq",
        created_at="2026-07-05T10:00:00",
        scan_context={"start_date": "2026-01-01", "end_date": "2026-06-30"},
        items=[item],
    )
    assert group.items[0].strategy_id == "xgboost"
    assert group.items[0].metrics["hit_count"] == 5


def test_roundtrip_serialization():
    item = StrategyParameterItem(
        strategy_id="smart_hot_cold",
        strategy_name="智能冷热号",
        param_name="lookback",
        param_value=100,
        enabled=True,
        metrics={"total_fixed_prize": 80, "hit_count": 3},
    )
    group = ParameterGroup(
        id="g2",
        name="最优组",
        profile_key="ssq",
        created_at="2026-07-05T10:00:00",
        scan_context={},
        items=[item],
    )
    data = parameter_group_to_dict(group)
    restored = parameter_group_from_dict(data)
    assert restored.id == "g2"
    assert restored.items[0].param_value == 100
    assert restored.items[0].metrics["hit_count"] == 3


def test_backward_compatible_missing_fields():
    data = {
        "id": "g3",
        "name": "旧数据",
        "profile_key": "ssq",
        "created_at": "2026-07-05T10:00:00",
        "items": [
            {
                "strategy_id": "random",
                "strategy_name": "完全随机",
                "param_name": None,
                "param_value": None,
                "enabled": True,
                "metrics": {},
            }
        ],
    }
    restored = parameter_group_from_dict(data)
    assert restored.scan_context == {}
    assert restored.items[0].metrics == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_parameter_group_model.py -v`
Expected: 3 FAIL（`caipiao.core.parameter_group` 未定义）

- [ ] **Step 3: 实现最小模型**

```python
# caipiao/core/parameter_group.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class StrategyParameterItem:
    strategy_id: str
    strategy_name: str
    param_name: str | None
    param_value: int | None
    enabled: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterGroup:
    id: str
    name: str
    profile_key: str
    created_at: str
    items: List[StrategyParameterItem]
    scan_context: Dict[str, Any] = field(default_factory=dict)


def parameter_group_to_dict(group: ParameterGroup) -> dict:
    return asdict(group)


def parameter_group_from_dict(data: dict) -> ParameterGroup:
    items = [
        StrategyParameterItem(
            strategy_id=item.get("strategy_id", ""),
            strategy_name=item.get("strategy_name", ""),
            param_name=item.get("param_name"),
            param_value=item.get("param_value"),
            enabled=item.get("enabled", True),
            metrics=item.get("metrics", {}),
        )
        for item in data.get("items", [])
    ]
    return ParameterGroup(
        id=data.get("id", ""),
        name=data.get("name", ""),
        profile_key=data.get("profile_key", ""),
        created_at=data.get("created_at", ""),
        items=items,
        scan_context=data.get("scan_context", {}),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_parameter_group_model.py -v`
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/core/parameter_group.py tests/test_parameter_group_model.py
git commit -m "feat: add parameter group data model"
```

---

### Task 2: 参数组持久化存储

**Files:**
- Create: `caipiao/persistence/parameter_group_store.py`
- Test: `tests/test_parameter_group_store.py`

**Interfaces:**
- Consumes: `ParameterGroup`, `parameter_group_to_dict`, `parameter_group_from_dict`
- Produces: `ParameterGroupStore` (methods: `load_all`, `save`, `delete`, `rename`, `get`)

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_parameter_group_store.py
import tempfile
from pathlib import Path

from caipiao.core.parameter_group import ParameterGroup, StrategyParameterItem
from caipiao.persistence.parameter_group_store import ParameterGroupStore


def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        group = ParameterGroup(
            id="g1",
            name="测试组",
            profile_key="ssq",
            created_at="2026-07-05T10:00:00",
            items=[
                StrategyParameterItem(
                    strategy_id="random",
                    strategy_name="完全随机",
                    param_name=None,
                    param_value=None,
                )
            ],
        )
        store.save(group)
        loaded = store.load_all("ssq")
        assert len(loaded) == 1
        assert loaded[0].name == "测试组"


def test_delete_and_rename():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        group = ParameterGroup(
            id="g2",
            name="可改名",
            profile_key="ssq",
            created_at="2026-07-05T10:00:00",
            items=[],
        )
        store.save(group)
        assert store.rename("ssq", "g2", "新名字")
        loaded = store.load_all("ssq")
        assert loaded[0].name == "新名字"
        assert store.delete("ssq", "g2")
        assert store.load_all("ssq") == []


def test_corrupted_file_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        store = ParameterGroupStore(Path(tmp))
        path = store.path_for("ssq")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        assert store.load_all("ssq") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_parameter_group_store.py -v`
Expected: 3 FAIL

- [ ] **Step 3: 实现存储类**

```python
# caipiao/persistence/parameter_group_store.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from ..core.parameter_group import ParameterGroup, parameter_group_from_dict, parameter_group_to_dict

logger = logging.getLogger(__name__)


class ParameterGroupStore:
    def __init__(self, data_dir: Path) -> None:
        self._base_dir = data_dir / "param_groups"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, profile_key: str) -> Path:
        return self._base_dir / f"{profile_key}.json"

    def load_all(self, profile_key: str) -> List[ParameterGroup]:
        path = self.path_for(profile_key)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("参数组文件损坏或读取失败: %s, 错误: %s", path, exc)
            return []
        if not isinstance(data, list):
            return []
        return [parameter_group_from_dict(item) for item in data]

    def save(self, group: ParameterGroup) -> None:
        groups = self.load_all(group.profile_key)
        updated = [g for g in groups if g.id != group.id]
        updated.append(group)
        self._write(group.profile_key, updated)

    def delete(self, profile_key: str, group_id: str) -> bool:
        groups = self.load_all(profile_key)
        before = len(groups)
        remaining = [g for g in groups if g.id != group_id]
        if len(remaining) == before:
            return False
        self._write(profile_key, remaining)
        return True

    def rename(self, profile_key: str, group_id: str, new_name: str) -> bool:
        groups = self.load_all(profile_key)
        for g in groups:
            if g.id == group_id:
                g.name = new_name
                self._write(profile_key, groups)
                return True
        return False

    def get(self, profile_key: str, group_id: str) -> ParameterGroup | None:
        for g in self.load_all(profile_key):
            if g.id == group_id:
                return g
        return None

    def _write(self, profile_key: str, groups: List[ParameterGroup]) -> None:
        path = self.path_for(profile_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                [parameter_group_to_dict(g) for g in groups],
                f,
                ensure_ascii=False,
                indent=2,
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_parameter_group_store.py -v`
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/persistence/parameter_group_store.py tests/test_parameter_group_store.py
git commit -m "feat: add parameter group persistence store"
```

---

### Task 3: 参数组保存对话框

**Files:**
- Create: `caipiao/ui/components/parameter_group_save_dialog.py`
- Test: `tests/test_parameter_group_dialog.py`

**Interfaces:**
- Consumes: `StrategyScanResult`, `ParameterGroupStore`
- Produces: `ParameterGroupSaveDialog`（带 `group_saved` 信号）

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_parameter_group_dialog.py
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from caipiao.core.parameter_group import ParameterGroup
from caipiao.ui.components.parameter_group_save_dialog import ParameterGroupSaveDialog
from caipiao.ui.batch_backtest_result import BatchBacktestResult


def test_auto_name_contains_date_and_count(qtbot):
    store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        ("xgboost", 300, BatchBacktestResult(total_rounds=10, total_fixed_prize=100, hit_count=5)),
        ("smart_hot_cold", 100, BatchBacktestResult(total_rounds=10, total_fixed_prize=80, hit_count=3)),
    ]
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    assert "前2策略" in dialog.name_edit.text()
    assert "ssq" not in dialog.name_edit.text()  # 名称面向用户，不必包含 profile_key


def test_save_emits_group_saved(qtbot):
    store = MagicMock()
    scan_result = MagicMock()
    scan_result.all_results = [
        ("xgboost", 300, BatchBacktestResult(total_rounds=10, total_fixed_prize=100, hit_count=5)),
    ]
    dialog = ParameterGroupSaveDialog(scan_result, "ssq", store)
    qtbot.addWidget(dialog)
    spy = []
    dialog.group_saved.connect(lambda g: spy.append(g))
    dialog._on_save()
    assert len(spy) == 1
    assert isinstance(spy[0], ParameterGroup)
    assert spy[0].items[0].strategy_id == "xgboost"
    store.save.assert_called_once()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_parameter_group_dialog.py -v`
Expected: 2 FAIL

- [ ] **Step 3: 实现保存对话框**

```python
# caipiao/ui/components/parameter_group_save_dialog.py
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from ...core.parameter_group import ParameterGroup, StrategyParameterItem
from ...persistence.parameter_group_store import ParameterGroupStore
from ..optimal_strategy_scan_thread import StrategyScanResult


class ParameterGroupSaveDialog(QDialog):
    group_saved = Signal(object)  # ParameterGroup

    def __init__(
        self,
        scan_result: StrategyScanResult,
        profile_key: str,
        store: ParameterGroupStore,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("保存为参数组")
        self.resize(500, 400)
        self._scan_result = scan_result
        self._profile_key = profile_key
        self._store = store

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "将「一键找最优策略和参数」的排名结果保存为参数组，"
            "方便日后在主窗口「参数组」标签页中快速生成号码。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setText(self._auto_name())
        form.addRow("参数组名称:", self.name_edit)

        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 10)
        self.top_n_spin.setValue(min(3, len(self._eligible_results())))
        self.top_n_spin.valueChanged.connect(self._update_preview)
        form.addRow("取前几名:", self.top_n_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("即将保存的策略:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)
        layout.addWidget(self.preview_text)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _eligible_results(self):
        return [r for r in self._scan_result.all_results if not r[2].errors]

    def _auto_name(self) -> str:
        return f"最优组_{datetime.now().strftime('%Y-%m-%d')}_前{len(self._eligible_results())}策略"

    def _update_preview(self) -> None:
        top_n = self.top_n_spin.value()
        results = self._eligible_results()[:top_n]
        lines = []
        for rank, (strategy_id, value, res) in enumerate(results, start=1):
            param_text = f" 参数={value}" if value is not None else ""
            lines.append(
                f"{rank}. {strategy_id}{param_text}: "
                f"固定奖金 {res.total_fixed_prize} 元, "
                f"中奖 {res.hit_count} 次"
            )
        self.preview_text.setText("\n".join(lines))

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "名称错误", "请输入参数组名称")
            return

        top_n = self.top_n_spin.value()
        results = self._eligible_results()[:top_n]
        if not results:
            QMessageBox.warning(self, "无可用结果", "没有可保存的非失败策略")
            return

        items = []
        for strategy_id, value, res in results:
            items.append(
                StrategyParameterItem(
                    strategy_id=strategy_id,
                    strategy_name=strategy_id,  # 名称在批量回测对话框中可再查 engine
                    param_name=self._scan_result.param_name if value is not None else None,
                    param_value=value,
                    enabled=True,
                    metrics={
                        "total_fixed_prize": res.total_fixed_prize,
                        "hit_count": res.hit_count,
                        "total_rounds": res.total_rounds,
                        "first_ticket_hit_count": res.first_ticket_hit_count,
                        "total_cost": res.total_cost,
                    },
                )
            )

        group = ParameterGroup(
            id=str(uuid4()),
            name=name,
            profile_key=self._profile_key,
            created_at=datetime.now().isoformat(),
            scan_context={
                "start_date": self._scan_result.optimal_result.ticket_results[0].get("date_str", "")
                if self._scan_result.optimal_result.ticket_results
                else "",
                "end_date": "",
                "tickets_per_round": 0,
                "generated_from_scan": True,
            },
            items=items,
        )

        self._store.save(group)
        self.group_saved.emit(group)
        QMessageBox.information(self, "保存成功", f"参数组「{name}」已保存")
        self.accept()
```

**注意：** `scan_context` 的日期可以在实现时从批量回测对话框传入 `start_date` / `end_date` / `tickets_per_round`，避免从 `ticket_results` 推断。在 Task 5 中调整调用处传入这些值。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_parameter_group_dialog.py -v`
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add caipiao/ui/components/parameter_group_save_dialog.py tests/test_parameter_group_dialog.py
git commit -m "feat: add parameter group save dialog"
```

---

### Task 4: 参数组面板

**Files:**
- Create: `caipiao/ui/components/parameter_group_panel.py`

**Interfaces:**
- Consumes: `ParameterGroupStore`, `ParameterGroup`, `StrategyParameterItem`
- Produces: `ParameterGroupPanel`（信号 `request_generate(items: List[StrategyParameterItem])`、`group_selected(group_id: str)`）

- [ ] **Step 1: 实现面板 UI 与加载逻辑**

```python
# caipiao/ui/components/parameter_group_panel.py
from __future__ import annotations

from typing import List

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.parameter_group import ParameterGroup, StrategyParameterItem
from ...persistence.parameter_group_store import ParameterGroupStore


class ParameterGroupPanel(QWidget):
    request_generate = Signal(list)  # List[StrategyParameterItem]

    def __init__(
        self,
        store: ParameterGroupStore,
        profile_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._profile_key = profile_key
        self._groups: List[ParameterGroup] = []
        self._item_checkboxes: dict[str, QCheckBox] = {}

        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 顶部：选择参数组
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("已保存参数组:"))
        self.group_list = QListWidget()
        self.group_list.setMaximumHeight(120)
        self.group_list.currentItemChanged.connect(self._on_group_changed)
        top_layout.addWidget(self.group_list, 1)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        top_layout.addWidget(self.refresh_btn)

        self.rename_btn = QPushButton("重命名")
        self.rename_btn.clicked.connect(self._on_rename)
        top_layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._on_delete)
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)

        # 详情区
        self.detail_group = QGroupBox("参数组详情")
        self.detail_layout = QVBoxLayout(self.detail_group)
        self.detail_layout.addWidget(QLabel("请选择一个参数组"))
        layout.addWidget(self.detail_group)

        # 生成数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("每组生成注数:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(5)
        count_layout.addWidget(self.count_spin)
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.clicked.connect(self._select_none)
        self.generate_btn = QPushButton("使用参数组生成号码")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.select_none_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.generate_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def set_profile_key(self, profile_key: str) -> None:
        self._profile_key = profile_key
        self.refresh()

    def refresh(self) -> None:
        self.group_list.clear()
        self._groups = self._store.load_all(self._profile_key)
        for g in self._groups:
            item = QListWidgetItem(g.name)
            item.setData(1, g.id)  # role 1 存储 group id
            self.group_list.addItem(item)
        self._clear_detail()

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.detail_layout.addWidget(QLabel("请选择一个参数组"))
        self._item_checkboxes.clear()

    def _on_group_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        self._clear_detail()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return

        self.detail_layout.addWidget(QLabel(f"名称: {group.name}"))
        self.detail_layout.addWidget(QLabel(f"创建时间: {group.created_at}"))
        self.detail_layout.addWidget(QLabel("策略列表（勾选以启用）："))

        for item in group.items:
            param_text = ""
            if item.param_name is not None and item.param_value is not None:
                param_text = f"  [{item.param_name}={item.param_value}]"
            metrics = item.metrics
            metric_text = (
                f"固定奖金 {metrics.get('total_fixed_prize', 0)} 元, "
                f"中奖 {metrics.get('hit_count', 0)} 次"
            )
            checkbox = QCheckBox(f"{item.strategy_name}{param_text} — {metric_text}")
            checkbox.setChecked(item.enabled)
            self.detail_layout.addWidget(checkbox)
            self._item_checkboxes[item.strategy_id] = checkbox

    def _select_all(self) -> None:
        for cb in self._item_checkboxes.values():
            cb.setChecked(True)

    def _select_none(self) -> None:
        for cb in self._item_checkboxes.values():
            cb.setChecked(False)

    def _enabled_items(self) -> List[StrategyParameterItem]:
        current = self.group_list.currentItem()
        if current is None:
            return []
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return []
        return [item for item in group.items if self._item_checkboxes.get(item.strategy_id, QCheckBox()).isChecked()]

    def _on_generate(self) -> None:
        items = self._enabled_items()
        if not items:
            QMessageBox.warning(self, "提示", "请至少启用一个策略")
            return
        self.request_generate.emit(items)

    def _on_rename(self) -> None:
        current = self.group_list.currentItem()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=group.name)
        if ok and new_name.strip():
            if self._store.rename(self._profile_key, group_id, new_name.strip()):
                self.refresh()

    def _on_delete(self) -> None:
        current = self.group_list.currentItem()
        if current is None:
            return
        group_id = current.data(1)
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除参数组「{group.name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(self._profile_key, group_id)
            self.refresh()
```

- [ ] **Step 2: 运行已有测试确保无回归**

Run: `python -m pytest tests/test_core.py tests/test_data.py -q`
Expected: 全部通过

- [ ] **Step 3: 提交**

```bash
git add caipiao/ui/components/parameter_group_panel.py
git commit -m "feat: add parameter group panel"
```

---

### Task 5: 批量回测对话框集成保存按钮

**Files:**
- Modify: `caipiao/ui/components/batch_backtest_dialog.py`

**Interfaces:**
- Consumes: `ParameterGroupSaveDialog`, `ParameterGroupStore`
- Produces: 扫描结果区新增「保存为参数组」按钮

- [ ] **Step 1: 在导入区添加依赖**

```python
from ...persistence.parameter_group_store import ParameterGroupStore
from .parameter_group_save_dialog import ParameterGroupSaveDialog
from ...utils import app_data_dir
```

- [ ] **Step 2: 在 `__init__` 中初始化 store**

```python
self._param_group_store = ParameterGroupStore(app_data_dir())
self._start_date_for_scan: str = ""
self._end_date_for_scan: str = ""
```

- [ ] **Step 3: 在 `_run_optimal_strategy_scan` 中记录日期范围**

在创建 `OptimalStrategyScanThread` 之前添加：

```python
self._start_date_for_scan = self.start_date_edit.date().toString("yyyy-MM-dd")
self._end_date_for_scan = self.end_date_edit.date().toString("yyyy-MM-dd")
```

- [ ] **Step 4: 在 `_on_strategy_scan_finished` 中添加保存按钮**

在设置 `summary_label` 文本之后、打印排名之前，添加保存按钮：

```python
self.save_group_btn = QPushButton("保存为参数组")
self.save_group_btn.clicked.connect(lambda: self._save_parameter_group(result))
self.status_text.append("")  # 空行
# 注意：QTextEdit 中直接嵌入按钮较麻烦，改为在控制区或汇总区放置按钮更稳。
```

**推荐做法**：将按钮放在 `summary_label` 同一区域的右下角。由于 `summary_label` 是 QLabel，可以换成一个 QWidget 包含 QLabel + QPushButton：

```python
# 在 _setup_ui 中，将 self.summary_label 替换为 summary_header
summary_header = QWidget()
summary_header_layout = QHBoxLayout(summary_header)
self.summary_label = QLabel("尚未开始批量历史回测。")
self.summary_label.setWordWrap(True)
self.summary_label.setStyleSheet(
    "QLabel { color: #0A2540; background-color: #E3F2FD; "
    "border-radius: 4px; padding: 6px; font-size: 11pt; font-weight: bold; }"
)
summary_header_layout.addWidget(self.summary_label, 1)
self.save_group_btn = QPushButton("保存为参数组")
self.save_group_btn.setToolTip("将本次扫描排名的前 N 个策略保存为参数组")
self.save_group_btn.clicked.connect(self._on_save_parameter_group)
self.save_group_btn.setVisible(False)
summary_header_layout.addWidget(self.save_group_btn)
result_layout.addWidget(summary_header)
```

并在 `_on_strategy_scan_finished` 成功时显示按钮：

```python
self.save_group_btn.setVisible(True)
```

- [ ] **Step 5: 实现保存槽函数**

```python
def _on_save_parameter_group(self) -> None:
    if getattr(self, "_last_strategy_scan_result", None) is None:
        return
    dialog = ParameterGroupSaveDialog(
        self._last_strategy_scan_result,
        self.profile.key,
        self._param_group_store,
        parent=self,
    )
    dialog.exec()

# 在 _on_strategy_scan_finished 中保存结果引用
self._last_strategy_scan_result = result
```

- [ ] **Step 6: 在关闭/重置时隐藏按钮**

在 `_run_batch_backtest`、`_run_optimal_period_scan`、`_run_optimal_strategy_scan` 开始时隐藏按钮：

```python
self.save_group_btn.setVisible(False)
```

- [ ] **Step 7: 运行测试确认无回归**

Run: `python -m pytest tests/test_optimal_strategy_scan.py tests/test_batch_backtest_integration.py -q`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add caipiao/ui/components/batch_backtest_dialog.py
git commit -m "feat: integrate parameter group save button into batch backtest dialog"
```

---

### Task 6: 主窗口新增参数组标签页与顺序生成

**Files:**
- Modify: `caipiao/ui/main_window.py`

**Interfaces:**
- Consumes: `ParameterGroupPanel`, `ParameterGroupStore`, `StrategyParameterItem`
- Produces: 主窗口新增「参数组」标签页、`_generate_from_parameter_group` 方法

- [ ] **Step 1: 添加导入**

```python
from .components.parameter_group_panel import ParameterGroupPanel
from ...persistence.parameter_group_store import ParameterGroupStore
from ...core.parameter_group import StrategyParameterItem
```

- [ ] **Step 2: 在 `__init__` 中初始化 store 和面板**

```python
# 在 self.context_manager 之后
self._param_group_store = ParameterGroupStore(self.data_dir)

# 在 _setup_ui 调用之前或之后都可以，但面板需要 current.profile
```

- [ ] **Step 3: 在 `_setup_ui` 中添加参数组标签页**

在「设置」标签页之后添加：

```python
# 参数组页
self.parameter_group_tab = self._build_parameter_group_tab()
self.tabs.addTab(self.parameter_group_tab, "参数组")
```

- [ ] **Step 4: 实现 `_build_parameter_group_tab`**

```python
def _build_parameter_group_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    self.parameter_group_panel = ParameterGroupPanel(
        self._param_group_store,
        self.current.profile.key,
        parent=tab,
    )
    self.parameter_group_panel.request_generate.connect(
        self._generate_from_parameter_group
    )
    layout.addWidget(self.parameter_group_panel)
    return tab
```

- [ ] **Step 5: 在 `_refresh_for_current_context` 中刷新面板**

```python
self.parameter_group_panel.set_profile_key(self.current.profile.key)
```

- [ ] **Step 6: 重构生成逻辑以支持顺序生成**

将 `_generate` 中的「准备并启动生成」部分提取为可复用的 `_run_generation_flow`。原 `_generate` 保持不变，仅将异步完成回调改为支持两种模式：单策略生成和参数组批量生成。

**修改 `_launch_generation`**：在创建线程后，记录当前回调：

```python
def _launch_generation(self, strategy_id, count, options, *, on_finished=None) -> None:
    self.generate_action.setEnabled(False)
    self.generate_action.setText("生成中...")
    self._generate_finished_callback = on_finished or self._on_generation_finished

    self._generate_thread = GenerateTicketsThread(
        self.current.engine, strategy_id, count, options, self
    )
    self._generate_thread.result_ready.connect(
        self._on_generation_finished_wrapper, Qt.ConnectionType.QueuedConnection
    )
    self._generate_thread.finished.connect(
        partial(self._cleanup_finished_thread, "_generate_thread")
    )
    self._generate_thread.start()


def _on_generation_finished_wrapper(self, tickets, error) -> None:
    callback = getattr(self, "_generate_finished_callback", self._on_generation_finished)
    callback(tickets, error)
```

**修改 `_generate`**：保持原逻辑，调用 `_launch_generation` 时不传 `on_finished`：

```python
self._launch_generation(strategy_id, count, options)
```

- [ ] **Step 7: 实现参数组顺序生成**

```python
def _generate_from_parameter_group(self, items: list[StrategyParameterItem]) -> None:
    if not items:
        QMessageBox.warning(self, "提示", "请至少启用一个策略")
        return

    self._parameter_group_items = list(items)
    self._parameter_group_tickets: list = []
    self._parameter_group_errors: list[str] = []
    self._parameter_group_count = self.parameter_group_panel.count_spin.value()

    self.generate_action.setEnabled(False)
    self.generate_action.setText("参数组生成中...")
    self._run_next_parameter_group_item()


def _run_next_parameter_group_item(self) -> None:
    if not self._parameter_group_items:
        self._finish_parameter_group_generation()
        return

    item = self._parameter_group_items.pop(0)
    strategy_id = item.strategy_id

    strategy = self.current.engine.get(strategy_id)
    if strategy is None:
        self._parameter_group_errors.append(f"策略 {item.strategy_name} 已不可用，已跳过")
        self._run_next_parameter_group_item()
        return

    options: dict = {}
    if item.param_name is not None and item.param_value is not None:
        options[item.param_name] = item.param_value

    count = self._parameter_group_count

    # 复用历史数据注入逻辑
    records: list[Any] = []
    if needs_history(strategy_id):
        records = self.current.data_repository.get_all()
        if not records:
            self._parameter_group_errors.append(f"{item.strategy_name}: 缺少历史数据")
            self._run_next_parameter_group_item()
            return
        options["history"] = records

    options["_training_record_count"] = len(options.get("history", records))

    # 使用新的 launch 接口，指定回调以继续队列
    self._launch_generation(
        strategy_id,
        count,
        options,
        on_finished=lambda tickets, error: self._on_parameter_group_item_finished(
            item, tickets, error
        ),
    )


def _on_parameter_group_item_finished(
    self, item: StrategyParameterItem, tickets, error
) -> None:
    if error:
        self._parameter_group_errors.append(f"{item.strategy_name}: {error}")
    elif tickets:
        for ticket in tickets:
            ticket.strategy_name = item.strategy_name
            if ticket.basis:
                ticket.basis = f"{item.strategy_name} | {ticket.basis}"
            else:
                ticket.basis = item.strategy_name
        self._parameter_group_tickets.extend(tickets)

    self._run_next_parameter_group_item()


def _finish_parameter_group_generation(self) -> None:
    self.generate_action.setEnabled(True)
    self.generate_action.setText("立即生成")

    tickets = self._parameter_group_tickets
    if not tickets:
        QMessageBox.warning(
            self,
            "生成失败",
            "参数组中所有策略均未能生成号码。\n"
            + "\n".join(self._parameter_group_errors[:5]),
        )
        return

    self._last_generated = tickets
    self._annotate_target_period(tickets)
    self._display_results(tickets)
    try:
        self.history_manager.add_many(tickets)
        self.history_panel.refresh()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(self, "保存历史失败", f"保存到历史记录失败:\n{exc}")

    if self._parameter_group_errors:
        QMessageBox.information(
            self,
            "部分策略未生成",
            "以下策略生成时出现问题：\n" + "\n".join(self._parameter_group_errors[:10]),
        )
```

- [ ] **Step 8: 处理原 `_on_generation_finished` 中的历史保存**

原 `_on_generation_finished` 会保存历史。由于 `_launch_generation` 现在使用回调包装器，单策略生成仍会走原 `_on_generation_finished`，行为不变。

- [ ] **Step 9: 运行测试确认无回归**

Run: `python -m pytest tests/test_main_window_toolbar.py tests/test_core.py -q`
Expected: 全部通过

- [ ] **Step 10: 提交**

```bash
git add caipiao/ui/main_window.py
git commit -m "feat: add parameter group tab and sequential generation in main window"
```

---

### Task 7: 全量测试与验证

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest tests/ -q`
Expected: 全部通过

- [ ] **Step 2: 手动验证流程**

1. 启动程序：`python main.py`
2. 进入「开奖数据」页，更新数据。
3. 进入「工具」→「批量历史回测」。
4. 点击「一键找最优策略和参数」。
5. 扫描完成后点击「保存为参数组」，选择前 3 名，保存。
6. 切换到主窗口「参数组」标签页，确认参数组已列出。
7. 勾选/取消勾选部分策略，设置每组生成注数。
8. 点击「使用参数组生成号码」，验证结果区显示多策略汇总结果。
9. 关闭程序，重新启动，确认参数组仍然保留。

- [ ] **Step 3: 提交**

```bash
git add .
git commit -m "test: verify parameter group feature end-to-end"
```

---

## Self-Review

### Spec Coverage

| 设计需求 | 对应 Task |
|---|---|
| 数据模型 | Task 1 |
| 按彩种持久化 | Task 2 |
| 保存对话框 | Task 3 |
| 主窗口参数组面板 | Task 4 |
| 回测对话框保存按钮 | Task 5 |
| 顺序生成与结果汇总 | Task 6 |
| 测试 | Task 7 |

### Placeholder Scan

- 无 TBD/TODO/"实现 later" 等占位符。
- 所有任务均包含具体代码和命令。

### Type Consistency

- `ParameterGroupStore` 方法签名在 Task 2 和 Task 3/4/5 中一致。
- `StrategyParameterItem` / `ParameterGroup` 字段在 Task 1 与后续任务中一致。
- `ParameterGroupPanel.request_generate` 发射 `List[StrategyParameterItem]`，与 `MainWindow._generate_from_parameter_group` 参数类型一致。

### 已知风险与应对

1. **ML 策略顺序训练耗时**：已在计划中说明顺序执行，避免并发。
2. **结果数量大**：面板内独立 `count_spin`，用户可控制每组注数。
3. **单策略生成入口回归**：原 `_generate` 调用 `_launch_generation` 时不传 `on_finished`，保持原 `_on_generation_finished` 回调。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-parameter-group-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**2. Inline Execution** - Execute tasks in this session using superpowers:executing-plans, batch execution with checkpoints for review.

Which approach?
