"""
UBID Fabric — Reconciliation Engine (L6)
Detects drift between the UBID Fabric state and the Target System state.
"""

from __future__ import annotations

from typing import Any

import structlog

from ubid_fabric.config import settings
from ubid_fabric.db import get_pg_connection
from ubid_fabric.models import DriftType, ReconciliationResult

logger = structlog.get_logger()

class ReconciliationEngine:
    """
    Periodically compares the state of fields in the UBID Fabric
    with the actual state in connected target systems.
    """

    def check_drift(
        self, ubid: str, target_system: str, field: str,
        expected_value: Any, actual_value: Any
    ) -> ReconciliationResult:
        """
        Evaluate if a field in the target system matches our expected converged state.
        If it doesn't, classify the type of drift.
        """
        if expected_value == actual_value:
            return ReconciliationResult(
                ubid=ubid,
                target_system=target_system,
                field_name=field,
                expected_value=expected_value,
                actual_value=actual_value,
                match=True,
            )

        # We have drift. Classify it.
        drift_type = self._classify_drift(ubid, field, target_system, expected_value, actual_value)
        
        result = ReconciliationResult(
            ubid=ubid,
            target_system=target_system,
            field_name=field,
            expected_value=expected_value,
            actual_value=actual_value,
            match=False,
            drift_type=drift_type,
        )

        logger.warning(
            "state_drift_detected",
            ubid=ubid,
            target=target_system,
            field=field,
            drift_type=drift_type.value,
        )

        self._record_drift(result)
        return result

    def _classify_drift(
        self, ubid: str, field: str, target: str, expected: Any, actual: Any
    ) -> DriftType:
        """
        Determine *why* the drift happened.
        - STALE: Target is just behind (maybe DLQ or slow).
        - OUT_OF_BAND: Target was updated directly by a human, bypassing the fabric.
        - AMBIGUOUS: Can't easily determine.
        """
        # For prototype: simple mock classification based on DLQ status
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status FROM dead_letter_queue
                    WHERE ubid = %s AND target_system = %s AND status = 'PENDING'
                    """,
                    (ubid, target)
                )
                in_dlq = cur.fetchone()

        if in_dlq:
            return DriftType.STALE  # It's drifting because propagation failed
        
        # If no failed writes, but it's different, someone probably edited it directly
        return DriftType.OUT_OF_BAND

    def _record_drift(self, result: ReconciliationResult):
        """Save the drift to PostgreSQL for the review console."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reconciliation_state 
                    (ubid, target_system, field_name, expected_value, actual_value, drift_type, last_checked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ubid, target_system, field_name) DO UPDATE SET
                        expected_value = EXCLUDED.expected_value,
                        actual_value = EXCLUDED.actual_value,
                        drift_type = EXCLUDED.drift_type,
                        last_checked = EXCLUDED.last_checked
                    """,
                    (
                        result.ubid, result.target_system, result.field_name,
                        str(result.expected_value), str(result.actual_value),
                        result.drift_type.value, result.checked_at
                    )
                )
                conn.commit()
