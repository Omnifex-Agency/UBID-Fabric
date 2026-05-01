"""
UBID Fabric — FastAPI Application
REST API for webhooks, review console, dashboard, and evidence graph.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ubid_fabric.config import settings
from ubid_fabric.db import close_all
from ubid_fabric.event_store import EventStore
from ubid_fabric.evidence_graph import EvidenceGraph
from ubid_fabric.models import (
    CaptureMethod, FieldChange, RawChange, UBIDRecord,
)
from ubid_fabric.pipeline import Pipeline
from ubid_fabric.ubid_resolver import UBIDResolver

logger = structlog.get_logger()

# ─── App Lifecycle ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ubid_fabric_starting", port=settings.port)
    yield
    close_all()
    logger.info("ubid_fabric_shutdown")

app = FastAPI(
    title="UBID Fabric",
    description="Deterministic Interoperability Layer for Karnataka SWS",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static frontend
import os
os.makedirs("frontend", exist_ok=True)
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")

# Singletons
pipeline = Pipeline()
event_store = EventStore()
evidence = EvidenceGraph()
resolver = UBIDResolver()


# ═══════════════════════════════════════════════════════════════
# Webhook Endpoints (L1 — Ingestion)
# ═══════════════════════════════════════════════════════════════

class WebhookPayload(BaseModel):
    source_system: str
    entity_type: str
    entity_id: str
    business_name: str = ""
    address: str = ""
    changes: list[dict]  # [{"field": "...", "old": ..., "new": ...}]
    timestamp: str | None = None


@app.post("/webhook/ingest")
async def ingest_webhook(payload: WebhookPayload):
    """
    Universal webhook endpoint. Any source system can push changes here.
    Processes through the full UBID Fabric pipeline.
    """
    field_changes = [
        FieldChange(
            field_name=c["field"],
            old_value=c.get("old"),
            new_value=c.get("new"),
        )
        for c in payload.changes
    ]

    ts = datetime.fromisoformat(payload.timestamp) if payload.timestamp else datetime.now()

    raw = RawChange(
        connector_id=f"webhook-{payload.source_system.lower()}",
        source_system=payload.source_system,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        changed_fields=field_changes,
        change_timestamp=ts,
        capture_method=CaptureMethod.WEBHOOK,
    )

    result = await pipeline.process(
        raw,
        business_name=payload.business_name,
        address=payload.address,
    )

    return {"status": "accepted", "result": result}


# ═══════════════════════════════════════════════════════════════
# UBID Registry Endpoints
# ═══════════════════════════════════════════════════════════════

class RegisterBusinessPayload(BaseModel):
    ubid: str
    business_name: str
    registered_address: str = ""
    registration_date: str | None = None
    business_type: str = ""
    system_ids: dict[str, str] = {}


@app.post("/registry/register")
async def register_business(payload: RegisterBusinessPayload):
    """Register a business in the UBID registry."""
    record = UBIDRecord(**payload.model_dump())
    resolver.register(record)
    return {"status": "registered", "ubid": payload.ubid}


@app.post("/registry/seed")
async def seed_registry():
    """Seed the registry with sample Karnataka businesses for demo."""
    sample_businesses = [
        UBIDRecord(
            ubid="UBID-KA-2024-00000001",
            business_name="Bangalore Tech Solutions Pvt Ltd",
            registered_address="42 MG Road, Bangalore 560001",
            business_type="IT_SERVICES",
            system_ids={"SWS": "SWS-001", "FACTORIES": "FAC-1001", "COMMERCIAL_TAXES": "CT-2001"},
        ),
        UBIDRecord(
            ubid="UBID-KA-2024-00000002",
            business_name="Mysore Silk Emporium",
            registered_address="15 Devaraja Urs Road, Mysore 570001",
            business_type="SHOP",
            system_ids={"SWS": "SWS-002", "SHOP_ESTABLISHMENT": "SE-3001"},
        ),
        UBIDRecord(
            ubid="UBID-KA-2024-00000003",
            business_name="Karnataka Steel Works",
            registered_address="KIADB Industrial Area, Hubli 580025",
            business_type="FACTORY",
            system_ids={"SWS": "SWS-003", "FACTORIES": "FAC-1002", "LABOUR": "LAB-4001"},
        ),
        UBIDRecord(
            ubid="UBID-KA-2024-00000004",
            business_name="Coastal Spice Traders",
            registered_address="Fish Market Road, Mangalore 575001",
            business_type="TRADING",
            system_ids={"SWS": "SWS-004", "COMMERCIAL_TAXES": "CT-2002"},
        ),
        UBIDRecord(
            ubid="UBID-KA-2024-00000005",
            business_name="Hampi Heritage Tours",
            registered_address="Main Road, Hospet 583201",
            business_type="TOURISM",
            system_ids={"SWS": "SWS-005", "SHOP_ESTABLISHMENT": "SE-3002"},
        ),
    ]
    for biz in sample_businesses:
        resolver.register(biz)

    return {"status": "seeded", "count": len(sample_businesses)}


# ═══════════════════════════════════════════════════════════════
# Event & Evidence Query Endpoints
# ═══════════════════════════════════════════════════════════════

@app.get("/events/{ubid}")
async def get_events(ubid: str):
    """Get all canonical events for a UBID."""
    events = event_store.get_by_ubid(ubid)
    return {"ubid": ubid, "count": len(events), "events": events}


@app.get("/events")
async def get_recent_events(limit: int = 20):
    """Get most recent events."""
    events = event_store.get_recent(limit)
    return {"count": len(events), "events": events}


@app.get("/evidence/{ubid}")
async def get_evidence(ubid: str):
    """Get full evidence graph for a UBID."""
    nodes = evidence.get_field_history(ubid)
    return {"ubid": ubid, "count": len(nodes), "nodes": nodes}


@app.get("/evidence/{ubid}/trace/{node_id}")
async def trace_causes(ubid: str, node_id: str):
    """Trace the causal chain leading to a specific evidence node."""
    chain = evidence.traverse_causes(node_id)
    return {"node_id": node_id, "chain_length": len(chain), "chain": chain}


@app.get("/api/evidence")
async def get_all_evidence(limit: int = 50):
    """Get most recent evidence nodes."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM evidence_nodes ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            return cur.fetchall()


