"""Pydantic 请求/响应模型。"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- 认证 ---
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str = "user"
    created_at: datetime.datetime


# --- 管理后台（P5.E） ---
class RoleUpdate(BaseModel):
    """管理员修改用户角色。"""

    role: str = Field(pattern="^(admin|user)$", description="admin 或 user")


class UserAdminOut(BaseModel):
    """管理员视角的用户摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    created_at: datetime.datetime


class AdminStats(BaseModel):
    """管理后台概览统计。"""

    user_count: int
    admin_count: int
    api_key_count: int
    total_usage: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- 彩种 / 策略 ---
class ProfileOut(BaseModel):
    key: str
    name: str
    category: str
    subtitle: str = ""
    group_keys: list[str]


class StrategyOut(BaseModel):
    id: str
    name: str
    description: str
    configurable: bool = False
    config_schema: dict[str, Any] | None = None


# --- 数据拉取（/fetch） ---
class FetchRequest(BaseModel):
    """触发从数据源抓取最新开奖并写入本地仓库。

    mode="latest" 仅抓取最新一期；mode="all" 抓取全量历史（可能较多，谨慎使用）。
    """

    mode: str = Field(default="latest", pattern="^(latest|all)$")


class FetchResult(BaseModel):
    """数据拉取结果摘要。"""

    profile_key: str
    mode: str
    fetched: int
    added: int
    total: int
    latest: dict[str, Any] | None = None


# --- 生成 ---
class PostFilter(BaseModel):
    """后过滤规则：name 应为对应彩种 key，params 为过滤函数参数。"""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    profile_key: str
    strategy_id: str
    count: int = Field(default=1, ge=1, le=100)
    options: dict[str, Any] = Field(default_factory=dict)
    post_filters: list[PostFilter] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    profile_key: str
    strategy_id: str
    count: int
    filtered_count: int = 0
    tickets: list[dict[str, Any]]


# --- 回测（走查式 + 持久化）---
class BacktestRequest(BaseModel):
    profile_key: str
    strategy_id: str
    count: int = Field(default=1, ge=1, le=100)
    rounds: int = Field(default=30, ge=1, le=300)
    history_window: int = Field(default=100, ge=1, le=500)
    start_date: str | None = None  # YYYY-MM-DD，限定回测起点
    end_date: str | None = None  # YYYY-MM-DD，限定回测终点
    options: dict[str, Any] = Field(default_factory=dict)
    post_filters: list[PostFilter] = Field(default_factory=list)


class BacktestRoundItem(BaseModel):
    target_date: str
    issue: str
    matches: dict[str, int]
    hit: bool
    best_tier: str | None = None  # 该期最佳奖级（浮动奖记原名，未中奖为 None）
    round_fixed_prize: int = 0  # 该期固定奖金合计
    round_float_count: int = 0  # 该期命中浮动奖的注数


class BacktestRoundSummary(BaseModel):
    total_rounds: int
    hit_count: int
    first_ticket_hit_count: int
    profit: int
    total_cost: int
    total_fixed_prize: int
    float_prize_count: int = 0  # 命中浮动奖的总注数（一等奖等高奖等金额浮动，未计入 profit）
    tier_breakdown: dict[str, int] = Field(default_factory=dict)  # 各奖级命中注数分布


class BacktestRunResponse(BaseModel):
    profile_key: str
    strategy_id: str
    batch_id: int
    rounds: list[BacktestRoundItem]
    summary: BacktestRoundSummary


class BacktestRecordOut(BaseModel):
    id: int
    created_at: str | None = None
    profile_key: str
    strategy_id: str
    target_date: str = ""
    start_date: str = ""
    end_date: str = ""
    total_rounds: int = 0
    tickets_count: int = 0
    total_cost: int = 0
    total_fixed_prize: int = 0
    float_prize_count: int = 0
    hit_count: int = 0
    profit: int = 0
    kind: str  # "single" | "batch"


class BacktestTicketOut(BaseModel):
    """单期回测中某一注的明细（用于历史记录钻取）。"""

    ticket_index: int
    groups: dict[str, list[int]]
    hits: dict[str, int]
    prize_name: str
    prize_amount: int | None = None
    is_first: bool = False


# --- 批量回测对比 ---
class StrategyCompareRequest(BaseModel):
    """批量回测对比请求：对多个策略运行相同回测参数并比较结果。"""

    profile_key: str
    strategy_ids: list[str] = Field(min_length=1, max_length=10)
    count: int = Field(default=1, ge=1, le=100)
    rounds: int = Field(default=30, ge=1, le=300)
    history_window: int = Field(default=100, ge=1, le=500)
    start_date: str | None = None
    end_date: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class StrategyCompareResult(BaseModel):
    """单个策略的回测对比结果。"""

    strategy_id: str
    strategy_name: str
    total_rounds: int
    hit_count: int
    hit_rate: float  # 命中率 0-1
    first_ticket_hit_count: int
    profit: int
    total_cost: int
    total_fixed_prize: int
    float_prize_count: int
    tier_breakdown: dict[str, int] = Field(default_factory=dict)
    # 风险调整指标
    profit_per_round: float = 0.0  # 平均每期利润
    roi: float = 0.0  # 投资回报率 = profit / total_cost
    max_drawdown: float = 0.0  # 最大回撤（累计利润最低点）


class StrategyCompareResponse(BaseModel):
    """批量回测对比响应。"""

    profile_key: str
    rounds_run: int
    strategies: list[StrategyCompareResult]
    ranking: list[str]  # 按 hit_rate 降序排列的 strategy_id 列表


class ParameterSuggestion(BaseModel):
    """参数优化建议。"""

    strategy_id: str
    strategy_name: str
    current_params: dict[str, Any] = Field(default_factory=dict)
    suggested_params: dict[str, Any] = Field(default_factory=dict)
    reason: str
    expected_improvement: float = 0.0  # 预期提升幅度（百分比）


class ParameterSuggestionResponse(BaseModel):
    """参数优化建议响应。"""

    profile_key: str
    strategy_id: str
    suggestions: list[ParameterSuggestion]
    based_on_rounds: int


# --- API Key ---
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime.datetime
    last_used_at: datetime.datetime | None = None
    key: str | None = None  # 仅创建时返回一次


# --- 缓存管理 ---
class CacheStats(BaseModel):
    """缓存统计信息。"""
    memory_cache_count: int
    engine_cache_count: int
    redis_available: bool
