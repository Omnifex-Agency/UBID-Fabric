# UBID Fabric — Round 1 Submission
## Theme 2: Two-Way Interoperability between SWS and Department Systems
### Karnataka Commerce & Industry Hackathon

**Team:** Omnifex Agency
**Solution Name:** UBID Fabric v0.2
**Submission Type:** Written Solution + Working Prototype

---

## 1. Problem Understanding — In Our Own Words

Karnataka's interoperability challenge is not a technical problem at its core — it is a **governance continuity problem**.

The SWS is the intended future of record. But 40+ department systems are the *present* of record. Millions of business registrations exist only inside those legacy systems. A business that updates its address through the Factories Department portal does so today, with real legal consequences, and the officer in SWS has no idea it happened.

The temptation is to "just migrate everything." The GST rollout is the cautionary tale. A big-bang cutover at this scale doesn't fail because of bad code — it fails because of the **combinatorial complexity** of edge cases, the political reality of departments being unwilling to accept downtime, and the sheer number of businesses that fall through the cracks during the transition window.

**The only viable path is an event-streaming sidecar.** A layer that neither SWS nor any department needs to know about, which watches all state, keeps all parties consistent, and does so without requiring a single change to any source system.

Three real-world constraints define the solution:

1. **UBID is a precondition, not a feature.** Without a common identifier, there is no join. We treat UBID as a first-class citizen — every event is first resolved to a UBID before any mapping or propagation logic runs.
2. **Schemas are not just different — they are adversarial.** Departments have field names, enumerations, phone formats, date formats, and nested structures that were designed independently over decades. Any mapping layer that hardcodes field-by-field translations will fail the moment a new department is onboarded.
3. **Real business data cannot be used for testing.** Any AI-assisted mapping must work on scrambled or synthetic schema skeletons. Raw PII must never reach a hosted LLM.

---

## 2. Two-Way Propagation — Without Touching Either System

Our interoperability layer is implemented as a **pure Sidecar**. It holds API credentials for both SWS and each department system (read and write), but neither system is aware of its existence, and neither is modified.

### Direction 1: SWS → Department Systems

```
SWS raises an event
        │
        ▼
[L1] Ingestion Layer receives webhook / polls SWS API
        │
        ▼
[L2] UBID Resolver joins the SWS entity to its UBID
        │
        ▼
[L3] Event recorded in Canonical Event Store (immutable)
        │
        ▼
[L4] Schema Mapper translates Canonical → each target's schema
        │
        ▼
[L5] Saga Orchestrator writes to each department system
     ├── On success → Evidence Graph records the write
     └── On failure → Dead Letter Queue, retry with backoff
```

Each propagation to a department system is made using **that department's own API**, in **its own schema**. The Fabric does not invent a new API — it speaks every department's native language via per-department `TargetWriter` adapters.

### Direction 2: Department Systems → SWS

```
Department system mutates a record
        │
        ▼
[L1] Connector detects change (webhook / polling / snapshot diff)
        │
        ▼
[L2] UBID Resolver joins the department entity ID to its UBID
        │
        ▼
[L3] Event recorded in Canonical Event Store
        │
        ▼
[L4] Schema Mapper translates department schema → SWS schema
        │
        ▼
[L5] Saga Orchestrator writes to SWS via SWS API
     ├── On success → Evidence Graph records the write
     └── On failure → DLQ + retry
```

The Fabric never modifies SWS's internal logic. It calls SWS through the same API that any external system would use.

---

## 3. Schema Translation — Handling Heterogeneity at Scale

The translation problem is not "map field A to field B." It is "how do you manage hundreds of mappings across 40+ departments as they evolve?"

### The Transformation Engine

We built a **declarative, rule-driven transformation engine** — not a hardcoded ETL script. Each department's schema mapping is stored as a JSON document in the `schema_mappings` table. The engine reads these rules at runtime and applies them using a library of named transformation functions.

**Built-in transformation functions:**

| Function | Purpose | Example |
| :--- | :--- | :--- |
| `uppercase` | Normalize casing | `"active"` → `"ACTIVE"` |
| `concat` | Join multiple source fields | `[first, " ", last]` → full name |
| `conditional_status` | Map heterogeneous enums | `"A"` → `"ACTIVE"`, `"I"` → `"INACTIVE"` |
| `format_phone` | Normalize phone numbers | `9876543210` → `+91-9876543210` |
| `extract_pincode` | Extract from embedded strings | `"42 MG Road, Bangalore 560001"` → `560001` |
| `date_iso_to_dd_mm_yyyy` | Date format conversion | `2024-06-01` → `01/06/2024` |

