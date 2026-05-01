"""
UBID Fabric — Conflict Convergence Engine (L4)
4-level resolution ladder: CRDT → Source Priority → Domain Ownership → Manual Review.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ubid_fabric.crdt import lww_register_merge, monotonic_merge, or_set_merge
from ubid_fabric.db import get_redis
from ubid_fabric.config import settings
from ubid_fabric.models import (
    CanonicalEvent, CanonicalFieldChange, ConflictLevel, ConflictResolution, CRDTType,
)

logger = structlog.get_logger()

# ─── Policy Configs (would be loaded from DB/file in production) ───

SOURCE_PRIORITY: dict[str, list[str]] = {
    "registered_address": ["SWS", "COMMERCIAL_TAXES", "FACTORIES", "SHOP_ESTABLISHMENT"],
    "business_name": ["SWS", "COMMERCIAL_TAXES", "FACTORIES"],
    "establishment_date": ["SWS", "FACTORIES"],
    "licence_status": ["ISSUING_DEPARTMENT", "SWS"],
}

DOMAIN_OWNERSHIP: dict[str, str] = {
    "factory_licence_number": "FACTORIES",
    "factory_licence_status": "FACTORIES",
    "shop_establishment_number": "SHOP_ESTABLISHMENT",
    "shop_establishment_status": "SHOP_ESTABLISHMENT",
}


class ConflictEngine:
    """
    Detects and resolves conflicts when concurrent events target
    the same UBID + field within the conflict window.

    4-Level Resolution Ladder:
      L1: CRDT deterministic merge (LWW, OR-Set, Monotonic)
      L2: Source Priority policy
      L3: Domain Ownership policy
      L4: Manual Review escalation
    """

    def __init__(self, window_seconds: int | None = None):
        self.window = window_seconds or settings.conflict_window_seconds

    def check_and_resolve(
        self, event: CanonicalEvent, field: CanonicalFieldChange
    ) -> ConflictResolution | None:
        """
        Check if there's a conflicting in-flight event for this UBID+field.
        If conflict found, resolve it. Returns None if no conflict.
        """
        redis = get_redis()
        conflict_key = f"conflict:{event.ubid}:{field.field_name}"

        # Check for in-flight event within conflict window
        existing_raw = redis.get(conflict_key)

        if existing_raw is None:
            # No conflict — register this event in the window
            redis.setex(
                conflict_key,
                self.window,
                json.dumps({
                    "event_id": event.event_id,
                    "source_system": event.source_system,
                    "lamport_ts": event.lamport_timestamp,
                    "value": field.new_value,
                    "crdt_type": field.crdt_type.value,
                }, default=str),
            )
            return None

        # CONFLICT DETECTED
        existing = json.loads(existing_raw)
        logger.warning(
            "conflict_detected",
            ubid=event.ubid,
            field=field.field_name,
            event_a=existing["event_id"][:16],
            event_b=event.event_id[:16],
        )

        return self._resolve(event, field, existing)

    def _resolve(
        self, event_b: CanonicalEvent, field_b: CanonicalFieldChange, existing: dict
    ) -> ConflictResolution:
        """Apply 4-level resolution ladder."""

        event_a_id = existing["event_id"]
        source_a = existing["source_system"]
        lamport_a = existing["lamport_ts"]
        value_a = existing["value"]
        crdt_type = CRDTType(existing["crdt_type"])

        # ─── Level 1: CRDT Resolution ────────────────────────
        if crdt_type == CRDTType.LWW_REGISTER:
            winner_value, winner_source = lww_register_merge(
                value_a, lamport_a, source_a,
                field_b.new_value, event_b.lamport_timestamp, event_b.source_system,
            )
            winning_id = event_a_id if winner_source == source_a else event_b.event_id
            losing_id = event_b.event_id if winner_source == source_a else event_a_id
            losing_value = field_b.new_value if winner_source == source_a else value_a

            # Check if L2 source priority should override
            l2_winner = self._check_source_priority(
                field_b.field_name, source_a, event_b.source_system
            )
            if l2_winner and l2_winner != winner_source:
                # Source priority overrides CRDT
                logger.info("l2_override", field=field_b.field_name, l1_winner=winner_source, l2_winner=l2_winner)
                override_value = value_a if l2_winner == source_a else field_b.new_value
                override_losing = field_b.new_value if l2_winner == source_a else value_a
                return ConflictResolution(
                    competing_event_ids=[event_a_id, event_b.event_id],
                    field=field_b.field_name,
                    ubid=event_b.ubid,
                    resolution_level=ConflictLevel.LEVEL_2_SOURCE_PRIORITY,
                    crdt_type=crdt_type,
                    winning_event_id=event_a_id if l2_winner == source_a else event_b.event_id,
                    winning_value=override_value,
                    losing_event_id=event_b.event_id if l2_winner == source_a else event_a_id,
                    losing_value=override_losing,
                )

            return ConflictResolution(
                competing_event_ids=[event_a_id, event_b.event_id],
                field=field_b.field_name,
                ubid=event_b.ubid,
                resolution_level=ConflictLevel.LEVEL_1_CRDT,
                crdt_type=crdt_type,
                winning_event_id=winning_id,
                winning_value=winner_value,
                losing_event_id=losing_id,
                losing_value=losing_value,
            )

        elif crdt_type == CRDTType.MONOTONIC_COUNTER:
            merged = monotonic_merge(value_a, field_b.new_value)
            winning_id = event_a_id if merged == value_a else event_b.event_id
            return ConflictResolution(
                competing_event_ids=[event_a_id, event_b.event_id],
                field=field_b.field_name,
                ubid=event_b.ubid,
                resolution_level=ConflictLevel.LEVEL_1_CRDT,
                crdt_type=crdt_type,
                winning_event_id=winning_id,
                winning_value=merged,
                losing_event_id=event_b.event_id if merged == value_a else event_a_id,
                losing_value=field_b.new_value if merged == value_a else value_a,
            )

        # ─── Level 3: Domain Ownership ───────────────────────
        domain_owner = DOMAIN_OWNERSHIP.get(field_b.field_name)
        if domain_owner:
            winner_source = domain_owner
            winner_value = value_a if source_a == domain_owner else field_b.new_value
            return ConflictResolution(
                competing_event_ids=[event_a_id, event_b.event_id],
                field=field_b.field_name,
                ubid=event_b.ubid,
                resolution_level=ConflictLevel.LEVEL_3_DOMAIN_OWNERSHIP,
                winning_event_id=event_a_id if source_a == domain_owner else event_b.event_id,
                winning_value=winner_value,
                losing_event_id=event_b.event_id if source_a == domain_owner else event_a_id,
                losing_value=field_b.new_value if source_a == domain_owner else value_a,
            )

        # ─── Level 4: Manual Review ──────────────────────────
        logger.warning(
            "conflict_escalated_l4",
            ubid=event_b.ubid,
            field=field_b.field_name,
        )
        return ConflictResolution(
            competing_event_ids=[event_a_id, event_b.event_id],
            field=field_b.field_name,
            ubid=event_b.ubid,
            resolution_level=ConflictLevel.LEVEL_4_MANUAL_REVIEW,
            winning_event_id="",
            winning_value=None,
            losing_event_id="",
            losing_value=None,
            deterministic=False,
        )

    def _check_source_priority(
        self, field_name: str, source_a: str, source_b: str
    ) -> str | None:
        """Check source priority policy. Returns winning source or None."""
        priority_list = SOURCE_PRIORITY.get(field_name)
        if not priority_list:
            return None

        rank_a = priority_list.index(source_a) if source_a in priority_list else 999
        rank_b = priority_list.index(source_b) if source_b in priority_list else 999

        if rank_a < rank_b:
            return source_a
        elif rank_b < rank_a:
            return source_b
        return None  # Same rank — no override
