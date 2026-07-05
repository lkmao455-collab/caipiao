# 工具栏按钮迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“生成号码”页左侧的 5 个操作按钮迁移到主窗口顶部工具栏，使用现有喜庆 3D 图标，并移除原按钮以减少界面占位。

**Architecture:** 在 `MainWindow` 中新增 `_setup_toolbar()` 方法创建 `QToolBar` 和 5 个 `QAction`；工具栏使用图标+文字模式，触发信号复用原有业务槽函数；同时从 `_build_generate_tab()` 删除原 `QPushButton` 并把所有 `self.generate_btn` 状态引用迁移到 `self.generate_action`；最后补充浅色/深色主题下的 `QToolBar`/`QToolButton` 样式。

**Tech Stack:** Python 3.10+, PySide6, Pillow（图标已生成）, pytest

## Global Constraints

- 复用现有图标：`caipiao/ui/resources/toolbar/{generate,copy,print,pdf,save}.png`
- 工具栏按钮展示方式：图标+文字（`ToolButtonTextUnderIcon`）
- 工具栏位置：主窗口顶部菜单栏下方
- 不修改业务逻辑槽函数内部实现
- 不修改 `scripts/generate_toolbar_icons.py`
- 图标缺失时优雅降级为纯文字按钮
- 主题切换后工具栏样式需与当前主题一致

---

## File Structure

- **修改:** `caipiao/ui/main_window.py`
  - 新增 `_setup_toolbar()` 方法
  - 在 `_setup_ui()` 中调用 `_setup_toolbar()`
  - 在 `_build_generate_tab()` 中删除 5 个原按钮
  - 把 `self.generate_btn` 状态引用改为 `self.generate_action`
  - 在 `_light_stylesheet()` / `_dark_stylesheet()` 中增加工具栏样式
- **新增:** `tests/test_main_window_toolbar.py`
  - UI 冒烟测试：验证工具栏存在且包含 5 个指定操作

---

### Task 1: 创建顶部工具栏并绑定 5 个操作

**Files:**
- Modify: `caipiao/ui/main_window.py`
- Test: `tests/test_main_window_toolbar.py`（此阶段可先注释掉，Task 4 再启用）

**Interfaces:**
- Consumes: 现有业务槽函数 `_generate`, `_copy_all`, `_print_results`, `_export_pdf_results`, `_save_to_history`
- Produces: `self.toolbar: QToolBar`, `self.generate_action: QAction`, `self.copy_action: QAction`, `self.print_action: QAction`, `self.pdf_action: QAction`, `self.save_action: QAction`

- [ ] **Step 1: 导入 QToolBar**

在 `caipiao/ui/main_window.py` 的 `PySide6.QtWidgets` 导入块中加入 `QToolBar`：

```python
from PySide6.QtWidgets import (
    ...,
    QToolBar,
    ...,
)
```

- [ ] **Step 2: 添加 `_setup_toolbar()` 方法**

在 `MainWindow` 类中新增方法（建议放在 `_setup_menu()` 之后）：

```python
def _setup_toolbar(self) -> None:
    """创建顶部工具栏，集中放置常用生成操作."""
    self.toolbar = QToolBar("主工具栏", self)
    self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    self.toolbar.setMovable(False)
    self.addToolBar(self.toolbar)

    resources_dir = Path(__file__).resolve().parent / "resources" / "toolbar"

    def _load_icon(name: str) -> QIcon:
        path = resources_dir / f"{name}.png"
        if path.exists():
            return QIcon(str(path))
        return QIcon()

    actions = [
        ("generate", "立即生成", "根据当前策略生成号码。ML 策略首次会训练模型，请稍候。", self._generate),
        ("copy", "复制全部号码", "将生成的号码复制到剪贴板。", self._copy_all),
        ("print", "打印结果", "将生成的号码打印或导出为 PDF。", self._print_results),
        ("pdf", "导出 PDF", "将生成的号码导出为 PDF 文件，不依赖打印机驱动。", self._export_pdf_results),
        ("save", "保存到历史", "将本次生成的号码保存到本地历史记录。", self._save_to_history),
    ]

    for idx, (name, text, tooltip, slot) in enumerate(actions):
        action = QAction(_load_icon(name), text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(slot)
        self.toolbar.addAction(action)
        setattr(self, f"{name}_action", action)
```

- [ ] **Step 3: 在 `_setup_ui()` 中调用 `_setup_toolbar()`**

在 `_setup_ui()` 方法末尾、`_register_boss_key()` 之前添加：

```python
self._setup_toolbar()
```

确保调用顺序在 `_setup_menu()` 之后。

- [ ] **Step 4: 验证代码可导入**

Run: `python -c "from caipiao.ui.main_window import MainWindow; print('import ok')"`
Expected: `import ok`（此时原按钮仍在，功能不受影响）

---

### Task 2: 移除生成页左侧原 5 个按钮