### Adding a New Department

When a new department is onboarded:

1. An admin provides a sample API response (or CSV schema).
2. Our **AI Mapping Service** generates a suggested field mapping — using only the *schema skeleton* (field names, types), never real values.
3. The admin reviews the mapping in the **Dry-Run Simulator**, which shows a side-by-side comparison of raw vs. canonical data.
4. Once approved, the mapping is saved to the database.
5. **No code deployment required.** The transformation engine picks up the new rules at the next event.

This means adding a 41st department is a **UI operation**, not a software release.

### AI Safety: PII Scrambling

Before any schema or data sample reaches a hosted LLM, our `AIService` runs a **recursive PII scrambler** that traverses the entire JSON structure and replaces:
- String values → `"SYNTHETIC_STRING_X"`
- Integer values → `999X`
- Dates → `"1900-01-0X"`
- Phone/email patterns → clearly synthetic formats

The LLM only ever sees the *shape* of the data — field names, nesting, and types — never the content.

---

## 4. Discovering Changes in Systems That Don't Emit Events

This is the hardest part of the problem. Many legacy department systems were built before webhooks were a concept. Three discovery strategies are implemented, selected per-connector:

### Strategy A: Webhook (Push)
For departments that support webhooks, they register our ingest endpoint. No polling required. Latency is near-real-time.

### Strategy B: API Polling (Pull)
For departments with a `GET /records?updated_since=<timestamp>` pattern, our `StreamConsumer` polls on a configurable schedule (default: 5 minutes). It uses the `last_polled_at` cursor stored per-connector to avoid re-processing old records.

### Strategy C: Snapshot Comparison (Diff)
For departments with no event or filtering API — only a full export or paginated dump — our reconciliation engine:
1. Downloads the full snapshot.
2. Computes a content hash per entity.
3. Compares to the last stored hash in the Fabric's registry.
4. Emits a synthetic "change event" only for records where the hash differs.

This is computationally heavier but requires zero cooperation from the department system. It works against a read-only database view, a CSV export endpoint, or a nightly file drop.

---

## 5. Conflict Detection & Resolution

### The Problem
Two updates for the same UBID arrive within seconds — one from SWS, one from the Factories Department. Which one wins? How do we ensure the resolution is explainable and reversible?

### Detection: The Conflict Window
When any event for a UBID is processed, a **30-second conflict window** is opened in Redis. Any subsequent event for the same UBID within that window is flagged as a potential conflict and routed to the Conflict Engine instead of being applied immediately.

**Lamport Clocks** provide causal ordering across distributed systems. Even if two events arrive out of order (network delay), we know the correct sequence because each event carries a monotonically increasing Lamport timestamp.

### Resolution: The 4-Level Ladder

```
Level 1 — CRDT Merge
  Can the two values be mathematically merged without data loss?
  Example: employee_count is an integer, take MAX.
  → If yes, merge and apply. No conflict recorded.

Level 2 — Source Priority
  Is there a configured priority order for these two sources?
  Example: For "registered_address", SWS always wins.
  → Apply the higher-priority source's value. Record the conflict.

Level 3 — Domain Ownership
  Is there a domain-ownership rule?
  Example: "employee_count" is owned by Factories Dept.
  → Apply the owning department's value. Record the conflict.

Level 4 — Manual Review Queue
  No automatic resolution is safe.
  → Suspend the conflicting updates. Alert a human reviewer.
  → Record full details: both values, both sources, timestamps.
```

### Reversibility
Every resolved conflict stores **both the losing and winning values** in the Evidence Graph. A reviewer can:
- **Inspect:** See exactly what happened and why.
- **Override:** Apply the losing value if the resolution was wrong.
- **Replay:** Retrigger downstream propagation with the corrected value.

---

## 6. Idempotency, At-Least-Once Delivery & Audit Trail

### Idempotency
Every canonical event is assigned a **deterministic idempotency key** derived from:
- Source system
- Entity ID
- Field name
- New value
- Timestamp (rounded to 1-second precision)

This key is checked in a Redis set before processing. If it already exists, the event is **acknowledged but not re-processed**. This means retrying a failed write 50 times produces exactly one database change — the same as retrying it once.

### At-Least-Once Delivery
The Saga Orchestrator writes to department systems using **transactional outbox semantics**:
1. The intent to write is stored in the database *before* the actual HTTP call.
2. A background worker reads the outbox and makes the API call.
3. Only on HTTP 2xx is the outbox entry marked complete.
4. On failure, the entry stays, and the exponential backoff scheduler retries.

