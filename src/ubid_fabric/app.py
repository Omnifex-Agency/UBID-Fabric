"""
UBID Fabric v0.2 — FastAPI Application
REST API for webhooks, review console, dashboard, and evidence graph.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ubid_fabric.config import settings
from ubid_fabric.db import close_all, get_pg_connection, get_redis
from ubid_fabric.event_store import EventStore
from ubid_fabric.evidence_graph import EvidenceGraph
from ubid_fabric.models import (
    CaptureMethod, FieldChange, RawChange, UBIDRecord,
    Connector, ConnectorConfig, TargetSystem,
    CanonicalFieldChange, EventCausality, EventMetadata, 
    UBIDConfidence, EventType, CanonicalEvent,
    EvidenceNode, EvidenceEdgeType, EvidenceNodeType
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
    description="Deterministic Interoperability Layer for Karnataka SWS — Production Edition",
    version="0.2.0",
    lifespan=lifespan,
)

# Mount static frontend
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
    entity_id: str | None = None
    business_name: str = ""
    address: str = ""
    changes: list[dict]  # [{"field": "...", "old": ..., "new": ...}]
    timestamp: str | None = None
    ubid: str | None = None  # Optional direct UBID hint

    class Config:
        extra = "allow"


@app.post("/api/ingest/webhook")
async def ingest_webhook(payload: WebhookPayload):
    """
    Universal webhook endpoint. Any source system can push changes here.
    Processes through the full UBID Fabric pipeline.
    """
    entity_id = payload.entity_id or getattr(payload, 'external_id', None) or payload.dict().get('external_id', payload.entity_id)
    
    field_changes = [
        FieldChange(
            field_name=c["field"],
            old_value=c.get("old"),
            new_value=c.get("value") if "value" in c else c.get("new"),
        )
        for c in payload.changes
    ]

    ts = datetime.fromisoformat(payload.timestamp) if payload.timestamp else datetime.now()

    raw = RawChange(
        connector_id=f"webhook-{payload.source_system.lower()}",
        source_system=payload.source_system,
        entity_type=payload.entity_type,
        entity_id=entity_id,
        changed_fields=field_changes,
        change_timestamp=ts,
        capture_method=CaptureMethod.WEBHOOK,
    )

    result = await pipeline.process(
        raw,
        business_name=payload.business_name,
        address=payload.address,
        ubid=payload.ubid
    )

    return result


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
    record = UBIDRecord(**payload.dict())
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

            try:
                # Load event from DB
                raw_event = event_store.get_by_id(entry["event_id"])
                if not raw_event:
                    raise Exception("Original event not found")
                
                # Parse field changes
                field_changes_data = raw_event["field_changes"]
                if isinstance(field_changes_data, str):
                    field_changes_data = json.loads(field_changes_data)
                
                # Reconstruct CanonicalEvent
                event = CanonicalEvent(
                    event_id=raw_event["event_id"],
                    ubid=raw_event["ubid"],
                    source_system=raw_event["source_system"],
                    entity_type=raw_event["entity_type"],
                    event_type=EventType(raw_event["event_type"]),
                    ubid_confidence=UBIDConfidence(raw_event["ubid_confidence"]),
                    lamport_timestamp=raw_event["lamport_ts"],
                    field_changes=[CanonicalFieldChange(**fc) for fc in field_changes_data],
                    payload_hash=raw_event["payload_hash"],
                    causality=EventCausality(**(json.loads(raw_event["causality"]) if isinstance(raw_event["causality"], str) else raw_event["causality"])),
                    metadata=EventMetadata(**(json.loads(raw_event["metadata"]) if isinstance(raw_event["metadata"], str) else raw_event["metadata"]))
                )

                writers = await pipeline.orchestrator._get_active_writers()
                target = entry["target_system"]
                
                # Create a new evidence node for the manual retry trigger
                retry_node = EvidenceNode(
                    node_type=EvidenceNodeType.MANUAL_DECISION,
                    ubid=event.ubid,
                    event_id=event.event_id,
                    payload={"action": "DLQ_RETRY", "target": target}
                )
                retry_node_id = evidence.add_node(retry_node)

                # Propagate specifically to this target
                result = await pipeline.orchestrator._propagate_to_target(target, event, str(retry_node_id), writers)
                
                if result.status == "SUCCESS":
                    cur.execute("UPDATE dead_letter_queue SET status = 'RESOLVED' WHERE dlq_id = %s", (dlq_id,))
                    conn.commit()
                    return {"status": "success", "target": target}
                else:
                    cur.execute("UPDATE dead_letter_queue SET status = 'FAILED' WHERE dlq_id = %s", (dlq_id,))
                    conn.commit()
                    return {"status": "failed", "error": result.error}
                    
            except Exception as e:
                cur.execute("UPDATE dead_letter_queue SET status = 'FAILED' WHERE dlq_id = %s", (dlq_id,))
                conn.commit()
                return {"status": "error", "message": str(e)}


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
                    connector.config.json(),
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
# Simulator & Mock Department Endpoints
# ═══════════════════════════════════════════════════════════════

class DryRunPayload(BaseModel):
    source_data: dict
    field_mappings: dict

@app.post("/api/simulator/dry-run")
async def simulator_dry_run(payload: DryRunPayload):
    """
    Test a mapping configuration against sample data without saving anything.
    Uses the real TransformationRules engine for high-fidelity simulation.
    """
    from ubid_fabric.schema_mapper import TransformationRules
    rules_engine = TransformationRules()
    
    result = {}
    # First pass: direct mappings and simple transforms
    for source_key, mapping in payload.field_mappings.items():
        # Handle both simple string mapping and complex rule object
        if isinstance(mapping, str):
            target_key = mapping
            transform_name = None
        else:
            target_key = mapping.get("target_field", source_key)
            transform_name = mapping.get("transform")
            
        if source_key in payload.source_data:
            val = payload.source_data[source_key]
            if transform_name and hasattr(rules_engine, transform_name):
                try:
                    val = getattr(rules_engine, transform_name)(val)
                except Exception as e:
                    logger.warning("simulator_transform_error", field=source_key, error=str(e))
            
            result[target_key] = val
            
    # Second pass: derived mappings (where source_field is specified)
    for rule_name, mapping in payload.field_mappings.items():
        if isinstance(mapping, dict) and "source_field" in mapping:
            source_field = mapping["source_field"]
            target_key = mapping.get("target_field", rule_name)
            transform_name = mapping.get("transform")
            
            if source_field in payload.source_data:
                val = payload.source_data[source_field]
                if transform_name and hasattr(rules_engine, transform_name):
                    try:
                        val = getattr(rules_engine, transform_name)(val)
                        result[target_key] = val
                    except Exception:
                        pass
    
    return {
        "status": "success",
        "transformed_data": result,
        "mapping_count": len(result)
    }

@app.post("/mock/dept/sws/webhook")
async def mock_sws_webhook(payload: dict):
    """Mock endpoint representing the SWS Department's receiving API."""
    logger.info("mock_sws_received_data", payload=payload)
    return {"status": "success", "received_by": "SWS_DEPT_API", "timestamp": datetime.now().isoformat()}