**Files:**
- Modify: `caipiao/ui/main_window.py:321-350`

**Interfaces:**
- Consumes: 工具栏已创建的 5 个 `QAction`
- Produces: 左侧控制面板不再包含原按钮；`_build_generate_tab()` 更紧凑

- [ ] **Step 1: 删除按钮定义与布局代码**

在 `_build_generate_tab()` 中删除以下代码块：

```python
        # 生成按钮
        self.generate_btn = QPushButton("立即生成")
        self.generate_btn.setObjectName("generate_btn")
        self.generate_btn.setToolTip("根据当前策略生成号码。ML 策略首次会训练模型，请稍候。")
        self.generate_btn.clicked.connect(self._generate)
        left_layout.addWidget(self.generate_btn)

        # 复制按钮
        self.copy_btn = QPushButton("复制全部号码")
        self.copy_btn.setToolTip("将生成的号码复制到剪贴板。")
        self.copy_btn.clicked.connect(self._copy_all)
        left_layout.addWidget(self.copy_btn)

        # 打印按钮
        self.print_btn = QPushButton("打印结果")
        self.print_btn.setToolTip("将生成的号码打印或导出为 PDF。")
        self.print_btn.clicked.connect(self._print_results)
        left_layout.addWidget(self.print_btn)

        # 导出 PDF 按钮
        self.export_pdf_btn = QPushButton("导出 PDF")
        self.export_pdf_btn.setToolTip("将生成的号码导出为 PDF 文件，不依赖打印机驱动。")
        self.export_pdf_btn.clicked.connect(self._export_pdf_results)
        left_layout.addWidget(self.export_pdf_btn)

        # 保存按钮
        self.save_btn = QPushButton("保存到历史")
        self.save_btn.setToolTip("将本次生成的号码保存到本地历史记录。")
        self.save_btn.clicked.connect(self._save_to_history)
        left_layout.addWidget(self.save_btn)
```

- [ ] **Step 2: 验证按钮已移除**

Run: `grep -n "generate_btn\|copy_btn\|print_btn\|export_pdf_btn\|save_btn" caipiao/ui/main_window.py`
Expected: 仅剩余 `generate_btn` 在状态引用代码中（Task 3 处理），不再出现在 `_build_generate_tab()` 中。

---

### Task 3: 迁移生成按钮状态引用到工具栏 Action

**Files:**
- Modify: `caipiao/ui/main_window.py:1269-1347`

**Interfaces:**
- Consumes: `self.generate_action`（Task 1 创建）
- Produces: 生成过程中工具栏“立即生成”按钮正确显示禁用/文本状态

- [ ] **Step 1: 替换 `_generate()` 中的引用**

把：
```python
self.generate_btn.setEnabled(False)
self.generate_btn.setText("准备模型...")
```
替换为：
```python
self.generate_action.setEnabled(False)
self.generate_action.setText("准备模型...")
```

两处（双色球 ML 策略分支和非双色球 ML 策略分支）都要替换。

- [ ] **Step 2: 替换 `_launch_generation()` 中的引用**

把：
```python
self.generate_btn.setEnabled(False)
self.generate_btn.setText("生成中...")
```
替换为：
```python
self.generate_action.setEnabled(False)
self.generate_action.setText("生成中...")
```

- [ ] **Step 3: 替换 `_after_generate_train()` 中的引用**

把该函数中所有 3 处：
```python
self.generate_btn.setEnabled(True)
self.generate_btn.setText("立即生成")
```
替换为：
```python
self.generate_action.setEnabled(True)
self.generate_action.setText("立即生成")
```

- [ ] **Step 4: 替换 `_on_generation_finished()` 中的引用**

把：
```python
self.generate_btn.setEnabled(True)
self.generate_btn.setText("立即生成")
```
替换为：
```python
self.generate_action.setEnabled(True)
self.generate_action.setText("立即生成")
```

- [ ] **Step 5: 删除已失效的 `QPushButton#generate_btn` 样式**

在 `_light_stylesheet()` 和 `_dark_stylesheet()` 中，删除 `#generate_btn` 专用样式块（该按钮已不存在）。Task 4 会为工具栏补充样式。

- [ ] **Step 6: 验证无残留 `generate_btn` 引用**

Run: `grep -n "generate_btn" caipiao/ui/main_window.py`
Expected: 无匹配输出。

---

### Task 4: 为主题样式表增加工具栏样式

**Files:**
- Modify: `caipiao/ui/main_window.py:1836-1946`（浅色样式）、`1949-2059`（深色样式）

**Interfaces:**
- Consumes: 现有 `_light_stylesheet()` / `_dark_stylesheet()`
- Produces: 工具栏在浅色/深色主题下视觉一致

- [ ] **Step 1: 在 `_light_stylesheet()` 末尾追加工具栏样式**

