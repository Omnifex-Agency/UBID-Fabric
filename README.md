<p align="center">
  <h1 align="center">🧬 UBID Fabric</h1>
  <p align="center">
    <strong>Deterministic Interoperability Layer for Government Systems</strong>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis">
    <img src="https://img.shields.io/badge/AI-Ollama%20%7C%20Gemini-FF6F00?logo=google&logoColor=white" alt="AI">
    <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License">
    <img src="https://img.shields.io/badge/tests-25%20passed-brightgreen" alt="Tests">
  </p>
  <p align="center">
    <a href="#quickstart">🚀 Quickstart</a>&nbsp;&nbsp;•&nbsp;&nbsp;
    <a href="#architecture">🏗️ Architecture</a>&nbsp;&nbsp;•&nbsp;&nbsp;
    <a href="#api-reference">📡 API Reference</a>&nbsp;&nbsp;•&nbsp;&nbsp;
    <a href="#ai-integration">🧠 AI Integration</a>&nbsp;&nbsp;•&nbsp;&nbsp;
    <a href="#license">📜 License</a>
  </p>
</p>

---

> **UBID Fabric** is a zero-cost, self-hosted interoperability engine that connects siloed government databases through a single deterministic pipeline. It ensures that when one department updates a business record, every other connected department receives the change — automatically, reliably, and with a full audit trail.

---

## ✨ Key Features

| Capability | Description |
|---|---|
| **🪪 UBID Identity Resolution** | Fuzzy-matches businesses across departments using Jaro-Winkler similarity + multi-factor confidence scoring |
| **🔀 CRDT Conflict Resolution** | Deterministic merging via Last-Writer-Wins, OR-Set, and Monotonic CRDTs — no human intervention needed |
| **🔁 Saga Orchestrator** | Propagates changes to all connected systems with exponential backoff retries and a Dead Letter Queue |
| **↩️ Compensation Saga** | Reverses propagated writes when a manual reviewer rejects an auto-merged decision |
| **🗺️ Schema Mapping Engine** | Transforms fields between systems (date formatting, field extraction, casing, enum mapping) |
| **🧠 AI-Powered Mapping** | Uses Ollama (local Llama 3) or Gemini to auto-suggest field mappings for new integrations |
| **📜 Evidence Graph** | Immutable causal audit trail — every single decision is traceable via recursive CTE queries |
| **🔍 Reconciliation Engine** | Detects drift (STALE / OUT_OF_BAND) between the Fabric and target systems |
| **🖥️ Control Center UI** | Real-time Glassmorphism dashboard for monitoring events, evidence, and system health |

---

<a id="architecture"></a>

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        UBID Fabric Engine                           │
│                                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │
│  │    L1     │   │    L2     │   │    L3     │   │       L4         │  │
│  │ Ingest    │──▶│ Pipeline  │──▶│ Identity  │──▶│ Conflict + Map  │  │
│  │ Connector │   │ EventLog  │   │ UBID Res. │   │ CRDT + Schema   │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────────┘  │
│                                                         │            │
│                                                         ▼            │
│                                    ┌──────────────────────────────┐  │
│                                    │            L5                 │  │
│                                    │   Saga Orchestrator           │  │
│                                    │   TargetWriters + DLQ         │  │
│                                    │   Compensate + Replay         │  │
│                                    └──────────────────────────────┘  │
│                                                         │            │
│                                                         ▼            │
│                                    ┌──────────────────────────────┐  │
│                                    │            L6                 │  │
│                                    │   Evidence Graph (Audit)      │  │
│                                    │   Reconciliation Engine       │  │
│                                    └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐        ┌──────────┐        ┌──────────────┐
   │   SWS    │        │Factories │        │  Shop & Est. │
   │  Dept.   │        │  Dept.   │        │    Dept.     │
   └──────────┘        └──────────┘        └──────────────┘