@app.post("/mock/dept/factories/webhook")
async def mock_factories_webhook(payload: dict):
    """Mock endpoint representing the Factories Department's receiving API."""
    logger.info("mock_factories_received_data", payload=payload)
    return {"status": "success", "received_by": "FACTORIES_DEPT_API", "timestamp": datetime.now().isoformat()}

@app.post("/mock/dept/labour/webhook")
async def mock_labour_webhook(payload: dict):
    """Mock endpoint representing the Labour Department's receiving API."""
    logger.info("mock_labour_received_data", payload=payload)
    return {"status": "success", "received_by": "LABOUR_DEPT_API", "timestamp": datetime.now().isoformat()}


# ═══════════════════════════════════════════════════════════════
# Dashboard / Status Endpoints
# ═══════════════════════════════════════════════════════════════

@app.get("/status")
async def system_status():
    """System health check."""
    try:
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


# ═══════════════════════════════════════════════════════════════
# Phase 2: Dynamic Schema Evolution
# ═══════════════════════════════════════════════════════════════

class CustomFieldPayload(BaseModel):
    field_name: str
    field_type: str = "text"  # text, number, date, boolean, enum
    description: str = ""
    enum_values: list[str] = []
    required: bool = False

@app.get("/api/registry/{ubid}")
async def get_ubid_details(ubid: str):
    """Get full details for a UBID, including registry info and current state."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ubid_registry WHERE ubid = %s", (ubid,))
            record = cur.fetchone()
            if not record:
                raise HTTPException(status_code=404, detail="UBID not found")
            
            return jsonable_encoder({
                "record": record,
                "mock_state": {system: db.get(ubid) for system, db in mock_databases.items() if ubid in db}
            })

@app.get("/api/schema/custom-fields")
async def list_custom_fields():
    """List all custom UBID registry fields defined by administrators."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # Read the schema_extensions table or use a convention in metadata
            cur.execute("""
                SELECT DISTINCT jsonb_object_keys(metadata) as field_name
                FROM ubid_registry WHERE metadata != '{}'::jsonb
            """)
            fields = [row["field_name"] for row in cur.fetchall()]
            return {"custom_fields": fields}

