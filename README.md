# 🧬 UBID Fabric: Deterministic Interoperability for Karnataka SWS

**The backbone of data sovereignty and seamless cross-departmental synchronization.**

UBID Fabric is a high-performance, deterministic interoperability layer designed to unify disparate business registries (SWS, Factories, Labour, Commercial Taxes) into a single, canonical **Unique Business Identifier (UBID)** ecosystem. 

It eliminates data silos and manual reconciliation through a 5-layer architecture, AI-driven mapping, and a real-time "Command Center" for full visibility into the state's business data lifecycle.

---

## 🚀 Key Features

*   **Interoperability Hub:** A unified command center to manage both **Ingestion** (Incoming from Depts) and **Propagation** (Outgoing to Depts) in real-time.
*   **AI-Assisted Field Mapping:** Zero-code integration using Gemini/Ollama to automatically map heterogeneous JSON schemas to the UBID Canonical Format.
*   **Deterministic Canonicalization:** Automated conflict resolution and "Golden Record" generation using Lamport Clocks for causal ordering.
*   **Evidence Graph (Audit Lineage):** Every change is tracked in a tamper-evident graph, providing 100% auditability of why a piece of data changed and which department triggered it.
*   **Self-Healing Propagation:** Integrated Dead Letter Queue (DLQ) with manual/automated retry logic for resilient cross-system synchronization.
*   **Modern Visuals:** A premium, glassmorphism-inspired UI designed for high-stakes government monitoring centers.

---

## 🏗️ 5-Layer Architecture

1.  **L1: Universal Ingestion (Connectors):** Webhooks and polling connectors with AI mapping.
2.  **L2: UBID Resolution:** Cross-referencing disparate System IDs (SWS-ID, FAC-ID) to a single UBID.
3.  **L3: Canonical Event Store:** Storage of every department-specific change as a timestamped event.
4.  **L4: Intelligent Mapping:** Translating department schemas to the Fabric's master schema.
5.  **L5: Propagation (The Saga):** Reliable delivery of converged data back to department systems.

---

## 🛠️ Tech Stack

*   **Backend:** FastAPI (Python 3.11+), PostgreSQL (Persistence), Redis (Event Queue).
*   **Frontend:** Vanilla JS / CSS (Modern UI, Glassmorphism).
*   **AI Engine:** Gemini 1.5 Pro / Ollama (Local LLM support).
*   **Deployment:** Docker Compose (Containerized for any environment).

---

## 🚦 Quick Start

### 1. Requirements
*   Docker & Docker Compose
*   (Optional) Gemini API Key or Ollama running locally

### 2. Launch the Fabric
```bash
docker-compose up --build -d
```

### 3. Access the Command Center
Navigate to: `http://localhost:8000/ui/index.html`

---

## 📺 Demo Instructions
See [DEMO_GUIDE.md](./DEMO_GUIDE.md) for a structured 5-minute walkthrough for your presentation.

## 📄 License
This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