This guarantees at-least-once delivery even if the Fabric process crashes mid-propagation.

### The Dead Letter Queue (DLQ)
After a configurable number of retries (default: 5), the event is moved to the DLQ. The UI provides:
- Full error history and HTTP response codes.
- Manual retry button.
- Skip/Discard with mandatory explanation (audited).

### Audit Trail — The Evidence Graph
Every event, conflict, resolution, write, and retry creates a node in the **Evidence Graph**. This is an append-only PostgreSQL table. For any UBID, an auditor can query:

```
What changed? → Field name, old value, new value
When? → ISO timestamp with millisecond precision
Who raised it? → Source system, with their API trace ID
Where was it propagated? → List of target systems with write confirmation
Was there a conflict? → Yes/No, and if yes: what was the resolution and why?
Were there retries? → Full retry log with timestamps and error codes
```

The **Time-Travel Debugger** allows an auditor to reconstruct the exact state of any UBID at any past timestamp by replaying the event log up to that point.

---

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        UBID FABRIC v0.2                         │
│                   (Sidecar — No Source Changes)                 │
│                                                                 │
│  ┌────────────────┐      ┌────────────────────────────────────┐ │
│  │  L1: Ingestion │      │          Control Plane (UI)        │ │
│  │  ─────────────  │      │  Dashboard / Hub / Metrics /      │ │
│  │  • Webhooks    │      │  Evidence / DLQ / Time-Travel /    │ │
│  │  • API Polling │      │  File Upload / Schema Builder      │ │
│  │  • CSV Upload  │      └────────────────────────────────────┘ │
│  │  • Snapshot Diff│                                            │
│  └───────┬────────┘                                            │
│          │                                                      │
│  ┌───────▼────────┐      ┌──────────────────────────────────┐  │
│  │  L2: UBID      │      │      Canonical Event Store       │  │
│  │  Resolver      │─────▶│  (PostgreSQL — Append-Only)      │  │
│  │  (Join Key)    │      │  • Lamport Clock ordering        │  │
│  └───────┬────────┘      │  • Idempotency key index         │  │
│          │               └──────────────────────────────────┘  │
│  ┌───────▼────────┐                                            │
│  │  L3: Conflict  │◀────── Redis Conflict Window (30s)         │
│  │  Engine        │                                            │
│  │  (4-Level)     │──────▶ Evidence Graph (PostgreSQL)         │
│  └───────┬────────┘                                            │
│          │                                                      │
│  ┌───────▼────────┐      ┌──────────────────────────────────┐  │
│  │  L4: Schema    │      │   Schema Mapping Registry        │  │
│  │  Mapper        │◀─────│   (JSON rules, per department)   │  │
│  │  + AI Mapping  │      │   + AI-assisted onboarding       │  │
│  └───────┬────────┘      └──────────────────────────────────┘  │
│          │                                                      │
│  ┌───────▼────────┐      ┌──────────────────────────────────┐  │
│  │  L5: Saga      │      │        Dead Letter Queue         │  │
│  │  Orchestrator  │─────▶│  (PostgreSQL + Redis)            │  │
│  │  (Propagation) │      │  • Retry scheduler               │  │
│  └────────────────┘      │  • Manual review UI              │  │
│                          └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                                          │
    ┌────▼────┐    ┌───────────┐    ┌──────────────▼──────┐
    │   SWS   │    │ Factories │    │  Labour / Shop Est. │
    │  (API)  │    │  (API)    │    │  (API / CSV / Diff) │
    └─────────┘    └───────────┘    └─────────────────────┘