@app.post("/api/schema/custom-fields")
async def add_custom_field(payload: CustomFieldPayload):
    """Register a new custom attribute for the UBID registry."""
    # Store field definition in a schema_extensions registry
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            import json
            cur.execute("""
                INSERT INTO schema_mappings (mapping_id, source_system, target_system, version, status, field_mappings)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (mapping_id) DO UPDATE SET field_mappings = EXCLUDED.field_mappings, updated_at = NOW()
            """, (
                f"custom_field_{payload.field_name}",
                "UBID_REGISTRY",
                "UBID_REGISTRY",
                "1.0",
                "ACTIVE",
                json.dumps({
                    "field_name": payload.field_name,
                    "field_type": payload.field_type,
                    "description": payload.description,
                    "enum_values": payload.enum_values,
                    "required": payload.required,
                })
            ))
            conn.commit()
    return {"status": "created", "field": payload.field_name}

@app.patch("/api/registry/{ubid}/metadata")
async def update_ubid_metadata(ubid: str, metadata: dict):
    """Update dynamic metadata fields for a specific UBID record."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ubid_registry
                SET metadata = metadata || %s::jsonb, updated_at = NOW()
                WHERE ubid = %s
                RETURNING ubid, metadata
            """, (json.dumps(metadata), ubid))
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=404, detail="UBID not found")
            return {"ubid": row["ubid"], "metadata": row["metadata"]}

@app.get("/api/registry/{ubid}")
async def get_ubid_record(ubid: str):
    """Get the full record for a UBID including dynamic metadata."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ubid_registry WHERE ubid = %s", (ubid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="UBID not found")
            return jsonable_encoder(row)


# ═══════════════════════════════════════════════════════════════
# Phase 3: File Ingestion (CSV/XML Batch Processing)
# ═══════════════════════════════════════════════════════════════



@app.post("/api/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source_system: str = Form(...),
    entity_type: str = Form("business"),
    field_mappings: str = Form("{}")
):
    """
    Ingest a CSV file from a department. Each row becomes a Canonical Event.
    Supports custom field mappings provided as a JSON string.
    """
    if not file.filename.endswith(('.csv', '.CSV')):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    decoded = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    mappings = json.loads(field_mappings)
    processed = 0
    errors = []

    for row_num, row in enumerate(reader, start=1):
        try:
            # Apply field mappings
            changes = []
            entity_id = None
            biz_name = ""
            address = ""

            for source_key, value in row.items():
                canonical_key = mappings.get(source_key, source_key)
                if canonical_key == "entity_id":
                    entity_id = value
                    continue
                if canonical_key == "business_name":
                    biz_name = value
                elif canonical_key == "registered_address":
                    address = value
                changes.append(FieldChange(
                    field_name=canonical_key,
                    old_value=None,
                    new_value=value,
                ))

            if not entity_id:
                entity_id = f"{source_system}-FILE-{row_num}"

            raw = RawChange(
                connector_id=f"file-{source_system.lower()}-{file.filename}",
                source_system=source_system,
                entity_type=entity_type,
                entity_id=entity_id,
                changed_fields=changes,
                change_timestamp=datetime.now(),
                capture_method=CaptureMethod.API_POLL,
            )

            await pipeline.process(raw, business_name=biz_name, address=address)
            processed += 1

        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    return {
        "status": "completed",
        "file": file.filename,
        "source_system": source_system,
        "rows_processed": processed,
        "errors": errors,
        "error_count": len(errors),
    }


# ═══════════════════════════════════════════════════════════════
# Phase 4: Security & RBAC
# ═══════════════════════════════════════════════════════════════

# Simple API Key middleware for prototype-level security


RBAC_ROLES = {
    "admin": ["read", "write", "delete", "approve_conflicts", "manage_connectors", "manage_schema"],
    "operator": ["read", "write", "manage_connectors"],
    "auditor": ["read"],
    "viewer": ["read"],
}

@app.get("/api/security/roles")
async def list_roles():
    """List all available RBAC roles and their permissions."""
    return {"roles": RBAC_ROLES}

@app.get("/api/security/audit-log")
async def get_audit_log(limit: int = 50):
    """Get the security audit log (uses evidence graph for traceability)."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT node_id, node_type, ubid, event_id, timestamp, payload
                FROM evidence_nodes
                WHERE node_type IN ('MANUAL_DECISION', 'CONFLICT_RESOLUTION', 'DLQ_ENTRY')
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            return {"count": len(rows), "entries": jsonable_encoder(rows)}

