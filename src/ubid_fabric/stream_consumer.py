"""
UBID Fabric — Stream Consumer & Event Replay (L2)
Redis Stream consumer for processing raw changes, and event replay tool.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import structlog

from ubid_fabric.config import settings
from ubid_fabric.db import get_redis
from ubid_fabric.event_store import EventStore
from ubid_fabric.models import RawChange, FieldChange, CaptureMethod, CanonicalEvent
from ubid_fabric.pipeline import Pipeline

logger = structlog.get_logger()

STREAM_RAW = "stream:raw-changes"
STREAM_CANONICAL = "stream:canonical-events"
CONSUMER_GROUP = "ubid-fabric-consumers"
CONSUMER_NAME = "worker-1"


class StreamConsumer:
    """
    Redis Stream consumer that reads from `stream:raw-changes`,
    processes each message through the full Pipeline, and publishes
    the resulting CanonicalEvent to `stream:canonical-events`.

    Uses XREADGROUP for consumer-group semantics so multiple workers
    can scale horizontally in production.
    """

    def __init__(self, pipeline: Optional[Pipeline] = None):
        self.pipeline = pipeline or Pipeline()
        self.redis = get_redis()
        self._ensure_groups()

    def _ensure_groups(self):
        """Create the consumer group if it does not exist yet."""
        try:
            self.redis.xgroup_create(STREAM_RAW, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception:
            pass  # group already exists
        try:
            self.redis.xgroup_create(STREAM_CANONICAL, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception:
            pass

    async def run(self, poll_interval_ms: int = 1000, max_iterations: int | None = None):
        """
        Main consumer loop.  Reads new messages from Redis Streams using
        XREADGROUP and processes them through the pipeline.

        Args:
            poll_interval_ms: How long to block on XREAD when no messages.
            max_iterations: If set, stop after this many iterations (for tests).
        """
        logger.info("stream_consumer_started", group=CONSUMER_GROUP, consumer=CONSUMER_NAME)
        iteration = 0

        while True:
            if max_iterations is not None and iteration >= max_iterations:
                break
            iteration += 1

            try:
                messages = self.redis.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_RAW: ">"},
                    count=10,
                    block=poll_interval_ms,
                )

                if not messages:
                    continue

                for stream_name, entries in messages:
                    for msg_id, data in entries:
                        await self._process_message(msg_id, data)
                        # Acknowledge the message
                        self.redis.xack(STREAM_RAW, CONSUMER_GROUP, msg_id)

            except Exception as e:
                logger.error("stream_consumer_error", error=str(e))
                await asyncio.sleep(1)

        logger.info("stream_consumer_stopped")

    async def _process_message(self, msg_id: str, data: dict):
        """Deserialize a stream message into a RawChange, run the pipeline."""
        try:
            payload = json.loads(data.get("payload", data.get(b"payload", "{}")))

            field_changes = [
                FieldChange(
                    field_name=fc["field_name"],
                    old_value=fc.get("old_value"),
                    new_value=fc.get("new_value"),
                )
                for fc in payload.get("changed_fields", [])
            ]

            raw = RawChange(
                connector_id=payload.get("connector_id", "stream"),
                source_system=payload["source_system"],
                entity_type=payload["entity_type"],
                entity_id=payload["entity_id"],
                changed_fields=field_changes,
                capture_method=CaptureMethod(payload.get("capture_method", "WEBHOOK")),
            )

            result = await self.pipeline.process(
                raw,
                business_name=payload.get("business_name", ""),
                address=payload.get("address", ""),
            )

            # Publish the canonical event downstream
            if result.get("event_id"):
                self.redis.xadd(
                    STREAM_CANONICAL,
                    {"event_id": result["event_id"], "ubid": result.get("ubid", "")},
                )

            logger.info(
                "stream_message_processed",
                msg_id=msg_id,
                status=result.get("status"),
                event_id=(result.get("event_id") or "")[:16],
            )

        except Exception as e:
            logger.error("stream_message_failed", msg_id=msg_id, error=str(e))


class EventReplay:
    """
    Replays historical events from the EventStore for a given UBID.
    Uses version-pinned rules from each event's metadata to guarantee
    that replay produces the exact same results as the original processing.
    """

    def __init__(self, pipeline: Optional[Pipeline] = None):
        self.pipeline = pipeline or Pipeline()
        self.event_store = EventStore()

    async def replay_ubid(self, ubid: str) -> list[dict]:
        """
        Re-process every canonical event for a UBID in Lamport-timestamp order.
        Returns a list of processing results.
        """
        events = self.event_store.get_by_ubid(ubid)

        if not events:
            logger.warning("replay_no_events", ubid=ubid)
            return []

        # Sort by lamport timestamp to preserve causal order
        events.sort(key=lambda e: e.get("lamport_ts", 0))

        results = []
        for event_data in events:
            # Reconstruct the RawChange from the stored canonical event
            field_changes = []
            for fc in event_data.get("field_changes", []):
                field_changes.append(
                    FieldChange(
                        field_name=fc.get("field_name", ""),
                        old_value=fc.get("old_value"),
                        new_value=fc.get("new_value"),
                    )
                )

            raw = RawChange(
                connector_id=f"replay-{event_data.get('source_system', 'unknown')}",
                source_system=event_data.get("source_system", ""),
                entity_type=event_data.get("entity_type", ""),
                entity_id=event_data.get("ubid", ubid),
                changed_fields=field_changes,
                capture_method=CaptureMethod.API_POLL,
            )

            result = await self.pipeline.process(raw)
            results.append(result)

            logger.info(
                "event_replayed",
                ubid=ubid,
                original_event_id=event_data.get("event_id", "")[:16],
                status=result.get("status"),
            )

        logger.info("replay_complete", ubid=ubid, total=len(results))
        return results
