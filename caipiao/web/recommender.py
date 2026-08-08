"""智能推荐系统：基于用户历史偏好和回测结果推荐策略组合。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserPreference:
    """用户偏好数据。"""

    user_id: str
    profile_key: str
    strategy_usage: dict[str, int] = field(default_factory=dict)  # 策略使用次数
    filter_usage: dict[str, int] = field(default_factory=dict)  # 过滤器使用次数
    favorite_strategies: list[str] = field(default_factory=list)  # 收藏的策略
    backtest_results: list[dict[str, Any]] = field(default_factory=list)  # 回测结果


@dataclass
class Recommendation:
    """推荐结果。"""

    strategy_id: str
    strategy_name: str
    score: float  # 推荐分数 0-100
    reason: str  # 推荐理由
    suggested_params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class RecommendationEngine:
    """智能推荐引擎。"""

    def __init__(self):
        self._user_preferences: dict[str, UserPreference] = {}

    def record_usage(self, user_id: str, profile_key: str, strategy_id: str) -> None:
        """记录用户策略使用。"""
        key = f"{user_id}:{profile_key}"
        if key not in self._user_preferences:
            self._user_preferences[key] = UserPreference(user_id=user_id, profile_key=profile_key)
        pref = self._user_preferences[key]
        pref.strategy_usage[strategy_id] = pref.strategy_usage.get(strategy_id, 0) + 1

    def record_backtest(
        self,
        user_id: str,
        profile_key: str,
        strategy_id: str,
        hit_rate: float,
        profit: int,
    ) -> None:
        """记录回测结果。"""
        key = f"{user_id}:{profile_key}"
        if key not in self._user_preferences:
            self._user_preferences[key] = UserPreference(user_id=user_id, profile_key=profile_key)
        pref = self._user_preferences[key]
        pref.backtest_results.append({
            "strategy_id": strategy_id,
            "hit_rate": hit_rate,
            "profit": profit,
        })

    def get_recommendations(
        self,
        user_id: str,
        profile_key: str,
        available_strategies: list[dict[str, Any]],
        top_n: int = 5,
    ) -> list[Recommendation]:
        """获取推荐策略列表。"""
        key = f"{user_id}:{profile_key}"
        pref = self._user_preferences.get(key)

        recommendations: list[Recommendation] = []

        for strat in available_strategies:
            strat_id = strat["id"]
            strat_name = strat.get("name", strat_id)
            score = 50.0  # 基础分
            reasons: list[str] = []
            tags: list[str] = []

            if pref:
                # 1. 基于使用频率（常用策略加分）
                usage = pref.strategy_usage.get(strat_id, 0)
                if usage > 0:
                    score += min(usage * 5, 20)  # 最多加20分
                    reasons.append(f"您已使用 {usage} 次")
                    tags.append("常用")

                # 2. 基于回测结果（高命中率策略加分）
                bt_results = [r for r in pref.backtest_results if r["strategy_id"] == strat_id]
                if bt_results:
                    avg_hit = sum(r["hit_rate"] for r in bt_results) / len(bt_results)
                    avg_profit = sum(r["profit"] for r in bt_results) / len(bt_results)
                    if avg_hit > 0.3:
                        score += 15
                        reasons.append(f"历史命中率 {avg_hit:.1%}")
                        tags.append("高命中")
                    if avg_profit > 0:
                        score += 10
                        reasons.append(f"平均盈利 {avg_profit:.0f} 元")
                        tags.append("盈利")

                # 3. 基于收藏
                if strat_id in pref.favorite_strategies:
                    score += 10
                    reasons.append("已收藏")
                    tags.append("收藏")

            # 4. 可配置策略加分
            if strat.get("configurable"):
                score += 5
                tags.append("可配置")

            # 5. ML 策略加分
            if strat.get("is_ml", False):
                score += 3
                tags.append("智能")

            # 限制分数范围
            score = min(max(score, 0), 100)

            # 生成推荐理由
            if not reasons:
                reasons.append("综合评估推荐")

            recommendations.append(Recommendation(
                strategy_id=strat_id,
                strategy_name=strat_name,
                score=score,
                reason="；".join(reasons),
                tags=tags,
            ))

        # 按分数排序
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations[:top_n]


# 全局推荐引擎实例
recommendation_engine = RecommendationEngine()
