"""
UBID Fabric — Target System Writers (L5)
Generic async HTTP writers that push schema-mapped payloads to external department APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import httpx
import structlog

from ubid_fabric.evidence_graph import EvidenceGraph
from ubid_fabric.models import (
    EvidenceNode, EvidenceEdgeType, EvidenceNodeType,
)

logger = structlog.get_logger()


class TargetWriter(ABC):
    """
    Abstract base for all target system writers.
    Each writer knows how to push a schema-mapped payload to one external API.
    """

    def __init__(self, system_name: str, base_url: str, evidence: EvidenceGraph):
        self.system_name = system_name
        self.base_url = base_url
        self.evidence = evidence

    async def write(self, payload: Dict[str, Any], event_node_id: str) -> Dict[str, Any]:
        """
        Push the payload to the target system and record the result in the
        evidence graph regardless of success or failure.
        """
        try:
            result = await self._do_write(payload)

            # Record success in evidence graph
            node = EvidenceNode(
                node_type=EvidenceNodeType.WRITE_CONFIRMATION,
                ubid=payload.get("ubid", ""),
                event_id=payload.get("event_id", ""),
                payload={
                    "target": self.system_name,
                    "status": "SUCCESS",
                    "response": result,
                },
            )
            node_id = self.evidence.add_node(node)
            self.evidence.link(event_node_id, node_id, EvidenceEdgeType.RESOLVED_BY)

            logger.info(
                "target_write_success",
                target=self.system_name,
                ubid=payload.get("ubid"),
            )
            return {"status": "SUCCESS", "target": self.system_name, "response": result}

        except Exception as e:
            # Record failure in evidence graph
            node = EvidenceNode(
                node_type=EvidenceNodeType.PROPAGATION_WRITE,
                ubid=payload.get("ubid", ""),
                event_id=payload.get("event_id", ""),
                payload={
                    "target": self.system_name,
                    "status": "FAILED",
                    "error": str(e),
                },
            )
            node_id = self.evidence.add_node(node)
            self.evidence.link(event_node_id, node_id, EvidenceEdgeType.ESCALATED_TO)

            logger.error(
                "target_write_failed",
                target=self.system_name,
                error=str(e),
            )
            return {"status": "FAILED", "target": self.system_name, "error": str(e)}

    @abstractmethod
    async def _do_write(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Subclasses implement the actual HTTP call here."""
        ...


class MockFactoriesWriter(TargetWriter):
    """
    Writes to the Karnataka Factories Department mock API.
    In production, this would hit the real Factories REST endpoint.
    """

    def __init__(self, evidence: EvidenceGraph):
        super().__init__(
            system_name="FACTORIES",
            base_url="http://localhost:8001/mock-factories",
            evidence=evidence,
        )

    async def _do_write(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/webhook",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()


class MockSWSWriter(TargetWriter):
    """
    Writes to the SWS (State-Wide System) mock API.
    """

    def __init__(self, evidence: EvidenceGraph):
        super().__init__(
            system_name="SWS",
            base_url="http://localhost:8001/mock-sws",
            evidence=evidence,
        )

    async def _do_write(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/webhook",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()


class MockShopEstablishmentWriter(TargetWriter):
    """
    Writes to the Shop & Establishment Department mock API.
    """

    def __init__(self, evidence: EvidenceGraph):
        super().__init__(
            system_name="SHOP_ESTABLISHMENT",
            base_url="http://localhost:8001/mock-shop-estb",
            evidence=evidence,
        )

    async def _do_write(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/webhook",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()
