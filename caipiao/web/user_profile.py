"""用户画像系统：用户标签、行为特征、个性化推荐。"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger
from . import db as _webdb

logger = get_logger(__name__)


def _profile_to_dict(p: UserProfile) -> dict[str, Any]:
    return {
        "user_id": p.user_id,
        "tags": [
            {
                "name": t.name,
                "value": t.value,
                "confidence": t.confidence,
                "source": t.source,
                "created_at": t.created_at,
                "expires_at": t.expires_at,
            }
            for t in p.tags.values()
        ],
        "preferences": p.preferences,
        "behavior_features": p.behavior_features,
        "engagement_score": p.engagement_score,
        "churn_risk": p.churn_risk,
        "lifetime_value": p.lifetime_value,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _dict_to_profile(d: dict[str, Any]) -> UserProfile:
    return UserProfile(
        user_id=d["user_id"],
        tags={
            t["name"]: UserTag(
                name=t["name"],
                value=t["value"],
                confidence=t.get("confidence", 1.0),
                source=t.get("source", "manual"),
                created_at=t.get("created_at", time.time()),
                expires_at=t.get("expires_at"),
            )
            for t in d.get("tags", [])
        },
        preferences=d.get("preferences", {}),
        behavior_features=d.get("behavior_features", {}),
        engagement_score=d.get("engagement_score", 0),
        churn_risk=d.get("churn_risk", 0),
        lifetime_value=d.get("lifetime_value", 0),
        created_at=d.get("created_at", time.time()),
        updated_at=d.get("updated_at", time.time()),
    )


def _segment_to_dict(s: Segment) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "rules": s.rules,
        "user_count": s.user_count,
        "created_at": s.created_at,
    }


def _dict_to_segment(d: dict[str, Any]) -> Segment:
    return Segment(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        rules=d.get("rules", {}),
        user_count=d.get("user_count", 0),
        created_at=d.get("created_at", time.time()),
    )


@dataclass
class UserTag:
    name: str
    value: str
    confidence: float = 1.0
    source: str = "manual"  # manual, inferred, ml
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None


@dataclass
class UserProfile:
    user_id: str
    tags: dict[str, UserTag] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    behavior_features: dict[str, float] = field(default_factory=dict)
    engagement_score: float = 0
    churn_risk: float = 0
    lifetime_value: float = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Segment:
    id: str
    name: str
    description: str = ""
    rules: dict[str, Any] = field(default_factory=dict)
    user_count: int = 0
    created_at: float = field(default_factory=time.time)


class UserProfileSystem:
    """用户画像系统：标签管理、特征提取、分群分析。"""

    def __init__(self):
        self._profiles: dict[str, UserProfile] = {}
        self._segments: dict[str, Segment] = {}
        self._tag_definitions: dict[str, dict] = {}
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._profiles = {}
        self._segments = {}
        from .models import ProfileSegmentRow, UserProfileRow

        with _webdb._SessionLocal() as session:
            for row in session.query(UserProfileRow).all():
                try:
                    self._profiles[row.id] = _dict_to_profile(json.loads(row.data_json))
                except Exception as exc:
                    logger.error("加载用户画像 %s 失败: %s", row.id, exc)
            for row in session.query(ProfileSegmentRow).all():
                try:
                    self._segments[row.id] = _dict_to_segment(json.loads(row.data_json))
                except Exception as exc:
                    logger.error("加载分群 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def _persist_profile(self, user_id: str) -> None:
        from .models import UserProfileRow

        profile = self._profiles.get(user_id)
        with _webdb._SessionLocal() as session:
            row = session.get(UserProfileRow, user_id)
            if profile is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_profile_to_dict(profile), ensure_ascii=False)
            if row is None:
                session.add(
                    UserProfileRow(
                        id=user_id, data_json=data, updated_at=profile.updated_at
                    )
                )
            else:
                row.data_json = data
                row.updated_at = profile.updated_at
            session.commit()

    def _persist_segment(self, seg_id: str) -> None:
        from .models import ProfileSegmentRow

        seg = self._segments.get(seg_id)
        with _webdb._SessionLocal() as session:
            row = session.get(ProfileSegmentRow, seg_id)
            if seg is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            data = json.dumps(_segment_to_dict(seg), ensure_ascii=False)
            if row is None:
                session.add(
                    ProfileSegmentRow(
                        id=seg_id, data_json=data, updated_at=seg.created_at
                    )
                )
            else:
                row.data_json = data
            session.commit()

    def get_or_create_profile(self, user_id: str) -> UserProfile:
        self._ensure_loaded()
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)
            self._persist_profile(user_id)
        return self._profiles[user_id]

    def add_tag(self, user_id: str, tag: UserTag):
        profile = self.get_or_create_profile(user_id)
        profile.tags[tag.name] = tag
        profile.updated_at = time.time()
        self._persist_profile(user_id)

    def remove_tag(self, user_id: str, tag_name: str) -> bool:
        self._ensure_loaded()
        profile = self._profiles.get(user_id)
        if profile and tag_name in profile.tags:
            del profile.tags[tag_name]
            profile.updated_at = time.time()
            self._persist_profile(user_id)
            return True
        return False

    def get_tags(self, user_id: str) -> dict[str, UserTag]:
        self._ensure_loaded()
        profile = self._profiles.get(user_id)
        return profile.tags if profile else {}

    def update_preferences(self, user_id: str, preferences: dict[str, Any]):
        profile = self.get_or_create_profile(user_id)
        profile.preferences.update(preferences)
        profile.updated_at = time.time()
        self._persist_profile(user_id)

    def update_behavior_features(self, user_id: str, features: dict[str, float]):
        profile = self.get_or_create_profile(user_id)
        profile.behavior_features.update(features)
        profile.updated_at = time.time()
        self._calculate_engagement(user_id)
        self._persist_profile(user_id)

    def _calculate_engagement(self, user_id: str):
        profile = self._profiles.get(user_id)
        if not profile:
            return
        features = profile.behavior_features
        score = 0
        if features.get("login_frequency", 0) > 5:
            score += 20
        if features.get("session_duration", 0) > 300:
            score += 20
        if features.get("actions_count", 0) > 50:
            score += 20
        if features.get("days_active", 0) > 10:
            score += 20
        if features.get("feature_usage", 0) > 0.5:
            score += 20
        profile.engagement_score = min(100, score)

    def calculate_churn_risk(self, user_id: str) -> float:
        self._ensure_loaded()
        profile = self._profiles.get(user_id)
        if not profile:
            return 0
        features = profile.behavior_features
        risk = 0
        if features.get("days_since_last_login", 0) > 7:
            risk += 30
        if features.get("login_frequency", 0) < 2:
            risk += 25
        if features.get("session_duration", 0) < 60:
            risk += 20
        if features.get("actions_count", 0) < 10:
            risk += 15
        profile.churn_risk = min(100, risk)
        return profile.churn_risk

    def calculate_lifetime_value(self, user_id: str) -> float:
        self._ensure_loaded()
        profile = self._profiles.get(user_id)
        if not profile:
            return 0
        features = profile.behavior_features
        value = 0
        value += features.get("total_revenue", 0)
        value += features.get("days_active", 0) * 0.5
        value += features.get("actions_count", 0) * 0.1
        profile.lifetime_value = round(value, 2)
        return profile.lifetime_value

    # 分群管理
    def create_segment(self, segment: Segment) -> Segment:
        self._ensure_loaded()
        self._segments[segment.id] = segment
        self._persist_segment(segment.id)
        return segment

    def get_segment(self, segment_id: str) -> Segment | None:
        self._ensure_loaded()
        return self._segments.get(segment_id)

    def list_segments(self) -> list[Segment]:
        self._ensure_loaded()
        return list(self._segments.values())

    def match_segment(self, user_id: str, segment_id: str) -> bool:
        self._ensure_loaded()
        segment = self._segments.get(segment_id)
        profile = self._profiles.get(user_id)
        if not segment or not profile:
            return False
        for tag_name, tag_value in segment.rules.items():
            user_tag = profile.tags.get(tag_name)
            if not user_tag or user_tag.value != tag_value:
                return False
        return True

    def get_segment_users(self, segment_id: str) -> list[str]:
        self._ensure_loaded()
        return [uid for uid in self._profiles if self.match_segment(uid, segment_id)]

    # 批量查询
    def get_profiles(self, user_ids: list[str]) -> list[UserProfile]:
        self._ensure_loaded()
        return [self._profiles[uid] for uid in user_ids if uid in self._profiles]

    def get_users_by_tag(self, tag_name: str, tag_value: str | None = None) -> list[str]:
        self._ensure_loaded()
        result = []
        for uid, profile in self._profiles.items():
            tag = profile.tags.get(tag_name)
            if tag and (tag_value is None or tag.value == tag_value):
                result.append(uid)
        return result

    def get_profile_summary(self, user_id: str) -> dict:
        self._ensure_loaded()
        profile = self._profiles.get(user_id)
        if not profile:
            return {}
        return {
            "user_id": user_id,
            "tags": {name: tag.value for name, tag in profile.tags.items()},
            "engagement_score": profile.engagement_score,
            "churn_risk": profile.churn_risk,
            "lifetime_value": profile.lifetime_value,
            "preferences": profile.preferences,
        }

    def get_analytics(self) -> dict:
        self._ensure_loaded()
        total = len(self._profiles)
        if total == 0:
            return {"total_users": 0}

        engagement_scores = [p.engagement_score for p in self._profiles.values()]
        churn_risks = [p.churn_risk for p in self._profiles.values()]
        ltv_values = [p.lifetime_value for p in self._profiles.values()]

        return {
            "total_users": total,
            "avg_engagement": round(sum(engagement_scores) / total, 2),
            "avg_churn_risk": round(sum(churn_risks) / total, 2),
            "avg_ltv": round(sum(ltv_values) / total, 2),
            "high_engagement": sum(1 for s in engagement_scores if s >= 70),
            "high_churn_risk": sum(1 for r in churn_risks if r >= 50),
            "segments": len(self._segments),
        }


# 全局用户画像系统
_system: UserProfileSystem | None = None


def get_user_profile_system() -> UserProfileSystem:
    global _system
    if _system is None:
        _system = UserProfileSystem()
    return _system
