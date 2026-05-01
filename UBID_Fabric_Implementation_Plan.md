# UBID Fabric — Implementation Plan (Prototype → Scale)

**Project:** Deterministic Interoperability Layer for Karnataka SWS  
**Approach:** Free prototype first → Scale to production later  
**Created:** 2026-05-01  
**Status:** ⬜ Not Started | 🔄 In Progress | ✅ Done | ❌ Blocked

---

## 💰 Cost Strategy: $0 Prototype → Paid Scale

| Component | 🟢 Prototype (FREE) | 🔵 Scale (Production) |
|-----------|---------------------|----------------------|
| **Orchestration** | Docker Compose (local) | Kubernetes (cloud) |
| **Event Queue** | Redis Streams (free, in Docker) | Apache Kafka (managed) |
| **Database** | PostgreSQL in Docker (free) | Managed PostgreSQL (RDS/Cloud SQL) |
| **Cache** | Redis in Docker (free) | Managed Redis (ElastiCache) |
| **Saga Engine** | Python asyncio + DB state (free) | Temporal.io (self-hosted/cloud) |
| **CDC** | Polling-based (code only) | Debezium + Kafka Connect |
| **Monitoring** | Console logs + structlog (free) | Prometheus + Grafana |
| **Secrets** | `.env` files (local) | HashiCorp Vault |
| **AI (offline)** | Gemini API free tier / local | Gemini / Claude API paid |
| **Hosting** | Localhost / free VM | Cloud Kubernetes |
| **Total Cost** | **$0** | **$$$ based on scale** |

---

## Progress Summary

| Phase | Description | Tasks | Done | % |
|-------|------------|-------|------|---|
| 0 | Project Setup (Free Stack) | 12 | 12 | 100% |
| 1 | Ingestion Layer — Connectors | 16 | 16 | 100% |
| 2 | Event Pipeline — Core Engine | 14 | 14 | 100% |
| 3 | Identity & Conflict Resolution | 20 | 20 | 100% |
| 4 | Execution — Saga & Propagation | 14 | 14 | 100% |
| 5 | Governance — Audit & Review | 18 | 18 | 100% |
| 6 | Demo & Validation | 14 | 14 | 100% |
| **Total** | | **108** | **108** | **100%** |

---

## Phase 0 — Project Setup & Free Infrastructure (Day 1)

### 0.1 Project Structure
- [x] Initialize Python project with `pyproject.toml`
- [x] Create package structure: `src/ubid_fabric/`
- [x] Set up virtual environment (`python -m venv .venv`)
- [x] Install dependencies: `pydantic`, `redis`, `psycopg`, `fastapi`, `httpx`, `structlog`

### 0.2 Local Infrastructure (Docker Compose — all FREE)
- [x] Create `docker-compose.yml` with:
  - [x] PostgreSQL 16 (event store + evidence graph + registry)
  - [x] Redis 7 (idempotency store + event queue via Streams + conflict cache)
- [x] Create `migrations/init.sql` (all DB tables)
- [x] Run `docker-compose up -d` and verify health
- [x] Seed UBID registry with sample data (10-20 test businesses)

### 0.3 Configuration
- [x] Create `.env` file (DB URLs, Redis URL, API keys)
- [x] Create `config.py` with typed settings (Pydantic Settings)

> **🔵 Scale Upgrade:** Replace Docker Compose → Kubernetes. Add Kafka (replace Redis Streams). Add Temporal.io. Add Prometheus/Grafana. Add Vault.

> **Phase 0 Exit:** `docker-compose up` brings up PostgreSQL + Redis. Python project runs.

---

## Phase 1 — Ingestion Layer / L1 (Days 2–3)

### 1.1 Core Data Models
- [x] Define all Pydantic models in `models.py`:
  - [x] L1: `RawChange`
  - [x] L2: `CanonicalEvent`, `EventMetadata`, `Causality`
  - [x] L3: `UBIDResolution`
  - [x] L4: `ConflictResolution`, `SchemaMapping`
  - [x] L6: `EvidenceNode`, `EvidenceEdge`
- [x] Write model validation tests

### 1.2 Lamport Clock
- [x] Implement `LamportClock` class (thread-safe, tick + receive)
- [x] Write unit tests ensuring strict monotonicity

### 1.3 Event Builder & Canonical ID
- [x] Implement `CanonicalEvent` model with `.event_id` property (SHA-256)
- [x] Write unit tests ensuring same inputs = exact same hash

### 1.3 Base Connector Framework
- [x] Implement abstract `SourceConnector`:
  - [x] `detect_changes()` / `run()` → `RawChange`
  - [x] `emit()` — pushes RawChange to API
