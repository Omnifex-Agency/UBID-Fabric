"""
UBID Fabric — Evidence Graph (L6)
Causal DAG for complete audit trail.
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog

from ubid_fabric.db import get_pg_connection
from ubid_fabric.models import EvidenceEdge, EvidenceEdgeType, EvidenceNode

logger = structlog.get_logger()


class EvidenceGraph:
    """
    Causal evidence graph — a DAG recording every decision.
    Answers: "why is this field set to this value?"
    """

    def add_node(self, node: EvidenceNode) -> UUID:
        """Insert an evidence node."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evidence_nodes (node_id, node_type, ubid, event_id, timestamp, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (node_id) DO NOTHING
                    """,
                    (str(node.node_id), node.node_type.value, node.ubid,
                     node.event_id, node.timestamp,
                     json.dumps(node.payload, default=str)),
                )
                conn.commit()
        return node.node_id

    def add_edge(self, edge: EvidenceEdge) -> UUID:
        """Insert a causal edge between nodes."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evidence_edges (edge_id, from_node_id, to_node_id, edge_type, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (edge_id) DO NOTHING
                    """,
                    (str(edge.edge_id), str(edge.from_node_id), str(edge.to_node_id),
                     edge.edge_type.value, json.dumps(edge.metadata, default=str)),
                )
                conn.commit()
        return edge.edge_id

    def link(self, from_id: UUID, to_id: UUID, edge_type: EvidenceEdgeType,
             metadata: dict | None = None) -> UUID:
        """Convenience: create and insert an edge."""
        edge = EvidenceEdge(
            from_node_id=from_id,
            to_node_id=to_id,
            edge_type=edge_type,
            metadata=metadata or {},
        )
        return self.add_edge(edge)

    def traverse_causes(self, node_id: str | UUID, max_depth: int = 20) -> list[dict]:
        """
        Walk backward through causal edges (recursive CTE).
        Returns the full causal chain leading to this node.
        """
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH RECURSIVE chain AS (
                        SELECT n.node_id, n.node_type, n.ubid, n.event_id, n.payload,
                               n.timestamp, 0 AS depth
                        FROM evidence_nodes n
                        WHERE n.node_id = %s::uuid

                        UNION ALL

                        SELECT n.node_id, n.node_type, n.ubid, n.event_id, n.payload,
                               n.timestamp, c.depth + 1
                        FROM evidence_edges e
                        JOIN evidence_nodes n ON n.node_id = e.from_node_id
                        JOIN chain c ON c.node_id = e.to_node_id
                        WHERE e.edge_type = 'caused_by'
                          AND c.depth < %s
                    )
                    SELECT * FROM chain ORDER BY depth ASC
                    """,
                    (str(node_id), max_depth),
                )
                return cur.fetchall()

    def get_field_history(self, ubid: str, field_name: str | None = None) -> list[dict]:
        """Get all evidence nodes for a UBID, optionally filtered by field."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                if field_name:
                    cur.execute(
                        """
                        SELECT * FROM evidence_nodes
                        WHERE ubid = %s AND payload->>'field' = %s
                        ORDER BY timestamp ASC
                        """,
                        (ubid, field_name),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM evidence_nodes WHERE ubid = %s ORDER BY timestamp ASC",
                        (ubid,),
                    )
                return cur.fetchall()

    def get_stats(self) -> dict:
        """Get evidence graph statistics."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM evidence_nodes")
                nodes = cur.fetchone()["cnt"]
                cur.execute("SELECT COUNT(*) as cnt FROM evidence_edges")
                edges = cur.fetchone()["cnt"]
                return {"nodes": nodes, "edges": edges}