```

### How It Works

1. **A department pushes a change** → hits the `/webhook/ingest` endpoint.
2. **L1 (Ingest)** normalizes the raw payload into a `RawChange`.
3. **L2 (Event Store)** generates a deterministic SHA-256 `event_id` and stores it immutably.
4. **L3 (Identity)** resolves or creates a `UBID` using exact system ID match or Jaro-Winkler fuzzy matching.
5. **L4 (Conflict)** merges the change using CRDTs. If CRDTs can't resolve, it escalates through source priority → domain ownership → manual review.
6. **L5 (Execute)** the Saga Orchestrator schema-maps the payload and pushes it to **every other connected department** via their `TargetWriter`.
7. **L6 (Audit)** every step above is recorded as a node in the **Evidence Graph** for full traceability.

### Module Map

```
src/ubid_fabric/
├── ai_service.py          # AI integration (Ollama / Gemini)
├── app.py                 # FastAPI REST API (webhooks, registry, AI, dashboard)
├── config.py              # Typed settings from .env
├── conflict_engine.py     # 4-tier conflict resolution ladder
├── connectors.py          # Source system connectors (SWS, Factories)
├── crdt.py                # CRDT implementations (LWW, OR-Set, Monotonic)
├── db.py                  # PostgreSQL + Redis connection management
├── event_builder.py       # Canonical event construction + SHA-256 IDs
├── event_store.py         # Immutable append-only event log
├── evidence_graph.py      # Causal audit graph (recursive CTE)
├── idempotency.py         # Redis SET NX deduplication
├── lamport.py             # Lamport logical clock
├── models.py              # All Pydantic data models
├── orchestrator.py        # Saga orchestrator (Propagate / Compensate / Replay)
├── pipeline.py            # Full pipeline: L1 → L2 → L3 → L4 → L5 → L6
├── reconciliation.py      # Drift detection engine
├── schema_mapper.py       # Field transformation engine
├── stream_consumer.py     # Redis Stream consumer (XREADGROUP) + Event Replay
├── target_writers.py      # Pluggable HTTP writers per department
└── ubid_resolver.py       # UBID identity resolution (exact + fuzzy)
```

---

<a id="quickstart"></a>

## 🚀 Quickstart

### Prerequisites

| Requirement | Version |
|---|---|
| Docker Desktop | Latest (with Docker Compose) |
| Git | 2.x+ |

### Step 1 — Clone & Launch

```bash
git clone https://github.com/Omnifex-Agency/UBID-Fabric.git
cd UBID-Fabric
docker-compose up --build -d
```

This starts **3 services**:

| Service | Port | Purpose |
|---|---|---|
| `ubid-api` | `8000` | FastAPI application + Control Center UI |
| `ubid-postgres` | `5432` | PostgreSQL 16 (event store, registry, evidence graph) |
| `ubid-redis` | `6379` | Redis 7 (idempotency, conflict cache, streams) |

### Step 2 — Open the Control Center

```
http://localhost:8000/ui/index.html
```

A real-time Glassmorphism dashboard that shows events, evidence nodes, and system health.

### Step 3 — Seed the Registry

```bash
# Seed 5 sample Karnataka businesses into the UBID registry
curl -X POST http://localhost:8000/registry/seed
```

### Step 4 — Send Your First Change

```bash
# Simulate a business name update from the SWS department
curl -X POST http://localhost:8000/webhook/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_system": "SWS",
    "entity_type": "BUSINESS",
    "entity_id": "SWS-001",
    "business_name": "Bangalore Tech Solutions Pvt Ltd",
    "address": "42 MG Road, Bangalore 560001",
    "changes": [{"field": "business_name", "old": "Old Name", "new": "Bangalore Tech Solutions Pvt Ltd"}]
  }'