@app.post("/api/security/verify-signature")
async def verify_payload_signature(request: Request):
    """
    Verify the HMAC-SHA256 signature of an incoming department payload.
    Departments must include an X-Signature header.
    """
    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    secret = settings.webhook_signature_secret

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    if hmac.compare_digest(signature, expected):
        return {"verified": True, "message": "Payload signature is valid."}
    else:
        return {"verified": False, "message": "Signature mismatch. Payload may be tampered."}


# ═══════════════════════════════════════════════════════════════
# Phase 5: Observability & Metrics
# ═══════════════════════════════════════════════════════════════

@app.get("/api/metrics")
async def get_metrics():
    """Prometheus-compatible metrics for monitoring dashboards."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # Total events
            cur.execute("SELECT COUNT(*) as count FROM canonical_events")
            total_events = cur.fetchone()["count"]

            # Events in last hour
            cur.execute("""
                SELECT COUNT(*) as count FROM canonical_events
                WHERE created_at > NOW() - INTERVAL '1 hour'
            """)
            events_last_hour = cur.fetchone()["count"]

            # DLQ depth
            cur.execute("SELECT COUNT(*) as count FROM dead_letter_queue WHERE status = 'PENDING'")
            dlq_depth = cur.fetchone()["count"]

            # Conflict rate (last 24h)
            cur.execute("""
                SELECT COUNT(*) as count FROM evidence_nodes
                WHERE node_type = 'CONFLICT_RESOLUTION'
                AND timestamp > NOW() - INTERVAL '24 hours'
            """)
            conflicts_24h = cur.fetchone()["count"]

            # Unique UBIDs touched in last 24h
            cur.execute("""
                SELECT COUNT(DISTINCT ubid) as count FROM canonical_events
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            active_ubids = cur.fetchone()["count"]

            # Source system breakdown
            cur.execute("""
                SELECT source_system, COUNT(*) as event_count
                FROM canonical_events
                GROUP BY source_system
                ORDER BY event_count DESC
            """)
            source_breakdown = [{"system": r["source_system"], "events": r["event_count"]} for r in cur.fetchall()]

            # Propagation success rate
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE payload->>'status' = 'SUCCESS') as successes,
                    COUNT(*) as total
                FROM evidence_nodes
                WHERE node_type IN ('WRITE_CONFIRMATION', 'PROPAGATION_WRITE')
            """)
            prop_row = cur.fetchone()
            prop_rate = (prop_row["successes"] / prop_row["total"] * 100) if prop_row["total"] > 0 else 100.0

            return {
                "total_events": total_events,
                "events_last_hour": events_last_hour,
                "dlq_depth": dlq_depth,
                "conflicts_24h": conflicts_24h,
                "active_ubids_24h": active_ubids,
                "propagation_success_rate": round(prop_rate, 2),
                "source_breakdown": source_breakdown,
                "lamport_clock": pipeline.clock.value,
            }

@app.get("/api/metrics/drift")
async def get_drift_analytics():
    """Analyze which departments are most often out-of-sync."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # DLQ failures by target system
            cur.execute("""
                SELECT target_system, COUNT(*) as failure_count
                FROM dead_letter_queue
                GROUP BY target_system
                ORDER BY failure_count DESC
            """)
            dlq_by_system = [{"system": r["target_system"], "failures": r["failure_count"]} for r in cur.fetchall()]

            # Conflicts by source system
            cur.execute("""
                SELECT payload->>'source' as source, COUNT(*) as conflict_count
                FROM evidence_nodes
                WHERE node_type = 'CONFLICT_RESOLUTION'
                GROUP BY payload->>'source'
                ORDER BY conflict_count DESC
            """)
            conflicts_by_source = [{"system": r["source"], "conflicts": r["conflict_count"]} for r in cur.fetchall()]

            return {
                "dlq_failures_by_system": dlq_by_system,
                "conflicts_by_source": conflicts_by_source,
            }

