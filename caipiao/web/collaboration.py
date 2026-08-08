"""实时协作系统：多用户协作分析和共享。"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class Collaborator:
    user_id: str
    username: str
    cursor: dict[str, float] = field(default_factory=dict)
    selection: list[str] = field(default_factory=list)
    joined_at: float = field(default_factory=time.time)


@dataclass
class CollaborationSession:
    id: str
    name: str
    owner_id: str
    created_at: float = field(default_factory=time.time)
    collaborators: dict[str, Collaborator] = field(default_factory=dict)
    shared_data: dict[str, Any] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)

    def add_collaborator(self, user_id: str, username: str):
        self.collaborators[user_id] = Collaborator(
            user_id=user_id, username=username
        )

    def remove_collaborator(self, user_id: str):
        if user_id in self.collaborators:
            del self.collaborators[user_id]

    def update_cursor(self, user_id: str, x: float, y: float):
        if user_id in self.collaborators:
            self.collaborators[user_id].cursor = {"x": x, "y": y}

    def update_selection(self, user_id: str, selection: list[str]):
        if user_id in self.collaborators:
            self.collaborators[user_id].selection = selection

    def add_message(self, user_id: str, username: str, content: str):
        self.messages.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "username": username,
            "content": content,
            "timestamp": time.time(),
        })

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "created_at": self.created_at,
            "collaborators": {
                uid: {
                    "user_id": c.user_id,
                    "username": c.username,
                    "cursor": c.cursor,
                    "selection": c.selection,
                    "joined_at": c.joined_at,
                }
                for uid, c in self.collaborators.items()
            },
            "shared_data": self.shared_data,
            "messages": self.messages[-50:],  # 最近 50 条消息
        }


class CollaborationManager:
    """协作管理器：管理协作会话和实时同步。"""

    def __init__(self):
        self._sessions: dict[str, CollaborationSession] = {}
        self._user_sessions: dict[str, str] = {}  # user_id -> session_id
        self._connections: dict[str, Any] = {}  # user_id -> websocket

    def create_session(self, name: str, owner_id: str) -> CollaborationSession:
        """创建协作会话。"""
        session_id = str(uuid.uuid4())[:8]
        session = CollaborationSession(
            id=session_id,
            name=name,
            owner_id=owner_id,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> CollaborationSession | None:
        return self._sessions.get(session_id)

    def join_session(self, session_id: str, user_id: str, username: str) -> bool:
        """加入协作会话。"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.add_collaborator(user_id, username)
        self._user_sessions[user_id] = session_id
        return True

    def leave_session(self, user_id: str):
        """离开协作会话。"""
        session_id = self._user_sessions.pop(user_id, None)
        if session_id:
            session = self._sessions.get(session_id)
            if session:
                session.remove_collaborator(user_id)

    def set_connection(self, user_id: str, ws: Any):
        """设置用户 WebSocket 连接。"""
        self._connections[user_id] = ws

    def remove_connection(self, user_id: str):
        """移除用户连接。"""
        self._connections.pop(user_id, None)

    async def broadcast_to_session(self, session_id: str, message: dict, exclude_user: str | None = None):
        """向会话内所有用户广播消息。"""
        session = self._sessions.get(session_id)
        if not session:
            return

        data = json.dumps(message)
        for user_id, collab in session.collaborators.items():
            if user_id == exclude_user:
                continue
            ws = self._connections.get(user_id)
            if ws:
                try:
                    await ws.send_text(data)
                except Exception:
                    pass

    async def send_cursor_update(self, user_id: str, x: float, y: float):
        """发送光标更新。"""
        session_id = self._user_sessions.get(user_id)
        if not session_id:
            return

        session = self._sessions.get(session_id)
        if not session:
            return

        collab = session.collaborators.get(user_id)
        if collab:
            collab.cursor = {"x": x, "y": y}

        await self.broadcast_to_session(
            session_id,
            {"type": "cursor", "user_id": user_id, "x": x, "y": y},
            exclude_user=user_id,
        )

    async def send_selection_update(self, user_id: str, selection: list[str]):
        """发送选择更新。"""
        session_id = self._user_sessions.get(user_id)
        if not session_id:
            return

        session = self._sessions.get(session_id)
        if session:
            session.update_selection(user_id, selection)

        await self.broadcast_to_session(
            session_id,
            {"type": "selection", "user_id": user_id, "selection": selection},
            exclude_user=user_id,
        )

    async def send_chat_message(self, user_id: str, username: str, content: str):
        """发送聊天消息。"""
        session_id = self._user_sessions.get(user_id)
        if not session_id:
            return

        session = self._sessions.get(session_id)
        if session:
            session.add_message(user_id, username, content)

        await self.broadcast_to_session(
            session_id,
            {"type": "chat", "user_id": user_id, "username": username, "content": content},
        )

    def list_sessions(self) -> list[dict]:
        """列出所有活跃会话。"""
        return [
            {"id": s.id, "name": s.name, "owner_id": s.owner_id, "collaborators": len(s.collaborators)}
            for s in self._sessions.values()
        ]

    def get_user_session(self, user_id: str) -> str | None:
        return self._user_sessions.get(user_id)


# 全局协作管理器
_collab_manager: CollaborationManager | None = None


def get_collab_manager() -> CollaborationManager:
    global _collab_manager
    if _collab_manager is None:
        _collab_manager = CollaborationManager()
    return _collab_manager
