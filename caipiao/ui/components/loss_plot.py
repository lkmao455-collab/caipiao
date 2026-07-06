"""训练损失曲线实时显示窗口（纯文本版，避免 matplotlib 崩溃）."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QDialog, QLabel, QPushButton, QTextEdit,
    QVBoxLayout,
)


class LossPlotWindow(QDialog):
    """浮动窗口，实时显示训练 loss 数据，支持导出 CSV。"""

    data_ready = Signal(str, float)

    def __init__(self, parent=None, title: str = "训练 Loss 曲线"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 380)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self._losses: dict[str, list[tuple[int, float]]] = {}
        self._init_ui()
        self.data_ready.connect(self._update_plot)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self._status_label = QLabel("等待训练开始...")
        layout.addWidget(self._status_label)

        self._text_display = QTextEdit()
        self._text_display.setReadOnly(True)
        self._text_display.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt;"
        )
        layout.addWidget(self._text_display)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._export_csv_btn = QPushButton("导出 CSV")
        self._export_csv_btn.clicked.connect(self._export_csv)
        self._export_csv_btn.setEnabled(False)
        btn_layout.addWidget(self._export_csv_btn)

        layout.addLayout(btn_layout)

    def add_loss(self, model_name: str, epoch: int, loss: float):
        """线程安全地添加 loss 数据."""
        self.data_ready.emit(f"{model_name}|{epoch}", loss)

    def _update_plot(self, key: str, loss: float):
        parts = key.split("|")
        model_name = parts[0]
        epoch = int(parts[1])

        if model_name not in self._losses:
            self._losses[model_name] = []
        self._losses[model_name].append((epoch, loss))

        self._status_label.setText(f"{model_name} - Epoch {epoch}, Loss: {loss:.4f}")

        self._export_csv_btn.setEnabled(True)

        # 用文本模拟折线图
        lines = []
        for name, data in self._losses.items():
            lines.append(f"━━━ {name} ━━━")
            if not data:
                lines.append("  (无数据)")
                continue
            min_loss = min(d[1] for d in data)
            max_loss = max(d[1] for d in data)
            span = max_loss - min_loss if max_loss > min_loss else 1.0
            bar_width = 40
            for ep, lv in data:
                bar_len = int((lv - min_loss) / span * bar_width) if span > 0 else 0
                bar = "█" * bar_len + "░" * (bar_width - bar_len)
                lines.append(f"  E{ep:03d} │{bar}│ {lv:.4f}")
            lines.append("")
        self._text_display.setText("\n".join(lines))

        # 自动滚动到底部
        sb = self._text_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _export_csv(self):
        """导出 loss 数据为 CSV 文件."""
        default_name = f"loss_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Loss 数据", default_name, "CSV 文件 (*.csv)"
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            headers = ["Epoch"]
            for name in self._losses:
                headers.append(f"{name}_Loss")
            writer.writerow(headers)

            max_epochs = max(len(v) for v in self._losses.values()) if self._losses else 0
            for i in range(max_epochs):
                row = [i + 1]
                for name in self._losses:
                    if i < len(self._losses[name]):
                        row.append(f"{self._losses[name][i][1]:.6f}")
                    else:
                        row.append("")
                writer.writerow(row)

        self._status_label.setText(f"已导出: {Path(path).name}")

    def closeEvent(self, event):
        """正常关闭窗口."""
        event.accept()