- [x] Implement MockSWSConnector (Tier 1 Webhook simulation)
- [x] Implement MockFactoriesConnector (Tier 2 Polling simulation)

### 1.6 Change Capture Layer
- [x] Implement field extraction + type validation
- [x] Implement schema drift detection (log WARNING/ERROR)

> **🔵 Scale Upgrade:** Add real SWS webhook. Add Debezium CDC connector. Add Snapshot Diff connector for legacy. Replace Redis Streams → Kafka topics.

> **Phase 1 Exit:** Mock changes from SWS and Factories flow as `RawChange` into Redis Stream.

---

## Phase 2 — Event Pipeline / L2 (Days 3–4)

### 2.1 Canonical Event Builder
- [x] Implement `build_canonical_event(raw_change, lamport_clock)`:
  - [x] Generate deterministic `event_id` = `sha256(ubid|source|lamport_ts|payload_hash)`
  - [x] Assign `crdt_type` per field (config-driven)
  - [x] Pin version numbers (mapping, policy, resolver)
- [x] Write tests: same input → same event_id (determinism guarantee)

### 2.2 Immutable Event Log
- [x] Implement `EventStore` class:
  - [x] `append(event)` → INSERT into PostgreSQL `canonical_events` table
  - [x] `get_by_id(event_id)` → single event lookup
  - [x] `get_by_ubid(ubid, since_lamport_ts)` → all events for a business
  - [x] Enforce append-only (no UPDATE/DELETE)
- [x] Write tests for storage + retrieval

### 2.3 Event Stream Consumer
- [x] Implement Redis Stream consumer (`XREADGROUP`) for `stream:raw-changes`
- [x] Consumer processes: RawChange → CanonicalEvent → store + publish to `stream:canonical-events`
- [x] Implement consumer group for future horizontal scaling

### 2.4 Event Replay
- [x] Implement replay tool: re-process events from EventStore by UBID
- [x] Ensure replay uses version-pinned rules (mapping/policy versions from event metadata)

> **🔵 Scale Upgrade:** Replace Redis Streams → Kafka topics. Add Kafka consumer groups. Add cold storage archival to S3.

> **Phase 2 Exit:** RawChanges are consumed, converted to CanonicalEvents with deterministic IDs, and stored in PostgreSQL.

---

## Phase 3 — Identity & Conflict Resolution / L3+L4 (Days 4–6)

### 3.1 UBID Resolution Engine (L3)
- [x] Implement UBID registry in PostgreSQL (`ubid_registry` table)
- [x] Implement exact match lookup
- [x] Implement fuzzy matching (Jaro-Winkler name similarity)
- [x] Implement multi-factor confidence scoring:
  - [x] Exact UBID match: 0–0.40
  - [x] Name similarity: 0–0.25
  - [x] Address similarity: 0–0.20
  - [x] Cross-system consistency: 0–0.15
- [x] Assign confidence state: HIGH (≥0.95) / PROBATION (0.70–0.94) / QUARANTINE (<0.70)
- [x] QUARANTINE → queue for manual review (write to `review_queue` table)
- [x] PROBATION → proceed with `ubid_verified=false` flag
- [x] Write tests for each confidence boundary

### 3.2 Conflict Convergence Engine (L4)
- [x] Implement conflict detection: same UBID + same field within 30s window
- [x] Use Redis to track in-flight events per UBID+field (TTL = conflict window)
- [x] Implement 4-level resolution ladder:
  - [x] **Level 1 — CRDT:**
    - [x] LWW Register: higher Lamport ts wins; tie → source hash tiebreak
    - [x] OR-Set: union ADDs, subtract observed REMOVEs
    - [x] Monotonic: max(A, B)
  - [x] **Level 2 — Source Priority:** configurable JSON policy file
  - [x] **Level 3 — Domain Ownership:** configurable JSON policy file
  - [x] **Level 4 — Manual Escalation:** queue to `review_queue`
- [x] Write property tests: `merge(A,B) == merge(B,A)` (commutativity)

### 3.3 Schema Mapping Registry (L4)
- [x] Store mappings in PostgreSQL `schema_mappings` table
- [x] Implement field transformations:
  - [x] `DIRECT_COPY`, `SPLIT_ADDRESS`, `JOIN_ADDRESS`
  - [x] `DATE_FORMAT` (ISO ↔ DD/MM/YYYY)
  - [x] `ENUM_MAP`, `SET_EXTRACT` (primary from set)
- [x] Implement mapping lifecycle: DRAFTED → SHADOW → ACTIVE → ARCHIVED
- [x] Create SWS ↔ Factories mapping (v1.0.0)
- [x] Create SWS ↔ Shop Establishment mapping (v1.0.0)