@app.get("/api/dlq")
async def list_dlq(limit: int = 50):
    """List entries in the Dead Letter Queue."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dead_letter_queue ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            return cur.fetchall()


@app.post("/api/dlq/{dlq_id}/retry")
async def retry_dlq(dlq_id: int):
    """Retry a failed propagation from the DLQ."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dead_letter_queue WHERE dlq_id = %s", (dlq_id,))
            entry = cur.fetchone()
            if not entry:
                raise HTTPException(status_code=404, detail="DLQ entry not found")
            
            # Update status to RETRYING
            cur.execute("UPDATE dead_letter_queue SET status = 'RETRYING' WHERE dlq_id = %s", (dlq_id,))
            conn.commit()
            
            # In a real system, this would trigger a background task. 
            # For the prototype, we just mark it as handled.
            return {"status": "retry_initiated", "dlq_id": dlq_id}


# ═══════════════════════════════════════════════════════════════
# AI Intelligence Endpoints
# ═══════════════════════════════════════════════════════════════

class AIMappingPayload(BaseModel):
    source_sample: dict
    target_sample: dict

@app.post("/ai/suggest-mapping")
async def suggest_mapping(payload: AIMappingPayload):
    """
    Use the configured AI (Ollama/Gemini) to suggest a field mapping
    between two disparate system schemas.
    """
    from ubid_fabric.ai_service import AIService
    ai = AIService()
    suggestion = await ai.get_mapping_suggestion(
        payload.source_sample, 
        payload.target_sample
    )
    return {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "suggestion": suggestion
    }


# ═══════════════════════════════════════════════════════════════
# Dynamic Connector Management Endpoints
# ═══════════════════════════════════════════════════════════════

from ubid_fabric.models import Connector, ConnectorConfig, TargetSystem
from ubid_fabric.db import get_pg_connection

from fastapi.encoders import jsonable_encoder

@app.get("/api/connectors")
async def list_connectors():
    """List all registered connectors."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM connectors ORDER BY created_at DESC")
            return jsonable_encoder(cur.fetchall())

@app.post("/api/connectors")
async def create_connector(connector: Connector):
    """Register a new custom connector."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO connectors (id, name, system_type, connector_type, config, is_active, last_status, success_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    str(connector.id),
                    connector.name,
                    connector.system_type,
                    connector.connector_type,
                    connector.config.model_dump_json(),
                    connector.is_active,
                    connector.last_status,
                    connector.success_rate
                )
            )
            new_row = cur.fetchone()
            conn.commit()
            return new_row

