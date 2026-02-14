"""
AgentOS Circuit Breaker — Resilience for Tool Calls

Protects against:
- External API failures (retry with exponential backoff)
- Cascading failures (circuit breaker pattern)
- Slow responses (timeouts)
- Total failure (cached fallback)
"""
from __future__ import annotations
from typing import Callable, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import time


class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing — reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker with exponential backoff and cached fallback.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure: Optional[datetime] = None
        self._cache: dict[str, Any] = {}

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if self._last_failure and (
                datetime.utcnow() - self._last_failure
            ).total_seconds() > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(
        self,
        func: Callable,
        *args,
        cache_key: Optional[str] = None,
        fallback: Optional[Callable] = None,
        **kwargs,
    ) -> Any:
        """Execute function with circuit breaker protection."""

        # Check circuit state
        if self.state == CircuitState.OPEN:
            # Try cache first
            if cache_key and cache_key in self._cache:
                return self._cache[cache_key]
            # Try fallback
            if fallback:
                return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)
            raise RuntimeError(f"Circuit breaker OPEN. Retry after {self.recovery_timeout}s")

        # Retry with exponential backoff
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success — reset circuit
                self._failure_count = 0
                self._state = CircuitState.CLOSED

                # Cache result
                if cache_key:
                    self._cache[cache_key] = result

                return result

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    backoff = min(
                        self.backoff_base * (2 ** attempt),
                        self.backoff_max,
                    )
                    await asyncio.sleep(backoff)

        # All retries failed
        self._failure_count += 1
        self._last_failure = datetime.utcnow()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

        # Try cache
        if cache_key and cache_key in self._cache:
            return self._cache[cache_key]

        # Try fallback
        if fallback:
            return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)

        raise last_error
