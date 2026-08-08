"""DevOps 平台：CI/CD 流水线、构建部署。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineStage:
    name: str
    type: str  # build, test, scan, deploy, notify
    config: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: float | None = None
    completed_at: float | None = None
    output: str = ""


@dataclass
class Pipeline:
    id: str
    name: str
    description: str = ""
    stages: list[PipelineStage] = field(default_factory=list)
    trigger: str = "manual"  # manual, push, schedule, webhook
    status: str = "pending"  # pending, running, completed, failed
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    branch: str = "main"
    commit_sha: str = ""


@dataclass
class BuildArtifact:
    id: str
    pipeline_id: str
    name: str
    version: str
    file_path: str = ""
    file_size: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class DeploymentTarget:
    id: str
    name: str
    environment: str  # dev, staging, production
    host: str = ""
    port: int = 0
    status: str = "active"
    current_version: str = ""
    last_deployed: float | None = None


class DevOpsPlatform:
    """DevOps 平台：流水线管理、构建部署。"""

    def __init__(self):
        self._pipelines: dict[str, Pipeline] = {}
        self._artifacts: list[BuildArtifact] = []
        self._targets: dict[str, DeploymentTarget] = {}

    # 流水线管理
    def create_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> list[Pipeline]:
        return list(self._pipelines.values())

    def delete_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id in self._pipelines:
            del self._pipelines[pipeline_id]
            return True
        return False

    def run_pipeline(self, pipeline_id: str, branch: str = "main", commit_sha: str = "") -> Pipeline | None:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return None

        pipeline.status = "running"
        pipeline.started_at = time.time()
        pipeline.branch = branch
        pipeline.commit_sha = commit_sha

        for stage in pipeline.stages:
            stage.status = "running"
            stage.started_at = time.time()

            try:
                stage.status = "completed"
                stage.completed_at = time.time()
                stage.output = f"Stage {stage.name} completed successfully"
            except Exception as e:
                stage.status = "failed"
                stage.completed_at = time.time()
                stage.output = str(e)
                pipeline.status = "failed"
                pipeline.completed_at = time.time()
                return pipeline

        pipeline.status = "completed"
        pipeline.completed_at = time.time()
        return pipeline

    def get_pipeline_runs(self, pipeline_id: str, limit: int = 10) -> list[dict]:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return []

        runs = []
        if pipeline.completed_at:
            runs.append({
                "pipeline_id": pipeline_id,
                "status": pipeline.status,
                "branch": pipeline.branch,
                "started_at": pipeline.started_at,
                "completed_at": pipeline.completed_at,
                "duration": pipeline.completed_at - (pipeline.started_at or pipeline.completed_at),
            })

        return runs[:limit]

    # 构件管理
    def add_artifact(self, artifact: BuildArtifact) -> BuildArtifact:
        self._artifacts.append(artifact)
        return artifact

    def get_artifacts(self, pipeline_id: str | None = None, limit: int = 50) -> list[BuildArtifact]:
        artifacts = self._artifacts
        if pipeline_id:
            artifacts = [a for a in artifacts if a.pipeline_id == pipeline_id]
        return artifacts[-limit:]

    # 部署目标
    def create_target(self, target: DeploymentTarget) -> DeploymentTarget:
        self._targets[target.id] = target
        return target

    def get_target(self, target_id: str) -> DeploymentTarget | None:
        return self._targets.get(target_id)

    def list_targets(self, environment: str | None = None) -> list[DeploymentTarget]:
        targets = list(self._targets.values())
        if environment:
            targets = [t for t in targets if t.environment == environment]
        return targets

    def deploy(self, target_id: str, version: str, artifact_id: str) -> bool:
        target = self._targets.get(target_id)
        if not target:
            return False

        target.current_version = version
        target.last_deployed = time.time()
        logger.info(f"Deployed {version} to {target.name}")
        return True

    def rollback(self, target_id: str, previous_version: str) -> bool:
        target = self._targets.get(target_id)
        if not target:
            return False

        target.current_version = previous_version
        target.last_deployed = time.time()
        logger.info(f"Rolled back {target.name} to {previous_version}")
        return True

    # 统计
    def get_stats(self) -> dict:
        total_pipelines = len(self._pipelines)
        total_artifacts = len(self._artifacts)
        total_targets = len(self._targets)

        return {
            "total_pipelines": total_pipelines,
            "total_artifacts": total_artifacts,
            "total_targets": total_targets,
            "environments": {
                env: len([t for t in self._targets.values() if t.environment == env])
                for env in ["dev", "staging", "production"]
            },
        }


# 全局 DevOps 平台
_platform: DevOpsPlatform | None = None


def get_devops_platform() -> DevOpsPlatform:
    global _platform
    if _platform is None:
        _platform = DevOpsPlatform()
    return _platform
