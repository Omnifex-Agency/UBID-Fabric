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