```

Watch the Control Center UI auto-refresh with the new event and evidence trail.

### Step 5 — Run the Full Demo

```bash
docker exec ubid-api pip install rich
docker exec ubid-api python demo.py
```

### Step 6 — Run Tests

```bash
docker exec ubid-api pip install pytest
docker exec ubid-api python -m pytest tests/ -v
# ======================== 25 passed ========================
```

---

<a id="api-reference"></a>

## 📡 API Reference

> Full interactive docs available at: **http://localhost:8000/docs**

### Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook/ingest` | Universal webhook — any source system pushes changes here |

<details>
<summary><strong>Request Body</strong></summary>

```json
{
  "source_system": "SWS",
  "entity_type": "BUSINESS",
  "entity_id": "SWS-001",
  "business_name": "My Business",
  "address": "123 Main St",
  "changes": [
    {"field": "business_name", "old": "Old Name", "new": "My Business"}
  ],
  "timestamp": "2026-05-01T12:00:00"
}
```

</details>

### Registry

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/registry/register` | Register a new business in the UBID registry |
| `POST` | `/registry/seed` | Seed the registry with 5 sample Karnataka businesses |

### Events & Evidence

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/events` | List recent canonical events (default: 20) |
| `GET` | `/events/{ubid}` | Get all events for a specific UBID |
| `GET` | `/evidence/{ubid}` | Get the full evidence graph for a UBID |
| `GET` | `/evidence/{ubid}/trace/{node_id}` | Trace the causal chain of a decision |

### AI Intelligence

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ai/suggest-mapping` | AI-powered schema mapping suggestion |

<details>
<summary><strong>Request Body</strong></summary>

```json
{
  "source_sample": {"biz_name": "ABC Corp", "loc": "Bangalore", "incorp_dt": "2022-01-01"},
  "target_sample": {"factory_title": "", "address": "", "estb_date": ""}
}
```

</details>

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/status` | Health check (PostgreSQL, Redis, metrics) |
| `GET` | `/docs` | Interactive Swagger documentation |
| `GET` | `/` | Root endpoint (version info) |

---

<a id="ai-integration"></a>

## 🧠 AI Integration

UBID Fabric supports **two AI backends** for intelligent schema mapping. The system defaults to **Ollama (local)** so no data ever leaves your network.

### Option A: Self-Hosted (Default) — Ollama + Llama 3

> 🔒 **Zero data leakage.** Runs entirely on your local machine or private server.

```bash
# 1. Uncomment the ollama service in docker-compose.yml
# 2. Start the stack
docker-compose up -d

# 3. Pull a model (one-time)
docker exec ubid-ollama ollama pull llama3
```

**Configuration (`.env`):**
```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3
```

### Option B: Cloud — Google Gemini

> ☁️ For higher-order reasoning on complex, multi-language schemas.

**Configuration (`.env`):**
```env
AI_PROVIDER=gemini
AI_API_KEY=your_gemini_api_key_here
AI_MODEL=gemini-1.5-flash
```

### Usage Example

```bash
curl -X POST http://localhost:8000/ai/suggest-mapping \
  -H "Content-Type: application/json" \
  -d '{
    "source_sample": {"biz_name": "ABC Corp", "loc": "Bangalore", "incorp_dt": "2022-01-01"},
    "target_sample": {"factory_title": "", "address": "", "estb_date": ""}
  }'
```

**Response:**
```json
{
  "provider": "ollama",
  "model": "llama3",
  "suggestion": "mapping: biz_name → factory_title, loc → address, incorp_dt → estb_date (transform: YYYY-MM-DD → DD/MM/YYYY)"
}
```

---

## ⚙️ Configuration

All settings are managed via environment variables in `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `AI_PROVIDER` | `ollama` | AI backend: `ollama` or `gemini` |
| `AI_BASE_URL` | `http://localhost:11434/v1` | Ollama API endpoint |
| `AI_MODEL` | `llama3` | Model name |
| `AI_API_KEY` | *(empty)* | API key for Gemini (leave blank for Ollama) |
| `MAX_SAGA_RETRIES` | `5` | Max retry attempts before DLQ |
| `CONFLICT_WINDOW_SECONDS` | `30` | Time window for conflict detection |
| `IDEMPOTENCY_TTL_SECONDS` | `604800` | 7-day deduplication window |

