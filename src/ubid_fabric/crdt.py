"""
UBID Fabric — CRDT Implementations
Conflict-free Replicated Data Types for deterministic convergence.

Three CRDT types:
  1. LWW Register — scalar fields (address, name, date)
  2. OR-Set — set-valued fields (signatories, activities)
  3. Monotonic Merge — counters/timestamps that only go up
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog

logger = structlog.get_logger()


def lww_register_merge(
    value_a: Any,
    lamport_a: int,
    source_a: str,
    value_b: Any,
    lamport_b: int,
    source_b: str,
) -> tuple[Any, str]:
    """
    Last-Write-Wins Register merge.

    Returns (winning_value, winning_source).

    Guarantees:
      - Commutative: merge(A,B) == merge(B,A)
      - Idempotent: merge(A, merge(A,B)) == merge(A,B)
      - Deterministic tiebreak via source hash when timestamps equal
    """
    if lamport_a > lamport_b:
        return value_a, source_a
    elif lamport_b > lamport_a:
        return value_b, source_b
    else:
        # Tiebreak: deterministic hash of source system name
        hash_a = hashlib.sha256(source_a.encode()).hexdigest()
        hash_b = hashlib.sha256(source_b.encode()).hexdigest()
        if hash_a >= hash_b:
            logger.info("lww_tiebreak", winner=source_a, loser=source_b)
            return value_a, source_a
        else:
            logger.info("lww_tiebreak", winner=source_b, loser=source_a)
            return value_b, source_b


def or_set_merge(
    adds_a: list[tuple[Any, str]],  # [(element, unique_tag), ...]
    removes_a: set[str],            # {tag, ...} — tags observed when removing
    adds_b: list[tuple[Any, str]],
    removes_b: set[str],
) -> set[Any]:
    """
    Observed-Remove Set (OR-Set) merge.

    Guarantees:
      - Additions survive concurrent operations
      - If A adds "Priya" and B removes "Rajesh" concurrently,
        merged set contains "Priya" without "Rajesh"
      - If A adds "Priya" and B removes "Priya" concurrently,
        merged set CONTAINS "Priya" (add wins over concurrent remove)
    """
    all_adds = adds_a + adds_b
    all_removes = removes_a | removes_b

    result = set()
    for element, tag in all_adds:
        if tag not in all_removes:
            result.add(element)

    return result


def monotonic_merge(value_a: Any, value_b: Any) -> Any:
    """
    Monotonic merge — value never decreases.

    Used for: employee_count, last_inspection_date, version numbers.

    Guarantees:
      - Commutative: max(A,B) == max(B,A)
      - Idempotent: max(A, max(A,B)) == max(A,B)
    """
    return max(value_a, value_b)
