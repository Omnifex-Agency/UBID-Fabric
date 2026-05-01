<p align="center">
  <h1 align="center">🧬 UBID Fabric</h1>
  <p align="center">
    <strong>Deterministic Interoperability Layer for Government Systems</strong>
  </p>
  <p align="center">
    <a href="#quickstart">Quickstart</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#api-reference">API Reference</a> •
    <a href="#ai-integration">AI Integration</a> •
    <a href="#license">License</a>
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

## 🚀 Quickstart

### Prerequisites

- **Docker Desktop** (with Docker Compose)
- **Git**

### 1. Clone & Start

```bash
git clone https://github.com/Omnifex-Agency/UBID-Fabric.git
cd UBID-Fabric
docker-compose up --build -d
```

This starts **3 services**:
| Service | Port | Purpose |
|---|---|---|
| `ubid-api` | `8000` | FastAPI application |
| `ubid-postgres` | `5432` | PostgreSQL 16 (event store, registry, evidence graph) |
| `ubid-redis` | `6379` | Redis 7 (idempotency, conflict cache, streams) |

### 2. Open the Control Center

```
http://localhost:8000/ui/index.html
```

### 3. Seed the Registry & Test

```bash
# Seed 5 sample Karnataka businesses
curl -X POST http://localhost:8000/registry/seed

# Send a test change from the SWS department
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

### 4. Run the Demo Script

```bash
docker exec ubid-api pip install rich
docker exec ubid-api python demo.py
```

### 5. Run Tests

```bash
docker exec ubid-api pip install pytest
docker exec ubid-api python -m pytest tests/ -v
```

---

## 📡 API Reference

### Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook/ingest` | Universal webhook — any source system pushes changes here |

### Registry

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/registry/register` | Register a new business in the UBID registry |
| `POST` | `/registry/seed` | Seed the registry with sample Karnataka businesses |

### Events & Evidence

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/events` | List recent canonical events |
| `GET` | `/events/{ubid}` | Get all events for a specific UBID |
| `GET` | `/evidence/{ubid}` | Get the full evidence graph for a UBID |
| `GET` | `/evidence/{ubid}/trace/{node_id}` | Trace the causal chain of a decision |

### AI Intelligence

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ai/suggest-mapping` | AI-powered schema mapping suggestion (Ollama / Gemini) |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/status` | Health check (PostgreSQL, Redis, metrics) |
| `GET` | `/docs` | Interactive Swagger documentation |

---

## 🧠 AI Integration

UBID Fabric supports **two AI backends** for intelligent schema mapping:

### Option A: Self-Hosted (Default) — Ollama + Llama 3

Runs entirely on your machine. No data leaves your network.

```bash
# 1. Uncomment the ollama service in docker-compose.yml
# 2. Start the stack
docker-compose up -d

# 3. Pull a model
docker exec ubid-ollama ollama pull llama3
```

### Option B: Cloud — Google Gemini

For higher-order reasoning on complex schemas.

```env
# In your .env file:
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

The AI will return a suggested field mapping with transformation rules.

---

## ⚙️ Configuration

All settings are managed via environment variables in `.env`:

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

---

## 🧪 Testing

The project includes **25 unit tests** covering:

- ✅ Lamport Clock monotonicity
- ✅ CRDT commutativity and idempotency (LWW, OR-Set, Monotonic)
- ✅ Deterministic event ID generation (SHA-256)
- ✅ UBID confidence classification boundaries
- ✅ Jaro-Winkler fuzzy matching accuracy

```bash
docker exec ubid-api python -m pytest tests/ -v
# ======================== 25 passed ========================
```

---

## 🛣️ Roadmap

### ✅ Completed (Prototype)
- [x] Full 6-layer pipeline (Ingest → Event → Identity → Conflict → Execute → Audit)
- [x] CRDT-based deterministic conflict resolution
- [x] Saga orchestrator with compensation and replay
- [x] Schema mapping engine with date/field transformations
- [x] AI-powered schema suggestions (Ollama + Gemini)
- [x] Glassmorphism Control Center UI
- [x] Redis Stream consumer with consumer groups
- [x] Reconciliation engine for drift detection

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
├── .env                   # Environment configuration
├── LICENSE                # Apache License 2.0
├── UBID_Fabric_Document.md          # Full technical specification
└── UBID_Fabric_Implementation_Plan.md  # Development tracker (108/108 ✅)
```

---

## 📜 License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

```
Copyright 2026 Saurabh Pawar
```

---

<p align="center">
  Built with ❤️ for Karnataka's Digital Infrastructure
</p>
