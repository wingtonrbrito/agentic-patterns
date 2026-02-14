"""Base model and mixins for all SQLAlchemy models.

Provides:
- Base: Declarative base class for all models
- TenantMixin: Adds tenant_id, UUID primary key, and timestamps

Every model inherits from Base and includes TenantMixin for multi-tenant
isolation. The tenant_id column is indexed for efficient per-tenant queries.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all AgentOS models."""
    pass


class TenantMixin:
    """Mixin providing multi-tenant isolation and standard audit columns.

    Adds:
    - id: UUID primary key (auto-generated)
    - tenant_id: Indexed string for tenant isolation
    - created_at: Timestamp set on insert
    - updated_at: Timestamp updated on every change
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        default="default",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
