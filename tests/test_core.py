"""
UBID Fabric — Unit Tests for Core Components
Tests CRDT guarantees, Lamport clock, deterministic events, and UBID resolution.
Run with: pytest tests/ -v
"""

from datetime import datetime
from ubid_fabric.lamport import LamportClock
from ubid_fabric.crdt import lww_register_merge, or_set_merge, monotonic_merge
from ubid_fabric.models import (
    RawChange, FieldChange, CaptureMethod, CanonicalFieldChange,
    CRDTType, FieldType, UBIDConfidence,
)
from ubid_fabric.event_builder import EventBuilder


# ═══════════════════════════════════════════════════════════════
# Lamport Clock Tests
# ═══════════════════════════════════════════════════════════════

class TestLamportClock:

    def test_tick_increases(self):
        clock = LamportClock(0)
        v1 = clock.tick()
        v2 = clock.tick()
        v3 = clock.tick()
        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    def test_receive_takes_max_plus_one(self):
        clock = LamportClock(5)
        # Receive a higher timestamp
        result = clock.receive(100)
        assert result == 101

    def test_receive_ignores_lower(self):
        clock = LamportClock(100)
        # Receive a lower timestamp — local is higher
        result = clock.receive(50)
        assert result == 101

    def test_receive_handles_equal(self):
        clock = LamportClock(50)
        result = clock.receive(50)
        assert result == 51

    def test_monotonicity(self):
        """Clock value never decreases."""
        clock = LamportClock(0)
        values = []
        values.append(clock.tick())
        values.append(clock.receive(5))
        values.append(clock.tick())
        values.append(clock.receive(2))  # Lower than current
        values.append(clock.tick())

        for i in range(1, len(values)):
            assert values[i] > values[i - 1], f"Not monotonic at index {i}"


# ═══════════════════════════════════════════════════════════════
# CRDT Tests — Mathematical Properties
# ═══════════════════════════════════════════════════════════════

class TestLWWRegister:

    def test_higher_timestamp_wins(self):
        val, src = lww_register_merge("old", 100, "SWS", "new", 200, "FACTORIES")
        assert val == "new"
        assert src == "FACTORIES"

    def test_commutative(self):
        """merge(A,B) == merge(B,A) — order doesn't matter."""
        r1, s1 = lww_register_merge("val_A", 100, "SWS", "val_B", 200, "FAC")
        r2, s2 = lww_register_merge("val_B", 200, "FAC", "val_A", 100, "SWS")
        assert r1 == r2
        assert s1 == s2

    def test_deterministic_tiebreak(self):
        """Equal timestamps → deterministic tiebreak by source hash."""
        r1, s1 = lww_register_merge("val_A", 100, "SWS", "val_B", 100, "FAC")
        r2, s2 = lww_register_merge("val_A", 100, "SWS", "val_B", 100, "FAC")
        assert r1 == r2  # Always the same winner
        assert s1 == s2

    def test_tiebreak_commutative(self):
        """Tiebreak is also commutative."""
        r1, s1 = lww_register_merge("val_A", 100, "SWS", "val_B", 100, "FAC")
        r2, s2 = lww_register_merge("val_B", 100, "FAC", "val_A", 100, "SWS")
        assert r1 == r2
        assert s1 == s2


class TestORSet:

    def test_concurrent_add_and_remove(self):
        """Add wins over concurrent remove (add-wins semantics)."""
        adds_a = [("Priya", "tag-1")]
        removes_a: set[str] = set()

        adds_b: list[tuple] = []
        removes_b = {"tag-1"}  # B observed tag-1 and removed it

        # But A also added with a NEW tag
        adds_a.append(("Priya", "tag-2"))

        result = or_set_merge(adds_a, removes_a, adds_b, removes_b)
        assert "Priya" in result  # tag-2 wasn't in removes

    def test_union_of_adds(self):
        adds_a = [("Priya", "t1"), ("Rajesh", "t2")]
        adds_b = [("Suresh", "t3")]
        result = or_set_merge(adds_a, set(), adds_b, set())
        assert result == {"Priya", "Rajesh", "Suresh"}

    def test_commutative(self):
        adds_a = [("A", "t1"), ("B", "t2")]
        removes_a = {"t3"}
        adds_b = [("C", "t3"), ("D", "t4")]
        removes_b = {"t1"}

        r1 = or_set_merge(adds_a, removes_a, adds_b, removes_b)
        r2 = or_set_merge(adds_b, removes_b, adds_a, removes_a)
        assert r1 == r2


