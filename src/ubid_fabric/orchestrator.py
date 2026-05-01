"""
UBID Fabric — Execution Layer / Saga Orchestrator (L5)
Handles propagating converged events to target systems with retries and dead-letter queues.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
import structlog

from ubid_fabric.config import settings
from ubid_fabric.db import get_pg_connection
from ubid_fabric.models import (
    CanonicalEvent, PropagationResult, SagaStepResult,
    EvidenceNode, EvidenceEdgeType, EvidenceNodeType,
)
from ubid_fabric.evidence_graph import EvidenceGraph
from ubid_fabric.target_writers import MockFactoriesWriter, MockSWSWriter, MockShopEstablishmentWriter

logger = structlog.get_logger()

class SagaOrchestrator:
    """
    Executes distributed sagas to propagate data out.
    If a target system is down, it retries up to N times before sending to DLQ.
    """

    def __init__(self, evidence_graph: EvidenceGraph):
        self.evidence = evidence_graph
        from ubid_fabric.schema_mapper import SchemaMapper
        self.mapper = SchemaMapper()
        
        # Registry of writers for different systems
        self.writers = {
            "SWS": MockSWSWriter(evidence_graph),
            "FACTORIES": MockFactoriesWriter(evidence_graph),
            "SHOP_ESTABLISHMENT": MockShopEstablishmentWriter(evidence_graph),
        }

    async def propagate(self, event: CanonicalEvent, event_node_id: str) -> PropagationResult:
        """Propagate a converged event to all subscribed target systems."""
        steps = []
        
        # Simple rule for prototype: propagate to all systems EXCEPT the source
        targets = [sys for sys in self.writers.keys() if sys != event.source_system]

        # In Python 3.11+, TaskGroup is preferred, but gather is fine
        results = await asyncio.gather(
            *[self._propagate_to_target(target, event, event_node_id) for target in targets],
            return_exceptions=True
        )

        for res in results:
            if isinstance(res, Exception):
                logger.error("saga_unhandled_exception", error=str(res))
            elif isinstance(res, SagaStepResult):
                steps.append(res)

        # Log completion
        has_errors = any(s.status == "DLQ" for s in steps)
        if has_errors:
            logger.warning("propagation_completed_with_errors", event_id=event.event_id[:16])
        else:
            logger.info("propagation_success", event_id=event.event_id[:16], targets=targets)

        return PropagationResult(
            event_id=event.event_id,
            steps=steps,
        )

    async def _propagate_to_target(
        self, target: str, event: CanonicalEvent, event_node_id: str
    ) -> SagaStepResult:
        """Attempt to push an event to a specific target system, with retries."""
        if target not in self.writers:
            logger.error("no_writer_found", target=target)
            return SagaStepResult(target_system=target, status="ERROR", error="No writer found")

        # Apply L4 Schema Mapping transformations
        payload = self.mapper.map_event_for_target(target, event)

        retries = 0
        while retries <= settings.max_saga_retries:
            try:
                # Use the dedicated writer for this system
                result = await self.writers[target].write(payload, event_node_id)
                
                if result["status"] == "SUCCESS":
                    return SagaStepResult(
                        target_system=target,
                        status="SUCCESS",
                        retries=retries,
                    )
                else:
                    raise Exception(result.get("error", "Unknown error"))

            except Exception as e:
                retries += 1
                logger.warning(
                    "saga_retry",
                    target=target,
                    event_id=event.event_id[:16],
                    attempt=retries,
                    error=str(e)
                )
                # Exponential backoff
                if retries <= settings.max_saga_retries:
                    await asyncio.sleep(2 ** retries)

        # Max retries exceeded -> Dead Letter Queue
        dlq_node = EvidenceNode(
            node_type=EvidenceNodeType.DLQ_ENTRY,
            ubid=event.ubid,
            event_id=event.event_id,
            payload={"target": target, "reason": "Max retries exceeded"}
        )
        dlq_id = self.evidence.add_node(dlq_node)
        self.evidence.link(event_node_id, dlq_id, EvidenceEdgeType.ESCALATED_TO)

        self._write_to_dlq(event.event_id, event.ubid, target)
        
        return SagaStepResult(
            target_system=target,
            status="DLQ",
            error="Max retries exceeded",
            retries=retries - 1,
        )

    def _write_to_dlq(self, event_id: str, ubid: str, target: str):
        """Write failed propagation task to the Dead Letter Queue in PostgreSQL."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dead_letter_queue (event_id, ubid, target_system, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (event_id, ubid, target, 'PENDING')
                )
                conn.commit()

    async def compensate(self, event: CanonicalEvent, event_node_id: str) -> PropagationResult:
        """
        Reverse a previously propagated event by sending the old values back.
        Used when a manual review rejects an auto-merged conflict or UBID resolution.
        """
        steps = []
        targets = [sys for sys in TARGET_SYSTEM_WEBHOOKS.keys() if sys != event.source_system]

        logger.info("compensating_event", event_id=event.event_id[:16], ubid=event.ubid)

        # Build payload with old values to reverse the change
        payload = {
            "ubid": event.ubid,
            "event_id": f"comp-{event.event_id}",
            "is_compensation": True,
            "lamport_timestamp": event.lamport_timestamp + 1,
            "changes": [
                {"field": fc.field_name, "value": fc.old_value}
                for fc in event.field_changes
            ]
        }

        async def _compensate_target(target: str) -> SagaStepResult:
            webhook_url = TARGET_SYSTEM_WEBHOOKS[target]
            try:
                comp_node = EvidenceNode(
                    node_type=EvidenceNodeType.MANUAL_DECISION,
                    ubid=event.ubid,
                    event_id=event.event_id,
                    payload={"target": target, "action": "COMPENSATE_WRITE"}
                )
                comp_id = self.evidence.add_node(comp_node)
                self.evidence.link(event_node_id, comp_id, EvidenceEdgeType.CAUSED_BY)

                async with httpx.AsyncClient() as client:
                    resp = await client.post(webhook_url, json=payload, timeout=5.0)
                    resp.raise_for_status()

                return SagaStepResult(target_system=target, status="COMPENSATED", retries=0)
            except Exception as e:
                logger.error("compensation_failed", target=target, error=str(e))
                self._write_to_dlq(f"comp-{event.event_id}", event.ubid, target)
                return SagaStepResult(target_system=target, status="DLQ", error=str(e), retries=0)

        results = await asyncio.gather(*[_compensate_target(t) for t in targets], return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                logger.error("compensation_unhandled_exception", error=str(res))
            elif isinstance(res, SagaStepResult):
                steps.append(res)

        return PropagationResult(event_id=event.event_id, steps=steps)

    async def replay(self, event: CanonicalEvent, event_node_id: str) -> PropagationResult:
        """
        Re-inject a corrected event into the pipeline and re-propagate.
        Used after a manual review resolves a quarantined UBID or after
        a schema mapping is updated.

        Flow: Compensate old writes → Re-propagate with corrected data.
        """
        logger.info("replay_saga_start", event_id=event.event_id[:16], ubid=event.ubid)

        # Step 1: Compensate the old writes first
        comp_result = await self.compensate(event, event_node_id)
        comp_failures = [s for s in comp_result.steps if s.status == "DLQ"]

        if comp_failures:
            logger.warning(
                "replay_compensation_partial",
                event_id=event.event_id[:16],
                failed_targets=[f.target_system for f in comp_failures],
            )

        # Step 2: Re-propagate the corrected event
        prop_result = await self.propagate(event, event_node_id)

        # Record replay evidence
        replay_node = EvidenceNode(
            node_type=EvidenceNodeType.MANUAL_DECISION,
            ubid=event.ubid,
            event_id=event.event_id,
            payload={
                "action": "REPLAY",
                "compensation_steps": len(comp_result.steps),
                "propagation_steps": len(prop_result.steps),
            }
        )
        replay_id = self.evidence.add_node(replay_node)
        self.evidence.link(event_node_id, replay_id, EvidenceEdgeType.CAUSED_BY)

        # Merge all steps
        all_steps = comp_result.steps + prop_result.steps
        return PropagationResult(event_id=event.event_id, steps=all_steps)
