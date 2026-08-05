"""用户路由：当前用户信息、按用户命名空间隔离的参数组。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.parameter_group import (
    parameter_group_from_dict,
    parameter_group_to_dict,
)
from ...persistence.parameter_group_store import ParameterGroupStore
from ..config import user_data_dir
from ..deps import get_current_user
from ..schemas import UserOut

router = APIRouter(tags=["user"])


@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)) -> UserOut:
    return user


@router.get("/me/param-groups/{profile_key}")
def list_param_groups(profile_key: str, user=Depends(get_current_user)) -> list[dict]:
    store = ParameterGroupStore(user_data_dir(user.id))
    return [parameter_group_to_dict(g) for g in store.load_all(profile_key)]


@router.post("/me/param-groups/{profile_key}", status_code=status.HTTP_201_CREATED)
def save_param_group(profile_key: str, payload: dict, user=Depends(get_current_user)) -> dict:
    try:
        group = parameter_group_from_dict(payload)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"参数组格式无效：{exc}") from exc
    group.profile_key = profile_key
    if not group.id:
        group.id = str(uuid.uuid4())
    store = ParameterGroupStore(user_data_dir(user.id))
    store.save(group)
    return parameter_group_to_dict(group)
