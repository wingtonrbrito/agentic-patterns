"""
AgentOS Core Integrations — Universal Adapter Framework.

Provides vendor-agnostic integration infrastructure:
- AdapterBase: Universal HTTP adapter with auth, rate limiting, circuit breaker
- OAuthManager: OAuth2 lifecycle (authorize, exchange, refresh, revoke)
- DataNormalizer: Vendor → canonical schema mapping
- WebhookEmitter: Outbound event delivery with HMAC signing
"""
from core.integrations.adapter_base import (
    AdapterBase,
    AdapterRequest,
    AdapterResponse,
    AuthCredentials,
    AuthType,
    IntegrationHealth,
    RateLimiter,
)
from core.integrations.normalizer import (
    DataNormalizer,
    FieldMapping,
    NormalizedContact,
    NormalizedDeal,
    NormalizedDocument,
    SchemaMapping,
    TRANSFORMS,
)
from core.integrations.oauth_manager import (
    OAuthConfig,
    OAuthManager,
    OAuthToken,
)
from core.integrations.webhooks import (
    WebhookDelivery,
    WebhookEmitter,
    WebhookEvent,
    WebhookRegistration,
)

__all__ = [
    # Adapter
    "AdapterBase",
    "AdapterRequest",
    "AdapterResponse",
    "AuthCredentials",
    "AuthType",
    "IntegrationHealth",
    "RateLimiter",
    # Normalizer
    "DataNormalizer",
    "FieldMapping",
    "NormalizedContact",
    "NormalizedDeal",
    "NormalizedDocument",
    "SchemaMapping",
    "TRANSFORMS",
    # OAuth
    "OAuthConfig",
    "OAuthManager",
    "OAuthToken",
    # Webhooks
    "WebhookDelivery",
    "WebhookEmitter",
    "WebhookEvent",
    "WebhookRegistration",
]