class TestMonotonicMerge:

    def test_takes_max(self):
        assert monotonic_merge(45, 52) == 52
        assert monotonic_merge(52, 45) == 52

    def test_commutative(self):
        assert monotonic_merge(10, 20) == monotonic_merge(20, 10)

    def test_idempotent(self):
        assert monotonic_merge(10, monotonic_merge(10, 20)) == monotonic_merge(10, 20)


# ═══════════════════════════════════════════════════════════════
# Canonical Event Builder Tests
# ═══════════════════════════════════════════════════════════════

class TestEventBuilder:

    def _make_raw(self, source="SWS", entity_id="SWS-001",
                  field="registered_address", old_val="old", new_val="new"):
        return RawChange(
            connector_id="test-connector",
            source_system=source,
            entity_type="business_registration",
            entity_id=entity_id,
            changed_fields=[FieldChange(field_name=field, old_value=old_val, new_value=new_val)],
            change_timestamp=datetime(2026, 5, 1, 10, 0, 0),
            capture_method=CaptureMethod.WEBHOOK,
        )

    def test_deterministic_event_id(self):
        """Same input → same event_id, always."""
        clock = LamportClock(99)
        builder = EventBuilder(clock)
        raw = self._make_raw()

        event = builder.build(raw, ubid="UBID-KA-2024-00000001")

        # Rebuild with same clock state
        clock2 = LamportClock(99)
        builder2 = EventBuilder(clock2)
        event2 = builder2.build(raw, ubid="UBID-KA-2024-00000001")

        assert event.event_id == event2.event_id

    def test_different_input_different_id(self):
        """Different input → different event_id."""
        clock = LamportClock(0)
        builder = EventBuilder(clock)

        event1 = builder.build(self._make_raw(new_val="addr_1"), ubid="UBID-1")
        event2 = builder.build(self._make_raw(new_val="addr_2"), ubid="UBID-1")

        assert event1.event_id != event2.event_id

    def test_crdt_type_assignment(self):
        """Fields get correct CRDT types based on config."""
        clock = LamportClock(0)
        builder = EventBuilder(clock)

        raw = RawChange(
            connector_id="test",
            source_system="SWS",
            entity_type="business",
            entity_id="SWS-001",
            changed_fields=[
                FieldChange(field_name="registered_address", old_value="a", new_value="b"),
                FieldChange(field_name="employee_count", old_value=10, new_value=15),
                FieldChange(field_name="authorised_signatories", old_value=None, new_value=["Priya"]),
            ],
            change_timestamp=datetime(2026, 5, 1),
            capture_method=CaptureMethod.WEBHOOK,
        )

        event = builder.build(raw, ubid="UBID-1")

        crdt_map = {fc.field_name: fc.crdt_type for fc in event.field_changes}
        assert crdt_map["registered_address"] == CRDTType.LWW_REGISTER
        assert crdt_map["employee_count"] == CRDTType.MONOTONIC_COUNTER
        assert crdt_map["authorised_signatories"] == CRDTType.OR_SET


# ═══════════════════════════════════════════════════════════════
# UBID Resolution Tests (no DB — just scoring logic)
# ═══════════════════════════════════════════════════════════════

class TestUBIDConfidenceClassification:

    def test_high_confidence(self):
        from ubid_fabric.ubid_resolver import UBIDResolver
        assert UBIDResolver._classify(0.95) == UBIDConfidence.HIGH_CONFIDENCE
        assert UBIDResolver._classify(1.0) == UBIDConfidence.HIGH_CONFIDENCE

    def test_probation(self):
        from ubid_fabric.ubid_resolver import UBIDResolver
        assert UBIDResolver._classify(0.70) == UBIDConfidence.PROBATION
        assert UBIDResolver._classify(0.94) == UBIDConfidence.PROBATION

    def test_quarantine(self):
        from ubid_fabric.ubid_resolver import UBIDResolver
        assert UBIDResolver._classify(0.69) == UBIDConfidence.QUARANTINE
        assert UBIDResolver._classify(0.0) == UBIDConfidence.QUARANTINE


class TestJaroWinkler:

    def test_exact_match(self):
        from ubid_fabric.ubid_resolver import _jaro_winkler
        assert _jaro_winkler("hello", "hello") == 1.0

    def test_similar_strings(self):
        from ubid_fabric.ubid_resolver import _jaro_winkler
        score = _jaro_winkler("Bangalore Tech Solutions", "Bangalore Tech Solution")
        assert score > 0.9

    def test_different_strings(self):
        from ubid_fabric.ubid_resolver import _jaro_winkler
        score = _jaro_winkler("Bangalore Tech", "Mysore Silk Emporium")
        assert score < 0.7

    def test_empty_strings(self):
        from ubid_fabric.ubid_resolver import _jaro_winkler
        assert _jaro_winkler("", "hello") == 0.0
        assert _jaro_winkler("hello", "") == 0.0
