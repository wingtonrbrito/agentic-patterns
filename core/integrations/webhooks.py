"""
AgentOS Webhook Emitter — Outbound Event Delivery.

Emits events to registered webhook endpoints with:
- HMAC-SHA256 payload signing
- Retry with exponential backoff
- Fan-out to multiple subscribers
- Delivery tracking and history
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import hashlib
import hmac
import json
import uuid
import asyncio

import httpx


class WebhookEvent(str, Enum):
    """Standard webhook event types."""
    RECORD_CREATED = "record.created"
    RECORD_UPDATED = "record.updated"
    RECORD_DELETED = "record.deleted"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    AGENT_RESPONSE = "agent.response"
    REVIEW_REQUIRED = "review.required"
    REVIEW_COMPLETED = "review.completed"


@dataclass
class WebhookRegistration:
    """A registered webhook endpoint."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    url: str = ""
    events: list[str] = field(default_factory=list)  # Empty = all events
    secret: str = ""  # HMAC signing secret
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    registration_id: str = ""
    event: str = ""
    url: str = ""
    status_code: int = 0
    latency_ms: float = 0.0
    attempt: int = 1
    success: bool = False
    error: str | None = None
    delivered_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "registration_id": self.registration_id,
            "event": self.event,
            "url": self.url,
            "status_code": self.status_code,
            "latency_ms": round(self.latency_ms, 1),
            "attempt": self.attempt,
            "success": self.success,
            "error": self.error,
            "delivered_at": self.delivered_at.isoformat(),
        }


class WebhookEmitter:
    """Emits webhook events to registered endpoints."""

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0

    def __init__(self):
        self._registrations: dict[str, WebhookRegistration] = {}
        self._deliveries: list[WebhookDelivery] = []

    def register(self, registration: WebhookRegistration) -> str:
        """Register a webhook endpoint. Returns registration ID."""
        self._registrations[registration.id] = registration
        return registration.id

    def unregister(self, registration_id: str) -> bool:
        """Remove a webhook registration."""
        return self._registrations.pop(registration_id, None) is not None

    def list_registrations(self, tenant_id: str | None = None) -> list[WebhookRegistration]:
        """List registrations, optionally filtered by tenant."""
        regs = list(self._registrations.values())
        if tenant_id:
            regs = [r for r in regs if r.tenant_id == tenant_id]
        return regs

    def _sign_payload(self, payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for a payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def emit(
        self,
        event: str,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> list[WebhookDelivery]:
        """
        Emit an event to all matching registrations.
        Fan-out: delivers to all matching endpoints concurrently.
        """
        matching = [
            reg for reg in self._registrations.values()
            if reg.active
            and reg.tenant_id == tenant_id
            and (not reg.events or event in reg.events)
        ]

        if not matching:
            return []

        tasks = [
            self._deliver(reg, event, payload)
            for reg in matching
        ]
        deliveries = await asyncio.gather(*tasks)
        self._deliveries.extend(deliveries)
        return list(deliveries)

    async def _deliver(
        self,
        registration: WebhookRegistration,
        event: str,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """Deliver a webhook to a single endpoint with retries."""
        body = json.dumps(payload, default=str, sort_keys=True)
        signature = self._sign_payload(body, registration.secret) if registration.secret else ""

        headers = {
            "Content-Type": "application/json",
            "X-AgentOS-Event": event,
            "X-AgentOS-Delivery": str(uuid.uuid4()),
        }
        if signature:
            headers["X-AgentOS-Signature"] = f"sha256={signature}"

        last_error: str | None = None
        import time

        for attempt in range(1, self.MAX_RETRIES + 1):
            start = time.time()
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        registration.url,
                        content=body,
                        headers=headers,
                        timeout=10.0,
                    )
                    latency = (time.time() - start) * 1000

                    if 200 <= resp.status_code < 300:
                        return WebhookDelivery(
                            registration_id=registration.id,
                            event=event,
                            url=registration.url,
                            status_code=resp.status_code,
                            latency_ms=latency,
                            attempt=attempt,
                            success=True,
                        )

                    last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                latency = (time.time() - start) * 1000
                last_error = str(exc)

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.BACKOFF_BASE * (2 ** (attempt - 1)))

        return WebhookDelivery(
            registration_id=registration.id,
            event=event,
            url=registration.url,
            status_code=0,
            latency_ms=latency,
            attempt=self.MAX_RETRIES,
            success=False,
            error=last_error,
        )

    def get_deliveries(
        self,
        tenant_id: str | None = None,
        event: str | None = None,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        """Query delivery history."""
        results = list(self._deliveries)
        if tenant_id:
            reg_ids = {r.id for r in self._registrations.values() if r.tenant_id == tenant_id}
            results = [d for d in results if d.registration_id in reg_ids]
        if event:
            results = [d for d in results if d.event == event]
        return sorted(results, key=lambda d: d.delivered_at, reverse=True)[:limit]
