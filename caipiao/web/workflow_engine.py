"""工作流引擎：可视化编排和执行自动化流程。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from ..log import get_logger

logger = get_logger(__name__)


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
        self._register_default_handlers()

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
            result = eval(expr, {"ctx": context})
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_condition(self, config: dict, context: dict) -> Any:
        expr = config.get("expression", "True")
        try:
            result = bool(eval(expr, {"ctx": context}))
            return {"result": result}
        except Exception:
            return {"result": False}

    def register_action(self, name: str, handler: ActionHandler):
        self._action_handlers[name] = handler

    def create_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._definitions[definition.id] = definition
        return definition

    def get_definition(self, def_id: str) -> WorkflowDefinition | None:
        return self._definitions.get(def_id)

    def list_definitions(self) -> list[WorkflowDefinition]:
        return list(self._definitions.values())

    def delete_definition(self, def_id: str) -> bool:
        if def_id in self._definitions:
            del self._definitions[def_id]
            return True
        return False

    async def execute(self, workflow_id: str, initial_context: dict | None = None) -> WorkflowRun | None:
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
