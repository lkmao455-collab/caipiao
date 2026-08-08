"""可视化平台路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import get_current_principal
from ..visualization import ChartConfig, Dashboard, get_visualization_platform

router = APIRouter(prefix="/viz", tags=["visualization"])


class ChartCreate(BaseModel):
    name: str
    chart_type: str
    data_source: str = ""
    query: str = ""
    options: dict = {}
    position: dict = {"x": 0, "y": 0, "w": 6, "h": 4}
    refresh_interval: int = 0


class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    layout: str = "grid"
    theme: str = "light"
    is_public: bool = False


@router.post("/dashboards")
def create_dashboard(
    req: DashboardCreate,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    dashboard = Dashboard(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        description=req.description,
        layout=req.layout,
        theme=req.theme,
        is_public=req.is_public,
        owner_id=principal.id,
    )
    platform.create_dashboard(dashboard)
    return {"id": dashboard.id, "name": dashboard.name}


@router.get("/dashboards")
def list_dashboards(
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    dashboards = platform.list_dashboards(principal.id)
    return [
        {"id": d.id, "name": d.name, "description": d.description, "charts": len(d.charts)}
        for d in dashboards
    ]


@router.get("/dashboards/{dashboard_id}")
def get_dashboard(
    dashboard_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    d = platform.get_dashboard(dashboard_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "仪表盘不存在")
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "layout": d.layout,
        "theme": d.theme,
        "charts": [
            {"id": c.id, "name": c.name, "chart_type": c.chart_type, "options": c.options, "position": c.position}
            for c in d.charts
        ],
    }


@router.delete("/dashboards/{dashboard_id}")
def delete_dashboard(
    dashboard_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    if not platform.delete_dashboard(dashboard_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "仪表盘不存在")
    return {"status": "ok"}


@router.post("/dashboards/{dashboard_id}/charts")
def add_chart(
    dashboard_id: str,
    req: ChartCreate,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    chart = ChartConfig(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        chart_type=req.chart_type,
        data_source=req.data_source,
        query=req.query,
        options=req.options,
        position=req.position,
        refresh_interval=req.refresh_interval,
    )
    if not platform.add_chart(dashboard_id, chart):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "仪表盘不存在")
    return {"id": chart.id, "name": chart.name}


@router.delete("/dashboards/{dashboard_id}/charts/{chart_id}")
def remove_chart(
    dashboard_id: str,
    chart_id: str,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    if not platform.remove_chart(dashboard_id, chart_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图表不存在")
    return {"status": "ok"}


@router.get("/templates")
def list_templates(
    category: str | None = None,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    templates = platform.get_templates(category)
    return [
        {"id": t.id, "name": t.name, "description": t.description, "chart_type": t.chart_type, "category": t.category}
        for t in templates
    ]


@router.post("/templates/{template_id}/create-chart")
def create_chart_from_template(
    template_id: str,
    name: str,
    principal=Depends(get_current_principal),
):
    platform = get_visualization_platform()
    chart = platform.create_chart_from_template(template_id, name)
    if not chart:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "模板不存在")
    return {"id": chart.id, "name": chart.name, "chart_type": chart.chart_type}