```python
        QToolBar {
            background-color: rgba(255, 255, 255, 0.45);
            border: 1px solid rgba(0, 119, 182, 0.25);
            border-radius: 10px;
            padding: 4px;
            spacing: 6px;
        }
        QToolButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #E1EEF7);
            color: #0A2540;
            border: 1px solid rgba(0, 119, 182, 0.35);
            border-radius: 8px;
            padding: 6px 8px;
            font-weight: bold;
            font-size: 9pt;
        }
        QToolButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E1EEF7, stop:1 #CCE3F2);
            border: 1px solid #48CAE4;
        }
        QToolButton:pressed {
            background: #B8D9ED;
        }
        QToolButton::icon {
            padding-bottom: 2px;
        }
```

- [ ] **Step 2: 在 `_dark_stylesheet()` 末尾追加工具栏样式**

```python
        QToolBar {
            background-color: rgba(16, 24, 39, 0.55);
            border: 1px solid rgba(0, 210, 255, 0.25);
            border-radius: 10px;
            padding: 4px;
            spacing: 6px;
        }
        QToolButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0F172A, stop:1 #1E293B);
            color: #E0F7FF;
            border: 1px solid rgba(0, 210, 255, 0.35);
            border-radius: 8px;
            padding: 6px 8px;
            font-weight: bold;
            font-size: 9pt;
        }
        QToolButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1E293B, stop:1 #334155);
            border: 1px solid #48CAE4;
        }
        QToolButton:pressed {
            background: #0B1220;
        }
        QToolButton::icon {
            padding-bottom: 2px;
        }
```

- [ ] **Step 3: 验证样式表语法**

Run: `python -c "from caipiao.ui.main_window import MainWindow; print('light len', len(MainWindow._light_stylesheet())); print('dark len', len(MainWindow._dark_stylesheet()))"`
Expected: 两条长度输出，无异常。

---

### Task 5: 添加工具栏 UI 冒烟测试

**Files:**
- Create: `tests/test_main_window_toolbar.py`

**Interfaces:**
- Consumes: `MainWindow` 类
- Produces: 自动化验证工具栏存在且包含 5 个指定操作

- [ ] **Step 1: 编写测试文件**

```python
"""主窗口工具栏冒烟测试."""

import pytest


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.slow
@pytest.mark.filterwarnings("ignore:.*")
def test_main_window_has_toolbar_with_five_actions(tmp_path, monkeypatch):
    """启动 MainWindow 后，顶部工具栏应包含 5 个指定操作."""
    _ensure_qapp()

    from caipiao.ui.main_window import MainWindow
    from caipiao.utils import app_data_dir

    # 使用临时数据目录，避免污染真实数据
    monkeypatch.setattr(
        "caipiao.ui.main_window.app_data_dir", lambda: tmp_path / ".caipiao"
    )
    monkeypatch.setattr(
        "caipiao.ui.lottery_context.app_data_dir", lambda: tmp_path / ".caipiao"
    )

    window = MainWindow()
    assert hasattr(window, "toolbar")
    assert window.toolbar is not None

    texts = [action.text() for action in window.toolbar.actions()]
    expected = ["立即生成", "复制全部号码", "打印结果", "导出 PDF", "保存到历史"]
    assert texts == expected
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_main_window_toolbar.py -v -m slow`
Expected: `test_main_window_has_toolbar_with_five_actions` PASS

---

### Task 6: 运行完整测试套件并手动冒烟验证

**Files:**
- N/A

**Interfaces:**
- Consumes: 前述所有修改
- Produces: 功能正确、无回归

- [ ] **Step 1: 运行全部自动化测试**

Run: `pytest tests/ -q`
Expected: 全部通过（或仅有与本次改动无关的既有失败）

- [ ] **Step 2: 手动启动应用验证**

Run: `python main.py`
Expected: 应用启动后可见顶部工具栏包含 5 个图标+文字按钮，且“生成号码”页左侧不再显示这 5 个按钮。

- [ ] **Step 3: 验证功能交互**

1. 选择一个生成策略，点击“立即生成”，确认号码生成。
2. 点击“复制全部号码”，确认剪贴板内容变化。
3. 点击“导出 PDF”，确认弹出保存对话框。
4. 点击“保存到历史”，确认历史页出现新记录。
5. 切换浅色/深色主题，确认工具栏样式正常。

---

## Self-Review

**Spec coverage:**
- 顶部工具栏创建 → Task 1
- 5 个图标+文字操作 → Task 1
- 删除原按钮 → Task 2
- 状态引用迁移 → Task 3
- 样式表 → Task 4
- 图标缺失降级 → Task 1 中 `_load_icon` 返回空 `QIcon`
- 测试验证 → Task 5、Task 6

**Placeholder scan:**
- 无 TBD/TODO/"implement later"/"适当处理" 等模糊表述
- 所有代码块均给出完整内容
- 命令包含预期输出

**Type consistency:**
- `self.generate_action` 全程使用 `QAction` 的 `setEnabled()` / `setText()`
- 其余 action 仅作为触发器，无状态修改
