"""统计端点：复用核心层 DrawAnalyzer 产出开奖数据统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.profile import get_profile as _get_profile
from ...data.analyzer import DrawAnalyzer
from ...data.repository import DrawRepository
from ..config import DATA_ROOT
from ..db import get_db

router = APIRouter(prefix="/profiles", tags=["stats"])


@router.get("/{key}/stats")
def profile_stats(key: str, db: Session = Depends(get_db)) -> dict:
    """返回某彩种开奖数据的统计摘要（频率/热冷/遗漏/奇偶/大小/和值/跨度等）。

    复用核心层 ``DrawAnalyzer``，不修改核心代码。未知彩种回落到默认（与 get_profile 一致）。
    """
    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()
    analyzer = DrawAnalyzer(records, profile)

    groups: dict[str, dict] = {}
    for g in profile.groups:
        freq = analyzer.frequency(g.key)
        groups[g.key] = {
            "key": g.key,
            "name": g.name,
            "lo": g.lo,
            "hi": g.hi,
            "count": g.count,
            "color": g.color,
            "frequency": freq,
            "hot": analyzer.hot(g.key, 10),
            "cold": analyzer.cold(g.key, 10),
            "missing": [[n, gap] for n, gap in analyzer.missing(g.key, 50)],
        }

    primary = profile.primary_group.key
    return {
        "profile_key": profile.key,
        "total_records": len(records),
        "groups": groups,
        "summary": analyzer.summary(),
        "odd_even_ratio": analyzer.odd_even_ratio(),
        "high_low_ratio": analyzer.high_low_ratio(),
        "sum_statistics": analyzer.sum_statistics(),
        "span": analyzer.span(),
        "zone_distribution": analyzer.zone_distribution(),
        "common_pairs": [
            {"pair": list(pair), "count": cnt}
            for pair, cnt in analyzer.common_pairs(top_n=10)
        ],
        "primary_group": primary,
    }
