"""走查式回测路由：对最近 N 期逐期用「早于该期的历史」生成并比对，结果持久化。

核心层零侵入：仅复用 ``GenerationEngine``、``DrawRepository``、``BacktestDatabase``、
``records_from_options``（策略只用到 options["history"] 截止数据）以及 ``filters_registry``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.profile import get_profile as _get_profile
from ...data.repository import DrawRepository
from ...persistence.backtest_db import BacktestDatabase
from ..config import DATA_ROOT
from ..db import get_db
from ..deps import get_current_principal
from ..engine import get_profile_engine
from ..filters_registry import apply_filters
from ..metering import record_usage
from ..ratelimit import limiter
from ..schemas import (
    BacktestRecordOut,
    BacktestRequest,
    BacktestRoundItem,
    BacktestRunResponse,
    BacktestRoundSummary,
)
from starlette.requests import Request

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _backtest_db() -> BacktestDatabase:
    """显式指定持久化路径（BacktestDatabase 默认 app_data_dir() 会忽略 web 的 DATA_ROOT）。"""
    return BacktestDatabase(path=DATA_ROOT / "backtests.db")


def _group_hits(ticket_groups: dict[str, list[int]], actual_groups: dict[str, list[int]]) -> dict[str, int]:
    """计算生成号码与真实开奖在各组的重合数。"""
    return {
        g: len(set(ticket_groups.get(g, [])) & set(actual_groups.get(g, [])))
        for g in actual_groups
    }


def _is_hit(profile, ticket_groups: dict[str, list[int]], actual_groups: dict[str, list[int]]) -> bool:
    """轻量中奖判定：主号组全部命中即记为一注命中（不引入真实奖级表，core 零侵入）。"""
    primary = profile.primary_group.key
    return _group_hits(ticket_groups, actual_groups).get(primary, 0) >= profile.group(primary).count


@router.post("", response_model=BacktestRunResponse)
@limiter.limit("30/minute")
def backtest(request: Request, req: BacktestRequest, principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> BacktestRunResponse:
    try:
        profile = _get_profile(req.profile_key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    repo = DrawRepository(DATA_ROOT / profile.storage_file, profile)
    all_records = repo.get_all()
    if len(all_records) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "本地开奖数据不足，无法回测")

    # 选取回测目标期（按日期倒序取最近 rounds 期，可经 start/end 裁剪）
    targets = list(reversed(all_records))
    if req.start_date:
        targets = [r for r in targets if r.draw_date >= req.start_date]
    if req.end_date:
        targets = [r for r in targets if r.draw_date <= req.end_date]
    targets = targets[: req.rounds]
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "没有符合条件的回测目标期")

    engine = get_profile_engine(req.profile_key)
    options = dict(req.options or {})
    post_filters = [p.model_dump() for p in req.post_filters]

    rounds: list[BacktestRoundItem] = []
    total_cost = 0
    total_fixed_prize = 0  # 轻量回测不计算真实奖金
    first_ticket_hit_count = 0
    ticket_index_hits: dict[int, int] = {}

    bdb = _backtest_db()
    single_rows: list[tuple] = []  # (target, issue, actual_groups, round_hit, ticket_matches)

    for t in targets:
        # 仅使用早于目标期的历史（走查式：模拟当时未知未来开奖）
        history = [r for r in all_records if r.draw_date < t.draw_date][-req.history_window:]
        if not history:
            continue
        run_options = dict(options)
        run_options["history"] = history
        try:
            tickets = engine.generate(req.strategy_id, req.count, run_options)
        except Exception:
            continue
        tickets = apply_filters(req.profile_key, tickets, history, post_filters)

        actual = t.groups
        round_hit = False
        ticket_matches: list[dict[str, int]] = []
        for idx, tk in enumerate(tickets):
            tg = tk.groups
            hits = _group_hits(tg, actual)
            ticket_matches.append(hits)
            hit = _is_hit(profile, tg, actual)
            if hit:
                ticket_index_hits[idx] = ticket_index_hits.get(idx, 0) + 1
                if idx == 0:
                    first_ticket_hit_count += 1
                round_hit = True
            total_cost += 2  # 单注成本近似

        matches = ticket_matches[0] if ticket_matches else {}
        if round_hit:
            total_fixed_prize += 0  # 不计算真实奖金
        rounds.append(
            BacktestRoundItem(
                target_date=str(t.draw_date),
                issue=t.issue,
                matches=matches,
                hit=round_hit,
            )
        )
        single_rows.append((t, actual, round_hit, ticket_matches))

    hit_count = sum(1 for r in rounds if r.hit)
    profit = total_fixed_prize - total_cost

    summary = BacktestRoundSummary(
        total_rounds=len(rounds),
        hit_count=hit_count,
        first_ticket_hit_count=first_ticket_hit_count,
        profit=profit,
        total_cost=total_cost,
        total_fixed_prize=total_fixed_prize,
    )

    batch_id = bdb.save_batch(
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        start_date=rounds[0].target_date if rounds else "",
        end_date=rounds[-1].target_date if rounds else "",
        tickets_per_round=req.count,
        options=options,
        total_cost=total_cost,
        total_fixed_prize=total_fixed_prize,
        float_prize_count=0,
        hit_count=hit_count,
        total_rounds=len(rounds),
        first_ticket_hit_count=first_ticket_hit_count,
        ticket_index_hits=ticket_index_hits,
    )

    # 逐期持久化明细
    for t, actual, round_hit, ticket_matches in single_rows:
        bdb.save_single(
            profile_key=req.profile_key,
            strategy_id=req.strategy_id,
            target_date=str(t.draw_date),
            issue=t.issue,
            tickets_count=req.count,
            options=options,
            actual_groups=actual,
            total_cost=req.count * 2,
            total_fixed_prize=0,
            float_prize_count=0,
            hit_count=1 if round_hit else 0,
            tickets=[],
        )

    record_usage(db, principal, "backtest", 1)

    return BacktestRunResponse(
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        batch_id=batch_id,
        rounds=rounds,
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# 历史回测记录查询
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[BacktestRecordOut])
def list_backtests(
    profile_key: str | None = None,
    strategy_id: str | None = None,
    limit: int = 100,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[BacktestRecordOut]:
    bdb = _backtest_db()
    out: list[BacktestRecordOut] = []
    for r in bdb.list_single(profile_key=profile_key, strategy_id=strategy_id, limit=limit):
        out.append(
            BacktestRecordOut(
                id=r.id or 0,
                created_at=str(r.created_at) if r.created_at else None,
                profile_key=r.profile_key,
                strategy_id=r.strategy_id,
                target_date=r.target_date,
                total_rounds=0,
                tickets_count=r.tickets_count,
                total_cost=r.total_cost,
                total_fixed_prize=r.total_fixed_prize,
                hit_count=r.hit_count,
                profit=r.profit,
                kind="single",
            )
        )
    for r in bdb.list_batch(profile_key=profile_key, strategy_id=strategy_id, limit=limit):
        out.append(
            BacktestRecordOut(
                id=r.id or 0,
                created_at=str(r.created_at) if r.created_at else None,
                profile_key=r.profile_key,
                strategy_id=r.strategy_id,
                start_date=r.start_date,
                end_date=r.end_date,
                total_rounds=r.total_rounds,
                tickets_count=r.tickets_per_round,
                total_cost=r.total_cost,
                total_fixed_prize=r.total_fixed_prize,
                hit_count=r.hit_count,
                profit=r.profit,
                kind="batch",
            )
        )
    out.sort(key=lambda x: (x.created_at or ""), reverse=True)
    return out


@router.get("/{backtest_id}", response_model=dict)
def get_backtest(
    backtest_id: int,
    kind: str = "batch",
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    bdb = _backtest_db()
    if kind == "single":
        single = bdb.get_single(backtest_id)
        if single is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "回测记录不存在")
        return {
            "kind": "single",
            "id": single.id,
            "profile_key": single.profile_key,
            "strategy_id": single.strategy_id,
            "target_date": single.target_date,
            "issue": single.issue,
            "total_cost": single.total_cost,
            "total_fixed_prize": single.total_fixed_prize,
            "hit_count": single.hit_count,
            "profit": single.profit,
            "tickets": single.tickets,
        }
    batch = bdb.get_batch(backtest_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "回测记录不存在")
    return {
        "kind": "batch",
        "id": batch.id,
        "profile_key": batch.profile_key,
        "strategy_id": batch.strategy_id,
        "start_date": batch.start_date,
        "end_date": batch.end_date,
        "total_rounds": batch.total_rounds,
        "tickets_per_round": batch.tickets_per_round,
        "total_cost": batch.total_cost,
        "total_fixed_prize": batch.total_fixed_prize,
        "hit_count": batch.hit_count,
        "first_ticket_hit_count": batch.first_ticket_hit_count,
        "profit": batch.profit,
        "ticket_index_hits": batch.ticket_index_hits,
    }


@router.delete("/{backtest_id}")
def delete_backtest(
    backtest_id: int,
    kind: str = "batch",
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    bdb = _backtest_db()
    if kind == "single":
        if bdb.get_single(backtest_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "回测记录不存在")
        bdb.delete_single(backtest_id)
        return {"deleted": backtest_id, "kind": "single"}
    if bdb.get_batch(backtest_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "回测记录不存在")
    bdb.delete_batch(backtest_id)
    return {"deleted": backtest_id, "kind": "batch"}
