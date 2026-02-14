"""Dataclass-based domain configuration pattern.

Each vertical defines its thresholds, limits, and feature flags as a
frozen dataclass. This gives you:
- Type safety (IDE autocompletion, mypy checking)
- Default values (sensible out-of-the-box)
- Immutability (frozen=True prevents accidental mutation)
- Easy overrides (from env vars, config files, or tenant settings)

Example domain: a bookstore with pricing, inventory, and loyalty config.
"""

from dataclasses import dataclass, field
from decimal import Decimal


# ---------------------------------------------------------------------------
# Nested config sections
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PricingConfig:
    """Pricing rules and thresholds."""

    min_price: Decimal = Decimal("0.99")
    max_discount_pct: Decimal = Decimal("30.0")
    bulk_discount_threshold: int = 10  # items
    bulk_discount_pct: Decimal = Decimal("15.0")
    free_shipping_threshold: Decimal = Decimal("35.00")
    tax_rate: Decimal = Decimal("8.875")  # NYC rate


@dataclass(frozen=True)
class InventoryConfig:
    """Inventory management thresholds."""

    low_stock_threshold: int = 5
    reorder_point: int = 10
    max_backorder_days: int = 14
    auto_reorder_enabled: bool = True


@dataclass(frozen=True)
class LoyaltyConfig:
    """Customer loyalty program settings."""

    points_per_dollar: int = 10
    points_for_signup: int = 100
    discount_per_100_points: Decimal = Decimal("5.00")
    vip_threshold_points: int = 1000
    vip_discount_pct: Decimal = Decimal("10.0")


# ---------------------------------------------------------------------------
# Top-level domain config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BookstoreConfig:
    """Complete configuration for the bookstore vertical.

    Usage::

        config = BookstoreConfig.default()
        if order.total >= config.pricing.free_shipping_threshold:
            apply_free_shipping(order)
    """

    pricing: PricingConfig = field(default_factory=PricingConfig)
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    loyalty: LoyaltyConfig = field(default_factory=LoyaltyConfig)

    # Feature flags
    enable_recommendations: bool = True
    enable_reviews: bool = True
    enable_wishlists: bool = True
    max_items_per_order: int = 50

    @classmethod
    def default(cls) -> "BookstoreConfig":
        """Create config with all defaults."""
        return cls()

    @classmethod
    def from_env(cls, prefix: str = "BOOKSTORE_") -> "BookstoreConfig":
        """Create config from environment variables.

        Example: BOOKSTORE_MAX_ITEMS_PER_ORDER=100
        """
        import os

        overrides = {}
        max_items = os.getenv(f"{prefix}MAX_ITEMS_PER_ORDER")
        if max_items:
            overrides["max_items_per_order"] = int(max_items)

        return cls(**overrides)
