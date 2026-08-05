"""Pydantic 请求/响应模型。"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- 认证 ---
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    created_at: datetime.datetime


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
    config_schema: Optional[dict[str, Any]] = None


# --- 生成 ---
class GenerateRequest(BaseModel):
    profile_key: str
    strategy_id: str
    count: int = Field(default=1, ge=1, le=100)
    options: dict[str, Any] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    profile_key: str
    strategy_id: str
    count: int
    tickets: list[dict[str, Any]]


# --- 回测（简化版）---
class BacktestRequest(BaseModel):
    profile_key: str
    strategy_id: str
    count: int = Field(default=1, ge=1, le=100)
    options: dict[str, Any] = Field(default_factory=dict)


class BacktestResultItem(BaseModel):
    ticket: dict[str, Any]
    matches: dict[str, int]


class BacktestResponse(BaseModel):
    profile_key: str
    strategy_id: str
    latest_draw: dict[str, Any]
    results: list[BacktestResultItem]
    note: str


# --- API Key ---
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime.datetime
    last_used_at: Optional[datetime.datetime] = None
    key: Optional[str] = None  # 仅创建时返回一次
