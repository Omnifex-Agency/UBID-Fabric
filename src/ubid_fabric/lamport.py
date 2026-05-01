"""
UBID Fabric — Lamport Logical Clock
Causal ordering without synchronised wall clocks.
Thread-safe with persistent state recovery.
"""

import threading
import structlog

logger = structlog.get_logger()


class LamportClock:
    """
    Thread-safe Lamport logical clock.
    - tick() → strictly increasing for local events
    - receive(ts) → always > max(local, ts)
    """

    def __init__(self, initial_value: int = 0):
        self._counter = initial_value
        self._lock = threading.Lock()

    @property
    def value(self) -> int:
        with self._lock:
            return self._counter

    def tick(self) -> int:
        """Increment for a local event."""
        with self._lock:
            self._counter += 1
            return self._counter

    def receive(self, received_timestamp: int) -> int:
        """Update based on received event timestamp."""
        with self._lock:
            self._counter = max(self._counter, received_timestamp) + 1
            return self._counter

    def __repr__(self) -> str:
        return f"LamportClock({self._counter})"
