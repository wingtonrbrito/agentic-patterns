"""
AgentOS Core Resilience — Fault Tolerance Primitives.

Provides reliability patterns for distributed operations:
- DeadLetterQueue: Capture and retry failed events
- IdempotencyStore: Prevent duplicate processing
"""
from core.resilience.dlq import (
    DeadLetter,
    DeadLetterQueue,
    DLQStats,
    DLQStatus,
)
from core.resilience.idempotency import (
    IdempotencyRecord,
    IdempotencyStatus,
    IdempotencyStore,
    generate_idempotency_key,
)

__all__ = [
    # DLQ
    "DeadLetter",
    "DeadLetterQueue",
    "DLQStats",
    "DLQStatus",
    # Idempotency
    "IdempotencyRecord",
    "IdempotencyStatus",
    "IdempotencyStore",
    "generate_idempotency_key",
]
