"""
UBID Fabric — Pipeline Orchestrator
Wires all layers together: Ingest → Event → Identity → Conflict → Execute → Audit.
"""

from __future__ import annotations

from datetime import datetime

import structlog

from ubid_fabric.models import (
    RawChange, CanonicalEvent, EvidenceNode, EvidenceEdgeType,
    EvidenceNodeType, UBIDConfidence,
)
from ubid_fabric.lamport import LamportClock
from ubid_fabric.event_builder import EventBuilder
from ubid_fabric.event_store import EventStore
from ubid_fabric.ubid_resolver import UBIDResolver
from ubid_fabric.conflict_engine import ConflictEngine
from ubid_fabric.idempotency import IdempotencyStore
from ubid_fabric.evidence_graph import EvidenceGraph
from ubid_fabric.orchestrator import SagaOrchestrator

logger = structlog.get_logger()


class Pipeline:
    """
    The full UBID Fabric processing pipeline.
    Takes a RawChange from any connector and processes it
    through all 6 layers.
    """

    def __init__(self):
        self.clock = LamportClock()
        self.event_builder = EventBuilder(self.clock)
        self.event_store = EventStore()
        self.ubid_resolver = UBIDResolver()
        self.conflict_engine = ConflictEngine()
        self.idempotency = IdempotencyStore()
        self.evidence = EvidenceGraph()
        self.orchestrator = SagaOrchestrator(self.evidence)

    async def process(self, raw: RawChange, business_name: str = "",
                address: str = "") -> dict:
        """
        Process a single RawChange through the full pipeline.
        Returns processing result summary.
        """
        result = {
            "status": "pending",
            "event_id": None,
            "ubid": None,
            "ubid_confidence": None,
            "conflicts": [],
            "evidence_nodes": [],
        }

        try:
            # ─── L3: UBID Resolution ────────────────────────
            resolution = self.ubid_resolver.resolve(
                entity_id=raw.entity_id,
                source_system=raw.source_system,
                business_name=business_name,
                address=address,
            )

            result["ubid"] = resolution.ubid
            result["ubid_confidence"] = resolution.state.value

            if resolution.state == UBIDConfidence.QUARANTINE:
                logger.warning("pipeline_quarantine", entity_id=raw.entity_id)
                result["status"] = "quarantined"
                # Record quarantine in evidence graph
                qnode = EvidenceNode(
                    node_type=EvidenceNodeType.UBID_RESOLUTION,
                    ubid=resolution.ubid or raw.entity_id,
                    payload={
                        "action": "QUARANTINE",
                        "confidence": resolution.confidence,
                        "reason": resolution.reason,
                        "entity_id": raw.entity_id,
                        "source_system": raw.source_system,
                    },
                )
                self.evidence.add_node(qnode)
                return result

            # ─── L2: Build Canonical Event ───────────────────
            event = self.event_builder.build(
                raw=raw,
                ubid=resolution.ubid,
                ubid_confidence=resolution.state,
            )

            # ─── L5: Idempotency Check ──────────────────────
            if not self.idempotency.try_claim(event.event_id):
                result["status"] = "duplicate"
                result["event_id"] = event.event_id
                return result

            # ─── L2: Store Event ─────────────────────────────
            self.event_store.append(event)
            result["event_id"] = event.event_id

            # Record canonical event in evidence graph
            event_node = EvidenceNode(
                node_type=EvidenceNodeType.CANONICAL_EVENT,
                ubid=event.ubid,
                event_id=event.event_id,
                payload={
                    "source": event.source_system,
                    "type": event.event_type.value,
                    "lamport_ts": event.lamport_timestamp,
                    "fields": [fc.field_name for fc in event.field_changes],
                },
            )
            event_node_id = self.evidence.add_node(event_node)
            result["evidence_nodes"].append(str(event_node_id))

            # ─── L3: Record UBID resolution ──────────────────
            res_node = EvidenceNode(
                node_type=EvidenceNodeType.UBID_RESOLUTION,
                ubid=event.ubid,
                event_id=event.event_id,
                payload={
                    "confidence": resolution.confidence,
                    "state": resolution.state.value,
                    "reason": resolution.reason,
                },
            )
            res_node_id = self.evidence.add_node(res_node)
            self.evidence.link(event_node_id, res_node_id, EvidenceEdgeType.CAUSED_BY)

            # ─── L4: Conflict Detection ──────────────────────
            for field in event.field_changes:
                conflict = self.conflict_engine.check_and_resolve(event, field)
                if conflict:
                    result["conflicts"].append({
                        "field": conflict.field,
                        "level": conflict.resolution_level.value,
                        "winner": conflict.winning_value,
                        "loser": conflict.losing_value,
                    })

                    conf_node = EvidenceNode(
                        node_type=EvidenceNodeType.CONFLICT_RESOLUTION,
                        ubid=event.ubid,
                        event_id=event.event_id,
                        payload={
                            "field": conflict.field,
                            "level": conflict.resolution_level.value,
                            "winning_value": str(conflict.winning_value),
                            "losing_value": str(conflict.losing_value),
                        },
                    )
                    conf_node_id = self.evidence.add_node(conf_node)
                    self.evidence.link(event_node_id, conf_node_id, EvidenceEdgeType.RESOLVED_BY)

            # ─── L5: Propagate to Target Systems ─────────────
            try:
                prop_result = await self.orchestrator.propagate(event, str(event_node_id))
                result["propagation"] = [
                    {"target": s.target_system, "status": s.status}
                    for s in prop_result.steps
                ]
            except Exception as prop_err:
                logger.warning("propagation_skipped", error=str(prop_err))
                result["propagation"] = []

            # ─── L5: Mark Processed ──────────────────────────
            self.idempotency.mark_processed(event.event_id, "pipeline_complete")
            result["status"] = "processed"

            logger.info(
                "pipeline_complete",
                event_id=event.event_id[:16],
                ubid=event.ubid,
                conflicts=len(result["conflicts"]),
                propagations=len(result.get("propagation", [])),
            )

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error("pipeline_error", error=str(e), entity_id=raw.entity_id)

        return result
