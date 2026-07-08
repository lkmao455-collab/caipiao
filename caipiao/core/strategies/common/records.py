"""历史记录标准化工具."""

from __future__ import annotations

from typing import Any, Dict, List

from ....data.models import DrawRecord


def records_from_options(options: Dict[str, Any]) -> List[DrawRecord]:
    """从 options['history'] 提取 DrawRecord 列表。"""
    history = options.get("history") or []
    records: List[DrawRecord] = []
    for r in history:
        if isinstance(r, DrawRecord):
            records.append(r)
        else:
            records.append(
                DrawRecord(
                    issue="",
                    draw_date=r.generated_at,
                    profile=r.profile.key,
                    groups=r.groups,
                )
            )
    return records
