"""老板键设置编辑器.

提供快捷键输入框，支持显示/隐藏主窗口的快捷键注册与实时生效。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)


class HotkeyEdit(QWidget):
    """捕获键盘组合键的输入框."""

    hotkey_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modifiers: set[str] = set()
        self._key: str = ""
        self._pressed_keys: set[int] = set()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText("点击此处并按快捷键...")
        self.edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.edit, 1)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setToolTip("清空快捷键")
        self.clear_btn.clicked.connect(self.clear_hotkey)
        layout.addWidget(self.clear_btn)

    def set_hotkey(self, hotkey: str) -> None:
        """设置显示的快捷键文本."""
        self.edit.setText(hotkey)

    def clear_hotkey(self) -> None:
        """清空快捷键."""
        self.edit.clear()
        self.hotkey_changed.emit("")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        self._pressed_keys.add(key)

        # 忽略单独的修饰键
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            event.accept()
            return

        modifiers = event.modifiers()
        parts: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")

        key_name = _key_to_name(key)
        if key_name:
            parts.append(key_name)

        if len(parts) >= 2 and key_name:
            hotkey = "+".join(parts)
            self.edit.setText(hotkey)
            self.hotkey_changed.emit(hotkey)
        else:
            self.edit.setText("+".join(parts))

        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self._pressed_keys.discard(event.key())
        event.accept()

    def focusInEvent(self, event) -> None:  # noqa: N802
        self.edit.setPlaceholderText("请按下快捷键组合（如 Ctrl+Shift+B）...")
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self.edit.setPlaceholderText("点击此处并按快捷键...")
        super().focusOutEvent(event)


def _key_to_name(key: int) -> str:
    """把 Qt 键值转换为可读字符串."""
    key_enum = Qt.Key(key)
    name = key_enum.name
    if name and name.startswith("Key_"):
        return name[4:]
    return ""


def parse_hotkey(hotkey: str) -> tuple[frozenset[str], str]:
    """把快捷键字符串解析为 (修饰键集合, 主键)."""
    parts = [p.strip() for p in hotkey.split("+") if p.strip()]
    if not parts:
        return frozenset(), ""
    modifiers = frozenset(parts[:-1])
    return modifiers, parts[-1]


def is_valid_hotkey(hotkey: str) -> bool:
    """校验快捷键是否合法（至少包含一个修饰键 + 一个主键）."""
    mods, key = parse_hotkey(hotkey)
    return bool(mods and key and key not in {"Ctrl", "Shift", "Alt", "Meta"})


def validate_hotkey_dialog(hotkey: str, parent: QWidget | None = None) -> bool:
    """校验快捷键并在非法时弹出提示."""
    if not hotkey:
        return True
    if not is_valid_hotkey(hotkey):
        QMessageBox.warning(
            parent,
            "快捷键无效",
            "老板键必须包含至少一个修饰键（Ctrl/Shift/Alt/Meta）和一个普通按键，\n"
            "例如：Ctrl+Shift+B、Alt+M。",
        )
        return False
    return True
