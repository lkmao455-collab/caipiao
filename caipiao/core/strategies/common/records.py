"""历史记录标准化工具."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ....data.models import DrawRecord


def records_from_options(options: dict[str, Any]) -> list[DrawRecord]:
    """从 options['history'] 提取 DrawRecord 列表。"""
    history = options.get("history") or []
    records: list[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        elif isinstance(r, dict):
            # 处理字典格式的历史记录
            draw_date = r.get("draw_date")
            if isinstance(draw_date, str):
                draw_date = datetime.strptime(draw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).astimezone()
            elif not isinstance(draw_date, datetime):
                draw_date = datetime.now(timezone.utc).astimezone()
            records.append(
                DrawRecord(
                    issue=r.get("issue", ""),
                    draw_date=draw_date,
                    profile=r.get("profile", "pl5"),
                    groups=r.get("groups", {}),
                )
            )
        else:
            # 处理对象格式的历史记录（向后兼容）
            records.append(
                DrawRecord(
                    issue=getattr(r, "issue", ""),
                    draw_date=getattr(r, "draw_date", datetime.now(timezone.utc).astimezone()),
                    profile=getattr(r, "profile", None),
                    groups=getattr(r, "groups", {}),
                )
            )
    return records
