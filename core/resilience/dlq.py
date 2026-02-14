"""
AgentOS Dead Letter Queue — Never Lose Events.

Failed messages are captured with full context for later
retry, inspection, or manual resolution. Supports:
- Per-queue, per-tenant isolation
- Retry status tracking
- Statistics and monitoring
- Configurable retention and purging
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid


class DLQStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    RESOLVED = "resolved"
    DISCARDED = "discarded"


@dataclass
class DeadLetter:
    """A failed event captured in the DLQ."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    queue_name: str = ""
    tenant_id: str = ""
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_traceback: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    status: DLQStatus = DLQStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    @property
    def can_retry(self) -> bool:
        return self.status == DLQStatus.PENDING and self.retry_count < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "queue_name": self.queue_name,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "status": self.status.value,
            "can_retry": self.can_retry,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class DLQStats:
    """Aggregate statistics for a DLQ."""
    queue_name: str
    total: int = 0
    pending: int = 0
    retrying: int = 0
    resolved: int = 0
    discarded: int = 0
    oldest: datetime | None = None
    newest: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_name": self.queue_name,
            "total": self.total,
            "pending": self.pending,
            "retrying": self.retrying,
            "resolved": self.resolved,
            "discarded": self.discarded,
            "oldest": self.oldest.isoformat() if self.oldest else None,
            "newest": self.newest.isoformat() if self.newest else None,
        }


class DeadLetterQueue:
    """In-memory DLQ implementation. Replace backing store for production."""

    def __init__(self):
        self._letters: dict[str, DeadLetter] = {}

    def enqueue(
        self,
        queue_name: str,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        error: str,
        error_traceback: str | None = None,
        max_retries: int = 3,
    ) -> DeadLetter:
        """Add a failed event to the DLQ."""
        letter = DeadLetter(
            queue_name=queue_name,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            error=error,
            error_traceback=error_traceback,
            max_retries=max_retries,
        )
        self._letters[letter.id] = letter
        return letter

    def get(self, letter_id: str) -> DeadLetter | None:
        """Get a dead letter by ID."""
        return self._letters.get(letter_id)

    def list_pending(
        self,
        queue_name: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[DeadLetter]:
        """List pending dead letters, optionally filtered."""
        results = [
            dl for dl in self._letters.values()
            if dl.status in (DLQStatus.PENDING, DLQStatus.RETRYING)
        ]
        if queue_name:
            results = [dl for dl in results if dl.queue_name == queue_name]
        if tenant_id:
            results = [dl for dl in results if dl.tenant_id == tenant_id]
        results.sort(key=lambda dl: dl.created_at)
        return results[:limit]

    def mark_retrying(self, letter_id: str) -> bool:
        """Mark a dead letter as being retried."""
        letter = self._letters.get(letter_id)
        if not letter or not letter.can_retry:
            return False
        letter.status = DLQStatus.RETRYING
        letter.retry_count += 1
        letter.updated_at = datetime.utcnow()
        return True

    def mark_resolved(self, letter_id: str, resolved_by: str = "") -> bool:
        """Mark a dead letter as resolved (successfully reprocessed)."""
        letter = self._letters.get(letter_id)
        if not letter:
            return False
        letter.status = DLQStatus.RESOLVED
        letter.resolved_at = datetime.utcnow()
        letter.resolved_by = resolved_by
        letter.updated_at = datetime.utcnow()
        return True

    def mark_discarded(self, letter_id: str, reason: str = "") -> bool:
        """Mark a dead letter as discarded (won't be retried)."""
        letter = self._letters.get(letter_id)
        if not letter:
            return False
        letter.status = DLQStatus.DISCARDED
        letter.error = f"{letter.error} | Discarded: {reason}" if reason else letter.error
        letter.updated_at = datetime.utcnow()
        return True

    def get_stats(self, queue_name: str = "") -> DLQStats:
        """Get aggregate statistics."""
        letters = list(self._letters.values())
        if queue_name:
            letters = [dl for dl in letters if dl.queue_name == queue_name]

        stats = DLQStats(queue_name=queue_name or "all")
        stats.total = len(letters)
        stats.pending = sum(1 for dl in letters if dl.status == DLQStatus.PENDING)
        stats.retrying = sum(1 for dl in letters if dl.status == DLQStatus.RETRYING)
        stats.resolved = sum(1 for dl in letters if dl.status == DLQStatus.RESOLVED)
        stats.discarded = sum(1 for dl in letters if dl.status == DLQStatus.DISCARDED)

        if letters:
            stats.oldest = min(dl.created_at for dl in letters)
            stats.newest = max(dl.created_at for dl in letters)

        return stats

    def purge_resolved(self, queue_name: str | None = None) -> int:
        """Remove resolved entries. Returns count removed."""
        to_remove = [
            dl_id for dl_id, dl in self._letters.items()
            if dl.status == DLQStatus.RESOLVED
            and (queue_name is None or dl.queue_name == queue_name)
        ]
        for dl_id in to_remove:
            del self._letters[dl_id]
        return len(to_remove)