---

## 🧪 Testing

The project includes **25 unit tests** covering all deterministic guarantees:

| Test Suite | Tests | Validates |
|---|---|---|
| `TestLamportClock` | 5 | Monotonicity, receive semantics, thread safety |
| `TestLWWRegister` | 4 | Higher-timestamp wins, commutativity, deterministic tiebreak |
| `TestORSet` | 3 | Concurrent add/remove, union of adds, commutativity |
| `TestMonotonicMerge` | 3 | Max selection, commutativity, idempotency |
| `TestEventBuilder` | 3 | Deterministic SHA-256 IDs, CRDT type assignment |
| `TestUBIDConfidence` | 3 | HIGH / PROBATION / QUARANTINE boundaries |
| `TestJaroWinkler` | 4 | Exact match, similar strings, different strings, edge cases |

```bash
docker exec ubid-api python -m pytest tests/ -v
# ======================== 25 passed ========================
```

---

## 🛣️ Roadmap

### ✅ Completed (Prototype — 108/108 Tasks)
- [x] Full 6-layer pipeline (Ingest → Event → Identity → Conflict → Execute → Audit)
- [x] CRDT-based deterministic conflict resolution
- [x] Saga orchestrator with compensation and replay
- [x] Schema mapping engine with date/field transformations
- [x] AI-powered schema suggestions (Ollama + Gemini)
- [x] Glassmorphism Control Center UI
- [x] Redis Stream consumer with consumer groups
- [x] Reconciliation engine for drift detection
- [x] Modular TargetWriter system for pluggable integrations

### 🔮 Future (Production Scale)
- [ ] Replace Docker Compose → **Kubernetes**
- [ ] Replace Redis Streams → **Apache Kafka**
- [ ] Replace Python Saga → **Temporal.io** workflows
- [ ] Add **Debezium CDC** for real-time database change capture
- [ ] Add **JWT-based RBAC** for the Review Console
- [ ] Add **Prometheus + Grafana** monitoring
- [ ] Add **ML-based UBID resolution** as an optional scorer

---

## 🏛️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.11+ | Core engine |
| **API** | FastAPI | REST endpoints + Swagger docs |
| **Database** | PostgreSQL 16 | Immutable event log, evidence graph, registry |
| **Cache** | Redis 7 | Idempotency, conflict windows, streams |
| **AI** | Ollama / Gemini | Schema mapping intelligence |
| **Models** | Pydantic v2 | Data validation and serialization |
| **HTTP** | httpx | Async target system communication |
| **Matching** | Jellyfish | Jaro-Winkler fuzzy string matching |
| **Logging** | structlog | Structured JSON logging |
| **Containers** | Docker Compose | Local development infrastructure |

---

## 📂 Project Structure

```
UBID-Fabric/
├── src/ubid_fabric/       # Core engine (21 modules)
├── tests/                 # Unit tests (25 tests)
├── migrations/            # PostgreSQL schema (init.sql)
├── frontend/              # Control Center UI (HTML/CSS/JS)
├── docker-compose.yml     # Infrastructure definition
├── Dockerfile             # API container build
├── pyproject.toml         # Python project metadata
├── .env.example           # Example environment configuration
├── .gitignore             # Git ignore rules
├── LICENSE                # Apache License 2.0
├── UBID_Fabric_Document.md          # Full technical specification
└── UBID_Fabric_Implementation_Plan.md  # Development tracker (108/108 ✅)
```

---

<a id="license"></a>

## 📜 License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

```
Copyright 2026 Saurabh Pawar

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

---

<p align="center">
  Built with ❤️ for Karnataka's Digital Infrastructure
</p>
