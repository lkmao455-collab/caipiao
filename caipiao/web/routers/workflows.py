"""工作流路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import get_current_principal
from ..workflow_engine import WorkflowDefinition, WorkflowNode, WorkflowEdge, NodeType, get_workflow_engine

router = APIRouter(prefix="/workflows", tags=["workflows"])


class NodeSchema(BaseModel):
    id: str
    type: str
    name: str
    config: dict = {}
    next_nodes: list[str] = []


class EdgeSchema(BaseModel):
    source: str
    target: str
    condition: str = ""


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    nodes: list[NodeSchema] = []
    edges: list[EdgeSchema] = []


class WorkflowRunRequest(BaseModel):
    context: dict = {}


@router.post("")
def create_workflow(
    req: WorkflowCreate,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    nodes = [
        WorkflowNode(
            id=n.id,
            type=NodeType(n.type),
            name=n.name,
            config=n.config,
            next_nodes=n.next_nodes,
        )
        for n in req.nodes
    ]
    edges = [WorkflowEdge(source=e.source, target=e.target, condition=e.condition) for e in req.edges]
    definition = WorkflowDefinition(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        nodes=nodes,
        edges=edges,
    )
    engine.create_definition(definition)
    return {"id": definition.id, "name": definition.name}


@router.get("")
def list_workflows(
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    return [
        {"id": d.id, "name": d.name, "description": d.description, "nodes": len(d.nodes)}
        for d in engine.list_definitions()
    ]


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: str,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    d = engine.get_definition(workflow_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工作流不存在")
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "nodes": [{"id": n.id, "type": n.type, "name": n.name, "config": n.config, "next_nodes": n.next_nodes} for n in d.nodes],
        "edges": [{"source": e.source, "target": e.target, "condition": e.condition} for e in d.edges],
    }


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: str,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    if not engine.delete_definition(workflow_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工作流不存在")
    return {"status": "ok"}


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    req: WorkflowRunRequest,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    run = await engine.execute(workflow_id, req.context)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工作流不存在")
    return {"run_id": run.id, "status": run.status}


@router.get("/{workflow_id}/runs")
def list_workflow_runs(
    workflow_id: str,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    runs = engine.list_runs(workflow_id)
    return [
        {"id": r.id, "status": r.status, "started_at": r.started_at, "completed_at": r.completed_at, "error": r.error}
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_workflow_run(
    run_id: str,
    principal=Depends(get_current_principal),
):
    engine = get_workflow_engine()
    run = engine.get_run(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "运行不存在")
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "node_states": run.node_states,
        "node_outputs": run.node_outputs,
        "error": run.error,
    }
