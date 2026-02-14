"""
AgentOS Data Normalizer — Vendor-Agnostic Schema Mapping.

Maps vendor-specific API responses to canonical AgentOS schemas.
Supports nested field access, transform functions, and per-adapter
mapping configurations.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
import json


# ---------------------------------------------------------------------------
# Canonical schemas
# ---------------------------------------------------------------------------

@dataclass
class NormalizedContact:
    """Vendor-agnostic contact representation."""
    id: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    title: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    adapter_name: str = ""
    tenant_id: str = ""
    normalized_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class NormalizedDeal:
    """Vendor-agnostic deal/opportunity representation."""
    id: str = ""
    name: str = ""
    amount: float = 0.0
    stage: str = ""
    close_date: str = ""
    contact_id: str = ""
    owner: str = ""
    probability: float = 0.0
    raw_data: dict[str, Any] = field(default_factory=dict)
    adapter_name: str = ""
    tenant_id: str = ""
    normalized_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NormalizedDocument:
    """Vendor-agnostic document representation."""
    id: str = ""
    title: str = ""
    content: str = ""
    doc_type: str = ""
    url: str = ""
    created_by: str = ""
    created_at: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    adapter_name: str = ""
    tenant_id: str = ""
    normalized_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

@dataclass
class FieldMapping:
    """Maps a source vendor field to a canonical target field."""
    source_field: str       # Dot-notation path, e.g. "properties.email"
    target_field: str       # Canonical field name, e.g. "email"
    transform: str | None = None  # Optional transform name
    default: Any = None     # Default if source is missing


@dataclass
class SchemaMapping:
    """Complete mapping config for an adapter + entity type."""
    adapter_name: str
    entity_type: str  # contact | deal | document
    mappings: list[FieldMapping] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transform functions
# ---------------------------------------------------------------------------

TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    "lowercase": lambda v: str(v).lower() if v else "",
    "uppercase": lambda v: str(v).upper() if v else "",
    "int": lambda v: int(v) if v is not None else 0,
    "float": lambda v: float(v) if v is not None else 0.0,
    "str": lambda v: str(v) if v is not None else "",
    "strip": lambda v: str(v).strip() if v else "",
    "date_parse": lambda v: str(v)[:10] if v else "",
    "timestamp_ms": lambda v: datetime.fromtimestamp(int(v) / 1000).isoformat() if v else "",
    "list_from_csv": lambda v: [s.strip() for s in str(v).split(",")] if v else [],
    "bool": lambda v: bool(v) if v is not None else False,
}


# ---------------------------------------------------------------------------
# DataNormalizer
# ---------------------------------------------------------------------------

class DataNormalizer:
    """Normalizes vendor data to canonical schemas using registered mappings."""

    def __init__(self):
        self._mappings: dict[str, SchemaMapping] = {}  # key: {adapter}:{entity_type}

    def register_mapping(self, mapping: SchemaMapping) -> None:
        """Register a schema mapping for an adapter + entity type."""
        key = f"{mapping.adapter_name}:{mapping.entity_type}"
        self._mappings[key] = mapping

    def normalize(
        self,
        adapter_name: str,
        entity_type: str,
        raw_data: dict[str, Any],
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """
        Normalize raw vendor data to canonical schema.

        Returns a dict with mapped fields. Use to construct
        NormalizedContact / NormalizedDeal / NormalizedDocument.
        """
        key = f"{adapter_name}:{entity_type}"
        mapping = self._mappings.get(key)
        if not mapping:
            return {"raw_data": raw_data, "adapter_name": adapter_name, "tenant_id": tenant_id}

        result: dict[str, Any] = {
            "raw_data": raw_data,
            "adapter_name": adapter_name,
            "tenant_id": tenant_id,
        }

        for fm in mapping.mappings:
            value = self._get_nested(raw_data, fm.source_field)
            if value is None:
                value = fm.default

            if fm.transform and fm.transform in TRANSFORMS:
                try:
                    value = TRANSFORMS[fm.transform](value)
                except (ValueError, TypeError, KeyError):
                    value = fm.default

            result[fm.target_field] = value

        return result

    def normalize_contact(
        self, adapter_name: str, raw_data: dict[str, Any], tenant_id: str = ""
    ) -> NormalizedContact:
        """Shorthand: normalize and return a NormalizedContact."""
        data = self.normalize(adapter_name, "contact", raw_data, tenant_id)
        return NormalizedContact(**{k: v for k, v in data.items() if hasattr(NormalizedContact, k)})

    def normalize_deal(
        self, adapter_name: str, raw_data: dict[str, Any], tenant_id: str = ""
    ) -> NormalizedDeal:
        """Shorthand: normalize and return a NormalizedDeal."""
        data = self.normalize(adapter_name, "deal", raw_data, tenant_id)
        return NormalizedDeal(**{k: v for k, v in data.items() if hasattr(NormalizedDeal, k)})

    @staticmethod
    def _get_nested(data: dict[str, Any], path: str) -> Any:
        """Access nested dict values via dot notation (e.g. 'properties.email')."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current


# ---------------------------------------------------------------------------
# Pre-built mappings (examples — add your own per vendor)
# ---------------------------------------------------------------------------

SALESFORCE_CONTACT_MAPPING = SchemaMapping(
    adapter_name="salesforce",
    entity_type="contact",
    mappings=[
        FieldMapping("Id", "id"),
        FieldMapping("FirstName", "first_name", "strip"),
        FieldMapping("LastName", "last_name", "strip"),
        FieldMapping("Email", "email", "lowercase"),
        FieldMapping("Phone", "phone", "strip"),
        FieldMapping("Account.Name", "company"),
        FieldMapping("Title", "title"),
        FieldMapping("LeadSource", "source", "lowercase"),
    ],
)

HUBSPOT_CONTACT_MAPPING = SchemaMapping(
    adapter_name="hubspot",
    entity_type="contact",
    mappings=[
        FieldMapping("id", "id", "str"),
        FieldMapping("properties.firstname", "first_name", "strip"),
        FieldMapping("properties.lastname", "last_name", "strip"),
        FieldMapping("properties.email", "email", "lowercase"),
        FieldMapping("properties.phone", "phone", "strip"),
        FieldMapping("properties.company", "company"),
        FieldMapping("properties.jobtitle", "title"),
        FieldMapping("properties.hs_lead_status", "source", "lowercase"),
    ],
)

NETSUITE_CONTACT_MAPPING = SchemaMapping(
    adapter_name="netsuite",
    entity_type="contact",
    mappings=[
        FieldMapping("internalId", "id", "str"),
        FieldMapping("firstName", "first_name", "strip"),
        FieldMapping("lastName", "last_name", "strip"),
        FieldMapping("email", "email", "lowercase"),
        FieldMapping("phone", "phone", "strip"),
        FieldMapping("company.name", "company"),
        FieldMapping("title", "title"),
    ],
)
