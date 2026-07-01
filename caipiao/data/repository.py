"""历史数据仓库."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .models import DrawRecord

logger = logging.getLogger(__name__)


class DataRepository:
    """管理本地历史开奖数据的加载、保存与查询."""

    # 双色球每周二、四、日开奖（Python weekday(): 周一=0 ... 周日=6）
    DRAW_WEEKDAYS = (1, 3, 6)

    def __init__(self, storage_path: Path | str) -> None:
        self.storage_path = Path(storage_path)
        self._records: List[DrawRecord] = []
        self._load()

    def _load(self) -> None:
        """从本地文件加载数据，并清理重复记录."""
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            records = [DrawRecord.from_dict(item) for item in data]
            self._records = self._normalize_and_dedup(records)
            if len(self._records) != len(records):
                logger.info("已清理 %d 条重复记录", len(records) - len(self._records))
                self.save()
            logger.info("已加载 %d 条本地记录", len(self._records))
        except Exception as exc:  # noqa: BLE001
            logger.error("加载本地数据失败: %s", exc)
            self._records = []

    @staticmethod
    def _normalize_issue(record: DrawRecord) -> DrawRecord:
        """将期号统一为 4 位年份 + 3 位序号格式.

        例如：'03001' -> '2003001'，'2003001' 保持不变。
        """
        issue = record.issue.strip()
        if len(issue) < 3:
            return record
        try:
            sequence = int(issue[-3:])
            normalized = f"{record.draw_date.year}{sequence:03d}"
            if normalized != issue:
                return DrawRecord(
                    issue=normalized,
                    draw_date=record.draw_date,
                    red_balls=record.red_balls,
                    blue_ball=record.blue_ball,
                )
        except ValueError:
            pass
        return record

    def _normalize_and_dedup(self, records: List[DrawRecord]) -> List[DrawRecord]:
        """规范化期号并按日期去重."""
        normalized = [self._normalize_issue(r) for r in records]
        seen: set[str] = set()
        result: List[DrawRecord] = []
        for r in normalized:
            if r.issue not in seen:
                seen.add(r.issue)
                result.append(r)
        result.sort(key=lambda r: r.draw_date)
        return result

    def save(self) -> None:
        """保存数据到本地文件."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [record.to_dict() for record in self._records]
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update(self, records: List[DrawRecord]) -> int:
        """合并新记录，返回新增记录数."""
        normalized_new = self._normalize_and_dedup(records)
        existing_issues = {r.issue for r in self._records}
        new_records = [r for r in normalized_new if r.issue not in existing_issues]
        self._records.extend(new_records)
        self._records.sort(key=lambda r: r.draw_date)
        self.save()
        return len(new_records)

    def get_all(self) -> List[DrawRecord]:
        """获取全部记录."""
        return self._records[:]

    def get_recent(self, count: int = 100) -> List[DrawRecord]:
        """获取最近 N 期记录."""
        return self._records[-count:]

    def get_count(self) -> int:
        """获取记录总数."""
        return len(self._records)

    def get_latest(self) -> Optional[DrawRecord]:
        """获取最新一期记录."""
        return self._records[-1] if self._records else None

    def next_period_info(self) -> Optional[dict]:
        """根据最新一期记录推算下一期（即本次预测目标）的期号与开奖日期.

        返回字典 {base_issue, base_date, next_issue, next_date}；本地无数据时返回 None。
        用于在生成结果中提醒用户当前预测的是哪一期，避免忘记先更新最新开奖数据。
        """
        latest = self.get_latest()
        if latest is None:
            return None
        next_date = self._next_draw_date(latest.draw_date)
        next_issue = self._next_issue(latest.issue, next_date)
        return {
            "base_issue": latest.issue,
            "base_date": latest.draw_date,
            "next_issue": next_issue,
            "next_date": next_date,
        }

    @classmethod
    def _next_draw_date(cls, last_date: datetime) -> datetime:
        """给定上一期开奖日期，返回下一期开奖日期（周二/四/日）."""
        nxt = last_date + timedelta(days=1)
        while nxt.weekday() not in cls.DRAW_WEEKDAYS:
            nxt += timedelta(days=1)
        return nxt

    @staticmethod
    def _next_issue(latest_issue: str, next_date: datetime) -> str:
        """根据最新期号与下一期开奖日期推算下一期期号.

        期号为 4 位年份 + 3 位序号，跨年时序号从 001 重新计数；无法解析时返回空字符串。
        """
        issue = latest_issue.strip()
        try:
            year = int(issue[:4])
            sequence = int(issue[4:])
        except (ValueError, IndexError):
            return ""
        if next_date.year != year:
            return f"{next_date.year}001"
        return f"{year}{sequence + 1:03d}"

    def get_date_range(self) -> tuple[Optional[datetime], Optional[datetime]]:
        """获取数据日期范围."""
        if not self._records:
            return None, None
        return self._records[0].draw_date, self._records[-1].draw_date

    def get_records_before(self, cutoff: datetime) -> List[DrawRecord]:
        """获取指定日期之前的所有记录（不含当天）."""
        return [r for r in self._records if r.draw_date < cutoff]

    def get_record_by_date(self, draw_date: datetime) -> Optional[DrawRecord]:
        """按日期精确查找一条开奖记录."""
        for r in self._records:
            if r.draw_date.date() == draw_date.date():
                return r
        return None

    def clear(self) -> None:
        """清空本地数据."""
        self._records.clear()
        self.save()
