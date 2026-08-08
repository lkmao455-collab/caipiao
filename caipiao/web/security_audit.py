"""安全审计模块：操作日志、数据加密、敏感信息脱敏。

持久化：审计日志条目写入 web 数据库（合规关键，重启不丢失）。运行时仅保留
内存缓存（受 _max_logs 限制），实例会在每次调用时按需从数据库水合
（URL 感知，支持测试隔离与进程重启持久化）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from functools import wraps
import base64

from . import db as _webdb

logger = logging.getLogger("caipiao.audit")


@dataclass
class AuditLog:
    """审计日志条目。"""

    timestamp: str
    user_id: str
    action: str
    resource: str
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    success: bool = True
    error_message: str = ""


class AuditLogger:
    """审计日志记录器。"""

    def __init__(self):
        self._logs: list[AuditLog] = []
        self._max_logs = 10000
        self._loaded = False
        self._loaded_db_url: str | None = None

    def _ensure_loaded(self) -> None:
        _webdb._ensure_engine()
        url = _webdb._db_url()
        if self._loaded and self._loaded_db_url == url:
            return
        self._logs = []
        from .models import AuditLogRow

        with _webdb._SessionLocal() as session:
            rows = (
                session.query(AuditLogRow)
                .order_by(AuditLogRow.id.desc())
                .limit(self._max_logs)
                .all()
            )
            for row in reversed(rows):
                try:
                    self._logs.append(
                        AuditLog(
                            timestamp=row.timestamp,
                            user_id=row.user_id,
                            action=row.action,
                            resource=row.resource,
                            details=json.loads(row.details_json) if row.details_json else {},
                            ip_address=row.ip_address,
                            success=row.success,
                            error_message=row.error_message,
                        )
                    )
                except Exception as exc:
                    logger.error("加载审计日志 %s 失败: %s", row.id, exc)
        self._loaded = True
        self._loaded_db_url = url

    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        details: dict[str, Any] | None = None,
        ip_address: str = "",
        success: bool = True,
        error_message: str = "",
    ) -> None:
        """记录审计日志（写透到数据库）。"""
        self._ensure_loaded()
        log_entry = AuditLog(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            action=action,
            resource=resource,
            details=details or {},
            ip_address=ip_address,
            success=success,
            error_message=error_message,
        )
        self._logs.append(log_entry)

        # 限制内存日志数量
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

        # 写透到数据库
        from .models import AuditLogRow

        with _webdb._SessionLocal() as session:
            session.add(
                AuditLogRow(
                    timestamp=log_entry.timestamp,
                    user_id=log_entry.user_id,
                    action=log_entry.action,
                    resource=log_entry.resource,
                    details_json=json.dumps(log_entry.details, ensure_ascii=False),
                    ip_address=log_entry.ip_address,
                    success=log_entry.success,
                    error_message=log_entry.error_message,
                )
            )
            session.commit()

        # 同时输出到标准日志
        level = logging.INFO if success else logging.WARNING
        logger.log(
            level,
            f"[AUDIT] {user_id} {action} {resource} success={success}",
        )

    def get_logs(
        self,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """查询审计日志。"""
        self._ensure_loaded()
        filtered = self._logs
        if user_id:
            filtered = [l for l in filtered if l.user_id == user_id]
        if action:
            filtered = [l for l in filtered if l.action == action]
        return filtered[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """获取审计统计。"""
        from collections import Counter

        self._ensure_loaded()
        action_counts = Counter(l.action for l in self._logs)
        user_counts = Counter(l.user_id for l in self._logs)
        return {
            "total_logs": len(self._logs),
            "action_counts": dict(action_counts.most_common(20)),
            "user_counts": dict(user_counts.most_common(10)),
            "recent_errors": len([l for l in self._logs[-100:] if not l.success]),
        }


# 全局审计日志实例
audit_logger = AuditLogger()


class DataEncryption:
    """数据加密工具。"""

    def __init__(self, key: str | None = None):
        self._key = key or secrets.token_hex(32)

    def hash_data(self, data: str) -> str:
        """哈希数据（单向）。"""
        return hashlib.sha256(data.encode()).hexdigest()

    def mask_sensitive(self, data: str, visible_chars: int = 4) -> str:
        """脱敏敏感信息。"""
        if len(data) <= visible_chars:
            return "*" * len(data)
        return data[:visible_chars] + "*" * (len(data) - visible_chars)

    def mask_email(self, email: str) -> str:
        """脱敏邮箱。"""
        if "@" not in email:
            return self.mask_sensitive(email)
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"

    def mask_phone(self, phone: str) -> str:
        """脱敏手机号。"""
        clean = phone.replace("-", "").replace(" ", "")
        if len(clean) >= 7:
            return clean[:3] + "****" + clean[-4:]
        return self.mask_sensitive(clean)

    def mask_ip(self, ip: str) -> str:
        """脱敏 IP 地址。"""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return self.mask_sensitive(ip)


# 全局加密工具实例
encryption = DataEncryption()


def audit_action(action: str, resource: str):
    """审计日志装饰器。"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = kwargs.get("principal", None)
            if user_id and hasattr(user_id, "id"):
                user_id = user_id.id
            else:
                user_id = "anonymous"

            ip_address = ""
            request = kwargs.get("request", None)
            if request and hasattr(request, "client"):
                ip_address = request.client.host if request.client else ""

            try:
                result = await func(*args, **kwargs)
                audit_logger.log(
                    user_id=user_id,
                    action=action,
                    resource=resource,
                    ip_address=ip_address,
                    success=True,
                )
                return result
            except Exception as e:
                audit_logger.log(
                    user_id=user_id,
                    action=action,
                    resource=resource,
                    ip_address=ip_address,
                    success=False,
                    error_message=str(e),
                )
                raise

        return wrapper

    return decorator
