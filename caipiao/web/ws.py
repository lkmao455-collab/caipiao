"""WebSocket 实时推送：订阅事件总线，推送生成/开奖事件。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .eventbus import bus

router = APIRouter()


@router.websocket("/ws/draws")
async def ws_draws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = bus.subscribe()
    q_task: asyncio.Task | None = None
    r_task: asyncio.Task | None = None
    try:
        while True:
            q_task = asyncio.create_task(queue.get())
            r_task = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait(
                {q_task, r_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if q_task in done:
                message = q_task.result()
                await websocket.send_json(message)
                r_task.cancel()
            else:
                # 客户端发来消息或已断开
                try:
                    r_task.result()
                except Exception:
                    q_task.cancel()
                    break
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
        for task in (q_task, r_task):
            if task is not None:
                task.cancel()
