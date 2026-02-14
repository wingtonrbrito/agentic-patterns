"""
AgentOS OAuth2 Lifecycle Manager.

Centralized management for OAuth2 flows:
- Provider registration (authorize URL, token URL, scopes)
- Authorization code exchange
- Automatic token refresh with expiry tracking
- Token revocation
- Scope validation
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
import hashlib
import secrets

import httpx


@dataclass
class OAuthToken:
    """Tenant + adapter scoped OAuth token."""
    tenant_id: str
    adapter_name: str
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scopes: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    issued_at: datetime = field(default_factory=datetime.utcnow)
    refresh_count: int = 0

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        # Refresh 60s before actual expiry to avoid race conditions
        return datetime.utcnow() >= (self.expires_at - timedelta(seconds=60))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "adapter_name": self.adapter_name,
            "token_type": self.token_type,
            "scopes": self.scopes,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "refresh_count": self.refresh_count,
            "is_expired": self.is_expired,
        }


@dataclass
class OAuthConfig:
    """OAuth2 provider configuration."""
    provider_name: str
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: list[str] = field(default_factory=list)
    revoke_url: str | None = None
    redirect_uri: str = "http://localhost:8000/oauth/callback"


class OAuthManager:
    """Manages OAuth2 flows across providers and tenants."""

    def __init__(self):
        self._providers: dict[str, OAuthConfig] = {}
        self._tokens: dict[str, OAuthToken] = {}  # key: {tenant}:{adapter}
        self._states: dict[str, dict[str, str]] = {}  # CSRF state tracking

    def register_provider(self, config: OAuthConfig) -> None:
        """Register an OAuth2 provider."""
        self._providers[config.provider_name] = config

    def get_authorize_url(
        self,
        provider_name: str,
        tenant_id: str,
        extra_scopes: list[str] | None = None,
    ) -> str:
        """Generate authorization URL with CSRF state."""
        config = self._providers.get(provider_name)
        if not config:
            raise ValueError(f"Unknown OAuth provider: {provider_name}")

        state = secrets.token_urlsafe(32)
        self._states[state] = {"tenant_id": tenant_id, "provider": provider_name}

        scopes = config.scopes + (extra_scopes or [])
        scope_str = " ".join(scopes)

        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": scope_str,
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{config.authorize_url}?{query}"

    async def exchange_code(
        self,
        provider_name: str,
        tenant_id: str,
        code: str,
        state: str | None = None,
    ) -> OAuthToken:
        """Exchange authorization code for tokens."""
        # Validate CSRF state
        if state and state in self._states:
            stored = self._states.pop(state)
            if stored["tenant_id"] != tenant_id or stored["provider"] != provider_name:
                raise ValueError("OAuth state mismatch")

        config = self._providers.get(provider_name)
        if not config:
            raise ValueError(f"Unknown OAuth provider: {provider_name}")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config.redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        expires_in = data.get("expires_in", 3600)
        token = OAuthToken(
            tenant_id=tenant_id,
            adapter_name=provider_name,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            scopes=data.get("scope", "").split() if isinstance(data.get("scope"), str) else data.get("scope", []),
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
        )

        key = f"{tenant_id}:{provider_name}"
        self._tokens[key] = token
        return token

    async def get_valid_token(self, provider_name: str, tenant_id: str) -> OAuthToken | None:
        """Get a valid token, auto-refreshing if expired."""
        key = f"{tenant_id}:{provider_name}"
        token = self._tokens.get(key)
        if not token:
            return None

        if token.is_expired and token.refresh_token:
            refreshed = await self._refresh_token(provider_name, tenant_id)
            if refreshed:
                return refreshed
            return None

        return token

    async def _refresh_token(self, provider_name: str, tenant_id: str) -> OAuthToken | None:
        """Refresh an expired token."""
        key = f"{tenant_id}:{provider_name}"
        token = self._tokens.get(key)
        config = self._providers.get(provider_name)
        if not token or not token.refresh_token or not config:
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    config.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token.refresh_token,
                        "client_id": config.client_id,
                        "client_secret": config.client_secret,
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

        expires_in = data.get("expires_in", 3600)
        token.access_token = data["access_token"]
        if "refresh_token" in data:
            token.refresh_token = data["refresh_token"]
        token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        token.refresh_count += 1
        return token

    async def revoke_token(self, provider_name: str, tenant_id: str) -> bool:
        """Revoke a token."""
        key = f"{tenant_id}:{provider_name}"
        token = self._tokens.get(key)
        config = self._providers.get(provider_name)
        if not token:
            return False

        if config and config.revoke_url:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        config.revoke_url,
                        data={"token": token.access_token, "client_id": config.client_id},
                        timeout=10.0,
                    )
            except Exception:
                pass

        self._tokens.pop(key, None)
        return True

    def validate_scopes(self, provider_name: str, tenant_id: str, required_scopes: list[str]) -> bool:
        """Check if the token has all required scopes."""
        key = f"{tenant_id}:{provider_name}"
        token = self._tokens.get(key)
        if not token:
            return False
        return all(s in token.scopes for s in required_scopes)
