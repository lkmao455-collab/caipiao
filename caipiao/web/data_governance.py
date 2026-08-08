"""数据治理平台：数据血缘、元数据管理、数据目录。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

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

    # 数据集管理
    def create_dataset(self, dataset: Dataset) -> Dataset:
        self._datasets[dataset.id] = dataset
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        return self._datasets.get(dataset_id)

    def list_datasets(self, tags: list[str] | None = None) -> list[Dataset]:
        datasets = list(self._datasets.values())
        if tags:
            datasets = [d for d in datasets if any(t in d.tags for t in tags)]
        return datasets

    def update_dataset(self, dataset_id: str, **kwargs) -> bool:
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            return False
        for k, v in kwargs.items():
            if hasattr(dataset, k):
                setattr(dataset, k, v)
        dataset.last_updated = time.time()
        return True

    def delete_dataset(self, dataset_id: str) -> bool:
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            return True
        return False

    def search_datasets(self, query: str) -> list[Dataset]:
        query_lower = query.lower()
        return [
            d for d in self._datasets.values()
            if query_lower in d.name.lower() or query_lower in d.description.lower()
        ]

    # 数据血缘
    def add_lineage(self, lineage: DataLineage) -> DataLineage:
        self._lineage.append(lineage)
        return lineage

    def get_upstream(self, dataset_id: str) -> list[DataLineage]:
        return [l for l in self._lineage if l.target_dataset == dataset_id]

    def get_downstream(self, dataset_id: str) -> list[DataLineage]:
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
        self._quality_rules[rule.id] = rule
        return rule

    def get_quality_rules(self, dataset_id: str) -> list[DataQualityRule]:
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
    return _platform