@app.post("/api/connectors/test")
async def test_connector(config: ConnectorConfig):
    """Test a connector configuration by fetching sample data."""
    if not config.url:
        return {"status": "error", "message": "URL is required for testing"}
    
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            headers = {}
            if config.auth_header:
                headers["Authorization"] = config.auth_header
            
            response = await client.request(config.method, config.url, headers=headers, timeout=10.0)
            return {
                "status": "success" if response.is_success else "error",
                "status_code": response.status_code,
                "sample_data": response.json() if "application/json" in response.headers.get("content-type", "") else response.text[:500]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

@app.post("/api/connectors/auto-map")
async def auto_map_fields(payload: dict):
    """Use AI to suggest field mappings from a source sample to the canonical schema."""
    from ubid_fabric.ai_service import AIService
    ai = AIService()
    
    source_sample = payload.get("source_sample", {})
    # Canonical schema hint
    canonical_schema = {
        "business_name": "The legal name of the business entity",
        "registered_address": "The primary physical location of the business",
        "entity_id": "The system-specific identifier for the entity",
        "entity_type": "The type of business (e.g., FACTORY, SHOP, TRADING)",
        "registration_date": "When the business was officially registered",
        "owner_name": "Name of the primary proprietor or director",
        "gstin": "GST Identification Number if available"
    }
    
    suggestion = await ai.get_mapping_suggestion(source_sample, canonical_schema)
    return {"suggestion": suggestion}

@app.delete("/api/connectors/{connector_id}")
async def delete_connector(connector_id: str):
    """Remove a connector."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM connectors WHERE id = %s", (connector_id,))
            conn.commit()
            return {"status": "deleted"}

@app.patch("/api/connectors/{connector_id}/toggle")
async def toggle_connector(connector_id: str):
    """Enable or disable a connector."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE connectors SET is_active = NOT is_active WHERE id = %s RETURNING is_active",
                (connector_id,)
            )
            row = cur.fetchone()
            conn.commit()
            return {"id": connector_id, "is_active": row["is_active"]}

# --- Target Systems (Outbound) ---

@app.get("/api/targets")
async def list_targets():
    """List all registered target systems for propagation."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM target_systems ORDER BY created_at DESC")
            return jsonable_encoder(cur.fetchall())

@app.post("/api/targets")
async def create_target(target: TargetSystem):
    """Register a new target system."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            import json
            cur.execute(
                """
                INSERT INTO target_systems (id, name, system_type, base_url, auth_header, config, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    str(target.id),
                    target.name,
                    target.system_type,
                    target.base_url,
                    target.auth_header,
                    json.dumps(target.config),
                    target.is_active
                )
            )
            new_row = cur.fetchone()
            conn.commit()
            return new_row

@app.patch("/api/targets/{target_id}/toggle")
async def toggle_target(target_id: str):
    """Enable or disable a target system."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE target_systems SET is_active = NOT is_active WHERE id = %s RETURNING is_active", (target_id,))
            row = cur.fetchone()
            conn.commit()
            return {"id": target_id, "is_active": row["is_active"]}

@app.delete("/api/targets/{target_id}")
async def delete_target(target_id: str):
    """Remove a target system."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM target_systems WHERE id = %s", (target_id,))
            conn.commit()
            return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════
# Dashboard / Status Endpoints
# ═══════════════════════════════════════════════════════════════

@app.get("/status")
async def system_status():
    """System health check."""
    try:
        from ubid_fabric.db import get_redis, get_pg_connection
        # Check PostgreSQL
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 as ok")
                pg_ok = cur.fetchone()["ok"] == 1

        # Check Redis
        redis = get_redis()
        redis_ok = redis.ping()

        event_count = event_store.count()
        evidence_stats = evidence.get_stats()

        return {
            "status": "healthy" if (pg_ok and redis_ok) else "degraded",
            "components": {
                "postgresql": "up" if pg_ok else "down",
                "redis": "up" if redis_ok else "down",
            },
            "metrics": {
                "total_events": event_count,
                "evidence_nodes": evidence_stats["nodes"],
                "evidence_edges": evidence_stats["edges"],
                "lamport_clock": pipeline.clock.value,
            },
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/")
async def root():
    return {
        "name": "UBID Fabric",
        "version": "0.1.0",
        "description": "Deterministic Interoperability Layer",
        "docs": "/docs",
    }
