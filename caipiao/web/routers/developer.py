"""开发者门户路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_current_principal
from ..developer_portal import get_developer_portal

router = APIRouter(prefix="/developer", tags=["developer"])


@router.get("/docs")
def list_docs(
    category: str | None = None,
    principal=Depends(get_current_principal),
):
    portal = get_developer_portal()
    docs = portal.get_docs(category)
    return [
        {"id": d.id, "title": d.title, "category": d.category, "order": d.order}
        for d in docs
    ]


@router.get("/docs/{doc_id}")
def get_doc(
    doc_id: str,
    principal=Depends(get_current_principal),
):
    portal = get_developer_portal()
    doc = portal.get_doc(doc_id)
    if not doc:
        return {"error": "文档不存在"}
    return {"id": doc.id, "title": doc.title, "content": doc.content, "category": doc.category}


@router.get("/endpoints")
def list_endpoints(
    tag: str | None = None,
    principal=Depends(get_current_principal),
):
    portal = get_developer_portal()
    endpoints = portal.get_endpoints(tag)
    return [
        {
            "path": e.path,
            "method": e.method,
            "summary": e.summary,
            "tags": e.tags,
            "authentication": e.authentication,
        }
        for e in endpoints
    ]


@router.get("/openapi.json")
def get_openapi_spec(
    principal=Depends(get_current_principal),
):
    portal = get_developer_portal()
    return portal.generate_openapi_spec()
