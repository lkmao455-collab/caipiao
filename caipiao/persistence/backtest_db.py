"""回测结果 SQLite 持久化.

提供统一的回测记录存储，支持单期回测与批量回测两种模式。
数据保存在应用数据目录 ``.caipiao/backtests.db`` 中。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import app_data_dir


def _db_path() -> Path:
    """回测数据库文件路径."""
    return app_data_dir() / "backtests.db"


@dataclass
class SingleBacktestRecord:
    """单期回测记录."""

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    profile_key: str = ""
    strategy_id: str = ""
    target_date: str = ""  # YYYY-MM-DD
    issue: str = ""
    tickets_count: int = 0
    options: Dict[str, Any] = field(default_factory=dict)
    actual_groups: Dict[str, List[int]] = field(default_factory=dict)
    total_cost: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    hit_count: int = 0
    profit: int = 0
    tickets: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchBacktestRecord:
    """批量回测汇总记录."""

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    profile_key: str = ""
    strategy_id: str = ""
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""  # YYYY-MM-DD
    tickets_per_round: int = 0
    options: Dict[str, Any] = field(default_factory=dict)
    total_cost: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    hit_count: int = 0
    total_rounds: int = 0
    first_ticket_hit_count: int = 0
    profit: int = 0
    ticket_index_hits: Dict[int, int] = field(default_factory=dict)


class BacktestDatabase:
    """回测结果数据库访问类."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or _db_path()
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS single_backtests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    profile_key TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    tickets_count INTEGER NOT NULL,
                    options TEXT NOT NULL,
                    actual_groups TEXT NOT NULL,
                    total_cost INTEGER NOT NULL,
                    total_fixed_prize INTEGER NOT NULL,
                    float_prize_count INTEGER NOT NULL,
                    hit_count INTEGER NOT NULL,
                    profit INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_single_profile_date
                    ON single_backtests(profile_key, target_date);
                CREATE INDEX IF NOT EXISTS idx_single_strategy
                    ON single_backtests(strategy_id);

                CREATE TABLE IF NOT EXISTS single_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backtest_id INTEGER NOT NULL,
                    ticket_index INTEGER NOT NULL,
                    groups TEXT NOT NULL,
                    hits TEXT NOT NULL,
                    prize_name TEXT NOT NULL,
                    prize_amount INTEGER,
                    is_first INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (backtest_id) REFERENCES single_backtests(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_single_ticket_backtest
                    ON single_tickets(backtest_id);

                CREATE TABLE IF NOT EXISTS batch_backtests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    profile_key TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    tickets_per_round INTEGER NOT NULL,
                    options TEXT NOT NULL,
                    total_cost INTEGER NOT NULL,
                    total_fixed_prize INTEGER NOT NULL,
                    float_prize_count INTEGER NOT NULL,
                    hit_count INTEGER NOT NULL,
                    total_rounds INTEGER NOT NULL,
                    first_ticket_hit_count INTEGER NOT NULL,
                    profit INTEGER NOT NULL,
                    ticket_index_hits TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_batch_profile_dates
                    ON batch_backtests(profile_key, start_date, end_date);
                CREATE INDEX IF NOT EXISTS idx_batch_strategy
                    ON batch_backtests(strategy_id);
                """
            )
            conn.commit()

    # ------------------------------------------------------------------ #
    # 单期回测
    # ------------------------------------------------------------------ #
    def save_single(
        self,
        profile_key: str,
        strategy_id: str,
        target_date: str,
        issue: str,
        tickets_count: int,
        options: Dict[str, Any],
        actual_groups: Dict[str, List[int]],
        total_cost: int,
        total_fixed_prize: int,
        float_prize_count: int,
        hit_count: int,
        tickets: List[Dict[str, Any]],
    ) -> int:
        """保存一条单期回测记录，返回记录 ID."""
        profit = total_fixed_prize - total_cost
        options_json = json.dumps(options, ensure_ascii=False, default=str)
        actual_json = json.dumps(actual_groups, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO single_backtests
                (profile_key, strategy_id, target_date, issue, tickets_count,
                 options, actual_groups, total_cost, total_fixed_prize,
                 float_prize_count, hit_count, profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_key,
                    strategy_id,
                    target_date,
                    issue,
                    tickets_count,
                    options_json,
                    actual_json,
                    total_cost,
                    total_fixed_prize,
                    float_prize_count,
                    hit_count,
                    profit,
                ),
            )
            backtest_id = cur.lastrowid
            for idx, t in enumerate(tickets):
                conn.execute(
                    """
                    INSERT INTO single_tickets
                    (backtest_id, ticket_index, groups, hits, prize_name, prize_amount, is_first)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        backtest_id,
                        idx,
                        json.dumps(t["ticket"].groups, ensure_ascii=False),
                        json.dumps(t["hits"], ensure_ascii=False),
                        t["prize_name"],
                        t["prize_amount"],
                        1 if idx == 0 else 0,
                    ),
                )
            conn.commit()
            return backtest_id or 0

    def get_single(self, backtest_id: int) -> Optional[SingleBacktestRecord]:
        """按 ID 读取单期回测记录（含所有投注明细）."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM single_backtests WHERE id = ?", (backtest_id,)
            ).fetchone()
            if row is None:
                return None
            tickets = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM single_tickets WHERE backtest_id = ? ORDER BY ticket_index",
                    (backtest_id,),
                ).fetchall()
            ]
            return SingleBacktestRecord(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                profile_key=row["profile_key"],
                strategy_id=row["strategy_id"],
                target_date=row["target_date"],
                issue=row["issue"],
                tickets_count=row["tickets_count"],
                options=json.loads(row["options"]),
                actual_groups=json.loads(row["actual_groups"]),
                total_cost=row["total_cost"],
                total_fixed_prize=row["total_fixed_prize"],
                float_prize_count=row["float_prize_count"],
                hit_count=row["hit_count"],
                profit=row["profit"],
                tickets=tickets,
            )

    def list_single(
        self,
        profile_key: Optional[str] = None,
        strategy_id: Optional[str] = None,
        target_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SingleBacktestRecord]:
        """分页查询单期回测记录（不含投注明细）."""
        where_parts = ["1=1"]
        params: List[Any] = []
        if profile_key:
            where_parts.append("profile_key = ?")
            params.append(profile_key)
        if strategy_id:
            where_parts.append("strategy_id = ?")
            params.append(strategy_id)
        if target_date:
            where_parts.append("target_date = ?")
            params.append(target_date)
        where = " AND ".join(where_parts)
        sql = f"""
            SELECT * FROM single_backtests
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                SingleBacktestRecord(
                    id=r["id"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    profile_key=r["profile_key"],
                    strategy_id=r["strategy_id"],
                    target_date=r["target_date"],
                    issue=r["issue"],
                    tickets_count=r["tickets_count"],
                    options=json.loads(r["options"]),
                    actual_groups=json.loads(r["actual_groups"]),
                    total_cost=r["total_cost"],
                    total_fixed_prize=r["total_fixed_prize"],
                    float_prize_count=r["float_prize_count"],
                    hit_count=r["hit_count"],
                    profit=r["profit"],
                    tickets=[],
                )
                for r in rows
            ]

    def delete_single(self, backtest_id: int) -> None:
        """删除单期回测记录（级联删除投注明细）."""
        with self._connect() as conn:
            conn.execute("DELETE FROM single_backtests WHERE id = ?", (backtest_id,))
            conn.commit()

    # ------------------------------------------------------------------ #
    # 批量回测
    # ------------------------------------------------------------------ #
    def save_batch(
        self,
        profile_key: str,
        strategy_id: str,
        start_date: str,
        end_date: str,
        tickets_per_round: int,
        options: Dict[str, Any],
        total_cost: int,
        total_fixed_prize: int,
        float_prize_count: int,
        hit_count: int,
        total_rounds: int,
        first_ticket_hit_count: int,
        ticket_index_hits: Dict[int, int],
    ) -> int:
        """保存一条批量回测汇总记录，返回记录 ID."""
        profit = total_fixed_prize - total_cost
        options_json = json.dumps(options, ensure_ascii=False, default=str)
        hits_json = json.dumps(ticket_index_hits, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO batch_backtests
                (profile_key, strategy_id, start_date, end_date, tickets_per_round,
                 options, total_cost, total_fixed_prize, float_prize_count, hit_count,
                 total_rounds, first_ticket_hit_count, profit, ticket_index_hits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_key,
                    strategy_id,
                    start_date,
                    end_date,
                    tickets_per_round,
                    options_json,
                    total_cost,
                    total_fixed_prize,
                    float_prize_count,
                    hit_count,
                    total_rounds,
                    first_ticket_hit_count,
                    profit,
                    hits_json,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_batch(self, backtest_id: int) -> Optional[BatchBacktestRecord]:
        """按 ID 读取批量回测记录."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM batch_backtests WHERE id = ?", (backtest_id,)
            ).fetchone()
            if row is None:
                return None
            return BatchBacktestRecord(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                profile_key=row["profile_key"],
                strategy_id=row["strategy_id"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                tickets_per_round=row["tickets_per_round"],
                options=json.loads(row["options"]),
                total_cost=row["total_cost"],
                total_fixed_prize=row["total_fixed_prize"],
                float_prize_count=row["float_prize_count"],
                hit_count=row["hit_count"],
                total_rounds=row["total_rounds"],
                first_ticket_hit_count=row["first_ticket_hit_count"],
                profit=row["profit"],
                ticket_index_hits=json.loads(row["ticket_index_hits"]),
            )

    def list_batch(
        self,
        profile_key: Optional[str] = None,
        strategy_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BatchBacktestRecord]:
        """分页查询批量回测记录."""
        where_parts = ["1=1"]
        params: List[Any] = []
        if profile_key:
            where_parts.append("profile_key = ?")
            params.append(profile_key)
        if strategy_id:
            where_parts.append("strategy_id = ?")
            params.append(strategy_id)
        if start_date:
            where_parts.append("start_date >= ?")
            params.append(start_date)
        if end_date:
            where_parts.append("end_date <= ?")
            params.append(end_date)
        where = " AND ".join(where_parts)
        sql = f"""
            SELECT * FROM batch_backtests
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                BatchBacktestRecord(
                    id=r["id"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    profile_key=r["profile_key"],
                    strategy_id=r["strategy_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    tickets_per_round=r["tickets_per_round"],
                    options=json.loads(r["options"]),
                    total_cost=r["total_cost"],
                    total_fixed_prize=r["total_fixed_prize"],
                    float_prize_count=r["float_prize_count"],
                    hit_count=r["hit_count"],
                    total_rounds=r["total_rounds"],
                    first_ticket_hit_count=r["first_ticket_hit_count"],
                    profit=r["profit"],
                    ticket_index_hits=json.loads(r["ticket_index_hits"]),
                )
                for r in rows
            ]

    def delete_batch(self, backtest_id: int) -> None:
        """删除批量回测记录."""
        with self._connect() as conn:
            conn.execute("DELETE FROM batch_backtests WHERE id = ?", (backtest_id,))
            conn.commit()

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def summary(self) -> Dict[str, int]:
        """返回当前数据库中两种回测记录的条数."""
        with self._connect() as conn:
            single = conn.execute(
                "SELECT COUNT(*) FROM single_backtests"
            ).fetchone()[0]
            batch = conn.execute(
                "SELECT COUNT(*) FROM batch_backtests"
            ).fetchone()[0]
        return {"single_count": single, "batch_count": batch}
