"""历史数据仓库（多彩种统一）.

``DrawRepository`` 按彩种档案管理本地开奖数据。
旧类 ``DataRepository`` 保留为双色球专用别名，API 完全兼容。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, TypedDict

from ..core.profile import SSQ, LotteryProfile, get_profile
from .models import DrawRecord

logger = logging.getLogger(__name__)


class NextPeriodInfo(TypedDict):
    """下一期开奖信息。"""

    base_issue: str
    base_date: datetime
    next_issue: str
    next_date: datetime


class DrawRepository:
    """管理单彩种本地开奖数据的加载、保存与查询."""

    def __init__(
        self,
        storage_path: Path | str,
        profile: LotteryProfile | None = None,
    ) -> None:
        self.profile = profile or SSQ
        self.storage_path = Path(storage_path)
        self._records: List[DrawRecord] = []
        self._load()

    def _load(self) -> None:
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
            logger.info("已加载 %d 条 %s 本地记录", len(self._records), self.profile.name)
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.error("加载本地数据失败: %s", exc)
            self._records = []

    @staticmethod
    def _normalize_issue(record: DrawRecord) -> DrawRecord:
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
                    profile=record.profile,
                    groups=record.groups,
                )
        except ValueError:
            pass
        return record

    def _normalize_and_dedup(self, records: List[DrawRecord]) -> List[DrawRecord]:
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
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [record.to_dict() for record in self._records]
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update(self, records: List[DrawRecord]) -> int:
        normalized_new = self._normalize_and_dedup(records)
        existing_issues = {r.issue for r in self._records}
        new_records = [r for r in normalized_new if r.issue not in existing_issues]
        self._records.extend(new_records)
        self._records.sort(key=lambda r: r.draw_date)
        self.save()
        return len(new_records)

    def get_all(self) -> List[DrawRecord]:
        return self._records[:]

    def get_recent(self, count: int = 100) -> List[DrawRecord]:
        if count <= 0:
            return []
        return self._records[-count:]

    def get_count(self) -> int:
        return len(self._records)

    def get_latest(self) -> Optional[DrawRecord]:
        return self._records[-1] if self._records else None

    def next_period_info(self) -> Optional[NextPeriodInfo]:
        latest = self.get_latest()
        if latest is None:
            return None
        next_date = self._next_draw_date(latest.draw_date)
        next_issue = self._next_issue(latest.issue, next_date)
        return NextPeriodInfo(
            base_issue=latest.issue,
            base_date=latest.draw_date,
            next_issue=next_issue,
            next_date=next_date,
        )

    def _next_draw_date(self, last_date: datetime) -> datetime:
        nxt = last_date + timedelta(days=1)
        if self.profile.is_daily:
            return nxt
        if not self.profile.draw_weekdays:
            raise ValueError("draw_weekdays must not be empty for non-daily profile")
        while nxt.weekday() not in self.profile.draw_weekdays:
            nxt += timedelta(days=1)
        return nxt

    @staticmethod
    def _next_issue(latest_issue: str, next_date: datetime) -> str:
        issue = latest_issue.strip()
        if len(issue) < 4 or not issue[:4].isdigit():
            return ""
        try:
            year = int(issue[:4])
            sequence = int(issue[4:])
        except ValueError:
            return ""
        if next_date.year != year:
            return f"{next_date.year}001"
        return f"{year}{sequence + 1:03d}"

    def get_date_range(self) -> tuple[Optional[datetime], Optional[datetime]]:
        if not self._records:
            return None, None
        return self._records[0].draw_date, self._records[-1].draw_date

    def get_records_before(self, cutoff: datetime) -> List[DrawRecord]:
        return [r for r in self._records if r.draw_date < cutoff]

    def get_record_by_date(self, draw_date: datetime) -> Optional[DrawRecord]:
        for r in self._records:
            if r.draw_date.date() == draw_date.date():
                return r
        return None

    def clear(self) -> None:
        self._records.clear()
        self.save()


# 旧的双色球仓库别名：保持现有代码与测试完全兼容
DataRepository = DrawRepository
