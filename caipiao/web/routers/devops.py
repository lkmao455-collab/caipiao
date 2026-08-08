"""DevOps 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..devops import Pipeline, PipelineStage, BuildArtifact, DeploymentTarget, get_devops_platform

router = APIRouter(prefix="/devops", tags=["devops"])


class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    stages: list[dict] = []
    trigger: str = "manual"


class PipelineRun(BaseModel):
    branch: str = "main"
    commit_sha: str = ""


class ArtifactCreate(BaseModel):
    pipeline_id: str
    name: str
    version: str
    file_path: str = ""
    file_size: int = 0


class TargetCreate(BaseModel):
    name: str
    environment: str
    host: str = ""
    port: int = 0


class DeployRequest(BaseModel):
    version: str
    artifact_id: str = ""


@router.post("/pipelines")
def create_pipeline(
    req: PipelineCreate,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    stages = [PipelineStage(name=s.get("name", ""), type=s.get("type", "build")) for s in req.stages]
    pipeline = Pipeline(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        stages=stages,
        trigger=req.trigger,
    )
    platform.create_pipeline(pipeline)
    return {"id": pipeline.id, "name": pipeline.name}


@router.get("/pipelines")
def list_pipelines(
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    return [
        {"id": p.id, "name": p.name, "status": p.status, "trigger": p.trigger}
        for p in platform.list_pipelines()
    ]


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(
    pipeline_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    p = platform.get_pipeline(pipeline_id)
    if not p:
        return {"error": "Not found"}
    return {
        "id": p.id, "name": p.name, "status": p.status,
        "stages": [{"name": s.name, "type": s.type, "status": s.status} for s in p.stages],
    }


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(
    pipeline_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    if platform.delete_pipeline(pipeline_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/pipelines/{pipeline_id}/run")
def run_pipeline(
    pipeline_id: str,
    req: PipelineRun,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    pipeline = platform.run_pipeline(pipeline_id, req.branch, req.commit_sha)
    if not pipeline:
        return {"error": "Not found"}
    return {"id": pipeline.id, "status": pipeline.status}


@router.get("/pipelines/{pipeline_id}/runs")
def get_pipeline_runs(
    pipeline_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    return platform.get_pipeline_runs(pipeline_id)


@router.post("/artifacts")
def create_artifact(
    req: ArtifactCreate,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    artifact = BuildArtifact(
        id=str(__import__("uuid").uuid4())[:8],
        pipeline_id=req.pipeline_id,
        name=req.name,
        version=req.version,
        file_path=req.file_path,
        file_size=req.file_size,
    )
    platform.add_artifact(artifact)
    return {"id": artifact.id, "name": artifact.name}


@router.get("/artifacts")
def list_artifacts(
    pipeline_id: str | None = None,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    artifacts = platform.get_artifacts(pipeline_id)
    return [{"id": a.id, "name": a.name, "version": a.version, "created_at": a.created_at} for a in artifacts]


@router.post("/targets")
def create_target(
    req: TargetCreate,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    target = DeploymentTarget(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        environment=req.environment,
        host=req.host,
        port=req.port,
    )
    platform.create_target(target)
    return {"id": target.id, "name": target.name}


@router.get("/targets")
def list_targets(
    environment: str | None = None,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    targets = platform.list_targets(environment)
    return [
        {"id": t.id, "name": t.name, "environment": t.environment, "current_version": t.current_version}
        for t in targets
    ]


@router.post("/targets/{target_id}/deploy")
def deploy(
    target_id: str,
    req: DeployRequest,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    if platform.deploy(target_id, req.version, req.artifact_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/targets/{target_id}/rollback")
def rollback(
    target_id: str,
    previous_version: str,
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    if platform.rollback(target_id, previous_version):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    platform = get_devops_platform()
    return platform.get_stats()
