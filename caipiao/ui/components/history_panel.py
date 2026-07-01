"""历史记录面板."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QPageSize, QPdfWriter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.ticket import Ticket
from ...persistence.history import HistoryManager
from .ball_display import TicketRowWidget


class HistoryPanel(QWidget):
    """历史记录展示与管理面板."""

    history_changed = Signal()

    def __init__(
        self, history_manager: HistoryManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.history_manager = history_manager
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 顶部按钮
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("重新加载本地保存的历史记录。")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_csv_btn = QPushButton("导出 CSV")
        self.export_csv_btn.setToolTip("将历史记录导出为 CSV 表格文件。")
        self.export_csv_btn.clicked.connect(self._export_csv)
        self.export_txt_btn = QPushButton("导出 TXT")
        self.export_txt_btn.setToolTip("将历史记录导出为纯文本文件。")
        self.export_txt_btn.clicked.connect(self._export_txt)
        self.print_btn = QPushButton("打印历史")
        self.print_btn.setToolTip("打印历史记录（依赖系统打印机驱动）。")
        self.print_btn.clicked.connect(self._print_history)
        self.export_pdf_btn = QPushButton("导出 PDF")
        self.export_pdf_btn.setToolTip("将历史记录导出为 PDF 文件。")
        self.export_pdf_btn.clicked.connect(self._export_pdf_history)
        self.clear_btn = QPushButton("清空历史")
        self.clear_btn.setToolTip("删除所有本地保存的历史记录。")
        self.clear_btn.clicked.connect(self._clear)
        self.import_btn = QPushButton("导入 JSON")
        self.import_btn.setToolTip("从 JSON 文件导入历史记录。")
        self.import_btn.clicked.connect(self._import_json)

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.export_csv_btn)
        btn_layout.addWidget(self.export_txt_btn)
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.print_btn)
        btn_layout.addWidget(self.export_pdf_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)
        self.layout.addLayout(btn_layout)

        # 统计信息
        self.stats_label = QLabel("历史记录: 0 条")
        self.layout.addWidget(self.stats_label)

        # 历史列表
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.layout.addWidget(self.list_widget)

    def refresh(self) -> None:
        self.list_widget.clear()
        tickets = self.history_manager.get_all()
        self.stats_label.setText(f"历史记录: {len(tickets)} 条")

        for idx, ticket in enumerate(tickets, start=1):
            item = QListWidgetItem()
            widget = TicketRowWidget(ticket, show_index=idx)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "history.csv", "CSV 文件 (*.csv)"
        )
        if path:
            self.history_manager.export_csv(Path(path))
            QMessageBox.information(self, "导出成功", f"已导出到: {path}")

    def _export_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 TXT", "history.txt", "文本文件 (*.txt)"
        )
        if path:
            self.history_manager.export_txt(Path(path))
            QMessageBox.information(self, "导出成功", f"已导出到: {path}")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 JSON", "", "JSON 文件 (*.json)"
        )
        if path:
            try:
                count = self.history_manager.import_from_json(Path(path))
                self.refresh()
                self.history_changed.emit()
                QMessageBox.information(self, "导入成功", f"成功导入 {count} 条记录")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "导入失败", str(exc))

    def _clear(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self.refresh()
            self.history_changed.emit()

    def add_ticket(self, ticket: Ticket) -> None:
        self.history_manager.add(ticket)
        self.refresh()
        self.history_changed.emit()

    def add_tickets(self, tickets: list[Ticket]) -> None:
        self.history_manager.add_many(tickets)
        self.refresh()
        self.history_changed.emit()

    def _print_history(self) -> None:
        """打印全部历史记录."""
        tickets = self.history_manager.get_all()
        if not tickets:
            QMessageBox.information(self, "提示", "没有可打印的历史记录")
            return
        self._print_tickets(tickets, "双色球历史记录")

    def _export_pdf_history(self) -> None:
        """导出历史记录为 PDF."""
        tickets = self.history_manager.get_all()
        if not tickets:
            QMessageBox.information(self, "提示", "没有可导出的历史记录")
            return
        self._export_tickets_to_pdf(tickets, "双色球历史记录")

    def _print_tickets(self, tickets: list[Ticket], title: str) -> None:
        """通用打印方法，打印失败时只提示一次."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        html = self._build_print_html(tickets, title)
        document = QTextEdit()
        document.setHtml(html)
        try:
            document.print_(printer)
        except Exception as exc:  # noqa: BLE001
            self._show_print_error_once(str(exc))

    def _export_tickets_to_pdf(self, tickets: list[Ticket], title: str) -> None:
        """导出为 PDF，不依赖打印机驱动."""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF", "caipiao_history.pdf", "PDF 文件 (*.pdf)"
        )
        if not path:
            return

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize.A4)
        html = self._build_print_html(tickets, title)
        document = QTextEdit()
        document.setHtml(html)
        try:
            document.print_(writer)
            QMessageBox.information(self, "导出成功", f"已导出到: {path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _show_print_error_once(self, message: str) -> None:
        """会话内只显示一次打印错误."""
        if getattr(self, "_print_error_shown", False):
            return
        self._print_error_shown = True

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("打印失败")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("调用系统打印服务失败，可能是所选打印机配置有误。")
        msg_box.setInformativeText(f"错误信息：{message}\n\n建议尝试使用“导出 PDF”功能。")

        check_box = QCheckBox("不再提示此错误")
        msg_box.setCheckBox(check_box)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
        self._print_error_shown = check_box.isChecked()

    @staticmethod
    def _build_print_html(tickets: list[Ticket], title: str) -> str:
        from datetime import datetime

        rows = []
        for idx, ticket in enumerate(tickets, start=1):
            reds = " ".join(
                f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
                f'text-align:center;border-radius:14px;background:#D32F2F;color:#fff;'
                f'margin:2px;font-weight:bold;">{b.number:02d}</span>'
                for b in ticket.red_balls
            )
            blue = (
                f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
                f'text-align:center;border-radius:14px;background:#1976D2;color:#fff;'
                f'margin:2px;font-weight:bold;">{ticket.blue_ball.number:02d}</span>'
            )
            rows.append(
                f"<tr>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;'><b>{idx:02d}.</b></td>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;'>{ticket.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;'>{reds} {blue}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #ddd;color:#666;'>{ticket.strategy_name}</td>"
                f"</tr>"
            )
            if ticket.basis:
                rows.append(
                    f"<tr><td></td><td></td>"
                    f"<td colspan='2' style='padding:0 8px 8px 8px;color:#888;font-size:12px;'>"
                    f"生成依据：{ticket.basis}</td></tr>"
                )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: "Microsoft YaHei", sans-serif; margin: 40px; }}
                h1 {{ color: #D32F2F; text-align: center; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #f5f5f5; padding: 10px; text-align: left; }}
                td {{ vertical-align: middle; }}
                .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 12px; }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            <p style="text-align:center;color:#666;">打印时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <table>
                <tr>
                    <th style="width:60px;">序号</th>
                    <th style="width:160px;">生成时间</th>
                    <th>号码</th>
                    <th style="width:120px;">策略</th>
                </tr>
                {''.join(rows)}
            </table>
            <p class="footer">本结果由双色球号码生成器生成，仅供娱乐参考。</p>
        </body>
        </html>
        """

