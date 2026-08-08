"""实时协作路由：创建/加入会话、实时同步。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..collaboration import get_collab_manager
from ..deps import get_current_principal

router = APIRouter(prefix="/collab", tags=["collaboration"])


class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class SessionOut(BaseModel):
    id: str
    name: str
    owner_id: str
    collaborators: int


@router.post("/sessions", response_model=SessionOut)
def create_session(
    req: SessionCreate,
    principal=Depends(get_current_principal),
):
    """创建协作会话。"""
    mgr = get_collab_manager()
    session = mgr.create_session(name=req.name, owner_id=principal.id)
    mgr.join_session(session.id, principal.id, principal.username)
    return SessionOut(
        id=session.id,
        name=session.name,
        owner_id=session.owner_id,
        collaborators=len(session.collaborators),
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions():
    """列出活跃会话。"""
    mgr = get_collab_manager()
    return [
        SessionOut(
            id=s["id"],
            name=s["name"],
            owner_id=s["owner_id"],
            collaborators=s["collaborators"],
        )
        for s in mgr.list_sessions()
    ]


@router.post("/sessions/{session_id}/join")
def join_session(
    session_id: str,
    principal=Depends(get_current_principal),
):
    """加入协作会话。"""
    mgr = get_collab_manager()
    if not mgr.join_session(session_id, principal.id, principal.username):
        from fastapi import HTTPException
        raise HTTPException(404, "会话不存在")
    return {"status": "ok"}


@router.post("/sessions/{session_id}/leave")
def leave_session(
    session_id: str,
    principal=Depends(get_current_principal),
):
    """离开协作会话。"""
    mgr = get_collab_manager()
    mgr.leave_session(principal.id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    principal=Depends(get_current_principal),
):
    """获取会话详情。"""
    mgr = get_collab_manager()
    session = mgr.get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(404, "会话不存在")
    return session.to_dict()


@router.websocket("/ws/collab/{session_id}")
async def websocket_collab(websocket: WebSocket, session_id: str):
    """协作 WebSocket 端点。"""
    await websocket.accept()
    mgr = get_collab_manager()

    # 从查询参数获取用户信息
    user_id = websocket.query_params.get("user_id", "anonymous")
    username = websocket.query_params.get("username", "Anonymous")

    # 加入会话
    mgr.join_session(session_id, user_id, username)
    mgr.set_connection(user_id, websocket)

    try:
        # 广播加入消息
        await mgr.broadcast_to_session(
            session_id,
            {"type": "user_join", "user_id": user_id, "username": username},
            exclude_user=user_id,
        )

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "cursor":
                    await mgr.send_cursor_update(user_id, msg.get("x", 0), msg.get("y", 0))
                elif msg_type == "selection":
                    await mgr.send_selection_update(user_id, msg.get("selection", []))
                elif msg_type == "chat":
                    await mgr.send_chat_message(user_id, username, msg.get("content", ""))
                elif msg_type == "data_update":
                    session = mgr.get_session(session_id)
                    if session:
                        session.shared_data.update(msg.get("data", {}))
                    await mgr.broadcast_to_session(
                        session_id,
                        {"type": "data_update", "user_id": user_id, "data": msg.get("data", {})},
                        exclude_user=user_id,
                    )
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        mgr.remove_connection(user_id)
        mgr.leave_session(user_id)
        await mgr.broadcast_to_session(
            session_id,
            {"type": "user_leave", "user_id": user_id, "username": username},
        )
