"""
AgentOS Idempotency Store — Prevent Duplicate Processing.

Ensures operations are executed at most once, even with retries.
Uses deterministic key generation from operation + parameters.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
import hashlib
import json


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IdempotencyRecord:
    """Record of an idempotent operation."""
    key: str
    tenant_id: str
    operation: str
    result: Any = None
    status: IdempotencyStatus = IdempotencyStatus.IN_PROGRESS
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    error: str | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "tenant_id": self.tenant_id,
            "operation": self.operation,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_expired": self.is_expired,
        }


def generate_idempotency_key(operation: str, **kwargs: Any) -> str:
    """
    Generate a deterministic idempotency key from operation + params.
    Same inputs always produce the same key.
    """
    data = json.dumps({"op": operation, **kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:32]


class IdempotencyStore:
    """In-memory idempotency store. Replace backing store for production."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self._records: dict[str, IdempotencyRecord] = {}
        self.default_ttl = default_ttl_seconds

    def check(self, key: str) -> IdempotencyRecord | None:
        """
        Check if an operation was already processed.
        Returns the record if exists and not expired, None otherwise.
        """
        record = self._records.get(key)
        if record is None:
            return None
        if record.is_expired:
            del self._records[key]
            return None
        return record

    def reserve(
        self,
        key: str,
        tenant_id: str,
        operation: str,
        ttl_seconds: int | None = None,
    ) -> IdempotencyRecord | None:
        """
        Reserve an idempotency key (mark as in-progress).
        Returns None if key is already reserved/completed.
        """
        existing = self.check(key)
        if existing is not None:
            return None  # Already in use

        ttl = ttl_seconds or self.default_ttl
        record = IdempotencyRecord(
            key=key,
            tenant_id=tenant_id,
            operation=operation,
            status=IdempotencyStatus.IN_PROGRESS,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl),
        )
        self._records[key] = record
        return record

    def complete(self, key: str, result: Any) -> bool:
        """Mark an operation as completed with its result."""
        record = self._records.get(key)
        if not record:
            return False
        record.status = IdempotencyStatus.COMPLETED
        record.result = result
        record.completed_at = datetime.utcnow()
        return True

    def fail(self, key: str, error: str) -> bool:
        """
        Mark an operation as failed. This allows retrying
        (the key is removed so a new attempt can reserve it).
        """
        record = self._records.get(key)
        if not record:
            return False
        record.status = IdempotencyStatus.FAILED
        record.error = error
        # Remove so it can be retried
        del self._records[key]
        return True

    def remove(self, key: str) -> bool:
        """Explicitly remove an idempotency key."""
        return self._records.pop(key, None) is not None

    def cleanup_expired(self) -> int:
        """Remove all expired records. Returns count removed."""
        now = datetime.utcnow()
        expired = [
            k for k, v in self._records.items()
            if v.expires_at and now >= v.expires_at
        ]
        for k in expired:
            del self._records[k]
        return len(expired)
