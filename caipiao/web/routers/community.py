"""社区互动路由：分享、评论、排行榜。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..deps import get_current_principal
from ..ratelimit import limiter

router = APIRouter(prefix="/community", tags=["community"])


class PredictionShare(BaseModel):
    profile_key: str
    strategy_id: str
    numbers: list[list[int]]
    description: str = Field(default="", max_length=500)
    tags: list[str] = []


class PredictionOut(BaseModel):
    id: str
    user_id: str
    username: str
    profile_key: str
    strategy_id: str
    numbers: list[list[int]]
    description: str
    tags: list[str]
    likes: int
    comments_count: int
    created_at: str
    liked_by_me: bool = False


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class CommentOut(BaseModel):
    id: str
    user_id: str
    username: str
    content: str
    created_at: str
    likes: int


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    score: int
    predictions_count: int
    likes_received: int


class _CommunityStore:
    """简单的社区数据存储。"""

    def __init__(self):
        self._predictions: dict[str, dict[str, Any]] = {}
        self._comments: dict[str, list[dict[str, Any]]] = {}
        self._likes: dict[str, set[str]] = {}  # prediction_id -> set of user_ids

    def add_prediction(
        self,
        user_id: str,
        username: str,
        profile_key: str,
        strategy_id: str,
        numbers: list[list[int]],
        description: str,
        tags: list[str],
    ) -> dict[str, Any]:
        pred_id = str(uuid.uuid4())[:8]
        pred = {
            "id": pred_id,
            "user_id": user_id,
            "username": username,
            "profile_key": profile_key,
            "strategy_id": strategy_id,
            "numbers": numbers,
            "description": description,
            "tags": tags,
            "likes": 0,
            "created_at": datetime.now().isoformat(),
        }
        self._predictions[pred_id] = pred
        self._comments[pred_id] = []
        self._likes[pred_id] = set()
        return pred

    def list_predictions(
        self,
        profile_key: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        preds = list(self._predictions.values())
        if profile_key:
            preds = [p for p in preds if p["profile_key"] == profile_key]
        preds.sort(key=lambda p: p["created_at"], reverse=True)
        return preds[:limit]

    def get_prediction(self, pred_id: str) -> dict[str, Any] | None:
        return self._predictions.get(pred_id)

    def like_prediction(self, pred_id: str, user_id: str) -> bool:
        pred = self._predictions.get(pred_id)
        if not pred:
            return False
        if user_id not in self._likes[pred_id]:
            self._likes[pred_id].add(user_id)
            pred["likes"] += 1
            return True
        return False

    def unlike_prediction(self, pred_id: str, user_id: str) -> bool:
        pred = self._predictions.get(pred_id)
        if not pred:
            return False
        if user_id in self._likes[pred_id]:
            self._likes[pred_id].discard(user_id)
            pred["likes"] -= 1
            return True
        return False

    def add_comment(
        self,
        pred_id: str,
        user_id: str,
        username: str,
        content: str,
    ) -> dict[str, Any] | None:
        if pred_id not in self._predictions:
            return None
        comment = {
            "id": str(uuid.uuid4())[:8],
            "user_id": user_id,
            "username": username,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "likes": 0,
        }
        self._comments[pred_id].append(comment)
        return comment

    def get_comments(self, pred_id: str) -> list[dict[str, Any]]:
        return self._comments.get(pred_id, [])

    def get_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取排行榜。"""
        user_stats: dict[str, dict[str, Any]] = {}
        for pred in self._predictions.values():
            uid = pred["user_id"]
            if uid not in user_stats:
                user_stats[uid] = {
                    "user_id": uid,
                    "username": pred["username"],
                    "score": 0,
                    "predictions_count": 0,
                    "likes_received": 0,
                }
            user_stats[uid]["predictions_count"] += 1
            user_stats[uid]["likes_received"] += pred["likes"]
            user_stats[uid]["score"] += pred["likes"] * 10 + 5  # 每个预测5分，每个赞10分

        leaderboard = sorted(user_stats.values(), key=lambda u: u["score"], reverse=True)
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        return leaderboard[:limit]


