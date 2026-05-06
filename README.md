# 🧬 UBID Fabric v0.2: Deterministic Interoperability for Karnataka SWS

**The backbone of data sovereignty and seamless cross-departmental synchronization.**

UBID Fabric is a high-performance, deterministic interoperability layer designed to unify disparate business registries (SWS, Factories, Labour, Commercial Taxes) into a single, canonical **Unique Business Identifier (UBID)** ecosystem. 

---

## 🚀 Key Features

*   **Interoperability Hub:** A unified command center to manage both **Ingestion** (Incoming) and **Propagation** (Outgoing) in real-time.
*   **AI-Assisted Field Mapping:** Zero-code integration using Gemini/Ollama. **PII-safe** — all AI calls use scrambled data.
*   **4-Level Conflict Resolution:** CRDT → Source Priority → Domain Ownership → Manual Review.
*   **Evidence Graph:** Tamper-evident audit trail with 100% traceability.
*   **CSV File Ingestion:** Upload department data dumps for batch processing.
*   **Dynamic Schema Evolution:** Add custom fields to the UBID registry via the UI without SQL migrations.
*   **Time-Travel Debugging:** Reconstruct the state of any UBID at any historical point.
*   **Drift Analytics:** Identify which departments are most often out-of-sync.
*   **RBAC Security:** 4 roles (Admin, Operator, Auditor, Viewer) with granular permissions.
*   **Self-Healing Propagation:** Dead Letter Queue (DLQ) with manual/automated retry.

---

## 🏗️ 5-Layer Architecture

1.  **L1: Universal Ingestion** — Webhooks, API Polling, CSV File Upload, AI Mapping.
2.  **L2: UBID Resolution** — Cross-referencing disparate System IDs to a single UBID.
3.  **L3: Canonical Event Store** — Immutable event log with Lamport Clock ordering.
4.  **L4: Intelligent Mapping** — Transformation engine with `concat`, `conditional_status`, `format_phone`, etc.
5.  **L5: Propagation (The Saga)** — Reliable delivery with retries, DLQ, and compensation.

---

## 🛠️ Tech Stack

*   **Backend:** FastAPI (Python 3.11+), PostgreSQL (Persistence), Redis (Conflict Window & Queue).
*   **Frontend:** Vanilla JS / CSS (Glassmorphism UI).
*   **AI Engine:** Gemini 1.5 Pro / Ollama (Local LLM). PII-scrambled calls only.
*   **Deployment:** Docker Compose (3 containers: API, PostgreSQL, Redis).

---

## 🚦 How to Run

### Prerequisites
*   Docker & Docker Compose installed
*   (Optional) Gemini API Key or Ollama running locally

### Step 1: Clone & Configure
```bash
git clone <repo-url>
cd rasu
cp .env.example .env
# Edit .env if you want to use Gemini AI (set AI_PROVIDER=gemini and AI_API_KEY=your-key)
```

### Step 2: Start the Infrastructure
```bash
docker-compose up --build -d
```
This starts 3 containers:
- `ubid-postgres` — PostgreSQL 16 (port 5432)
- `ubid-redis` — Redis 7 (port 6379)
- `ubid-api` — FastAPI application (port 8000)

### Step 3: (Alternative) Run Locally Without Docker
```bash
# Start PostgreSQL and Redis via Docker only
docker-compose up postgres redis -d

# Create a virtual environment and install
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -e ".[dev]"

# Run the API server
uvicorn ubid_fabric.app:app --reload --port 8000
```

### Step 4: Access the Application
- **Control Center UI:** http://localhost:8000/ui/index.html
- **API Documentation (Swagger):** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/status

---

## ✅ How to Verify It's Working

### 1. Check System Health
```bash
curl http://localhost:8000/status
```
Expected: `{"status": "healthy", "components": {"postgresql": "up", "redis": "up"}, ...}`

### 2. Seed Demo Data
```bash
curl -X POST http://localhost:8000/registry/seed
```
Expected: `{"status": "seeded", "count": 5}`

### 3. Simulate a Department Update
```bash
curl -X POST http://localhost:8000/webhook/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_system": "FACTORIES",
    "entity_type": "factory",
    "entity_id": "FAC-1001",
    "business_name": "Bangalore Tech Solutions Pvt Ltd",
    "address": "42 MG Road, Bangalore",
    "changes": [
      {"field": "employee_count", "old": 50, "new": 55},
      {"field": "licence_status", "old": "PENDING", "new": "ACTIVE"}
    ]
  }'
```
Expected: `{"status": "accepted", "result": {"status": "processed", ...}}`

### 4. Verify the Event Was Stored
```bash
curl http://localhost:8000/events/UBID-KA-2024-00000001
```

### 5. Check Metrics
```bash
curl http://localhost:8000/api/metrics
```

### 6. Time-Travel a UBID
```bash
curl http://localhost:8000/api/metrics/time-travel/UBID-KA-2024-00000001
```

### 7. Upload a CSV File (via UI)
1. Go to the **File Upload** tab in the Control Center.
2. Set Source System to `LABOUR`.
3. Upload a CSV with columns like `company_name`, `addr`, `reg_id`.
4. Set field mappings: `{"company_name": "business_name", "addr": "registered_address", "reg_id": "entity_id"}`
5. Click **Upload & Process**.

---

## 📡 Full API Reference

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `POST` | `/webhook/ingest` | Universal data ingestion |
| `POST` | `/registry/seed` | Seed demo data |
| `POST` | `/registry/register` | Register a new business |
| `GET` | `/events/{ubid}` | Get events for a UBID |
| `GET` | `/events` | Get recent events |
| `GET` | `/evidence/{ubid}` | Get audit trail for a UBID |
| `GET` | `/status` | System health check |
| `GET/POST` | `/api/connectors` | Manage ingestion connectors |
| `GET/POST` | `/api/targets` | Manage propagation targets |
| `POST` | `/api/ingest/file` | CSV file upload |
| `POST` | `/api/simulator/dry-run` | Test mappings without saving |
| `GET/POST` | `/api/schema/custom-fields` | Dynamic schema management |
| `GET` | `/api/registry/{ubid}` | Get full UBID record |
| `PATCH` | `/api/registry/{ubid}/metadata` | Update dynamic fields |
| `GET` | `/api/metrics` | Observability metrics |
| `GET` | `/api/metrics/drift` | Drift analytics |
| `GET` | `/api/metrics/time-travel/{ubid}` | Time-travel debugger |
| `GET` | `/api/security/roles` | List RBAC roles |
| `GET` | `/api/security/audit-log` | Security audit log |
| `POST` | `/mock/dept/sws/webhook` | Mock SWS endpoint |
| `POST` | `/mock/dept/factories/webhook` | Mock Factories endpoint |
| `POST` | `/mock/dept/labour/webhook` | Mock Labour endpoint |

---

## 📺 Demo Instructions
See [DEMO_GUIDE.md](./DEMO_GUIDE.md) for a structured 7-minute walkthrough for your presentation.

## 📐 Architecture Details
See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full technical architecture with data flow diagrams.

## 📄 License
This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

