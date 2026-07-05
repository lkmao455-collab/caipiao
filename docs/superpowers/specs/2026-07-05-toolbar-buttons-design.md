# 工具栏按钮迁移设计

## 目标

将“生成号码”页左侧的 5 个操作按钮：

- 立即生成
- 复制全部号码
- 打印结果
- 导出 PDF
- 保存到历史

迁移到主窗口顶部的工具栏（QToolBar），并为每个操作配置喜庆吉祥的 3D 风格图标，以减少左侧控制面板的垂直控件占位。

## 背景

当前 `caipiao/ui/main_window.py` 的 `_build_generate_tab()` 在左侧控制面板中垂直堆叠了 5 个 `QPushButton`。项目已通过 `scripts/generate_toolbar_icons.py` 生成了一套红色喜庆 3D 图标，存放在 `caipiao/ui/resources/toolbar/` 目录下，但尚未被主界面使用。

## 设计方案

### 1. 工具栏位置与内容

在主窗口 `_setup_ui()` 中，于菜单栏 (`_setup_menu()`) 调用之后创建 `QToolBar`，并设置为顶部工具栏：

```python
self.toolbar = self.addToolBar("主工具栏")
self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
```

工具栏按顺序添加 5 个 `QAction`：

| 操作 | 图标文件 | 文本 | tooltip | 触发槽 |
|---|---|---|---|---|
| 立即生成 | `toolbar/generate.png` | 立即生成 | 根据当前策略生成号码。ML 策略首次会训练模型，请稍候。 | `_generate` |
| 复制全部号码 | `toolbar/copy.png` | 复制全部号码 | 将生成的号码复制到剪贴板。 | `_copy_all` |
| 打印结果 | `toolbar/print.png` | 打印结果 | 将生成的号码打印或导出为 PDF。 | `_print_results` |
| 导出 PDF | `toolbar/pdf.png` | 导出 PDF | 将生成的号码导出为 PDF 文件，不依赖打印机驱动。 | `_export_pdf_results` |
| 保存到历史 | `toolbar/save.png` | 保存到历史 | 将本次生成的号码保存到本地历史记录。 | `_save_to_history` |

### 2. 图标处理

- 图标使用现有 64×64 PNG，显示时缩放到 32×32（通过 `QIcon` 自动缩放）。
- 图标路径：`Path(__file__).resolve().parent / "resources" / "toolbar" / "{name}.png"`。
- 若图标文件缺失，则不设置图标，降级为纯文字按钮，不影响功能。

### 3. 删除原按钮

在 `_build_generate_tab()` 中删除以下 5 个 `QPushButton` 的定义与 `left_layout.addWidget()` 调用：

- `self.generate_btn`
- `self.copy_btn`
- `self.print_btn`
- `self.export_pdf_btn`
- `self.save_btn`

### 4. 状态同步改造

原代码中通过 `self.generate_btn` 更新生成状态（禁用/启用、文本变化）的逻辑，需要迁移到 `self.generate_action`：

- `_generate()`：`self.generate_btn.setEnabled(False)` / `setText("准备模型...")` → `self.generate_action.setEnabled(False)` / `setText("准备模型...")`。
- `_launch_generation()`：`self.generate_btn.setEnabled(False)` / `setText("生成中...")` → `self.generate_action.setEnabled(False)` / `setText("生成中...")`。
- `_after_generate_train()`：错误/数据不足时恢复 `self.generate_action.setEnabled(True)` / `setText("立即生成")`。
- `_on_generation_finished()`：生成完成后恢复 `self.generate_action.setEnabled(True)` / `setText("立即生成")`。

其余 4 个操作均为瞬时动作，无需状态管理，直接连接触发信号即可。

### 5. 样式表

在 `_light_stylesheet()` 和 `_dark_stylesheet()` 中增加 `QToolBar` 与 `QToolButton` 样式：

- 工具栏背景与窗口渐变/背景色协调。
- 工具按钮 hover/pressed 状态使用与现有 `QPushButton` 相近的渐变配色。
- 文字颜色跟随当前主题。
- 工具按钮之间保持适当间距。

### 6. 快捷键

保持原有菜单栏/按钮的快捷键不变；本设计不引入新的全局快捷键，避免与菜单冲突。

## 影响范围

- `caipiao/ui/main_window.py`：新增工具栏、删除原按钮、更新状态引用、增加样式。
- 不改动业务逻辑（`_generate`、`_copy_all`、`_print_results`、`_export_pdf_results`、`_save_to_history` 等槽函数内部实现保持不变）。
- 不改动 `scripts/generate_toolbar_icons.py` 及已有图标文件。

## 验证标准

1. 启动后主窗口顶部出现包含 5 个图标+文字按钮的工具栏。
2. “生成号码”页左侧不再显示这 5 个按钮，控制面板更紧凑。
3. 点击工具栏按钮能正确触发对应功能。
4. 生成过程中“立即生成”按钮禁用并显示“生成中...”；生成完成后恢复。
5. 切换浅色/深色主题后工具栏样式正常。
6. 删除图标文件后，工具栏仍能以纯文字模式工作（降级）。
