"""高级报表路由：创建、生成、导出报表。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from urllib.parse import quote

from ..deps import get_current_principal
from ..report_engine import (
    ReportColumn,
    ReportConfig,
    ReportFilter,
    get_report_engine,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _content_disposition(name: str, ext: str) -> str:
    """构造 Content-Disposition 头，兼容含非 ASCII（中文）文件名的下载。"""
    ascii_name = name.encode("ascii", "ignore").decode().strip() or "report"
    return (
        f"attachment; filename=\"{ascii_name}.{ext}\"; "
        f"filename*=UTF-8''{quote(f'{name}.{ext}')}"
    )


class ColumnSchema(BaseModel):
    key: str
    label: str
    type: str = "text"
    width: int | None = None


class FilterSchema(BaseModel):
    field: str
    operator: str
    value: Any


class ReportCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    columns: list[ColumnSchema] = []
    filters: list[FilterSchema] = []
    sort_by: str = ""
    sort_order: str = "asc"
    group_by: str = ""
    chart_type: str = ""


class ReportOut(BaseModel):
    id: str
    name: str
    description: str
    columns: list[ColumnSchema]
    filters: list[FilterSchema]
    sort_by: str
    sort_order: str
    group_by: str
    chart_type: str
    created_at: float
    updated_at: float


@router.post("", response_model=ReportOut, status_code=201)
def create_report(
    req: ReportCreate,
    principal=Depends(get_current_principal),
):
    """创建报表配置。"""
    engine = get_report_engine()
    config = ReportConfig(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        columns=[ReportColumn(key=c.key, label=c.label, type=c.type, width=c.width) for c in req.columns],
        filters=[ReportFilter(field=f.field, operator=f.operator, value=f.value) for f in req.filters],
        sort_by=req.sort_by,
        sort_order=req.sort_order,
        group_by=req.group_by,
        chart_type=req.chart_type,
    )
    engine.create_config(config)
    return ReportOut(
        id=config.id,
        name=config.name,
        description=config.description,
        columns=req.columns,
        filters=req.filters,
        sort_by=config.sort_by,
        sort_order=config.sort_order,
        group_by=config.group_by,
        chart_type=config.chart_type,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.get("", response_model=list[ReportOut])
def list_reports(
    principal=Depends(get_current_principal),
):
    """列出报表配置。"""
    engine = get_report_engine()
    configs = engine.list_configs()
    return [
        ReportOut(
            id=c.id,
            name=c.name,
            description=c.description,
            columns=[ColumnSchema(key=col.key, label=col.label, type=col.type, width=col.width) for col in c.columns],
            filters=[FilterSchema(field=f.field, operator=f.operator, value=f.value) for f in c.filters],
            sort_by=c.sort_by,
            sort_order=c.sort_order,
            group_by=c.group_by,
            chart_type=c.chart_type,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in configs
    ]


@router.get("/data-sources")
def list_data_sources(
    principal=Depends(get_current_principal),
):
    """列出可用数据源（彩种开奖历史），供生成/导出报表时选择。"""
    engine = get_report_engine()
    return {"data_sources": engine.list_data_sources()}


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    principal=Depends(get_current_principal),
):
    """获取报表配置。"""
    engine = get_report_engine()
    config = engine.get_config(report_id)
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报表不存在")
    return ReportOut(
        id=config.id,
        name=config.name,
        description=config.description,
        columns=[ColumnSchema(key=col.key, label=col.label, type=col.type, width=col.width) for col in config.columns],
        filters=[FilterSchema(field=f.field, operator=f.operator, value=f.value) for f in config.filters],
        sort_by=config.sort_by,
        sort_order=config.sort_order,
        group_by=config.group_by,
        chart_type=config.chart_type,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    principal=Depends(get_current_principal),
):
    """删除报表配置。"""
    engine = get_report_engine()
    if not engine.delete_config(report_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报表不存在")
    return {"status": "ok"}


@router.get("/{report_id}/generate")
def generate_report(
    report_id: str,
    data_source: str = "default",
    principal=Depends(get_current_principal),
):
    """生成报表。"""
    engine = get_report_engine()
    result = engine.generate_report(report_id, data_source)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报表不存在或数据源无效")
    return {
        "config": {
            "name": result.config.name,
            "description": result.config.description,
        },
        "summary": result.summary,
        "data": result.data[:1000],  # 限制返回行数
    }


@router.get("/{report_id}/export/csv")
def export_csv(
    report_id: str,
    data_source: str = "default",
    principal=Depends(get_current_principal),
):
    """导出报表为 CSV。"""
    engine = get_report_engine()
    result = engine.generate_report(report_id, data_source)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报表不存在")

    csv_content = engine.export_csv(result)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": _content_disposition(result.config.name, "csv")},
    )


@router.get("/{report_id}/export/json")
def export_json(
    report_id: str,
    data_source: str = "default",
    principal=Depends(get_current_principal),
):
    """导出报表为 JSON。"""
    engine = get_report_engine()
    result = engine.generate_report(report_id, data_source)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报表不存在")

    json_content = engine.export_json(result)
    return StreamingResponse(
        iter([json_content]),
        media_type="application/json",
        headers={"Content-Disposition": _content_disposition(result.config.name, "json")},
    )
