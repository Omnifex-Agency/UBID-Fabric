"""
UBID Fabric — Canonical Event Builder (L2)
Converts RawChange → CanonicalEvent with deterministic ID.
"""

from __future__ import annotations

from datetime import datetime

import structlog

from ubid_fabric.lamport import LamportClock
from ubid_fabric.models import (
    CanonicalEvent, CanonicalFieldChange, CaptureMethod, CRDTType,
    ChangeType, EventMetadata, Causality, FieldType, RawChange,
    UBIDConfidence,
)

logger = structlog.get_logger()

# ─── Field → CRDT Type Mapping ──────────────────────────────
# Determines which CRDT strategy is used for each field.

FIELD_CRDT_MAP: dict[str, CRDTType] = {
    "registered_address": CRDTType.LWW_REGISTER,
    "business_name": CRDTType.LWW_REGISTER,
    "establishment_date": CRDTType.LWW_REGISTER,
    "licence_status": CRDTType.LWW_REGISTER,
    "licence_expiry": CRDTType.LWW_REGISTER,
    "authorised_signatories": CRDTType.OR_SET,
    "business_activities": CRDTType.OR_SET,
    "employee_count": CRDTType.MONOTONIC_COUNTER,
    "last_inspection_date": CRDTType.MONOTONIC_COUNTER,
}

FIELD_TYPE_MAP: dict[str, FieldType] = {
    "registered_address": FieldType.STRING,
    "business_name": FieldType.STRING,
    "establishment_date": FieldType.DATE,
    "licence_status": FieldType.STRING,
    "authorised_signatories": FieldType.SET,
    "employee_count": FieldType.INTEGER,
    "last_inspection_date": FieldType.DATE,
}


class EventBuilder:
    """
    Builds canonical events from raw changes.

    Responsibilities:
      - Assign Lamport timestamp
      - Determine CRDT type per field
      - Generate deterministic event_id
      - Pin version numbers
    """

    def __init__(self, clock: LamportClock):
        self.clock = clock

    def build(
        self,
        raw: RawChange,
        ubid: str,
        ubid_confidence: UBIDConfidence = UBIDConfidence.HIGH_CONFIDENCE,
        caused_by: str | None = None,
    ) -> CanonicalEvent:
        """Convert a RawChange to a CanonicalEvent."""

        # Assign Lamport timestamp
        lamport_ts = self.clock.tick()

        # Build field changes with CRDT annotations
        field_changes = []
        for fc in raw.changed_fields:
            crdt_type = FIELD_CRDT_MAP.get(fc.field_name, CRDTType.LWW_REGISTER)
            field_type = FIELD_TYPE_MAP.get(fc.field_name, FieldType.STRING)

            field_changes.append(CanonicalFieldChange(
                field_name=fc.field_name,
                field_type=field_type,
                crdt_type=crdt_type,
                old_value=fc.old_value,
                new_value=fc.new_value,
                source_field_name=fc.field_name,
            ))

        # Determine change type
        change_type = ChangeType.FIELD_UPDATE
        if all(fc.old_value is None for fc in raw.changed_fields):
            change_type = ChangeType.ENTITY_CREATE

        # Calculate capture latency
        latency_ms = int(
            (raw.capture_timestamp - raw.change_timestamp).total_seconds() * 1000
        )

        event = CanonicalEvent(
            ubid=ubid,
            ubid_confidence=ubid_confidence,
            source_system=raw.source_system,
            event_type=change_type,
            lamport_timestamp=lamport_ts,
            wall_clock_timestamp=raw.change_timestamp,
            entity_type=raw.entity_type,
            field_changes=field_changes,
            causality=Causality(caused_by=caused_by),
            metadata=EventMetadata(
                connector_id=raw.connector_id,
                capture_method=raw.capture_method,
                capture_latency_ms=max(0, latency_ms),
            ),
        )

        logger.info(
            "event_built",
            event_id=event.event_id[:16],
            ubid=ubid,
            source=raw.source_system,
            lamport_ts=lamport_ts,
            fields=len(field_changes),
        )

        return event
