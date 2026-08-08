"""Web 后端 ORM 模型：用户与 API Key。"""

from __future__ import annotations

import datetime
import time
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """注册用户。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # 角色：admin（管理员）/ user（普通用户）。P5.E 多用户权限分级。
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class ApiKey(Base):
    """用户的开放平台 API Key（仅存储哈希，原始 key 仅创建时返回一次）。"""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped[User] = relationship("User", back_populates="api_keys")


class WorkflowDefinitionRow(Base):
    """持久化的工作流定义（节点/边以 JSON 存储，执行态仍在内存）。"""

    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class UserProfileRow(Base):
    """持久化的用户画像（标签/偏好/行为特征以 JSON 存储）。"""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class ProfileSegmentRow(Base):
    """持久化的用户分群定义。"""

    __tablename__ = "profile_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class DashboardRow(Base):
    """持久化的可视化仪表盘。"""

    __tablename__ = "dashboards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class VisualizationTemplateRow(Base):
    """持久化的可视化模板。"""

    __tablename__ = "visualization_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class TaskDefinitionRow(Base):
    """持久化的定时任务定义（运行状态仍在内存）。"""

    __tablename__ = "task_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class ScheduledTaskRow(Base):
    """持久化的自动化任务（fetch/backtest/analysis）。"""

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(32), default="")
    profile_key: Mapped[str] = mapped_column(String(32), default="")
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class FunnelRow(Base):
    """持久化的转化漏斗定义。"""

    __tablename__ = "funnels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class ABTestRow(Base):
    """持久化的 A/B 实验定义。"""

    __tablename__ = "ab_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class TenantRow(Base):
    """持久化的租户定义。"""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    status: Mapped[str] = mapped_column(String(32), default="active")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class TenantUserRow(Base):
    """持久化的租户成员关系。"""

    __tablename__ = "tenant_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class ResourceUsageRow(Base):
    """持久化的租户资源用量快照。"""

    __tablename__ = "resource_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class UsageRecord(Base):
    """按用户/端点累计的用量计量（用于开放平台配额与统计）。"""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    count: Mapped[int] = mapped_column(default=1, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class AuditLogRow(Base):
    """持久化的安全审计日志条目（合规关键，重启不丢失）。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(128), default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


# --- 发布管理 (release_manager) ---


class FeatureFlagRow(Base):
    """持久化的功能开关定义。"""

    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # flag key
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout_percentage: Mapped[float] = mapped_column(Float, default=0)
    target_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class ReleaseVersionRow(Base):
    """持久化的发布版本定义。"""

    __tablename__ = "release_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    rollout_percentage: Mapped[float] = mapped_column(Float, default=0)
    target_audience: Mapped[str] = mapped_column(String(32), default="all")
    features_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    released_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class DeploymentRow(Base):
    """持久化的部署记录（append-only）。"""

    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(32), default="production")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    rollback_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


# --- 数据治理 (data_governance) ---


class DatasetRow(Base):
    """持久化的数据集元数据定义。"""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(256), default="")
    schema_json: Mapped[str] = mapped_column(Text, default="[]")
    owner: Mapped[str] = mapped_column(String(64), default="")
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[float] = mapped_column(Float, default=time.time)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class DataLineageRow(Base):
    """持久化的数据血缘关系（append-only）。"""

    __tablename__ = "data_lineage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_dataset: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_dataset: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transform_type: Mapped[str] = mapped_column(String(32), default="copy")
    transform_logic: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class QualityRuleRow(Base):
    """持久化的数据质量规则定义。"""

    __tablename__ = "quality_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(32), default="not_null")
    field_name: Mapped[str] = mapped_column(String(128), default="")
    expression: Mapped[str] = mapped_column(Text, default="")
    threshold: Mapped[float] = mapped_column(Float, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


# --- 备份管理 (backup_manager) ---


class BackupConfigRow(Base):
    """持久化的备份配置定义。"""

    __tablename__ = "backup_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    backup_type: Mapped[str] = mapped_column(String(32), default="full")
    source_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    destination: Mapped[str] = mapped_column(String(512), default="")
    schedule: Mapped[str] = mapped_column(String(128), default="")
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    compression: Mapped[bool] = mapped_column(Boolean, default=True)
    encryption: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class BackupRecordRow(Base):
    """持久化的备份执行记录（append-only，引用磁盘上的备份文件）。"""

    __tablename__ = "backup_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    config_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    backup_type: Mapped[str] = mapped_column(String(32), default="full")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    compressed_size: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class RestorePointRow(Base):
    """持久化的恢复点定义。"""

    __tablename__ = "restore_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    backup_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
