"""历史记录管理."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

from ..core.ticket import Ticket

logger = logging.getLogger(__name__)


class HistoryManager:
    """管理生成历史记录的增删改查与导入导出."""

    def __init__(self, storage_path: Path | str, max_entries: int = 1000) -> None:
        self.storage_path = Path(storage_path)
        self.max_entries = max_entries
        self._tickets: List[Ticket] = []
        self._load()

    def _load(self) -> None:
        """从文件加载历史."""
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._tickets = [Ticket.from_dict(item) for item in data]
        except Exception as exc:  # noqa: BLE001
            logger.error("加载历史记录失败: %s", exc)
            self._tickets = []

    def save(self) -> None:
        """保存历史到文件."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [ticket.to_dict() for ticket in self._tickets[-self.max_entries :]]
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, ticket: Ticket) -> None:
        """添加单条记录."""
        self._tickets.append(ticket)
        self._trim()
        self.save()

    def add_many(self, tickets: Iterable[Ticket]) -> None:
        """批量添加记录."""
        self._tickets.extend(tickets)
        self._trim()
        self.save()

    def _trim(self) -> None:
        """限制记录数量."""
        if len(self._tickets) > self.max_entries:
            self._tickets = self._tickets[-self.max_entries :]

    def get_all(self) -> List[Ticket]:
        """获取全部记录."""
        return self._tickets[:]

    def get_recent(self, days: int = 30) -> List[Ticket]:
        """获取最近 N 天的记录."""
        cutoff = datetime.now() - timedelta(days=days)
        return [t for t in self._tickets if t.generated_at >= cutoff]

    def clear(self) -> None:
        """清空历史."""
        self._tickets.clear()
        self.save()

    def delete(self, ticket: Ticket) -> bool:
        """删除指定记录."""
        try:
            self._tickets.remove(ticket)
            self.save()
            return True
        except ValueError:
            return False

    def export_csv(self, path: Path | str) -> None:
        """导出为 CSV."""
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["时间", "策略", "红球", "蓝球", "紧凑格式", "依据"])
            for t in self._tickets:
                writer.writerow(
                    [
                        t.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
                        t.strategy_name,
                        " ".join(f"{b.number:02d}" for b in t.red_balls),
                        f"{t.blue_ball.number:02d}",
                        t.format_compact(),
                        t.basis,
                    ]
                )

    def export_txt(self, path: Path | str) -> None:
        """导出为纯文本."""
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            for t in self._tickets:
                f.write(t.format_compact() + "\n")

    def import_from_json(self, path: Path | str) -> int:
        """从 JSON 导入历史记录."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        imported = [Ticket.from_dict(item) for item in data]
        self.add_many(imported)
        return len(imported)
