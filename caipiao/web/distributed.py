"""分布式基础组件：分布式锁、分布式ID、分布式事务。"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..log import get_logger

logger = get_logger(__name__)


# === 分布式锁 ===
@dataclass
class LockInfo:
    lock_id: str
    resource: str
    owner: str
    acquired_at: float = field(default_factory=time.time)
    ttl: float = 30
    renew_count: int = 0


class DistributedLock:
    """分布式锁：基于内存的模拟实现。"""

    def __init__(self):
        self._locks: dict[str, LockInfo] = {}
        self._wait_queues: dict[str, list[asyncio.Future]] = defaultdict(list)

    async def acquire(self, resource: str, owner: str, ttl: float = 30, timeout: float = 10) -> str | None:
        lock_id = str(uuid.uuid4())[:12]
        start_time = time.time()

        while time.time() - start_time < timeout:
            existing = self._locks.get(resource)
            if existing is None or time.time() - existing.acquired_at > existing.ttl:
                self._locks[resource] = LockInfo(
                    lock_id=lock_id,
                    resource=resource,
                    owner=owner,
                    ttl=ttl,
                )
                logger.debug(f"Lock acquired: {resource} by {owner}")
                return lock_id

            await asyncio.sleep(0.01)

        logger.warning(f"Lock timeout: {resource} by {owner}")
        return None

    async def release(self, resource: str, lock_id: str) -> bool:
        lock = self._locks.get(resource)
        if lock and lock.lock_id == lock_id:
            del self._locks[resource]
            logger.debug(f"Lock released: {resource}")
            return True
        return False

    def is_locked(self, resource: str) -> bool:
        lock = self._locks.get(resource)
        if lock:
            if time.time() - lock.acquired_at > lock.ttl:
                del self._locks[resource]
                return False
            return True
        return False

    def get_lock_info(self, resource: str) -> LockInfo | None:
        return self._locks.get(resource)


# === 分布式ID生成器 ===
class DistributedIDGenerator:
    """分布式ID生成器：雪花算法模拟。"""

    def __init__(self, machine_id: int = 1):
        self._machine_id = machine_id & 0x3FF
        self._sequence = 0
        self._last_timestamp = -1
        self._epoch = 1609459200000  # 2021-01-01

    def _current_millis(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_ts: int) -> int:
        ts = self._current_millis()
        while ts <= last_ts:
            ts = self._current_millis()
        return ts

    def next_id(self) -> int:
        timestamp = self._current_millis()

        if timestamp < self._last_timestamp:
            raise Exception("Clock moved backwards")

        if timestamp == self._last_timestamp:
            self._sequence = (self._sequence + 1) & 0xFFF
            if self._sequence == 0:
                timestamp = self._wait_next_millis(self._last_timestamp)
        else:
            self._sequence = 0

        self._last_timestamp = timestamp

        id_val = ((timestamp - self._epoch) << 22) | (self._machine_id << 12) | self._sequence
        return id_val

    def next_id_str(self) -> str:
        return str(self.next_id())

    def parse_id(self, id_val: int) -> dict:
        sequence = id_val & 0xFFF
        machine_id = (id_val >> 12) & 0x3FF
        timestamp = (id_val >> 22) + self._epoch
        return {
            "id": id_val,
            "timestamp": timestamp,
            "machine_id": machine_id,
            "sequence": sequence,
        }


# === 分布式事务 ===
@dataclass
class TransactionOperation:
    name: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    compensate_action: str = ""
    compensate_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionRecord:
    id: str
    operations: list[TransactionOperation]
    status: str = "pending"  # pending, committed, rolled_back, failed
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    executed_ops: list[int] = field(default_factory=list)


class DistributedTransaction:
    """分布式事务：Saga模式模拟。"""

    def __init__(self):
        self._transactions: dict[str, TransactionRecord] = {}
        self._handlers: dict[str, callable] = {}

    def register_handler(self, action: str, handler: callable):
        self._handlers[action] = handler

    def begin(self, operations: list[TransactionOperation]) -> str:
        tx_id = str(uuid.uuid4())[:12]
        self._transactions[tx_id] = TransactionRecord(
            id=tx_id,
            operations=operations,
        )
        return tx_id

    async def commit(self, tx_id: str) -> bool:
        record = self._transactions.get(tx_id)
        if not record:
            return False

        record.status = "committing"

        for i, op in enumerate(record.operations):
            handler = self._handlers.get(op.action)
            if handler:
                try:
                    await handler(op.params)
                    record.executed_ops.append(i)
                except Exception as e:
                    logger.error(f"Transaction op failed: {e}")
                    record.status = "failed"
                    await self._compensate(record)
                    return False

        record.status = "committed"
        record.completed_at = time.time()
        return True

    async def _compensate(self, record: TransactionRecord):
        for i in reversed(record.executed_ops):
            op = record.operations[i]
            if op.compensate_action:
                handler = self._handlers.get(op.compensate_action)
                if handler:
                    try:
                        await handler(op.compensate_params)
                    except Exception as e:
                        logger.error(f"Compensation failed: {e}")

        record.status = "rolled_back"
        record.completed_at = time.time()

    async def rollback(self, tx_id: str) -> bool:
        record = self._transactions.get(tx_id)
        if not record or record.status not in ("pending", "failed"):
            return False
        await self._compensate(record)
        return True

    def get_transaction(self, tx_id: str) -> TransactionRecord | None:
        return self._transactions.get(tx_id)


# 全局实例
_lock = DistributedLock()
_id_generator = DistributedIDGenerator()
_transaction = DistributedTransaction()


def get_distributed_lock() -> DistributedLock:
    return _lock


def get_id_generator() -> DistributedIDGenerator:
    return _id_generator


def get_distributed_transaction() -> DistributedTransaction:
    return _transaction
