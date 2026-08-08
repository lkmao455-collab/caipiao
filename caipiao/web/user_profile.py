"""用户画像系统：用户标签、行为特征、个性化推荐。"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


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

    def get_or_create_profile(self, user_id: str) -> UserProfile:
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)
        return self._profiles[user_id]

    def add_tag(self, user_id: str, tag: UserTag):
        profile = self.get_or_create_profile(user_id)
        profile.tags[tag.name] = tag
        profile.updated_at = time.time()

    def remove_tag(self, user_id: str, tag_name: str) -> bool:
        profile = self._profiles.get(user_id)
        if profile and tag_name in profile.tags:
            del profile.tags[tag_name]
            profile.updated_at = time.time()
            return True
        return False

    def get_tags(self, user_id: str) -> dict[str, UserTag]:
        profile = self._profiles.get(user_id)
        return profile.tags if profile else {}

    def update_preferences(self, user_id: str, preferences: dict[str, Any]):
        profile = self.get_or_create_profile(user_id)
        profile.preferences.update(preferences)
        profile.updated_at = time.time()

    def update_behavior_features(self, user_id: str, features: dict[str, float]):
        profile = self.get_or_create_profile(user_id)
        profile.behavior_features.update(features)
        profile.updated_at = time.time()
        self._calculate_engagement(user_id)

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
        self._segments[segment.id] = segment
        return segment

    def get_segment(self, segment_id: str) -> Segment | None:
        return self._segments.get(segment_id)

    def list_segments(self) -> list[Segment]:
        return list(self._segments.values())

    def match_segment(self, user_id: str, segment_id: str) -> bool:
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
        return [uid for uid in self._profiles if self.match_segment(uid, segment_id)]

    # 批量查询
    def get_profiles(self, user_ids: list[str]) -> list[UserProfile]:
        return [self._profiles[uid] for uid in user_ids if uid in self._profiles]

    def get_users_by_tag(self, tag_name: str, tag_value: str | None = None) -> list[str]:
        result = []
        for uid, profile in self._profiles.items():
            tag = profile.tags.get(tag_name)
            if tag and (tag_value is None or tag.value == tag_value):
                result.append(uid)
        return result

    def get_profile_summary(self, user_id: str) -> dict:
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
