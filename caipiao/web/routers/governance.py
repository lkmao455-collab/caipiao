"""数据治理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..data_governance import Dataset, DataLineage, DataQualityRule, MetadataField, get_data_governance_platform
from ..deps import get_current_principal

router = APIRouter(prefix="/governance", tags=["governance"])


class DatasetCreate(BaseModel):
    name: str
    description: str = ""
    source: str = ""
    owner: str = ""
    tags: list[str] = []


class LineageCreate(BaseModel):
    source_dataset: str
    target_dataset: str
    transform_type: str
    transform_logic: str = ""


class QualityRuleCreate(BaseModel):
    dataset_id: str
    rule_type: str
    field_name: str = ""
    expression: str = ""
    threshold: float = 100


@router.post("/datasets")
def create_dataset(
    req: DatasetCreate,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    dataset = Dataset(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        source=req.source,
        owner=req.owner,
        tags=req.tags,
    )
    platform.create_dataset(dataset)
    return {"id": dataset.id, "name": dataset.name}


@router.get("/datasets")
def list_datasets(
    tags: str | None = None,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    tag_list = tags.split(",") if tags else None
    datasets = platform.list_datasets(tag_list)
    return [
        {"id": d.id, "name": d.name, "description": d.description, "quality_score": d.quality_score, "tags": d.tags}
        for d in datasets
    ]


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    d = platform.get_dataset(dataset_id)
    if not d:
        return {"error": "Not found"}
    return {
        "id": d.id, "name": d.name, "description": d.description,
        "schema": [{"name": f.name, "type": f.type} for f in d.schema],
        "quality_score": d.quality_score, "tags": d.tags,
    }


@router.get("/datasets/search")
def search_datasets(
    q: str,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    datasets = platform.search_datasets(q)
    return [{"id": d.id, "name": d.name} for d in datasets]


@router.post("/lineage")
def add_lineage(
    req: LineageCreate,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    lineage = DataLineage(
        id=str(__import__("uuid").uuid4())[:8],
        source_dataset=req.source_dataset,
        target_dataset=req.target_dataset,
        transform_type=req.transform_type,
        transform_logic=req.transform_logic,
    )
    platform.add_lineage(lineage)
    return {"id": lineage.id}


@router.get("/lineage/{dataset_id}")
def get_lineage(
    dataset_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    return platform.get_full_lineage(dataset_id)


@router.post("/quality/rules")
def create_quality_rule(
    req: QualityRuleCreate,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    rule = DataQualityRule(
        id=str(__import__("uuid").uuid4())[:8],
        dataset_id=req.dataset_id,
        rule_type=req.rule_type,
        field_name=req.field_name,
        expression=req.expression,
        threshold=req.threshold,
    )
    platform.create_quality_rule(rule)
    return {"id": rule.id}


@router.get("/quality/{dataset_id}/check")
def check_quality(
    dataset_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    results = platform.check_quality(dataset_id)
    return {"results": [{"rule_id": r.rule_id, "passed": r.passed, "score": r.score} for r in results]}


@router.get("/quality/{dataset_id}/score")
def get_quality_score(
    dataset_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    score = platform.get_quality_score(dataset_id)
    return {"dataset_id": dataset_id, "score": score}


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    platform = get_data_governance_platform()
    return platform.get_governance_stats()
