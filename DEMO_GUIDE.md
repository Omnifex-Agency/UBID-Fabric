# 📺 UBID Fabric v0.2: 7-Minute Demo Guide

This guide provides a structured walkthrough for recording a professional demo video or performing a live presentation of the UBID Fabric.

---

## ⏱️ Timeline Overview

1.  **Introduction (0:00 - 0:45):** The problem of data silos and the UBID solution.
2.  **The Command Center (0:45 - 1:30):** Real-time monitoring dashboard.
3.  **Low-Code Ingestion (1:30 - 2:30):** Setting up a new source with AI Mapping + Dry-Run Simulator.
4.  **Propagation Hub (2:30 - 3:30):** Managing targets and schema translation.
5.  **CSV File Upload (3:30 - 4:15):** Batch ingestion for legacy departments.
6.  **Metrics & Time-Travel (4:15 - 5:30):** Observability, drift analytics, and historical debugging.
7.  **Evidence & Governance (5:30 - 6:30):** Audit lineage and the Dead Letter Queue.
8.  **Conclusion (6:30 - 7:00):** Impact and scalability.

---

## 🎙️ Script & Actions

### 1. Introduction
*   **Action:** Show the Dashboard with "System Online" status.
*   **Script:** "Welcome to the UBID Fabric v0.2—the deterministic interoperability layer for government registries. When a business changes its address in the Factories department, the SWS registry is often left out of sync. UBID Fabric fixes this by creating a single, canonical 'Golden Record' that synchronizes in real-time across all departments."

### 2. The Command Center
*   **Action:** Hover over the stats cards showing Total Events, Evidence Nodes, and Lamport Clock.
*   **Script:** "This is our Command Center. Administrators can see every business event as it happens. We use Lamport Clocks to ensure correct ordering, even if events arrive out of sequence."

### 3. Low-Code Ingestion
*   **Action:** Click 'Interoperability Hub' → '+ Add Source'. Enter a URL, click 'Test', then 'Auto-Map with AI', then 'Run Simulator'.
*   **Script:** "Onboarding a new department takes minutes, not months. I provide their API URL, test it to get sample data, and our AI automatically maps their fields to our canonical schema. The Dry-Run Simulator shows me exactly how their data will look after transformation—before I save anything."

### 4. Propagation Setup
*   **Action:** Show the right side of the Hub. Click '+ Add Target'. Use a mock URL like `http://localhost:8000/mock/dept/labour/webhook`.
*   **Script:** "Interoperability is two-way. We configure target systems to receive converged data. I can use our built-in mock department endpoints for testing. Field mappings ensure each department receives data in their native format."

### 5. CSV File Upload
*   **Action:** Click 'File Upload' tab. Upload a sample CSV. Show the results.
*   **Script:** "Many government departments still work with batch files. Our File Upload tab lets them drop a CSV, define field mappings, and the Fabric converts every row into a Canonical Event automatically. This handles departments that don't have modern APIs."

### 6. Metrics & Time-Travel
*   **Action:** Click 'Metrics' tab. Show the stats cards, source breakdown chart, and drift table. Then use the Time-Travel Debugger.
*   **Script:** "The Metrics tab gives real-time visibility. We track DLQ depth, conflict rates, and propagation success. The Drift Analytics table shows which departments are most often out-of-sync. And the Time-Travel Debugger lets us reconstruct the exact state of any business record at any point in history—critical for government audits."

### 7. Evidence & Governance
*   **Action:** Click 'Evidence Graph' tab, then 'Dead Letter Queue'.
*   **Script:** "Trust is built on transparency. The Evidence Graph shows the full audit lineage for every UBID. If a target system is down, the Dead Letter Queue captures the failure for retry. All AI calls use PII-scrambled data, ensuring raw government data never leaves our servers."

### 8. Conclusion
*   **Action:** Return to the Dashboard.
*   **Script:** "UBID Fabric v0.2 transforms fragmented bureaucracies into a unified data organism. With AI-powered mapping, 4-level conflict resolution, CSV ingestion, time-travel debugging, and PII-safe AI—it provides the foundation for a truly digital and interoperable government. Thank you."

---

## 🧪 Pre-Demo Setup Checklist

1.  **Start the system:** `docker-compose up --build -d`
2.  **Seed demo data:** `curl -X POST http://localhost:8000/registry/seed`
3.  **Simulate an event:** `curl -X POST http://localhost:8000/webhook/ingest -H "Content-Type: application/json" -d '{"source_system":"FACTORIES","entity_type":"factory","entity_id":"FAC-1001","business_name":"Bangalore Tech Solutions","changes":[{"field":"employee_count","old":50,"new":55}]}'`
4.  **Prepare a sample CSV** with columns: `reg_id, company_name, addr, status`
5.  **Open the UI:** http://localhost:8000/ui/index.html

---

## 🎥 Tips for Recording
*   **Resolution:** 1080p or 4k.
*   **Browser:** Use Chrome/Edge in Full Screen (F11).
*   **Audio:** Use a dedicated microphone for clear voiceover.
*   **Swagger:** Keep http://localhost:8000/docs open in another tab for API demos.