_store = _CommunityStore()


@router.get("/predictions", response_model=list[PredictionOut])
@limiter.limit("60/minute")
def list_predictions(
    request: Request,
    profile_key: str | None = None,
    limit: int = 20,
    principal=Depends(get_current_principal),
) -> list[PredictionOut]:
    """获取分享的预测列表。"""
    preds = _store.list_predictions(profile_key, limit)
    return [
        PredictionOut(
            id=p["id"],
            user_id=p["user_id"],
            username=p["username"],
            profile_key=p["profile_key"],
            strategy_id=p["strategy_id"],
            numbers=p["numbers"],
            description=p["description"],
            tags=p["tags"],
            likes=p["likes"],
            comments_count=len(_store.get_comments(p["id"])),
            created_at=p["created_at"],
            liked_by_me=principal.id in _store._likes.get(p["id"], set()),
        )
        for p in preds
    ]


@router.post("/predictions", response_model=PredictionOut)
@limiter.limit("10/minute")
def share_prediction(
    request: Request,
    req: PredictionShare,
    principal=Depends(get_current_principal),
) -> PredictionOut:
    """分享预测。"""
    pred = _store.add_prediction(
        user_id=principal.id,
        username=principal.username,
        profile_key=req.profile_key,
        strategy_id=req.strategy_id,
        numbers=req.numbers,
        description=req.description,
        tags=req.tags,
    )
    return PredictionOut(
        id=pred["id"],
        user_id=pred["user_id"],
        username=pred["username"],
        profile_key=pred["profile_key"],
        strategy_id=pred["strategy_id"],
        numbers=pred["numbers"],
        description=pred["description"],
        tags=pred["tags"],
        likes=0,
        comments_count=0,
        created_at=pred["created_at"],
    )


@router.post("/predictions/{pred_id}/like")
def like_prediction(
    pred_id: str,
    principal=Depends(get_current_principal),
) -> dict:
    """点赞预测。"""
    if not _store.like_prediction(pred_id, principal.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预测不存在或已点赞")
    return {"liked": True}


@router.delete("/predictions/{pred_id}/like")
def unlike_prediction(
    pred_id: str,
    principal=Depends(get_current_principal),
) -> dict:
    """取消点赞。"""
    if not _store.unlike_prediction(pred_id, principal.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预测不存在或未点赞")
    return {"unliked": True}


@router.get("/predictions/{pred_id}/comments", response_model=list[CommentOut])
def get_comments(
    pred_id: str,
) -> list[CommentOut]:
    """获取评论列表。"""
    comments = _store.get_comments(pred_id)
    return [
        CommentOut(
            id=c["id"],
            user_id=c["user_id"],
            username=c["username"],
            content=c["content"],
            created_at=c["created_at"],
            likes=c["likes"],
        )
        for c in comments
    ]


@router.post("/predictions/{pred_id}/comments", response_model=CommentOut)
@limiter.limit("30/minute")
def add_comment(
    request: Request,
    pred_id: str,
    req: CommentCreate,
    principal=Depends(get_current_principal),
) -> CommentOut:
    """添加评论。"""
    comment = _store.add_comment(
        pred_id=pred_id,
        user_id=principal.id,
        username=principal.username,
        content=req.content,
    )
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预测不存在")
    return CommentOut(
        id=comment["id"],
        user_id=comment["user_id"],
        username=comment["username"],
        content=comment["content"],
        created_at=comment["created_at"],
        likes=comment["likes"],
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
@limiter.limit("30/minute")
def get_leaderboard(
    request: Request,
    limit: int = 10,
) -> list[LeaderboardEntry]:
    """获取排行榜。"""
    entries = _store.get_leaderboard(limit)
    return [
        LeaderboardEntry(
            rank=e["rank"],
            user_id=e["user_id"],
            username=e["username"],
            score=e["score"],
            predictions_count=e["predictions_count"],
            likes_received=e["likes_received"],
        )
        for e in entries
    ]