```

### Technology Choices & Rationale

| Component | Technology | Why |
| :--- | :--- | :--- |
| **API Layer** | FastAPI (Python 3.11) | Async-native, high throughput, auto-generated OpenAPI docs for auditors |
| **Persistence** | PostgreSQL 16 | ACID guarantees for the Event Store; JSONB for flexible department schemas |
| **Conflict Window** | Redis 7 | Sub-millisecond TTL-based key expiry — perfect for the 30s conflict window |
| **Schema Mapping** | JSON rules + Python engine | Zero-deployment config changes; declarative; testable without code changes |
| **AI Mapping** | Gemini / Ollama | Gemini for cloud; Ollama for air-gapped government environments |
| **Deployment** | Docker Compose | Runs on a single VM; scales to Kubernetes with no code changes |
| **Frontend** | Vanilla JS / CSS | Zero framework dependencies; runs in any browser; fast to load on govt. networks |

---

## 8. Risks, Trade-offs & Mitigations

| Risk | Severity | Mitigation |
| :--- | :--- | :--- |
| **Department API rate limits** | High | Respect `Retry-After` headers; configurable per-connector throttle |
| **Schema changes in dept. systems** | High | Schema version registry; alert on mapping failure; human review queue |
| **UBID missing for a dept. record** | High | Enrichment queue: attempt fuzzy match on name+address; flag for manual UBID assignment |
| **SWS API downtime** | Medium | Outbox pattern: queue SWS-bound writes and drain when it recovers |
| **Snapshot diff is too slow at scale** | Medium | Parallelise with worker pools; schedule off-peak; hash-based early exit |
| **Lamport clock skew across services** | Low | Lamport clocks are logical, not wall-clock — immune to NTP drift |
| **AI mapping hallucinations** | Medium | AI suggestions are never auto-applied; always require human review + dry-run validation |

**Key Trade-off: Eventual Consistency vs. Strong Consistency**

The Fabric guarantees eventual consistency — not immediate consistency. During the propagation window (typically seconds to a few minutes), SWS and a department system can temporarily hold different values. We accept this trade-off because:
- **Strong consistency would require 2-phase commit across systems we don't control** — impossible given the "no source modification" constraint.
- The conflict window and audit trail ensure that any temporary inconsistency is detected, resolved, and recorded.
- For the use cases described (address changes, signatory updates), a few seconds of lag is operationally acceptable.

---

## 9. Round 2 Implementation Plan

Assuming a sandbox with mock SWS and 3 mock department endpoints is provided:

### Week 1: Connectivity & Core Plumbing
- [ ] Configure connectors for Mock SWS and 3 mock departments
- [ ] Validate UBID resolution across all mock systems
- [ ] Smoke test: SWS → Dept propagation end-to-end

### Week 2: Schema Mapping Validation
- [ ] Use AI Mapper to generate mappings for all 3 mock department schemas
- [ ] Validate each mapping with Dry-Run Simulator
- [ ] Run the full transformation engine against all provided test payloads

### Week 3: Conflict Scenarios
- [ ] Implement the simultaneous-update test harness
- [ ] Validate all 4 conflict resolution levels with deterministic scrambled data
- [ ] Verify Evidence Graph records the conflict and resolution for every scenario

### Week 4: Resilience & Audit
- [ ] Simulate department system downtime → verify DLQ captures and retries
- [ ] Simulate crash mid-propagation → verify idempotency on restart
- [ ] Run full Time-Travel audit query for a complex multi-step scenario
- [ ] Prepare demonstration script for all success criteria

---

## 10. What Success Looks Like — Checked Against the Criteria

| Success Criterion | How We Meet It |
| :--- | :--- |
| Address change in SWS reaches every dept. with audit trail | ✅ L5 Saga Orchestrator + Evidence Graph |
| Same change in dept. reaches SWS | ✅ L1 Connectors (webhook/polling/diff) + L5 |
| Simultaneous conflict detected, resolved, auditable | ✅ Redis conflict window + 4-Level Engine + Evidence Graph |
| Any request traceable end-to-end incl. retries | ✅ Time-Travel Debugger + DLQ retry log |

---

## 11. Why This Approach Wins

### On "Clarity of Problem Understanding"
We identified the GST migration failure as the reference point the problem statement explicitly invokes, and we built the solution around the assumption that **big-bang is never coming**. Every architectural decision is made for a 5-10 year coexistence horizon, not a 6-month migration.

### On "Technical Soundness"
We didn't just describe the architecture — we built it. The Lamport Clock implementation, the CRDT merge logic, the PII scrambler, the Schema Mapper transformation engine, and the Saga Orchestrator are all running code in this submission.

### On "Feasibility Within Non-Negotiables"
Zero source system changes. UBID-first. PII-safe AI. Idempotent. Auditable. All five non-negotiables are satisfied, with technical evidence in the codebase.

### On "Failure Mode Depth"
We did not just describe happy-path propagation. The DLQ, the idempotency key system, the outbox pattern, the conflict window, and the Time-Travel debugger all exist specifically to handle the failure modes — crashes, retries, duplicates, late arrivals, and schema drift.

### On "Architecture Quality"
The system is designed for a government context: on-premise AI (Ollama), zero external dependencies in production mode, a single Docker Compose deployment, and a UI that works in any browser without a build step.

---

*UBID Fabric v0.2 — Built for Karnataka. Ready for Round 2.*