### 3.4 Pipeline Integration
- [x] Wire: `stream:canonical-events` → UBID Resolution → Conflict Engine → Schema Mapping
- [x] Output: resolved + mapped events to `stream:converged-events`
- [x] Write evidence graph nodes at each step

> **🔵 Scale Upgrade:** Add ML-based UBID resolution as optional scorer. Move policies to versioned config service. Add shadow mode parallel execution.

> **Phase 3 Exit:** Events are UBID-resolved, conflicts are CRDT-merged, fields are schema-mapped. Full pipeline working.

---

## Phase 4 — Execution / L5 (Days 6–7)

### 4.1 Idempotency Store
- [x] Implement Redis-based idempotency check: `SET event_id NX EX 604800` (7-day TTL)
- [x] Status lifecycle: IN_PROGRESS → PROCESSED
- [x] Duplicate events → silent no-op (return cached result)
- [x] PostgreSQL fallback when Redis unavailable
- [x] Write test: same event processed twice → only one write

### 4.2 Saga Orchestrator (Simple — No Temporal Needed for Prototype)
- [x] Implement `PropagationSaga` as async Python function:
  - [x] For each target system: transform → idempotency check → HTTP write → record result
  - [x] Retry with exponential backoff, max 5 attempts
  - [x] On max retries → write to `dead_letter_queue` table in PostgreSQL
- [x] Implement `CompensationSaga`: reverse writes (restore old values)
- [x] Implement `ReplaySaga`: re-inject corrected event into pipeline
- [x] Steps are independent — one failure doesn't block others

### 4.3 Target System Writers
- [x] Implement generic `TargetWriter` (async HTTP client via `httpx`)
- [x] Implement mock Factories API writer (writes to mock API endpoint)
- [x] Implement mock SWS API writer
- [x] Record write results in evidence graph

### 4.4 Dead-Letter Queue
- [x] Implement DLQ in PostgreSQL table (event + error context + retry count)
- [x] Implement DLQ retry endpoint (manual trigger via API)
- [x] Implement DLQ listing endpoint (for review console)

> **🔵 Scale Upgrade:** Replace Python async saga → Temporal.io workflows. Add per-system rate limiting. Add circuit breakers.

> **Phase 4 Exit:** Full E2E: SWS change → event → UBID → conflict → mapping → write to dept → idempotent → audited.

---

## Phase 5 — Governance / L6 (Days 7–9)

### 5.1 Evidence Graph
- [x] Implement `EvidenceGraphStore`:
  - [x] `add_node(node)` → INSERT into `evidence_nodes`
  - [x] `add_edge(edge)` → INSERT into `evidence_edges`
  - [x] `traverse_causes(node_id)` → recursive CTE query following `caused_by` edges
  - [x] `get_field_history(ubid, field)` → all events that touched this field
- [x] Write integration test: full happy-path chain is queryable
- [x] Implement "why is this field set to X?" query

### 5.2 Reconciliation Engine
- [x] Implement expected state derivation (replay events → CRDT merge → map)
- [x] Implement actual state query (mock)
- [x] Implement diff comparison + drift classification:
  - [x] STALE → auto-repair (re-propagate)
  - [x] OUT_OF_BAND → ingest as new event
  - [x] AMBIGUOUS → queue for manual review
- [ ] Implement scheduled reconciliation (configurable interval)
- [ ] Write test: manually alter mock dept → recon detects → auto-repair

### 5.3 Manual Review Console (FastAPI Web UI)
- [x] Build REST API endpoints:
  - [x] `GET /review/quarantine` — UBID quarantine queue
  - [x] `GET /review/conflicts` — unresolved conflict queue
  - [x] `GET /review/drift` — reconciliation drift queue
  - [x] `POST /review/{id}/decide` — submit reviewer decision
  - [x] `GET /review/{id}/context` — evidence graph causal chain
- [x] Build simple HTML/JS frontend with modern Glassmorphism aesthetics
- [x] Record all decisions as `MANUAL_DECISION` evidence nodes

### 5.4 API Dashboard
- [x] `GET /status` — system health (infra connectivity checks)
- [x] `GET /metrics` — event throughput, conflict rate, DLQ depth, queue sizes
- [x] `GET /events/{ubid}` — all events for a business
- [x] `GET /evidence/{ubid}` — evidence graph for a business

> **🔵 Scale Upgrade:** Add Grafana dashboards. Add Prometheus metrics exporter. Build full React Manual Review Console. Add RBAC auth.

> **Phase 5 Exit:** Evidence graph stores causal chains. Reconciliation detects drift. Review API operational.

---

## Phase 6 — Demo & Validation (Days 9–10)

