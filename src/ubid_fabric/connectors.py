"""
UBID Fabric — Source Connector Framework
Provides the base class for integrating external systems (API Poll, Webhooks, CDC).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx
import structlog

from ubid_fabric.models import CaptureMethod, FieldChange, RawChange
from ubid_fabric.config import settings

logger = structlog.get_logger()


class SourceConnector(ABC):
    """
    Abstract base connector for all source systems.
    Translates source-specific data to standard RawChange.
    """

    def __init__(self, connector_id: str, source_system: str, capture_method: CaptureMethod):
        self.connector_id = connector_id
        self.source_system = source_system
        self.capture_method = capture_method
        self.is_running = False

    @abstractmethod
    async def run(self):
        """Starts the connector (polling loop or webhook registration)."""
        pass

    async def emit(self, raw_change: RawChange) -> bool:
        """
        Pushes a translated RawChange to the UBID Fabric pipeline.
        In the local prototype, this posts directly to the FastAPI webhook endpoint.
        In production, this would push to Kafka/Redis Streams.
        """
        url = f"http://localhost:{settings.port}/webhook/ingest"
        
        # Flatten the payload for the webhook endpoint
        payload = {
            "source_system": raw_change.source_system,
            "entity_type": raw_change.entity_type,
            "entity_id": raw_change.entity_id,
            "changes": [
                {"field": fc.field_name, "old": fc.old_value, "new": fc.new_value}
                for fc in raw_change.changed_fields
            ],
            "timestamp": raw_change.change_timestamp.isoformat(),
        }

        # Try to infer business_name and address if they exist in changes (for UBID resolution)
        for fc in raw_change.changed_fields:
            if fc.field_name == "business_name":
                payload["business_name"] = fc.new_value
            elif fc.field_name == "registered_address":
                payload["address"] = fc.new_value

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=5.0)
                response.raise_for_status()
                logger.debug(
                    "connector_emit_success",
                    connector_id=self.connector_id,
                    entity=raw_change.entity_id,
                )
                return True
        except Exception as e:
            logger.error(
                "connector_emit_failed",
                connector_id=self.connector_id,
                entity=raw_change.entity_id,
                error=str(e),
            )
            return False


class MockSWSConnector(SourceConnector):
    """
    Mock connector for the Single Window System (SWS).
    Simulates polling an API for new registrations.
    """

    def __init__(self):
        super().__init__(
            connector_id="sws-poller-01",
            source_system="SWS",
            capture_method=CaptureMethod.API_POLL,
        )

    async def run(self):
        self.is_running = True
        logger.info("sws_connector_started")
        
        # Simulating fetching new registrations
        changes = [
            RawChange(
                connector_id=self.connector_id,
                source_system=self.source_system,
                entity_type="business",
                entity_id="SWS-001",  # Matches seeded UBID-KA-2024-00000001
                changed_fields=[
                    FieldChange(field_name="business_name", old_value=None, new_value="Bangalore Tech Solutions Pvt Ltd"),
                    FieldChange(field_name="registered_address", old_value=None, new_value="42 MG Road, Bangalore 560001"),
                    FieldChange(field_name="employee_count", old_value=None, new_value=50),
                ],
                change_timestamp=datetime.now(),
                capture_method=self.capture_method,
            )
        ]

        for change in changes:
            await self.emit(change)
            await asyncio.sleep(0.5)


class MockFactoriesConnector(SourceConnector):
    """
    Mock connector for the Department of Factories.
    Simulates receiving webhook events.
    """

    def __init__(self):
        super().__init__(
            connector_id="factories-webhook-01",
            source_system="FACTORIES",
            capture_method=CaptureMethod.WEBHOOK,
        )

    async def run(self):
        self.is_running = True
        logger.info("factories_connector_started")
        
        # Simulating an update from Factories for the same business
        # E.g., they inspected and found 55 employees instead of 50
        changes = [
            RawChange(
                connector_id=self.connector_id,
                source_system=self.source_system,
                entity_type="factory",
                entity_id="FAC-1001",  # Matches seeded UBID-KA-2024-00000001
                changed_fields=[
                    FieldChange(field_name="employee_count", old_value=50, new_value=55),
                    FieldChange(field_name="licence_status", old_value="PENDING", new_value="ACTIVE"),
                ],
                change_timestamp=datetime.now(),
                capture_method=self.capture_method,
            )
        ]

        for change in changes:
            await self.emit(change)
            await asyncio.sleep(0.5)
