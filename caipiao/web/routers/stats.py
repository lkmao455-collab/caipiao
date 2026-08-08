"""统计端点：复用核心层 DrawAnalyzer 产出开奖数据统计。"""

from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

from ...core.profile import get_profile as _get_profile
from ...core.strategies.factory import build_strategies
from ...data.analyzer import DrawAnalyzer
from ...data.repository import DrawRepository
from ..config import DATA_ROOT
from ..db import get_db
from ..deps import get_current_principal
from ..ratelimit import default_limit, limiter
from ..recommender import recommendation_engine

router = APIRouter(prefix="/profiles", tags=["stats"])


@router.get("/{key}/stats")
@limiter.limit(default_limit)
def profile_stats(request: Request, key: str, db: Session = Depends(get_db)) -> dict:
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


@router.get("/{key}/missing-analysis")
@limiter.limit(default_limit)
def missing_analysis(
    request: Request,
    key: str,
    windows: str = Query(default="10,30,50,100", description="遗漏统计窗口期数"),
    db: Session = Depends(get_db),
) -> dict:
    """多维度遗漏值深度分析：不同时间窗口的遗漏值对比、遗漏值趋势、冷热转换信号。"""
    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()
    analyzer = DrawAnalyzer(records, profile)
    primary = profile.primary_group.key

    window_list = [int(w.strip()) for w in windows.split(",") if w.strip()]

    # 多窗口遗漏对比
    missing_by_window: dict[int, list] = {}
    for w in window_list:
        missing_data = analyzer.missing(primary, last_n=w)
        missing_by_window[w] = [{"number": n, "gap": gap} for n, gap in missing_data]

    # 遗漏值趋势：对比不同窗口的遗漏变化
    current_missing = analyzer.missing(primary, last_n=100)
    recent_missing = analyzer.missing(primary, last_n=30)

    current_map = dict(current_missing)
    recent_map = dict(recent_missing)

    trend_data = []
    for group in profile.groups:
        for num in group.values:
            cur = current_map.get(num, 0)
            rec = recent_map.get(num, 0)
            trend_data.append({
                "number": num,
                "current_gap": cur,
                "recent_gap": rec,
                "trend": "up" if rec > cur else ("down" if rec < cur else "stable"),
                "change": rec - cur,
            })

    # 冷热转换信号：近期出现频率突然变化的号码
    hot_signals = []
    cold_signals = []
    for item in trend_data:
        if item["trend"] == "down" and item["change"] < -3:
            hot_signals.append(item["number"])
        elif item["trend"] == "up" and item["change"] > 3:
            cold_signals.append(item["number"])

    # 号码遗漏分布统计
    all_gaps = [item["current_gap"] for item in trend_data]
    gap_distribution = {}
    for gap in all_gaps:
        gap_distribution[gap] = gap_distribution.get(gap, 0) + 1

    return {
        "profile_key": key,
        "primary_group": primary,
        "windows": window_list,
        "missing_by_window": missing_by_window,
        "trend_data": trend_data,
        "hot_signals": hot_signals,
        "cold_signals": cold_signals,
        "gap_distribution": gap_distribution,
    }


@router.get("/{key}/combo-analysis")
@limiter.limit(default_limit)
def combo_analysis(request: Request, key: str, db: Session = Depends(get_db)) -> dict:
    """常见号码组合分析：统计历史数据中的常见对子、三连号、三区分布等。"""
    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()
    analyzer = DrawAnalyzer(records, profile)
    primary = profile.primary_group.key

    common_pairs = analyzer.common_pairs(top_n=15)
    consecutive_ratio = analyzer.consecutive_frequency()
    consecutive_dist = analyzer.consecutive_count_distribution()
    zone_dist = analyzer.zone_distribution()

    # 生成常见三连号组合
    from collections import Counter
    triple_counter: Counter = Counter()
    for record in records:
        nums = sorted(record.groups.get(primary, []))
        for i in range(len(nums) - 2):
            if nums[i] + 1 == nums[i + 1] and nums[i + 1] + 1 == nums[i + 2]:
                triple = tuple(nums[i:i + 3])
                triple_counter[triple] += 1
    common_triples = [{"list": list(t), "count": c} for t, c in triple_counter.most_common(10)]

    return {
        "profile_key": key,
        "total_records": len(records),
        "common_pairs": [{"pair": list(pair), "count": cnt} for pair, cnt in common_pairs],
        "common_triples": common_triples,
        "zone_distribution": zone_dist,
        "consecutive_frequency": consecutive_ratio,
        "consecutive_distribution": consecutive_dist,
    }


