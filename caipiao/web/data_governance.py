"""数据治理平台：数据血缘、元数据管理、数据目录。

持久化：数据集、数据血缘、质量规则定义写入 web 数据库（核心层零侵入）。
质量检查结果 (_quality_results) 为运行期计算结果，保持内存态。实例会在每次调用时
按需从数据库水合（URL 感知，支持测试隔离与进程重启持久化）。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


@dataclass
class MetadataField:
    name: str
    type: str  # string, number, boolean, date, json
    description: str = ""
    nullable: bool = True
    is_primary_key: bool = False
    is_sensitive: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    id: str
    name: str
    description: str = ""
    source: str = ""
    schema: list[MetadataField] = field(default_factory=list)
    owner: str = ""
    quality_score: float = 0
    row_count: int = 0
    last_updated: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class DataLineage:
    id: str
    source_dataset: str
    target_dataset: str
    transform_type: str  # copy, aggregate, filter, join, custom
    transform_logic: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class DataQualityRule:
    id: str
    dataset_id: str
    rule_type: str  # not_null, unique, range, format, custom
    field_name: str = ""
    expression: str = ""
    threshold: float = 100
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class QualityCheckResult:
    rule_id: str
    dataset_id: str
    passed: bool
    score: float = 0
    details: str = ""
    checked_at: float = field(default_factory=time.time)


class DataGovernancePlatform:
    """数据治理平台：元数据管理、数据血缘、质量检查。"""

    def __init__(self):
        self._datasets: dict[str, Dataset] = {}
        self._lineage: list[DataLineage] = []
        self._quality_rules: dict[str, DataQualityRule] = {}
        self._quality_results: list[QualityCheckResult] = []
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._datasets = {}
        self._lineage = []
        self._quality_rules = {}
        from .models import (
            DataLineageRow,
            DatasetRow,
            QualityRuleRow,
        )

        with _webdb._SessionLocal() as session:
            for row in session.query(DatasetRow).all():
                try:
                    self._datasets[row.id] = Dataset(
                        id=row.id,
                        name=row.name,
                        description=row.description,
                        source=row.source,
                        schema=[MetadataField(**f) for f in json.loads(row.schema_json)],
                        owner=row.owner,
                        quality_score=row.quality_score,
                        row_count=row.row_count,
                        last_updated=row.last_updated,
                        tags=json.loads(row.tags_json),
                        created_at=row.created_at,
                    )
                except Exception as exc:
                    logger.error("加载数据集 %s 失败: %s", row.id, exc)
            for row in session.query(DataLineageRow).all():
                try:
                    self._lineage.append(
                        DataLineage(
                            id=row.id,
                            source_dataset=row.source_dataset,
                            target_dataset=row.target_dataset,
                            transform_type=row.transform_type,
                            transform_logic=row.transform_logic,
                            created_at=row.created_at,
                        )
                    )
                except Exception as exc:
                    logger.error("加载血缘 %s 失败: %s", row.id, exc)
            for row in session.query(QualityRuleRow).all():
                try:
                    self._quality_rules[row.id] = DataQualityRule(
                        id=row.id,
                        dataset_id=row.dataset_id,
                        rule_type=row.rule_type,
                        field_name=row.field_name,
                        expression=row.expression,
                        threshold=row.threshold,
                        enabled=row.enabled,
                        created_at=row.created_at,
                    )
                except Exception as exc:
                    logger.error("加载质量规则 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_dataset(self, dataset_id: str) -> None:
        from .models import DatasetRow

        d = self._datasets.get(dataset_id)
        with _webdb._SessionLocal() as session:
            row = session.get(DatasetRow, dataset_id)
            if d is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            schema_json = json.dumps(
                [
                    {
                        "name": f.name,
                        "type": f.type,
                        "description": f.description,
                        "nullable": f.nullable,
                        "is_primary_key": f.is_primary_key,
                        "is_sensitive": f.is_sensitive,
                        "tags": f.tags,
                    }
                    for f in d.schema
                ],
                ensure_ascii=False,
            )
            if row is None:
                session.add(
                    DatasetRow(
                        id=d.id,
                        name=d.name,
                        description=d.description,
                        source=d.source,
                        schema_json=schema_json,
                        owner=d.owner,
                        quality_score=d.quality_score,
                        row_count=d.row_count,
                        last_updated=d.last_updated,
                        tags_json=json.dumps(d.tags, ensure_ascii=False),
                        created_at=d.created_at,
                    )
                )
            else:
                row.name = d.name
                row.description = d.description
                row.source = d.source
                row.schema_json = schema_json
                row.owner = d.owner
                row.quality_score = d.quality_score
                row.row_count = d.row_count
                row.last_updated = d.last_updated
                row.tags_json = json.dumps(d.tags, ensure_ascii=False)
                row.created_at = d.created_at
            session.commit()

    def _persist_lineage(self, lineage: DataLineage) -> None:
        from .models import DataLineageRow

        with _webdb._SessionLocal() as session:
            row = session.get(DataLineageRow, lineage.id)
            if row is None:
                session.add(
                    DataLineageRow(
                        id=lineage.id,
                        source_dataset=lineage.source_dataset,
                        target_dataset=lineage.target_dataset,
                        transform_type=lineage.transform_type,
                        transform_logic=lineage.transform_logic,
                        created_at=lineage.created_at,
                    )
                )
                session.commit()

    def _persist_quality_rule(self, rule_id: str) -> None:
        from .models import QualityRuleRow

        r = self._quality_rules.get(rule_id)
        with _webdb._SessionLocal() as session:
            row = session.get(QualityRuleRow, rule_id)
            if r is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                session.add(
                    QualityRuleRow(
                        id=r.id,
                        dataset_id=r.dataset_id,
                        rule_type=r.rule_type,
                        field_name=r.field_name,
                        expression=r.expression,
                        threshold=r.threshold,
                        enabled=r.enabled,
                        created_at=r.created_at,
                    )
                )
            else:
                row.dataset_id = r.dataset_id
                row.rule_type = r.rule_type
                row.field_name = r.field_name
                row.expression = r.expression
                row.threshold = r.threshold
                row.enabled = r.enabled
                row.created_at = r.created_at
            session.commit()

    # 数据集管理
    def create_dataset(self, dataset: Dataset) -> Dataset:
        self._ensure_loaded()
        self._datasets[dataset.id] = dataset
        self._persist_dataset(dataset.id)
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        self._ensure_loaded()
        return self._datasets.get(dataset_id)

    def list_datasets(self, tags: list[str] | None = None) -> list[Dataset]:
        self._ensure_loaded()
        datasets = list(self._datasets.values())
        if tags:
            datasets = [d for d in datasets if any(t in d.tags for t in tags)]
        return datasets

    def update_dataset(self, dataset_id: str, **kwargs) -> bool:
        self._ensure_loaded()
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            return False
        for k, v in kwargs.items():
            if hasattr(dataset, k):
                setattr(dataset, k, v)
        dataset.last_updated = time.time()
        self._persist_dataset(dataset_id)
        return True

    def delete_dataset(self, dataset_id: str) -> bool:
        self._ensure_loaded()
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            self._persist_dataset(dataset_id)
            return True
        return False

    def search_datasets(self, query: str) -> list[Dataset]:
        self._ensure_loaded()
        query_lower = query.lower()
        return [
            d for d in self._datasets.values()
            if query_lower in d.name.lower() or query_lower in d.description.lower()
        ]

    # 数据血缘
    def add_lineage(self, lineage: DataLineage) -> DataLineage:
        self._ensure_loaded()
        self._lineage.append(lineage)
        self._persist_lineage(lineage)
        return lineage

    def get_upstream(self, dataset_id: str) -> list[DataLineage]:
        self._ensure_loaded()
        return [l for l in self._lineage if l.target_dataset == dataset_id]

    def get_downstream(self, dataset_id: str) -> list[DataLineage]:
        self._ensure_loaded()
        return [l for l in self._lineage if l.source_dataset == dataset_id]

    def get_full_lineage(self, dataset_id: str) -> dict:
        upstream = []
        downstream = []

        def trace_up(did: str, depth: int = 0):
            if depth > 10:
                return
            for l in self.get_upstream(did):
                upstream.append({"dataset": l.source_dataset, "type": l.transform_type})
                trace_up(l.source_dataset, depth + 1)

        def trace_down(did: str, depth: int = 0):
            if depth > 10:
                return
            for l in self.get_downstream(did):
                downstream.append({"dataset": l.target_dataset, "type": l.transform_type})
                trace_down(l.target_dataset, depth + 1)

        trace_up(dataset_id)
        trace_down(dataset_id)

        return {"dataset_id": dataset_id, "upstream": upstream, "downstream": downstream}

    # 数据质量
    def create_quality_rule(self, rule: DataQualityRule) -> DataQualityRule:
        self._ensure_loaded()
        self._quality_rules[rule.id] = rule
        self._persist_quality_rule(rule.id)
        return rule

    def get_quality_rules(self, dataset_id: str) -> list[DataQualityRule]:
        self._ensure_loaded()
        return [r for r in self._quality_rules.values() if r.dataset_id == dataset_id]

    def check_quality(self, dataset_id: str) -> list[QualityCheckResult]:
        results = []
        rules = self.get_quality_rules(dataset_id)

        for rule in rules:
            if not rule.enabled:
                continue

            result = QualityCheckResult(
                rule_id=rule.id,
                dataset_id=dataset_id,
                passed=True,
                score=100,
            )
            results.append(result)
            self._quality_results.append(result)

        return results

    def get_quality_score(self, dataset_id: str) -> float:
        recent = [r for r in self._quality_results if r.dataset_id == dataset_id][-100:]
        if not recent:
            return 0
        return sum(r.score for r in recent) / len(recent)

    def get_quality_history(self, dataset_id: str, limit: int = 50) -> list[QualityCheckResult]:
        return [r for r in self._quality_results if r.dataset_id == dataset_id][-limit:]

    # 元数据查询
    def get_field_statistics(self, dataset_id: str) -> dict:
        self._ensure_loaded()
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            return {}
        return {
            "total_fields": len(dataset.schema),
            "nullable_fields": sum(1 for f in dataset.schema if f.nullable),
            "sensitive_fields": sum(1 for f in dataset.schema if f.is_sensitive),
            "primary_keys": sum(1 for f in dataset.schema if f.is_primary_key),
        }

    def get_governance_stats(self) -> dict:
        self._ensure_loaded()
        return {
            "total_datasets": len(self._datasets),
            "total_lineage": len(self._lineage),
            "total_quality_rules": len(self._quality_rules),
            "avg_quality_score": round(
                sum(self.get_quality_score(d.id) for d in self._datasets.values()) / max(len(self._datasets), 1),
                2,
            ),
        }


# 全局数据治理平台
_platform: DataGovernancePlatform | None = None


def get_data_governance_platform() -> DataGovernancePlatform:
    global _platform
    if _platform is None:
        _platform = DataGovernancePlatform()
    _platform._ensure_loaded()
    return _platform
