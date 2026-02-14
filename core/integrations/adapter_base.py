"""
AgentOS Universal Adapter Framework.

Every external API integration (CRM, ERP, MLS, LOS, payment gateway)
inherits from AdapterBase. Provides:
- Multi-auth (API key, Basic, OAuth2, custom)
- Per-tenant rate limiting (sliding window)
- Built-in circuit breaker (closed/open/half_open)
- Automatic OAuth token refresh on 401
- Health tracking (latency, errors, auth failures)
- Standardized request/response envelope
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
import asyncio
import base64
import hashlib
import time

import httpx


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class AuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


@dataclass
class AuthCredentials:
    """Tenant-scoped credentials for an adapter."""
    tenant_id: str
    adapter_name: str
    auth_type: AuthType = AuthType.NONE
    api_key: str | None = None
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    username: str | None = None
    password: str | None = None
    oauth_access_token: str | None = None
    oauth_refresh_token: str | None = None
    oauth_token_url: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_expires_at: datetime | None = None
    custom_headers: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request / Response envelope
# ---------------------------------------------------------------------------

@dataclass
class AdapterRequest:
    """Standardized outbound request."""
    method: str  # GET, POST, PUT, PATCH, DELETE
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0


@dataclass
class AdapterResponse:
    """Standardized inbound response."""
    status_code: int
    data: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
    adapter_name: str = ""
    tenant_id: str = ""
    error: str | None = None
    retries: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


# ---------------------------------------------------------------------------
# Rate Limiter (sliding window)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Per-tenant per-adapter sliding window rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counters: dict[str, list[float]] = {}

    def check(self, tenant_id: str, adapter_name: str) -> bool:
        """Return True if request is allowed."""
        key = f"{tenant_id}:{adapter_name}"
        now = time.time()
        cutoff = now - self.window_seconds

        if key not in self._counters:
            self._counters[key] = []

        # Clean old entries
        self._counters[key] = [t for t in self._counters[key] if t > cutoff]

        if len(self._counters[key]) >= self.max_requests:
            return False

        self._counters[key].append(now)
        return True

    def remaining(self, tenant_id: str, adapter_name: str) -> int:
        key = f"{tenant_id}:{adapter_name}"
        now = time.time()
        cutoff = now - self.window_seconds
        if key not in self._counters:
            return self.max_requests
        active = [t for t in self._counters[key] if t > cutoff]
        return max(0, self.max_requests - len(active))


# ---------------------------------------------------------------------------
# Health tracking
# ---------------------------------------------------------------------------

@dataclass
class IntegrationHealth:
    """Health metrics for an adapter."""
    adapter_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    auth_failures: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    circuit_state: str = "closed"
    last_success: datetime | None = None
    last_failure: datetime | None = None
    last_error: str | None = None

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "total_requests": self.total_requests,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "auth_failures": self.auth_failures,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "circuit_state": self.circuit_state,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
        }


# ---------------------------------------------------------------------------
# AdapterBase
# ---------------------------------------------------------------------------

class AdapterBase(ABC):
    """
    Base class for all external API adapters.

    Subclasses must set:
        name: str           — adapter identifier
        base_url: str       — API root URL
        auth_type: AuthType — authentication method
    """

    name: str = ""
    base_url: str = ""
    auth_type: AuthType = AuthType.NONE

    # Circuit breaker defaults
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: float = 30.0

    # Retry defaults
    MAX_RETRIES: int = 3
    BACKOFF_BASE: float = 1.0
    BACKOFF_MAX: float = 15.0

    def __init__(self):
        self._credentials: dict[str, AuthCredentials] = {}  # tenant_id -> creds
        self._rate_limiter = RateLimiter()
        self._health = IntegrationHealth(adapter_name=self.name)
        self._latencies: list[float] = []

        # Circuit breaker state
        self._cb_state: str = "closed"
        self._cb_failure_count: int = 0
        self._cb_last_failure: datetime | None = None

    # --- Credentials ---

    def set_credentials(self, creds: AuthCredentials) -> None:
        """Store credentials for a tenant."""
        self._credentials[creds.tenant_id] = creds

    def get_credentials(self, tenant_id: str) -> AuthCredentials | None:
        return self._credentials.get(tenant_id)

    # --- Auth headers ---

    def get_auth_headers(self, tenant_id: str) -> dict[str, str]:
        """Build auth headers for the given tenant."""
        creds = self._credentials.get(tenant_id)
        if not creds:
            return {}

        if creds.auth_type == AuthType.API_KEY and creds.api_key:
            return {creds.api_key_header: f"{creds.api_key_prefix} {creds.api_key}"}

        if creds.auth_type == AuthType.BASIC and creds.username and creds.password:
            encoded = base64.b64encode(f"{creds.username}:{creds.password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}

        if creds.auth_type == AuthType.OAUTH2 and creds.oauth_access_token:
            return {"Authorization": f"Bearer {creds.oauth_access_token}"}

        if creds.auth_type == AuthType.CUSTOM:
            return dict(creds.custom_headers)

        return {}

    async def _refresh_oauth_token(self, tenant_id: str) -> bool:
        """Refresh an expired OAuth2 token."""
        creds = self._credentials.get(tenant_id)
        if not creds or not creds.oauth_refresh_token or not creds.oauth_token_url:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    creds.oauth_token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": creds.oauth_refresh_token,
                        "client_id": creds.oauth_client_id or "",
                        "client_secret": creds.oauth_client_secret or "",
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    creds.oauth_access_token = data["access_token"]
                    if "refresh_token" in data:
                        creds.oauth_refresh_token = data["refresh_token"]
                    expires_in = data.get("expires_in", 3600)
                    creds.oauth_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    return True
        except Exception:
            pass
        self._health.auth_failures += 1
        return False

    # --- Circuit breaker ---

    def _check_circuit(self) -> bool:
        """Return True if request should proceed."""
        if self._cb_state == "closed":
            return True
        if self._cb_state == "open":
            if self._cb_last_failure and (
                datetime.utcnow() - self._cb_last_failure
            ).total_seconds() > self.CB_RECOVERY_TIMEOUT:
                self._cb_state = "half_open"
                return True
            return False
        # half_open: allow one test request
        return True

    def _record_success(self) -> None:
        self._cb_failure_count = 0
        self._cb_state = "closed"
        self._health.circuit_state = "closed"

    def _record_failure(self) -> None:
        self._cb_failure_count += 1
        self._cb_last_failure = datetime.utcnow()
        if self._cb_failure_count >= self.CB_FAILURE_THRESHOLD:
            self._cb_state = "open"
            self._health.circuit_state = "open"

    # --- Health ---

    def _update_health(self, latency_ms: float, success: bool, error: str | None = None) -> None:
        self._health.total_requests += 1
        self._latencies.append(latency_ms)
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]

        if success:
            self._health.successful_requests += 1
            self._health.last_success = datetime.utcnow()
            self._record_success()
        else:
            self._health.failed_requests += 1
            self._health.last_failure = datetime.utcnow()
            self._health.last_error = error
            self._record_failure()

        self._health.avg_latency_ms = sum(self._latencies) / len(self._latencies)
        sorted_lats = sorted(self._latencies)
        p95_idx = int(len(sorted_lats) * 0.95)
        self._health.p95_latency_ms = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]

    def get_health(self) -> IntegrationHealth:
        return self._health

    # --- Core request ---

    async def request(
        self,
        req: AdapterRequest,
        tenant_id: str,
    ) -> AdapterResponse:
        """
        Execute a request through the full adapter pipeline:
        Rate Limit → Circuit Breaker → Auth → Retry w/ Backoff → Health
        """
        # Rate limit check
        if not self._rate_limiter.check(tenant_id, self.name):
            return AdapterResponse(
                status_code=429,
                error="Rate limit exceeded",
                adapter_name=self.name,
                tenant_id=tenant_id,
            )

        # Circuit breaker check
        if not self._check_circuit():
            return AdapterResponse(
                status_code=503,
                error=f"Circuit breaker OPEN for {self.name}",
                adapter_name=self.name,
                tenant_id=tenant_id,
            )

        # Auth headers
        auth_headers = self.get_auth_headers(tenant_id)

        url = f"{self.base_url.rstrip('/')}/{req.path.lstrip('/')}"
        headers = {**auth_headers, **req.headers}

        last_error: str | None = None
        retries = 0

        async with httpx.AsyncClient() as client:
            for attempt in range(self.MAX_RETRIES + 1):
                start = time.time()
                try:
                    resp = await client.request(
                        method=req.method,
                        url=url,
                        params=req.params or None,
                        json=req.body,
                        headers=headers,
                        timeout=req.timeout,
                    )
                    latency = (time.time() - start) * 1000

                    # Auto-refresh on 401 (first attempt only)
                    if resp.status_code == 401 and attempt == 0:
                        creds = self._credentials.get(tenant_id)
                        if creds and creds.auth_type == AuthType.OAUTH2:
                            refreshed = await self._refresh_oauth_token(tenant_id)
                            if refreshed:
                                headers.update(self.get_auth_headers(tenant_id))
                                continue

                    if resp.status_code < 500:
                        self._update_health(latency, resp.status_code < 400)
                        return AdapterResponse(
                            status_code=resp.status_code,
                            data=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                            headers=dict(resp.headers),
                            latency_ms=latency,
                            adapter_name=self.name,
                            tenant_id=tenant_id,
                            retries=retries,
                        )

                    # 5xx — retry
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    retries += 1

                except Exception as exc:
                    latency = (time.time() - start) * 1000
                    last_error = str(exc)
                    retries += 1

                if attempt < self.MAX_RETRIES:
                    backoff = min(self.BACKOFF_BASE * (2 ** attempt), self.BACKOFF_MAX)
                    await asyncio.sleep(backoff)

        # All retries exhausted
        self._update_health(latency, False, last_error)
        return AdapterResponse(
            status_code=502,
            error=last_error,
            adapter_name=self.name,
            tenant_id=tenant_id,
            retries=retries,
        )