@router.get("/{key}/trend-analysis")
@limiter.limit(default_limit)
def trend_analysis(
    request: Request,
    key: str,
    rounds: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """号码趋势分析：返回最近 N 期的开奖数据，用于前端绘制趋势折线图。"""
    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()

    # 取最近 N 期
    recent = sorted(records, key=lambda r: r.draw_date)[-rounds:]

    trends = []
    for record in recent:
        trends.append({
            "draw_date": str(record.draw_date),
            "issue": record.issue,
            "numbers": record.groups,
        })

    return {
        "profile_key": key,
        "total_rounds": len(trends),
        "trends": trends,
    }


@router.get("/{key}/export")
@limiter.limit(default_limit)
def export_data(
    request: Request,
    key: str,
    format: Literal["csv", "excel"] = Query(default="csv"),
    db: Session = Depends(get_db),
):
    """导出开奖数据为 CSV 格式。"""
    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    headers = ["日期", "期号"]
    for g in profile.groups:
        headers.extend([f"{g.name}_{i + 1}" for i in range(g.count)])
    writer.writerow(headers)

    # 写入数据
    for record in sorted(records, key=lambda r: r.draw_date, reverse=True):
        row = [str(record.draw_date), record.issue]
        for g in profile.groups:
            nums = record.groups.get(g.key, [])
            row.extend([str(n) for n in nums] + [""] * (g.count - len(nums)))
        writer.writerow(row)

    output.seek(0)
    content = output.getvalue()
    output.close()

    filename = f"{key}_data.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class RecommendationOut(BaseModel):
    strategy_id: str
    strategy_name: str
    score: float
    reason: str
    suggested_params: dict = {}
    tags: list[str] = []


@router.get("/{key}/recommendations", response_model=list[RecommendationOut])
@limiter.limit(default_limit)
def get_recommendations(
    request: Request,
    key: str,
    top_n: int = Query(default=5, ge=1, le=10),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[RecommendationOut]:
    """获取智能推荐策略列表，基于用户历史偏好和回测结果。"""
    profile = _get_profile(key)
    all_strategies = build_strategies(profile)
    strategy_list = [
        {
            "id": s.id,
            "name": s.metadata.name,
            "configurable": s.metadata.configurable,
            "is_ml": getattr(s, "is_ml", False),
        }
        for s in all_strategies
    ]

    recommendations = recommendation_engine.get_recommendations(
        user_id=principal.id,
        profile_key=key,
        available_strategies=strategy_list,
        top_n=top_n,
    )

    return [
        RecommendationOut(
            strategy_id=r.strategy_id,
            strategy_name=r.strategy_name,
            score=r.score,
            reason=r.reason,
            suggested_params=r.suggested_params,
            tags=r.tags,
        )
        for r in recommendations
    ]


@router.get("/{key}/multi-period-analysis")
@limiter.limit(default_limit)
def multi_period_analysis(
    request: Request,
    key: str,
    periods: int = Query(default=5, ge=2, le=20),
    db: Session = Depends(get_db),
) -> dict:
    """多期联合分析：分析多期号码关联性，提供组合预测建议。"""
    from collections import Counter
    import itertools

    profile = _get_profile(key)
    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    records = repo.get_all()
    analyzer = DrawAnalyzer(records, profile)
    primary = profile.primary_group.key

    # 取最近 N 期数据
    recent = sorted(records, key=lambda r: r.draw_date)[-periods:]

    # 1. 号码共现分析：哪些号码经常一起出现
    pair_counter: Counter = Counter()
    for record in recent:
        nums = sorted(record.groups.get(primary, []))
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair_counter[(nums[i], nums[j])] += 1

    common_pairs = pair_counter.most_common(10)

    # 2. 号码连续出现分析：哪些号码连续多期出现
    number_appearances: dict[int, list[int]] = {}
    for idx, record in enumerate(recent):
        for num in record.groups.get(primary, []):
            if num not in number_appearances:
                number_appearances[num] = []
            number_appearances[num].append(idx)

    consecutive_appearances = []
    for num, positions in number_appearances.items():
        if len(positions) >= 2:
            consecutive_appearances.append({
                "number": num,
                "appearances": len(positions),
                "positions": positions,
                "streak": max(positions) - min(positions) + 1 == len(positions),
            })
    consecutive_appearances.sort(key=lambda x: x["appearances"], reverse=True)

    # 3. 区间轮动分析：分析号码在不同区间的分布变化
    zone_history = []
    for record in recent:
        zones = {"zone1": 0, "zone2": 0, "zone3": 0}
        for num in record.groups.get(primary, []):
            if 1 <= num <= 11:
                zones["zone1"] += 1
            elif 12 <= num <= 22:
                zones["zone2"] += 1
            elif 23 <= num <= 33:
                zones["zone3"] += 1
        zone_history.append({
            "date": str(record.draw_date),
            **zones,
        })

    # 4. 组合预测建议：基于历史数据推荐下期可能出现的组合
    hot_numbers = analyzer.hot(primary, 10)
    suggestions = []

    # 策略1：热门号码组合
    if len(hot_numbers) >= 6:
        suggestions.append({
            "strategy": "热门组合",
            "numbers": hot_numbers[:6],
            "reason": "基于近期出现频率最高的号码",
        })

    # 策略2：冷热交替
    cold_numbers = analyzer.cold(primary, 5)
    if hot_numbers[:3] and cold_numbers[:3]:
        suggestions.append({
            "strategy": "冷热交替",
            "numbers": hot_numbers[:3] + cold_numbers[:3],
            "reason": "热门号码 + 可能回补的冷号",
        })

    # 策略3：共现对子 + 补充
    if common_pairs:
        base_pair = list(common_pairs[0][0])
        remaining = [n for n in hot_numbers if n not in base_pair][:4]
        suggestions.append({
            "strategy": "共现组合",
            "numbers": base_pair + remaining,
            "reason": "基于历史共现频率最高的对子",
        })

    return {
        "profile_key": key,
        "periods_analyzed": periods,
        "common_pairs": [{"pair": list(p), "count": c} for p, c in common_pairs],
        "consecutive_appearances": consecutive_appearances[:10],
        "zone_history": zone_history,
        "suggestions": suggestions,
    }


@router.get("/compare-lotteries")
@limiter.limit(default_limit)
def compare_lotteries(
    request: Request,
    keys: str = Query(description="逗号分隔的彩种 key 列表"),
    db: Session = Depends(get_db),
) -> dict:
    """多彩种对比分析：比较不同彩种的特征差异。"""
    from ...core.profile import list_profiles

    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if len(key_list) < 2:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少需要2个彩种进行对比")

    # 获取所有彩种信息
    all_profiles = {p.key: p for p in list_profiles()}

    comparisons = []
    for key in key_list:
        if key not in all_profiles:
            continue
        profile = all_profiles[key]
        repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
        records = repo.get_all()
        analyzer = DrawAnalyzer(records, profile)
        primary = profile.primary_group.key

        # 统计数据
        freq = analyzer.frequency(primary)
        hot = analyzer.hot(primary, 5)
        cold = analyzer.cold(primary, 5)
        odd_even = analyzer.odd_even_ratio()
        high_low = analyzer.high_low_ratio()
        sum_stats = analyzer.sum_statistics()

        comparisons.append({
            "key": key,
            "name": profile.name,
            "category": profile.category,
            "total_records": len(records),
            "hot_numbers": hot,
            "cold_numbers": cold,
            "odd_even_ratio": list(odd_even),
            "high_low_ratio": list(high_low),
            "sum_mean": sum_stats.get("avg", 0),
            "sum_span": sum_stats.get("max", 0) - sum_stats.get("min", 0),
        })

    # 分析差异
    insights = []
    if len(comparisons) >= 2:
        # 奇偶比差异
        oe_diffs = [(c["key"], c["odd_even_ratio"][0]) for c in comparisons]
        oe_diffs.sort(key=lambda x: x[1], reverse=True)
        insights.append({
            "type": "odd_even",
            "description": f"奇数比例最高：{oe_diffs[0][0]} ({oe_diffs[0][1]:.2%})",
        })

        # 和值差异
        sum_diffs = [(c["key"], c["sum_mean"]) for c in comparisons]
        sum_diffs.sort(key=lambda x: x[1], reverse=True)
        insights.append({
            "type": "sum",
            "description": f"平均和值最高：{sum_diffs[0][0]} ({sum_diffs[0][1]:.1f})",
        })

    return {
        "comparisons": comparisons,
        "insights": insights,
    }