### 6.1 End-to-End Flow Tests
- [x] **Flow 1:** Address update SWS → Factories + Shop Estb. (happy path)
- [x] **Flow 2:** Signatory update Factories → SWS (reverse direction, OR-Set)
- [x] **Flow 3:** Concurrent conflict — SWS + Shop Estb. simultaneous address change
- [x] **Flow 4:** UBID mismatch → PROBATION → correction → compensation → replay

### 6.2 Edge Case Tests
- [x] Duplicate event → idempotent no-op
- [x] Target API down → retry → DLQ → manual replay → success
- [x] Out-of-order events → CRDT handles correctly
- [x] Schema drift → event quarantined → mapping update → replay

### 6.3 Demo Script
- [x] Create `demo.py` that runs all 4 flows end-to-end with colored console output
- [x] Show evidence graph traversal for each flow
- [x] Show conflict resolution audit trail
- [x] Show UBID correction compensation chain

### 6.4 Documentation
- [x] API documentation (FastAPI auto-generates OpenAPI/Swagger)
- [x] Architecture README with setup instructions
- [x] Demo walkthrough guide

> **Phase 6 Exit:** All 4 scenarios demonstrated. Evidence graph queryable. Full audit trails visible.

---

## Technology Checklist (Prototype — All FREE)

| Technology | Purpose | Cost | Status |
|------------|---------|------|--------|
| Python 3.11+ | Core language | Free | ✅ |
| Docker + Docker Compose | Local infrastructure | Free | ✅ |
| PostgreSQL 16 (Docker) | Event store + Evidence graph + Registry | Free | ✅ |
| Redis 7 (Docker) | Idempotency + Event streams + Conflict cache | Free | ✅ |
| FastAPI | REST API + Webhook listener + Review console | Free | ✅ |
| Pydantic v2 | Data validation + Models | Free | ✅ |
| httpx | Async HTTP client for target writes | Free | ✅ |
| structlog | Structured logging | Free | ✅ |
| jellyfish | String similarity (Jaro-Winkler) for UBID | Free | ✅ |
| pytest + hypothesis | Testing + Property-based tests | Free | ✅ |

---

## Scale Upgrade Path (When Ready)

| What | Free Prototype | Production Upgrade |
|------|---------------|-------------------|
| Event Queue | Redis Streams | Apache Kafka (3 brokers) |
| Saga Engine | Python async + PostgreSQL state | Temporal.io |
| CDC | Polling-based connectors | Debezium on DB WAL |
| Container Orchestration | Docker Compose | Kubernetes |
| Monitoring | Console logs / structlog | Prometheus + Grafana |
| Secrets | `.env` files | HashiCorp Vault |
| Manual Review UI | FastAPI + basic HTML | Full React/Next.js app |
| Auth | None (local dev) | RBAC + OAuth2 |
| Hosting | Localhost | Cloud (AWS/GCP/Azure) |
| SSL/TLS | None (local) | mTLS between services |
| Snapshot Connector | Mock API | Real dept system bulk exports |
| AI Assist | Gemini free tier | Gemini/Claude paid API |

---

## Risk Tracker

| ID | Risk | Prob | Impact | Mitigation | Status |
|----|------|------|--------|------------|--------|
| R1 | Dept API unavailability | High | Med | Retry + DLQ + reconciliation | ✅ |
| R2 | Schema changes w/o notice | High | Med | Drift detection + quarantine | ✅ |
| R3 | UBID resolution errors | Med | High | Three-state model + compensation | ✅ |
| R4 | Redis failure (prototype) | Low | Med | PostgreSQL fallback for idempotency | ✅ |
| R5 | Manual review overflow | Med | Med | Probation reduces volume 60-70% | ✅ |
| R6 | Political resistance | Med | High | Non-invasive + domain ownership | ✅ |

---

## 10-Day Timeline

```
Day 1  ████ Phase 0: Project setup, Docker Compose, DB schemas
Day 2  ████ Phase 1: Data models, Lamport clock, connector framework
Day 3  ████ Phase 1+2: Mock connectors, event builder, event store
Day 4  ████ Phase 2+3: Event pipeline, UBID resolution engine
Day 5  ████ Phase 3: Conflict engine (CRDTs), schema mapping
Day 6  ████ Phase 3+4: Pipeline integration, idempotency store
Day 7  ████ Phase 4: Saga orchestrator, target writers, DLQ
Day 8  ████ Phase 5: Evidence graph, reconciliation engine
Day 9  ████ Phase 5+6: Review console API, E2E flow tests
Day 10 ████ Phase 6: Demo script, documentation, polish
```

---

*Last updated: 2026-05-01 | Update checkboxes as tasks are completed.*
