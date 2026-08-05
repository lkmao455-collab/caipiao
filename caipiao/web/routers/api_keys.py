"""API Key 路由：开放平台密钥的签发 / 列表 / 吊销。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import ApiKey
from ..schemas import ApiKeyCreate, ApiKeyOut
from ..security import generate_api_key

router = APIRouter(prefix="/me/apikeys", tags=["api_keys"])


@router.post("", response_model=ApiKeyOut, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: ApiKeyCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
) -> ApiKeyOut:
    raw, key_hash = generate_api_key()
    key = ApiKey(owner_id=user.id, key_hash=key_hash, name=payload.name)
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        key=raw,  # 原始 key 仅此返回一次
    )


@router.get("", response_model=list[ApiKeyOut])
def list_keys(user=Depends(get_current_user), db: Session = Depends(get_db)) -> list[ApiKeyOut]:
    return db.query(ApiKey).filter_by(owner_id=user.id).all()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(key_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    key = db.query(ApiKey).filter_by(id=key_id, owner_id=user.id).first()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API Key 不存在")
    db.delete(key)
    db.commit()
