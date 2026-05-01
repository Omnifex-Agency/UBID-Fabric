"""
UBID Fabric — Core Data Models (All 6 Layers)
Pydantic models for type safety, validation, and JSON serialization.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


# ═══════════════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════════════

class CaptureMethod(str, Enum):
    WEBHOOK = "WEBHOOK"
    API_POLL = "API_POLL"
    CDC = "CDC"
    SNAPSHOT_DIFF = "SNAPSHOT_DIFF"

class ChangeType(str, Enum):
    FIELD_UPDATE = "FIELD_UPDATE"
    ENTITY_CREATE = "ENTITY_CREATE"
    ENTITY_DELETE = "ENTITY_DELETE"
    COMPENSATION = "COMPENSATION"
    REPLAY = "REPLAY"

class CRDTType(str, Enum):
    LWW_REGISTER = "LWW_REGISTER"
    OR_SET = "OR_SET"
    MONOTONIC_COUNTER = "MONOTONIC_COUNTER"
    NONE = "NONE"

class FieldType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    SET = "SET"
    LIST = "LIST"

class UBIDConfidence(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    PROBATION = "PROBATION"
    QUARANTINE = "QUARANTINE"

class ConflictLevel(str, Enum):
    LEVEL_1_CRDT = "LEVEL_1_CRDT"
    LEVEL_2_SOURCE_PRIORITY = "LEVEL_2_SOURCE_PRIORITY"
    LEVEL_3_DOMAIN_OWNERSHIP = "LEVEL_3_DOMAIN_OWNERSHIP"
    LEVEL_4_MANUAL_REVIEW = "LEVEL_4_MANUAL_REVIEW"

class MappingStatus(str, Enum):
    DRAFTED = "DRAFTED"
    SHADOW = "SHADOW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class DriftType(str, Enum):
    STALE = "STALE"
    OUT_OF_BAND = "OUT_OF_BAND"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"

class EvidenceNodeType(str, Enum):
    CANONICAL_EVENT = "CANONICAL_EVENT"
    UBID_RESOLUTION = "UBID_RESOLUTION"
    SCHEMA_TRANSLATION = "SCHEMA_TRANSLATION"
    CONFLICT_DETECTION = "CONFLICT_DETECTION"
    CONFLICT_RESOLUTION = "CONFLICT_RESOLUTION"
    PROPAGATION_WRITE = "PROPAGATION_WRITE"
    WRITE_CONFIRMATION = "WRITE_CONFIRMATION"
    WRITE_FAILURE = "WRITE_FAILURE"
    RETRY = "RETRY"
    DLQ_ENTRY = "DLQ_ENTRY"
    COMPENSATION = "COMPENSATION"
    REPLAY = "REPLAY"
    MANUAL_DECISION = "MANUAL_DECISION"
    RECONCILIATION_CHECK = "RECONCILIATION_CHECK"

class EvidenceEdgeType(str, Enum):
    CAUSED_BY = "caused_by"
    RESOLVED_BY = "resolved_by"
    SUPERSEDED_BY = "superseded_by"
    COMPENSATED_BY = "compensated_by"
    REPLAYED_AS = "replayed_as"
    TRANSLATED_VIA = "translated_via"
    ESCALATED_TO = "escalated_to"
    VERIFIED_BY = "verified_by"


# ═══════════════════════════════════════════════════════════════
# L1 — Ingestion Layer
# ═══════════════════════════════════════════════════════════════

class FieldChange(BaseModel):
    """A single field-level change from a source system."""
    field_name: str
    old_value: Any = None
    new_value: Any = None

class RawChange(BaseModel):
    """Uniform output from any connector (Tier 1/2/3)."""
    connector_id: str
    source_system: str
    entity_type: str
    entity_id: str
    changed_fields: list[FieldChange]
    change_timestamp: datetime
    capture_method: CaptureMethod
    capture_timestamp: datetime = Field(default_factory=datetime.now)


# ─── Dynamic Connectors ──────────────────────────────────────

class ConnectorConfig(BaseModel):
    """Configuration for a dynamic connector."""
    url: str | None = None
    interval_seconds: int = 60
    auth_header: str | None = None
    api_key: str | None = None
    webhook_secret: str | None = None
    method: str = "GET"
    payload_template: dict[str, Any] | None = None
    mcp_endpoint: str | None = None # For MCP-like protocol support
    field_mappings: dict[str, str] = {} # {source_field: canonical_field}

class Connector(BaseModel):
    """A registered connector in the fabric."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    system_type: str
    connector_type: CaptureMethod
    config: ConnectorConfig
    is_active: bool = True
    last_run: datetime | None = None
    last_status: str = "PENDING" # SUCCESS, FAILED, PENDING
    success_rate: float = 100.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class TargetSystem(BaseModel):
    """A registered target system for propagation (sending)."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    system_type: str
    base_url: str
    auth_header: str | None = None
    config: dict[str, Any] = {} # { method, payload_template, field_mappings }
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════════════
# L2 — Event Layer
# ═══════════════════════════════════════════════════════════════

class CanonicalFieldChange(BaseModel):
    """Field change annotated with CRDT type for conflict resolution."""
    field_name: str
    field_type: FieldType = FieldType.STRING
    crdt_type: CRDTType = CRDTType.LWW_REGISTER
    old_value: Any = None
    new_value: Any = None
    source_field_name: str = ""

class EventMetadata(BaseModel):
    """Processing metadata for every canonical event."""
    connector_id: str
    capture_method: CaptureMethod
    capture_latency_ms: int = 0
    mapping_version: str = "v1.0.0"
    policy_version: str = "v1.0.0"
    resolver_version: str = "v1.0.0"
    processing_node: str = ""

class Causality(BaseModel):
    """Causal links between events."""
    caused_by: str | None = None
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)

class CanonicalEvent(BaseModel):
    """
    The fundamental data unit of UBID Fabric.
    Deterministically identifiable and replayable.
    """
    event_version: str = "1.0"
    ubid: str
    ubid_confidence: UBIDConfidence = UBIDConfidence.HIGH_CONFIDENCE
    source_system: str
    event_type: ChangeType = ChangeType.FIELD_UPDATE
    lamport_timestamp: int
    wall_clock_timestamp: datetime
    entity_type: str
    field_changes: list[CanonicalFieldChange]
    causality: Causality = Field(default_factory=Causality)
    metadata: EventMetadata

    @computed_field
    @property
    def payload_hash(self) -> str:
        canonical = json.dumps(
            [fc.model_dump() for fc in self.field_changes],
            sort_keys=True, separators=(",", ":"), default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @computed_field
    @property
    def event_id(self) -> str:
        """Deterministic event ID — same input always = same ID."""
        raw = f"{self.ubid}|{self.source_system}|{self.lamport_timestamp}|{self.payload_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════
# L3 — Identity Layer
# ═══════════════════════════════════════════════════════════════

class UBIDRecord(BaseModel):
    """A business in the UBID registry."""
    ubid: str
    business_name: str
    registered_address: str = ""
    registration_date: str | None = None
    business_type: str = ""
    system_ids: dict[str, str] = {}  # {source_system: entity_id}

class UBIDResolution(BaseModel):
    """Result of UBID resolution."""
    ubid: str
    state: UBIDConfidence
    confidence: float
    scoring_breakdown: dict[str, float] = {}
    reason: str = ""


# ═══════════════════════════════════════════════════════════════
# L4 — Control Layer
# ═══════════════════════════════════════════════════════════════

class ConflictResolution(BaseModel):
    """Result of conflict resolution."""
    conflict_id: str = Field(default_factory=lambda: f"conf-{uuid4().hex[:12]}")
    competing_event_ids: list[str]
    field: str
    ubid: str
    resolution_level: ConflictLevel
    crdt_type: CRDTType | None = None
    winning_event_id: str
    winning_value: Any
    losing_event_id: str
    losing_value: Any
    policy_version: str = "v1.0.0"
    deterministic: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)

class FieldMapping(BaseModel):
    """Field correspondence between two systems."""
    source_field: str
    target_field: str
    transform: str = "DIRECT_COPY"
    direction: str = "BIDIRECTIONAL"
    validation: dict[str, Any] = {}

class SchemaMapping(BaseModel):
    """Versioned schema mapping between systems."""
    mapping_id: str
    source_system: str
    target_system: str
    version: str
    status: MappingStatus = MappingStatus.ACTIVE
    field_mappings: list[FieldMapping]


# ═══════════════════════════════════════════════════════════════
# L5 — Execution Layer
# ═══════════════════════════════════════════════════════════════

class SagaStepResult(BaseModel):
    target_system: str
    status: str  # SUCCESS / RETRY / DLQ
    write_id: str | None = None
    error: str | None = None
    retries: int = 0

class PropagationResult(BaseModel):
    event_id: str
    steps: list[SagaStepResult]
    completed_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════════════
# L6 — Governance Layer
# ═══════════════════════════════════════════════════════════════

class EvidenceNode(BaseModel):
    node_id: UUID = Field(default_factory=uuid4)
    node_type: EvidenceNodeType
    ubid: str | None = None
    event_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: dict[str, Any] = {}

class EvidenceEdge(BaseModel):
    edge_id: UUID = Field(default_factory=uuid4)
    from_node_id: UUID
    to_node_id: UUID
    edge_type: EvidenceEdgeType
    metadata: dict[str, Any] = {}

class ReconciliationResult(BaseModel):
    ubid: str
    target_system: str
    field_name: str
    expected_value: Any
    actual_value: Any
    drift_type: DriftType | None = None
    match: bool = True
    checked_at: datetime = Field(default_factory=datetime.now)
class SagaStepResult(BaseModel):
    """Result of attempting to propagate an event to a specific target."""
    target_system: str
    status: str  # SUCCESS, DLQ, PENDING
    error: str | None = None
    retries: int = 0

class PropagationResult(BaseModel):
    """Overall result of propagating a canonical event."""
    event_id: str
    steps: list[SagaStepResult]

class DriftType(str, Enum):
    """Reason why a target system's state differs from the fabric's state."""
    STALE = "STALE"  # Missed an update (e.g., propagation failed)
    OUT_OF_BAND = "OUT_OF_BAND"  # Someone edited the target system directly
    AMBIGUOUS = "AMBIGUOUS"  # Cannot determine the cause of drift

class ReconciliationResult(BaseModel):
    """Result of checking a specific field against a target system."""
    ubid: str
    target_system: str
    field_name: str
    expected_value: Any
    actual_value: Any
    match: bool
    drift_type: DriftType | None = None
    checked_at: datetime = Field(default_factory=datetime.now)
