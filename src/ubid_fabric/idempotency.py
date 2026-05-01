"""
UBID Fabric — Idempotency Store (L5)
Guarantees exactly-once processing via Redis SET NX.
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog

from ubid_fabric.db import get_redis
from ubid_fabric.config import settings

logger = structlog.get_logger()


class IdempotencyStore:
    """
    Atomic check-and-claim using Redis SET NX.
    Prevents duplicate processing of the same event.
    """

    def try_claim(self, event_id: str, node_id: str = "local") -> bool:
        """
        Attempt to claim an event for processing.
        Returns True if claimed (new event), False if already processed.
        """
        redis = get_redis()
        claimed = redis.set(
            f"idem:{event_id}",
            json.dumps({
                "status": "IN_PROGRESS",
                "claimed_at": datetime.now().isoformat(),
                "node": node_id,
            }),
            nx=True,  # Only set if key does not exist
            ex=86400,  # 24h safety TTL for IN_PROGRESS
        )

        if not claimed:
            existing = redis.get(f"idem:{event_id}")
            if existing:
                data = json.loads(existing)
                logger.debug("idempotent_skip", event_id=event_id[:16], status=data["status"])
            return False

        logger.debug("idempotent_claimed", event_id=event_id[:16])
        return True

    def mark_processed(self, event_id: str, result_summary: str = "") -> None:
        """Mark event as successfully processed."""
        redis = get_redis()
        redis.set(
            f"idem:{event_id}",
            json.dumps({
                "status": "PROCESSED",
                "processed_at": datetime.now().isoformat(),
                "result": result_summary,
            }),
            ex=settings.idempotency_ttl_seconds,  # 7-day TTL
        )
        logger.debug("idempotent_processed", event_id=event_id[:16])

    def release_claim(self, event_id: str) -> None:
        """Release claim on failure (allows retry)."""
        redis = get_redis()
        redis.delete(f"idem:{event_id}")
        logger.debug("idempotent_released", event_id=event_id[:16])

    def is_processed(self, event_id: str) -> bool:
        """Check if an event was already processed."""
        redis = get_redis()
        raw = redis.get(f"idem:{event_id}")
        if raw:
            data = json.loads(raw)
            return data.get("status") == "PROCESSED"
        return False
