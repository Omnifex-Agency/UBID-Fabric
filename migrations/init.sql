-- ============================================================
-- UBID Fabric — Database Schema Initialization
-- ============================================================

-- ─── Canonical Events (Immutable Event Log) ─────────────────
CREATE TABLE IF NOT EXISTS canonical_events (
    event_id        VARCHAR(64) PRIMARY KEY,
    event_version   VARCHAR(10) NOT NULL DEFAULT '1.0',
    ubid            VARCHAR(50) NOT NULL,
    ubid_confidence VARCHAR(20) NOT NULL DEFAULT 'HIGH_CONFIDENCE',
    source_system   VARCHAR(50) NOT NULL,
    event_type      VARCHAR(20) NOT NULL,
    lamport_ts      BIGINT NOT NULL,
    wall_clock_ts   TIMESTAMPTZ NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    field_changes   JSONB NOT NULL,
    payload_hash    VARCHAR(64) NOT NULL,
    causality       JSONB,
    metadata        JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ce_ubid ON canonical_events (ubid);
CREATE INDEX IF NOT EXISTS idx_ce_source ON canonical_events (source_system);
CREATE INDEX IF NOT EXISTS idx_ce_lamport ON canonical_events (lamport_ts);
CREATE INDEX IF NOT EXISTS idx_ce_type_ts ON canonical_events (event_type, wall_clock_ts);
CREATE INDEX IF NOT EXISTS idx_ce_payload ON canonical_events USING gin (field_changes);

-- ─── Evidence Graph — Nodes ─────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence_nodes (
    node_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type   VARCHAR(50) NOT NULL,
    ubid        VARCHAR(50),
    event_id    VARCHAR(64),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload     JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_en_ubid ON evidence_nodes (ubid);
CREATE INDEX IF NOT EXISTS idx_en_event_id ON evidence_nodes (event_id);
CREATE INDEX IF NOT EXISTS idx_en_type_ts ON evidence_nodes (node_type, timestamp);

-- ─── Evidence Graph — Edges ─────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence_edges (
    edge_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_node_id  UUID NOT NULL REFERENCES evidence_nodes(node_id),
    to_node_id    UUID NOT NULL REFERENCES evidence_nodes(node_id),
    edge_type     VARCHAR(30) NOT NULL,
    metadata      JSONB
);

CREATE INDEX IF NOT EXISTS idx_ee_from ON evidence_edges (from_node_id);
CREATE INDEX IF NOT EXISTS idx_ee_to ON evidence_edges (to_node_id);
CREATE INDEX IF NOT EXISTS idx_ee_type ON evidence_edges (edge_type);

-- ─── Schema Mappings Registry ───────────────────────────────
CREATE TABLE IF NOT EXISTS schema_mappings (
    mapping_id      VARCHAR(100) PRIMARY KEY,
    source_system   VARCHAR(50) NOT NULL,
    target_system   VARCHAR(50) NOT NULL,
    version         VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'DRAFTED',
    field_mappings  JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_status CHECK (status IN ('DRAFTED', 'SHADOW', 'APPROVED', 'ACTIVE', 'ARCHIVED'))
);

CREATE INDEX IF NOT EXISTS idx_sm_systems ON schema_mappings (source_system, target_system);
CREATE INDEX IF NOT EXISTS idx_sm_status ON schema_mappings (status);

-- ─── UBID Registry ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ubid_registry (
    ubid            VARCHAR(50) PRIMARY KEY,
    business_name   VARCHAR(300) NOT NULL,
    registered_address TEXT,
    registration_date DATE,
    business_type   VARCHAR(50),
    system_ids      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ur_name ON ubid_registry USING gin (to_tsvector('english', business_name));

-- ─── Reconciliation State ───────────────────────────────────
CREATE TABLE IF NOT EXISTS reconciliation_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ubid            VARCHAR(50) NOT NULL,
    target_system   VARCHAR(50) NOT NULL,
    field_name      VARCHAR(100) NOT NULL,
    expected_value  TEXT,
    actual_value    TEXT,
    drift_type      VARCHAR(30),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    CONSTRAINT chk_drift CHECK (drift_type IN ('STALE', 'OUT_OF_BAND', 'PARTIAL', 'AMBIGUOUS'))
);

CREATE INDEX IF NOT EXISTS idx_rs_ubid ON reconciliation_state (ubid);
CREATE INDEX IF NOT EXISTS idx_rs_status ON reconciliation_state (status);

-- ─── Lamport Clock State ────────────────────────────────────
CREATE TABLE IF NOT EXISTS lamport_clock_state (
    clock_id    VARCHAR(50) PRIMARY KEY DEFAULT 'global',
    counter     BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO lamport_clock_state (clock_id, counter) VALUES ('global', 0)
ON CONFLICT (clock_id) DO NOTHING;
-- ─── Dead Letter Queue ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    dlq_id          SERIAL PRIMARY KEY,
    event_id        VARCHAR(64) NOT NULL,
    ubid            VARCHAR(50) NOT NULL,
    target_system   VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, target_system)
);

-- ─── Connectors Registry ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS connectors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    system_type     VARCHAR(50) NOT NULL,
    connector_type  VARCHAR(20) NOT NULL, -- 'WEBHOOK', 'API_POLLING', 'CDC'
    config          JSONB NOT NULL, -- { url, interval, auth_header, etc. }
    is_active       BOOLEAN DEFAULT TRUE,
    last_run        TIMESTAMP WITH TIME ZONE,
    last_status     VARCHAR(20) DEFAULT 'PENDING',
    success_rate    FLOAT DEFAULT 100.0,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Target Systems Table (Sending)
CREATE TABLE IF NOT EXISTS target_systems (
    id              UUID PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    system_type     VARCHAR(50) NOT NULL,
    base_url        TEXT NOT NULL,
    auth_header     TEXT,
    config          JSONB NOT NULL, -- { method, payload_template, field_mappings }
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
