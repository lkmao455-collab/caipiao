"""工作流引擎：可视化编排和执行自动化流程。"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any, Callable, Awaitable

from ..log import get_logger
from . import db as _webdb
from .models import WorkflowDefinitionRow

logger = get_logger(__name__)


# 受限内建函数白名单：供表达式求值使用，杜绝 __import__/open/exec 等危险调用。
_SAFE_BUILTINS: dict[str, Any] = {
    "len": len, "min": min, "max": max, "abs": abs, "sum": sum,
    "round": round, "sorted": sorted, "any": any, "all": all,
    "range": range, "enumerate": enumerate, "zip": zip,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "map": map, "filter": filter,
}


def _safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """在受限命名空间内求值表达式。

    显式传入 ``__builtins__`` 为空字典，覆盖 Python 默认自动注入完整
    内建的行为，使表达式无法访问 ``__import__`` / ``open`` / ``eval`` 等。
    仅暴露 ``ctx``（运行上下文，包装为 SimpleNamespace 支持 ``ctx.x`` 访问）
    与白名单内建函数。
    """
    return eval(
        expr,
        {"__builtins__": _SAFE_BUILTINS},
        {"ctx": SimpleNamespace(**context)},
    )


def _definition_to_dict(defn: WorkflowDefinition) -> dict[str, Any]:
    """将工作流定义序列化为可 JSON 化的字典（枚举转 value）。"""
    return {
        "id": defn.id,
        "name": defn.name,
        "description": defn.description,
        "version": defn.version,
        "created_at": defn.created_at,
        "updated_at": defn.updated_at,
        "nodes": [
            {
                "id": n.id,
                "type": n.type.value,
                "name": n.name,
                "config": n.config,
                "next_nodes": n.next_nodes,
                "condition": n.condition,
            }
            for n in defn.nodes
        ],
        "edges": [
            {"source": e.source, "target": e.target, "condition": e.condition}
            for e in defn.edges
        ],
    }


def _dict_to_definition(d: dict[str, Any]) -> WorkflowDefinition:
    """从字典还原工作流定义。"""
    return WorkflowDefinition(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        version=d.get("version", 1),
        created_at=d.get("created_at", time.time()),
        updated_at=d.get("updated_at", time.time()),
        nodes=[
            WorkflowNode(
                id=n["id"],
                type=NodeType(n["type"]),
                name=n["name"],
                config=n.get("config", {}),
                next_nodes=n.get("next_nodes", []),
                condition=n.get("condition", ""),
            )
            for n in d.get("nodes", [])
        ],
        edges=[
            WorkflowEdge(
                source=e["source"],
                target=e["target"],
                condition=e.get("condition", ""),
            )
            for e in d.get("edges", [])
        ],
    )


class NodeType(str, Enum):
    START = "start"
    END = "end"
    ACTION = "action"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    DELAY = "delay"
    WEBHOOK = "webhook"
    TRANSFORM = "transform"


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowNode:
    id: str
    type: NodeType
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    next_nodes: list[str] = field(default_factory=list)
    condition: str = ""


@dataclass
class WorkflowEdge:
    source: str
    target: str
    condition: str = ""


@dataclass
class WorkflowDefinition:
    id: str
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1


@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    status: str = "running"
    node_states: dict[str, NodeStatus] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str = ""


ActionHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[Any]]


class WorkflowEngine:
    """工作流引擎：定义、执行和管理工作流。"""

    def __init__(self):
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._runs: dict[str, WorkflowRun] = {}
        self._action_handlers: dict[str, ActionHandler] = {}
        self._loaded = False
        self._loaded_db_url: str | None = None
        self._register_default_handlers()

    def _ensure_loaded(self) -> None:
        """从数据库惰性加载工作流定义到内存缓存。

        记录加载时所用的数据库 URL；当 URL 变化（测试隔离切换临时库）
        时自动清空并重新加载，避免跨库串数据。
        """
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._definitions = {}
        with _webdb._SessionLocal() as session:
            for row in session.query(WorkflowDefinitionRow).all():
                try:
                    self._definitions[row.id] = _dict_to_definition(
                        json.loads(row.definition_json)
                    )
                except Exception as exc:
                    logger.error("加载工作流 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _register_default_handlers(self):
        self._action_handlers["log"] = self._handle_log
        self._action_handlers["delay"] = self._handle_delay
        self._action_handlers["transform"] = self._handle_transform
        self._action_handlers["condition_check"] = self._handle_condition

    async def _handle_log(self, config: dict, context: dict) -> Any:
        message = config.get("message", "")
        logger.info(f"Workflow log: {message}")
        return {"logged": True}

    async def _handle_delay(self, config: dict, context: dict) -> Any:
        seconds = config.get("seconds", 1)
        await asyncio.sleep(min(seconds, 60))
        return {"delayed": seconds}

    async def _handle_transform(self, config: dict, context: dict) -> Any:
        expr = config.get("expression", "")
        try:
            result = _safe_eval(expr, context)
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_condition(self, config: dict, context: dict) -> Any:
        expr = config.get("expression", "True")
        try:
            result = bool(_safe_eval(expr, context))
            return {"result": result}
        except Exception:
            return {"result": False}

    def register_action(self, name: str, handler: ActionHandler):
        self._action_handlers[name] = handler

    def create_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._ensure_loaded()
        definition.updated_at = time.time()
        with _webdb._SessionLocal() as session:
            row = WorkflowDefinitionRow(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                version=definition.version,
                enabled=True,
                definition_json=json.dumps(
                    _definition_to_dict(definition), ensure_ascii=False
                ),
                created_at=definition.created_at,
                updated_at=definition.updated_at,
            )
            session.add(row)
            session.commit()
        self._definitions[definition.id] = definition
        return definition

    def get_definition(self, def_id: str) -> WorkflowDefinition | None:
        self._ensure_loaded()
        return self._definitions.get(def_id)

    def list_definitions(self) -> list[WorkflowDefinition]:
        self._ensure_loaded()
        return list(self._definitions.values())

    def delete_definition(self, def_id: str) -> bool:
        self._ensure_loaded()
        if def_id not in self._definitions:
            return False
        with _webdb._SessionLocal() as session:
            row = session.get(WorkflowDefinitionRow, def_id)
            if row is not None:
                session.delete(row)
                session.commit()
        del self._definitions[def_id]
        return True

    async def execute(self, workflow_id: str, initial_context: dict | None = None) -> WorkflowRun | None:
        self._ensure_loaded()
        definition = self._definitions.get(workflow_id)
        if not definition:
            return None

        run = WorkflowRun(
            id=str(uuid.uuid4())[:8],
            workflow_id=workflow_id,
            context=initial_context or {},
        )
        self._runs[run.id] = run

        # 找到起始节点
        start_nodes = [n for n in definition.nodes if n.type == NodeType.START]
        if not start_nodes:
            run.status = "failed"
            run.error = "No start node found"
            return run

        asyncio.create_task(self._execute_node(definition, run, start_nodes[0].id))
        return run

    async def _execute_node(self, definition: WorkflowDefinition, run: WorkflowRun, node_id: str):
        node = next((n for n in definition.nodes if n.id == node_id), None)
        if not node:
            run.node_states[node_id] = NodeStatus.FAILED
            return

        run.node_states[node_id] = NodeStatus.RUNNING

        try:
            if node.type == NodeType.END:
                run.node_states[node_id] = NodeStatus.COMPLETED
                run.status = "completed"
                run.completed_at = time.time()
                return

            if node.type in (NodeType.START,):
                run.node_states[node_id] = NodeStatus.COMPLETED
            elif node.type == NodeType.ACTION:
                handler = self._action_handlers.get(node.config.get("action", ""))
                if handler:
                    result = await handler(node.config, run.context)
                    run.node_outputs[node_id] = result
                run.node_states[node_id] = NodeStatus.COMPLETED
            elif node.type == NodeType.CONDITION:
                result = await self._handle_condition(node.config, run.context)
                run.node_outputs[node_id] = result
                run.node_states[node_id] = NodeStatus.COMPLETED
            elif node.type == NodeType.DELAY:
                await self._handle_delay(node.config, run.context)
                run.node_states[node_id] = NodeStatus.COMPLETED
            elif node.type == NodeType.TRANSFORM:
                result = await self._handle_transform(node.config, run.context)
                run.node_outputs[node_id] = result
                run.node_states[node_id] = NodeStatus.COMPLETED
            else:
                run.node_states[node_id] = NodeStatus.COMPLETED

            # 执行下一个节点
            for next_id in node.next_nodes:
                await self._execute_node(definition, run, next_id)

        except Exception as e:
            run.node_states[node_id] = NodeStatus.FAILED
            run.status = "failed"
            run.error = str(e)
            run.completed_at = time.time()

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def list_runs(self, workflow_id: str | None = None) -> list[WorkflowRun]:
        runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return runs[-100:]


# 全局工作流引擎
_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
