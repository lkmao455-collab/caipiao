"""实时监控 WebSocket 路由。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..realtime_monitor import get_monitor

router = APIRouter(tags=["realtime"])


class ConnectionManager:
    """WebSocket 连接管理器。"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """实时监控 WebSocket 端点。"""
    await manager.connect(websocket)
    monitor = get_monitor()
    monitor.subscribe(websocket)

    try:
        while True:
            # 接收客户端消息（如设置刷新频率）
            data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        manager.disconnect(websocket)
        monitor.unsubscribe(websocket)


@router.get("/monitor/history")
def get_metrics_history(minutes: int = 5):
    """获取历史指标（REST）。"""
    monitor = get_monitor()
    history = monitor.get_history(minutes)
    return {
        "metrics": [
            {
                "cpu_percent": m.cpu_percent,
                "memory_mb": round(m.memory_mb, 2),
                "memory_percent": m.memory_percent,
                "network_sent": round(m.network_sent, 2),
                "network_recv": round(m.network_recv, 2),
                "timestamp": m.timestamp,
            }
            for m in history
        ]
    }


@router.post("/monitor/custom")
def record_custom_metric(name: str, value: float):
    """记录自定义指标。"""
    monitor = get_monitor()
    monitor.record_custom_metric(name, value)
    return {"status": "ok"}


@router.get("/monitor/custom/{name}")
def get_custom_metric_history(name: str, minutes: int = 5):
    """获取自定义指标历史。"""
    monitor = get_monitor()
    history = monitor.get_custom_metric(name, minutes)
    return {
        "name": name,
        "points": [
            {"timestamp": p.timestamp, "value": p.value, "labels": p.labels}
            for p in history
        ],
    }