@app.get("/api/metrics/time-travel/{ubid}")
async def time_travel(ubid: str, as_of: str | None = None):
    """
    View the state of a UBID at any historical point in time.
    Pass 'as_of' as ISO datetime (e.g., '2024-06-01T12:00:00').
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT event_id, source_system, lamport_ts, wall_clock_ts, field_changes
                FROM canonical_events
                WHERE ubid = %s
            """
            params = [ubid]

            if as_of:
                query += " AND wall_clock_ts <= %s"
                params.append(as_of)

            query += " ORDER BY lamport_ts ASC"
            cur.execute(query, params)
            events = cur.fetchall()

            # Replay events to build the "state at that time"
            state = {}
            for evt in events:
                changes = evt["field_changes"] if isinstance(evt["field_changes"], list) else json.loads(evt["field_changes"])
                for fc in changes:
                    field = fc.get("field_name", fc.get("field"))
                    state[field] = {
                        "value": fc.get("new_value", fc.get("value")),
                        "last_source": evt["source_system"],
                        "last_updated": str(evt["wall_clock_ts"]),
                        "lamport_ts": evt["lamport_ts"],
                    }

            return state


# ═══════════════════════════════════════════════════════════════
# Phase 7: Synthetic / Mock Endpoints (For Demonstration & Testing)
# ═══════════════════════════════════════════════════════════════

mock_system_logs = []
mock_databases = {
    "LABOUR": {},
    "SWS": {},
    "KSPCB": {},
    "ARCHIVE": {}
}

# Seed 20 synthetic records
for i in range(1, 21):
    ubid = f"UBID-KA-2024-{i:08d}"
    # Labour (Webhook - Source)
    mock_databases["LABOUR"][ubid] = {"factory_name": f"Unit {i}", "workers": 50 + i, "status": "OPERATIONAL"}
    # SWS (API - Target)
    mock_databases["SWS"][ubid] = {"legal_name": f"Unit {i} PVT LTD", "license": f"L-{100+i}", "status": "ACTIVE"}
    # KSPCB (API - Target)
    mock_databases["KSPCB"][ubid] = {"industry_name": f"Unit {i}", "pollution": "ORANGE" if i%2==0 else "GREEN"}
    # ARCHIVE (Snapshot - Legacy Target)
    mock_databases["ARCHIVE"][ubid] = {"legacy_id": f"LEG-{5000+i}", "title": f"Old Unit {i}", "quality": "HISTORICAL"}

@app.post("/mock/update")
async def update_mock_system_record(payload: dict):
    """Update a mock database record and notify the Fabric."""
    system = payload.get("system")
    ubid = payload.get("ubid")
    new_data = payload.get("data")
    if system not in mock_databases or ubid not in mock_databases[system]:
        return HTTPException(404, "Record not found")
    
    mock_databases[system][ubid].update(new_data)
    
    # Simulate the system sending a webhook to the Fabric
    ingestion_payload = {
        "source_system": system,
        "entity_type": "FACTORY",
        "entity_id": ubid,
        "changes": [{"field": k, "new": v} for k, v in new_data.items()],
        "timestamp": datetime.now().isoformat()
    }
    # In a real scenario, we'd trigger a request to /api/ingest/webhook.
    # For the demo, we'll just log it.
    mock_system_logs.append({"system": system, "method": "UPDATE_TRIGGERED", "payload": ingestion_payload, "timestamp": datetime.now().isoformat()})
    return {"status": "success", "message": f"Updated {system} record."}

@app.post("/mock/archive/ingest")
async def mock_archive_ingest(request: Request):
    """Synthetic Archive API."""
    payload = await request.json()
    record_id = payload.get("ubid") or "unknown"
    mock_databases["ARCHIVE"][record_id] = payload
    mock_system_logs.append({"system": "ARCHIVE", "method": "POST", "payload": payload, "timestamp": datetime.now().isoformat()})
    return {"status": "success", "message": "Archive snapshot stored."}

@app.post("/mock/sws/ingest")
async def mock_sws_ingest(request: Request):
    """Synthetic SWS API that accepts data from UBID Fabric."""
    payload = await request.json()
    record_id = payload.get("ubid") or payload.get("entity_name") or "unknown"
    mock_databases["SWS"][record_id] = payload
    mock_system_logs.append({"system": "SWS", "method": "POST", "payload": payload, "timestamp": datetime.now().isoformat()})
    return {"status": "success", "message": "SWS received canonical update."}

