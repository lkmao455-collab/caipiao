"""用户行为分析：深度行为追踪、留存分析、路径分析。"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class UserSession:
    session_id: str
    user_id: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    pages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    device: str = ""
    browser: str = ""
    os: str = ""
    ip: str = ""

    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass
class PageView:
    page: str
    title: str = ""
    referrer: str = ""
    duration: float = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserAction:
    action_type: str  # click, scroll, input, hover, submit
    target: str
    value: str = ""
    x: float = 0
    y: float = 0
    timestamp: float = field(default_factory=time.time)


class BehaviorAnalyzer:
    """用户行为分析器。"""

    def __init__(self, max_sessions: int = 100000):
        self._sessions: dict[str, UserSession] = {}
        self._user_sessions: dict[str, list[str]] = defaultdict(list)
        self._max_sessions = max_sessions

    def start_session(
        self,
        user_id: str,
        device: str = "",
        browser: str = "",
        os: str = "",
        ip: str = "",
    ) -> str:
        session_id = str(uuid.uuid4())[:12]
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            device=device,
            browser=browser,
            os=os,
            ip=ip,
        )
        self._sessions[session_id] = session
        self._user_sessions[user_id].append(session_id)

        if len(self._sessions) > self._max_sessions:
            self._cleanup_old_sessions()

        return session_id

    def end_session(self, session_id: str):
        session = self._sessions.get(session_id)
        if session:
            session.end_time = time.time()

    def track_pageview(self, session_id: str, page: str, title: str = "", referrer: str = ""):
        session = self._sessions.get(session_id)
        if session:
            session.pages.append({
                "page": page,
                "title": title,
                "referrer": referrer,
                "timestamp": time.time(),
            })

    def track_action(self, session_id: str, action: UserAction):
        session = self._sessions.get(session_id)
        if session:
            session.events.append({
                "type": action.action_type,
                "target": action.target,
                "value": action.value,
                "x": action.x,
                "y": action.y,
                "timestamp": action.timestamp,
            })

    def _cleanup_old_sessions(self):
        cutoff = time.time() - 86400 * 7
        old_ids = [sid for sid, s in self._sessions.items() if s.start_time < cutoff]
        for sid in old_ids:
            del self._sessions[sid]

    def get_user_sessions(self, user_id: str, limit: int = 50) -> list[UserSession]:
        session_ids = self._user_sessions.get(user_id, [])[-limit:]
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_session(self, session_id: str) -> UserSession | None:
        return self._sessions.get(session_id)

    # 留存分析
    def analyze_retention(self, days: int = 30) -> dict:
        user_daily: dict[str, set[str]] = defaultdict(set)
        for session in self._sessions.values():
            day = int(session.start_time / 86400)
            user_daily[day].add(session.user_id)

        retention = {}
        base_day = min(user_daily.keys()) if user_daily else int(time.time() / 86400)

        for d in range(days):
            current_day = base_day + d
            current_users = user_daily.get(current_day, set())
            retained = 0
            for future_d in range(d + 1, min(d + 8, days + 1)):
                future_day = base_day + future_d
                future_users = user_daily.get(future_day, set())
                retained += len(current_users & future_users)

            retention[d] = {
                "users": len(current_users),
                "retained": retained,
                "rate": round(retained / len(current_users) * 100, 2) if current_users else 0,
            }

        return retention

    # 路径分析
    def analyze_paths(self, limit: int = 20) -> list[dict]:
        paths: dict[str, int] = defaultdict(int)
        for session in self._sessions.values():
            pages = [p.get("page", "") for p in session.pages]
            for i in range(len(pages) - 1):
                path = f"{pages[i]} -> {pages[i+1]}"
                paths[path] += 1

        sorted_paths = sorted(paths.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"path": p, "count": c} for p, c in sorted_paths]

    # 热力图数据
    def get_click_heatmap(self, page: str, width: int = 1920, height: int = 1080) -> list[list[int]]:
        heatmap = [[0] * (width // 20) for _ in range(height // 20)]
        for session in self._sessions.values():
            for evt in session.events:
                if evt.get("type") == "click":
                    page_match = any(p.get("page") == page for p in session.pages)
                    if page_match:
                        x = int(evt.get("x", 0)) // 20
                        y = int(evt.get("y", 0)) // 20
                        if 0 <= x < len(heatmap[0]) and 0 <= y < len(heatmap):
                            heatmap[y][x] += 1
        return heatmap

    # 概览统计
    def get_overview(self, minutes: int = 60) -> dict:
        cutoff = time.time() - minutes * 60
        active_sessions = [s for s in self._sessions.values() if s.start_time >= cutoff]
        active_users = set(s.user_id for s in active_sessions)

        total_pages = sum(len(s.pages) for s in active_sessions)
        total_events = sum(len(s.events) for s in active_sessions)

        return {
            "active_sessions": len(active_sessions),
            "active_users": len(active_users),
            "total_pageviews": total_pages,
            "total_events": total_events,
            "avg_pages_per_session": round(total_pages / len(active_sessions), 2) if active_sessions else 0,
            "avg_session_duration": round(
                sum(s.duration for s in active_sessions) / len(active_sessions), 2
            ) if active_sessions else 0,
        }


# 全局分析器
_analyzer: BehaviorAnalyzer | None = None


def get_behavior_analyzer() -> BehaviorAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = BehaviorAnalyzer()
    return _analyzer
