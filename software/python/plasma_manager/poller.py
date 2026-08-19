from __future__ import annotations

from copy import deepcopy
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Protocol


class FleetSnapshotSource(Protocol):
    def fleet_snapshot(self) -> dict[str, Any]: ...


class FleetPoller:
    """Background fleet polling with a thread-safe last-completed snapshot cache."""

    def __init__(self, source: FleetSnapshotSource, poll_interval_s: float) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")
        self.source = source
        self.poll_interval_s = float(poll_interval_s)
        self._state_lock = Lock()
        self._lifecycle_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._snapshot: dict[str, Any] | None = None
        self._last_refresh_monotonic: float | None = None
        self._last_refresh_error: str | None = None

    def start(self) -> None:
        """Prime the cache once, then refresh it periodically in the background."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.refresh()
            self._thread = Thread(
                target=self._run,
                name="plasma-manager-fleet-poller",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_s: float | None = None) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
            thread.join(timeout_s)
            if thread.is_alive():
                raise RuntimeError("Plasma Manager fleet poller did not stop within timeout")
            self._thread = None

    def refresh(self) -> dict[str, Any]:
        """Perform one fleet poll and atomically publish the completed snapshot."""
        try:
            snapshot = self.source.fleet_snapshot()
        except Exception as exc:
            with self._state_lock:
                self._last_refresh_error = f"{type(exc).__name__}: {exc}"
            raise

        with self._state_lock:
            self._snapshot = snapshot
            self._last_refresh_monotonic = monotonic()
            self._last_refresh_error = None
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        """Return the cached snapshot without contacting any PPU."""
        with self._state_lock:
            if self._snapshot is None or self._last_refresh_monotonic is None:
                raise RuntimeError("Plasma Manager fleet snapshot cache is not initialized")
            snapshot = deepcopy(self._snapshot)
            age_s = max(0.0, monotonic() - self._last_refresh_monotonic)
            refresh_error = self._last_refresh_error

        snapshot["cache"] = {
            "mode": "background",
            "poll_interval_s": self.poll_interval_s,
            "age_s": round(age_s, 3),
            "last_refresh_error": refresh_error,
        }
        return snapshot

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval_s):
            try:
                self.refresh()
            except Exception:
                # Keep serving the last completed snapshot. The cache metadata exposes
                # the refresh failure while the next interval attempts recovery.
                continue
