# 📺 UBID Fabric: 5-Minute Demo Guide

This guide provides a structured walkthrough for recording a professional demo video or performing a live presentation of the UBID Fabric.

---

## ⏱️ Timeline Overview

1.  **Introduction (0:00 - 0:45):** The problem of data silos and the UBID solution.
2.  **The Command Center (0:45 - 1:30):** High-level overview of real-time monitoring.
3.  **Low-Code Ingestion (1:30 - 2:30):** Setting up a new department source with AI Mapping.
4.  **The Interoperability Hub (2:30 - 3:30):** Managing propagation and schema translation.
5.  **Evidence & Governance (3:30 - 4:30):** Audit lineage and the Dead Letter Queue.
6.  **Conclusion (4:30 - 5:00):** Impact and scalability.

---

## 🎙️ Script & Actions

### 1. Introduction
*   **Action:** Show the Dashboard with "System Online" status.
*   **Script:** "Welcome to the UBID Fabric—the deterministic interoperability layer for government registries. In heterogeneous government ecosystems, data often lives in silos. When a business changes its address in the Factories department, the SWS registry is often left out of sync. UBID Fabric fixes this by creating a single, canonical 'Golden Record' that synchronizes in real-time across all departments."

### 2. The Command Center
*   **Action:** Hover over the "Recent Activity" and "Event Timeline" on the Dashboard.
*   **Script:** "This is our Command Center. Here, administrators can see every business event as it happens across the state. We use Lamport Clocks to ensure every change is ordered correctly, even if events arrive out of sequence from different departments."

### 3. Low-Code Ingestion (Receive)
*   **Action:** Click 'Interoperability Hub' -> Left Side '+ Add Source'.
*   **Script:** "Onboarding a new department used to take months of coding. With UBID Fabric, it takes minutes. I'll add a new source for the 'Labour Department'. I simply provide their webhook URL and a sample of their JSON data. Our integrated AI then automatically maps their local fields—like 'proprietor_name'—to our canonical 'owner_name', creating a zero-code integration bridge."

### 4. Propagation Setup (Send)
*   **Action:** Show the Right Side of the Hub. Click '+ Add Target'.
*   **Script:** "Interoperability is a two-way street. Once the Fabric converges a 'Golden Record', we must propagate it back to target systems. In the Send section, we can configure dynamic targets. I can define exactly how the Fabric's data is translated back to the SWS Central Registry's API, ensuring every department stays updated with the latest, verified information."

### 5. Evidence & Governance
*   **Action:** Click 'Evidence Graph' tab, then click 'Dead Letter Queue'.
*   **Script:** "Trust is built on transparency. The Evidence Graph shows the full audit lineage for every UBID. We can trace exactly why a field changed and which department provided the evidence. If a target system is down, the Dead Letter Queue captures the failure, allowing for manual retries or automated backoffs, ensuring no data is ever lost."

### 6. Conclusion
*   **Action:** Return to the Dashboard showing active metrics.
*   **Script:** "UBID Fabric transforms fragmented bureaucracies into a single, unified data organism. It is scalable, AI-powered, and deterministic—providing the foundation for a truly digital and interoperable government. Thank you."

---

## 🎥 Tips for Recording
*   **Resolution:** 1080p or 4k.
*   **Browser:** Use Chrome/Edge in Full Screen (F11).
*   **Audio:** Use a dedicated microphone for clear voiceover.
*   **Demo Data:** Seed the registry using the '/registry/seed' endpoint (or the 'Seed Data' button if available) before starting to show a populated dashboard.
