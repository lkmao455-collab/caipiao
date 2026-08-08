"""开发者门户：API 文档和开发者管理。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


@dataclass
class APIEndpoint:
    path: str
    method: str
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[dict] = field(default_factory=list)
    request_body: dict | None = None
    responses: dict[str, dict] = field(default_factory=dict)
    authentication: bool = True


@dataclass
class DeveloperDoc:
    id: str
    title: str
    content: str
    category: str = ""
    order: int = 0


class DeveloperPortal:
    """开发者门户：API 文档和管理。"""

    def __init__(self):
        self._endpoints: list[APIEndpoint] = []
        self._docs: list[DeveloperDoc] = []
        self._register_default_docs()

    def _register_default_docs(self):
        docs = [
            DeveloperDoc(
                id="quickstart",
                title="快速开始",
                content="""# 快速开始

## 1. 注册账户
```bash
curl -X POST /auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"username": "your_name", "password": "your_password"}'
```

## 2. 获取 Token
```bash
curl -X POST /auth/login \\
  -d "username=your_name&password=your_password"
```

## 3. 调用 API
```bash
curl -X GET /profiles \\
  -H "Authorization: Bearer YOUR_TOKEN"
```
""",
                category="入门",
                order=1,
            ),
            DeveloperDoc(
                id="authentication",
                title="认证方式",
                content="""# 认证方式

支持两种认证方式：

## JWT Token
在请求头中添加：
```
Authorization: Bearer YOUR_TOKEN
```

## API Key
在请求头中添加：
```
X-API-Key: YOUR_API_KEY
```
""",
                category="认证",
                order=2,
            ),
            DeveloperDoc(
                id="rate-limiting",
                title="限流规则",
                content="""# 限流规则

API 调用有限流保护：

| 级别 | 限制 |
|------|------|
| 每分钟 | 60 次 |
| 每小时 | 1000 次 |
| 每天 | 10000 次 |

超过限制返回 429 状态码。
""",
                category="限流",
                order=3,
            ),
            DeveloperDoc(
                id="error-codes",
                title="错误码",
                content="""# 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 429 | 超过限流 |
| 500 | 服务器错误 |
""",
                category="错误处理",
                order=4,
            ),
        ]
        self._docs = docs

    def register_endpoint(self, endpoint: APIEndpoint):
        self._endpoints.append(endpoint)

    def get_endpoints(self, tag: str | None = None) -> list[APIEndpoint]:
        endpoints = self._endpoints
        if tag:
            endpoints = [e for e in endpoints if tag in e.tags]
        return endpoints

    def get_docs(self, category: str | None = None) -> list[DeveloperDoc]:
        docs = sorted(self._docs, key=lambda d: d.order)
        if category:
            docs = [d for d in docs if d.category == category]
        return docs

    def get_doc(self, doc_id: str) -> DeveloperDoc | None:
        return next((d for d in self._docs if d.id == doc_id), None)

    def generate_openapi_spec(self) -> dict:
        """生成 OpenAPI 规范。"""
        paths = {}
        for ep in self._endpoints:
            if ep.path not in paths:
                paths[ep.path] = {}
            paths[ep.path][ep.method.lower()] = {
                "summary": ep.summary,
                "description": ep.description,
                "tags": ep.tags,
                "parameters": ep.parameters,
                "responses": ep.responses,
                "security": [{"bearerAuth": []}] if ep.authentication else [],
            }

        return {
            "openapi": "3.0.0",
            "info": {
                "title": "彩票号码生成器 API",
                "version": "1.0.0",
                "description": "智能彩票号码生成、分析和回测 API",
            },
            "servers": [{"url": "/api/v1"}],
            "paths": paths,
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    }
                }
            },
        }


# 全局开发者门户
_portal: DeveloperPortal | None = None


def get_developer_portal() -> DeveloperPortal:
    global _portal
    if _portal is None:
        _portal = DeveloperPortal()
    return _portal
