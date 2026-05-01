"""
UBID Fabric — Immutable Event Store (L2)
Append-only storage for canonical events in PostgreSQL.
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog

from ubid_fabric.db import get_pg_connection
from ubid_fabric.models import CanonicalEvent

logger = structlog.get_logger()


class EventStore:
    """
    Immutable, append-only event store backed by PostgreSQL.

    Guarantees:
      - Events are never updated or deleted
      - Events are queryable by event_id, ubid, source_system
      - Ordered by lamport_timestamp within a UBID
    """

    def append(self, event: CanonicalEvent) -> str:
        """
        Store a canonical event. Returns the event_id.
        Silently ignores duplicates (idempotent insert).
        """
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO canonical_events
                        (event_id, event_version, ubid, ubid_confidence,
                         source_system, event_type, lamport_ts, wall_clock_ts,
                         entity_type, field_changes, payload_hash, causality, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event.event_id,
                        event.event_version,
                        event.ubid,
                        event.ubid_confidence.value,
                        event.source_system,
                        event.event_type.value,
                        event.lamport_timestamp,
                        event.wall_clock_timestamp,
                        event.entity_type,
                        json.dumps([fc.model_dump() for fc in event.field_changes], default=str),
                        event.payload_hash,
                        json.dumps(event.causality.model_dump(), default=str),
                        json.dumps(event.metadata.model_dump(), default=str),
                    ),
                )
                conn.commit()

        logger.info("event_stored", event_id=event.event_id[:16], ubid=event.ubid)
        return event.event_id

    def get_by_id(self, event_id: str) -> dict | None:
        """Retrieve a single event by its deterministic ID."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM canonical_events WHERE event_id = %s",
                    (event_id,),
                )
                return cur.fetchone()

    def get_by_ubid(self, ubid: str, since_lamport: int = 0) -> list[dict]:
        """Get all events for a UBID, ordered by Lamport timestamp."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM canonical_events
                    WHERE ubid = %s AND lamport_ts >= %s
                    ORDER BY lamport_ts ASC
                    """,
                    (ubid, since_lamport),
                )
                return cur.fetchall()

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Get most recent events across all UBIDs."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM canonical_events ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                return cur.fetchall()

    def count(self) -> int:
        """Total number of events in the store."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM canonical_events")
                row = cur.fetchone()
                return row["cnt"] if row else 0
