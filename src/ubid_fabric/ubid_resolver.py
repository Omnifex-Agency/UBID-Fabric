"""
UBID Fabric — UBID Resolution Engine (L3)
Three-state confidence model: HIGH / PROBATION / QUARANTINE.
"""

from __future__ import annotations

import structlog

from ubid_fabric.db import get_pg_connection
from ubid_fabric.models import UBIDConfidence, UBIDRecord, UBIDResolution

logger = structlog.get_logger()


def _jaro_winkler(s1: str, s2: str) -> float:
    """Simple Jaro-Winkler similarity (0.0 to 1.0). No external deps needed."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    s1_lower = s1.lower().strip()
    s2_lower = s2.lower().strip()

    if s1_lower == s2_lower:
        return 1.0

    len1, len2 = len(s1_lower), len(s2_lower)
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1_lower[i] != s2_lower[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1_lower[i] != s2_lower[k]:
            transpositions += 1
        k += 1

    jaro = (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3

    # Winkler modification: boost for common prefix
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1_lower[i] == s2_lower[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1 - jaro)


class UBIDResolver:
    """
    Resolves UBID for incoming events using multi-factor scoring.

    Scoring:
      - Exact UBID match: 0–0.40
      - Name similarity (Jaro-Winkler): 0–0.25
      - Address similarity: 0–0.20
      - Cross-system consistency: 0–0.15

    States:
      - HIGH_CONFIDENCE (≥0.95): normal propagation
      - PROBATION (0.70–0.94): propagate with ubid_verified=false
      - QUARANTINE (<0.70): halt, route to manual review
    """

    def resolve(self, entity_id: str, source_system: str,
                business_name: str = "", address: str = "") -> UBIDResolution:
        """Resolve UBID for a source entity."""

        # Step 1: Exact match via system_ids
        record = self._lookup_by_system_id(entity_id, source_system)

        if record:
            # Found exact match — high base score
            score = 0.40

            # Add name similarity if available
            if business_name and record.business_name:
                name_sim = _jaro_winkler(business_name, record.business_name)
                score += name_sim * 0.25

            # Add address similarity
            if address and record.registered_address:
                addr_sim = _jaro_winkler(address, record.registered_address)
                score += addr_sim * 0.20

            # Cross-system consistency: more systems = higher confidence
            num_systems = len(record.system_ids)
            score += min(num_systems * 0.05, 0.15)

            state = self._classify(score)
            logger.info(
                "ubid_resolved",
                ubid=record.ubid,
                confidence=round(score, 3),
                state=state.value,
                method="exact_system_id",
            )
            return UBIDResolution(
                ubid=record.ubid,
                state=state,
                confidence=round(score, 4),
                scoring_breakdown={
                    "exact_match": 0.40,
                    "name_similarity": round(score - 0.40, 3),
                },
                reason=f"Exact system ID match in {source_system}",
            )

        # Step 2: Fuzzy search by name + address
        candidates = self._fuzzy_search(business_name, address)

        if not candidates:
            logger.warning("ubid_quarantine", reason="no_match", entity_id=entity_id)
            return UBIDResolution(
                ubid="",
                state=UBIDConfidence.QUARANTINE,
                confidence=0.0,
                reason="No matching UBID found in registry",
            )

        # Score the best candidate
        best = candidates[0]
        score = 0.0
        if business_name:
            score += _jaro_winkler(business_name, best.business_name) * 0.45
        if address:
            score += _jaro_winkler(address, best.registered_address) * 0.35
        score += min(len(best.system_ids) * 0.05, 0.20)

        state = self._classify(score)
        logger.info(
            "ubid_resolved",
            ubid=best.ubid,
            confidence=round(score, 3),
            state=state.value,
            method="fuzzy_search",
        )
        return UBIDResolution(
            ubid=best.ubid,
            state=state,
            confidence=round(score, 4),
            scoring_breakdown={"name": round(score * 0.45, 3), "address": round(score * 0.35, 3)},
            reason=f"Fuzzy match (name+address) score={score:.3f}",
        )

    def register(self, record: UBIDRecord) -> None:
        """Register or update a business in the UBID registry."""
        import json
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ubid_registry (ubid, business_name, registered_address,
                        registration_date, business_type, system_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ubid) DO UPDATE SET
                        business_name = EXCLUDED.business_name,
                        registered_address = EXCLUDED.registered_address,
                        system_ids = EXCLUDED.system_ids,
                        updated_at = NOW()
                    """,
                    (record.ubid, record.business_name, record.registered_address,
                     record.registration_date, record.business_type,
                     json.dumps(record.system_ids)),
                )
                conn.commit()

    def _lookup_by_system_id(self, entity_id: str, source_system: str) -> UBIDRecord | None:
        """Find UBID by source system entity ID."""
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ubid_registry WHERE system_ids ->> %s = %s",
                    (source_system, entity_id),
                )
                row = cur.fetchone()
                if row:
                    return UBIDRecord(
                        ubid=row["ubid"],
                        business_name=row["business_name"],
                        registered_address=row["registered_address"] or "",
                        system_ids=row["system_ids"] if isinstance(row["system_ids"], dict) else {},
                    )
        return None

    def _fuzzy_search(self, name: str, address: str) -> list[UBIDRecord]:
        """Search UBID registry by name similarity."""
        if not name:
            return []
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                # Use PostgreSQL trigram or simple ILIKE for prototype
                cur.execute(
                    "SELECT * FROM ubid_registry WHERE business_name ILIKE %s LIMIT 5",
                    (f"%{name[:20]}%",),
                )
                rows = cur.fetchall()
                return [
                    UBIDRecord(
                        ubid=r["ubid"],
                        business_name=r["business_name"],
                        registered_address=r["registered_address"] or "",
                        system_ids=r["system_ids"] if isinstance(r["system_ids"], dict) else {},
                    )
                    for r in rows
                ]

    @staticmethod
    def _classify(score: float) -> UBIDConfidence:
        if score >= 0.95:
            return UBIDConfidence.HIGH_CONFIDENCE
        elif score >= 0.70:
            return UBIDConfidence.PROBATION
        else:
            return UBIDConfidence.QUARANTINE