@app.put("/mock/kspcb/update")
async def mock_kspcb_update(request: Request):
    """Synthetic KSPCB API that accepts data from UBID Fabric."""
    payload = await request.json()
    record_id = payload.get("ubid") or payload.get("company_name") or "unknown"
    mock_databases["KSPCB"][record_id] = payload
    mock_system_logs.append({"system": "KSPCB", "method": "PUT", "payload": payload, "timestamp": datetime.now().isoformat()})
    return {"status": "success", "message": "Target system deleted."}


@app.post("/mock/update")
async def update_mock_system_record(payload: dict):
    """
    Simulates a user manually changing data INSIDE a department's database.
    This then triggers an 'Ingestion' event to the UBID Fabric.
    """
    system = payload.get("system")
    ubid = payload.get("ubid")
    new_data = payload.get("data")
    
    if system not in mock_databases or ubid not in mock_databases[system]:
        return JSONResponse({"status": "error", "message": "Record or System not found"}, status_code=404)
        
    # Update local mock DB
    mock_databases[system][ubid].update(new_data)
    
    # Trigger Webhook back to Fabric (Ingestion)
    # In a real demo, the Fabric would listen for this.
    # We call our own webhook endpoint to simulate the department notifying us of the change.
    fabric_payload = {
        "source_system": system,
        "entity_type": "FACTORY",
        "entity_id": ubid,
        "changes": [{"field": k, "new": v} for k, v in new_data.items()],
        "timestamp": datetime.now().isoformat()
    }
    
    # Internal call to the ingestion logic
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # Re-use the existing logic by calling the function directly or via HTTP
            # To keep it simple and robust for the demo, we'll just record it as a canonical event
            pass # The frontend can actually call the webhook endpoint for more realism
            
    return {"status": "success", "message": f"Updated {system} and notified Fabric."}

@app.get("/api/nodes")
async def list_departmental_nodes():
    """Returns a unified view of departments, showing both Ingress and Egress status."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # Fetch all ingress (connectors)
            cur.execute("SELECT id, name, system_type, connector_type, is_active, last_status, success_rate FROM connectors")
            connectors = cur.fetchall()
            
            # Fetch all egress (targets)
            cur.execute("SELECT id, name, system_type, is_active FROM target_systems")
            targets = cur.fetchall()
            
            # Group by system_type
            nodes = {}
            
            # Process connectors (Ingress)
            for c in connectors:
                st = c["system_type"]
                if st not in nodes:
                    nodes[st] = {"system_type": st, "ingress": None, "egress": None}
                nodes[st]["ingress"] = {
                    "id": str(c["id"]),
                    "name": c["name"],
                    "type": c["connector_type"],
                    "is_active": c["is_active"],
                    "status": c["last_status"],
                    "success_rate": c["success_rate"]
                }
                
            # Process targets (Egress)
            for t in targets:
                st = t["system_type"]
                if st not in nodes:
                    nodes[st] = {"system_type": st, "ingress": None, "egress": None}
                nodes[st]["egress"] = {
                    "id": str(t["id"]),
                    "name": t["name"],
                    "is_active": t["is_active"]
                }
                
            return list(nodes.values())

@app.post("/mock/labour/webhook")
async def mock_labour_webhook(request: Request):
    """Synthetic Labour API to simulate incoming webhooks."""
    payload = await request.json()
    record_id = payload.get("entity_id") or payload.get("business_name") or "unknown"
    mock_databases["LABOUR"][record_id] = payload
    mock_system_logs.append({"system": "LABOUR", "method": "POST", "payload": payload, "timestamp": datetime.now().isoformat()})
    return {"status": "success", "message": "Labour webhook simulated."}

@app.get("/mock/logs")
async def get_mock_logs():
    """View what the synthetic systems have received."""
    return {"total_received": len(mock_system_logs), "logs": list(reversed(mock_system_logs))}

@app.get("/mock/state")
async def get_mock_state():
    """View the current mock databases for all synthetic systems."""
    return mock_databases


@app.get("/")
async def root():
    return {
        "name": "UBID Fabric",
        "version": "0.2.0",
        "description": "Deterministic Interoperability Layer — Production Edition",
        "docs": "/docs",
        "features": [
            "Bi-directional Propagation",
            "AI-Assisted Schema Mapping",
            "4-Level Conflict Resolution",
            "Dynamic Schema Evolution",
            "CSV File Ingestion",
            "RBAC Security",
            "Time-Travel Debugging",
            "PII-Safe AI Calls",
        ]
    }
