"""用户收藏路由：管理用户收藏的策略组合。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteCreate(BaseModel):
    profile_key: str
    strategy_id: str
    name: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class FavoriteOut(BaseModel):
    id: str
    profile_key: str
    strategy_id: str
    name: str
    params: dict[str, Any]
    created_at: str


class _FavoriteStore:
    """简单的文件存储（JSON），用于用户收藏。"""

    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}

    def list(self, user_id: str) -> list[dict[str, Any]]:
        return [v for v in self._data.values() if v.get("user_id") == user_id]

    def add(self, user_id: str, item: dict[str, Any]) -> dict[str, Any]:
        item["id"] = str(uuid.uuid4())[:8]
        item["user_id"] = user_id
        item["created_at"] = str(__import__("datetime").datetime.now())
        self._data[item["id"]] = item
        return item

    def delete(self, user_id: str, fav_id: str) -> bool:
        item = self._data.get(fav_id)
        if item and item.get("user_id") == user_id:
            del self._data[fav_id]
            return True
        return False


_store = _FavoriteStore()


@router.get("", response_model=list[FavoriteOut])
def list_favorites(
    principal=Depends(get_current_principal),
) -> list[FavoriteOut]:
    """列出当前用户的所有收藏。"""
    items = _store.list(principal.id)
    return [
        FavoriteOut(
            id=i["id"],
            profile_key=i["profile_key"],
            strategy_id=i["strategy_id"],
            name=i["name"],
            params=i.get("params", {}),
            created_at=i.get("created_at", ""),
        )
        for i in items
    ]


@router.post("", response_model=FavoriteOut)
def add_favorite(
    req: FavoriteCreate,
    principal=Depends(get_current_principal),
) -> FavoriteOut:
    """添加收藏。"""
    item = _store.add(principal.id, {
        "profile_key": req.profile_key,
        "strategy_id": req.strategy_id,
        "name": req.name,
        "params": req.params,
    })
    return FavoriteOut(
        id=item["id"],
        profile_key=item["profile_key"],
        strategy_id=item["strategy_id"],
        name=item["name"],
        params=item.get("params", {}),
        created_at=item.get("created_at", ""),
    )


@router.delete("/{fav_id}")
def delete_favorite(
    fav_id: str,
    principal=Depends(get_current_principal),
) -> dict:
    """删除收藏。"""
    if not _store.delete(principal.id, fav_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "收藏不存在")
    return {"deleted": fav_id}
