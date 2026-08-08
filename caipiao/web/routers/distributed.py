"""分布式组件路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..distributed import (
    get_distributed_lock,
    get_id_generator,
    get_distributed_transaction,
)

router = APIRouter(prefix="/distributed", tags=["distributed"])


class LockAcquire(BaseModel):
    resource: str
    owner: str
    ttl: float = 30


class IDParse(BaseModel):
    id: int


@router.post("/lock/acquire")
async def acquire_lock(
    req: LockAcquire,
    principal=Depends(get_current_principal),
):
    lock = get_distributed_lock()
    lock_id = await lock.acquire(req.resource, req.owner, req.ttl)
    if not lock_id:
        return {"error": "Could not acquire lock"}
    return {"lock_id": lock_id, "resource": req.resource}


@router.post("/lock/release")
async def release_lock(
    resource: str,
    lock_id: str,
    principal=Depends(get_current_principal),
):
    lock = get_distributed_lock()
    if await lock.release(resource, lock_id):
        return {"status": "ok"}
    return {"error": "Lock not found"}


@router.get("/lock/check")
def check_lock(
    resource: str,
    principal=Depends(get_current_principal),
):
    lock = get_distributed_lock()
    info = lock.get_lock_info(resource)
    if info:
        return {"locked": True, "owner": info.owner, "acquired_at": info.acquired_at}
    return {"locked": False}


@router.get("/id/next")
def next_id(
    principal=Depends(get_current_principal),
):
    gen = get_id_generator()
    return {"id": gen.next_id(), "id_str": gen.next_id_str()}


@router.post("/id/parse")
def parse_id(
    req: IDParse,
    principal=Depends(get_current_principal),
):
    gen = get_id_generator()
    return gen.parse_id(req.id)
