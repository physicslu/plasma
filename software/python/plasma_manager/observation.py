from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Protocol

from .persistence import ObservationPersistence


class FleetSnapshotSource(Protocol):
    def fleet_snapshot(self) -> dict[str, Any]: ...


class FleetObservationStore:
    """Enrich current fleet observations with last-known PPU state."""

    def __init__(
        self,
        source: FleetSnapshotSource,
        persistence: ObservationPersistence | None = None,
    ) -> None:
        self.source = source
        self.persistence = persistence
        self._lock = Lock()
        self._last_known_by_endpoint: dict[str, dict[str, Any]] = {}
        self._persistence_error: str | None = None
        self._restore_persisted_records()

    def fleet_snapshot(self) -> dict[str, Any]:
        current = self.source.fleet_snapshot()
        snapshot = deepcopy(current)
        observed_at = snapshot.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at:
            raise RuntimeError("fleet snapshot is missing observed_at")

        ppus = snapshot.get("ppus")
        summary = snapshot.get("summary")
        if not isinstance(ppus, list) or not isinstance(summary, dict):
            raise RuntimeError("fleet snapshot is missing PPU observation data")

        with self._lock:
            configured_endpoints = {
                item.get("endpoint")
                for item in ppus
                if isinstance(item, dict) and isinstance(item.get("endpoint"), str)
            }
            self._last_known_by_endpoint = {
                endpoint: record
                for endpoint, record in self._last_known_by_endpoint.items()
                if endpoint in configured_endpoints
            }

            known_ppus = 0
            stale_ppus = 0
            unknown_ppus = 0

            for item in ppus:
                if not isinstance(item, dict):
                    continue
                endpoint = item.get("endpoint")
                if not isinstance(endpoint, str) or not endpoint:
                    continue

                if self._is_trusted_current_observation(item):
                    record = {
                        "observed_at": observed_at,
                        "ppu": deepcopy(item["ppu"]),
                        "sites": deepcopy(item["sites"]),
                    }
                    self._last_known_by_endpoint[endpoint] = record
                    state = "current"
                else:
                    record = self._last_known_by_endpoint.get(endpoint)
                    state = "stale" if record is not None else "unknown"

                if record is not None:
                    known_ppus += 1
                if state == "stale":
                    stale_ppus += 1
                elif state == "unknown":
                    unknown_ppus += 1

                item["observation"] = {
                    "state": state,
                    "stale": state == "stale",
                    "last_success_at": record["observed_at"] if record is not None else None,
                    "stale_age_s": self._stale_age_s(observed_at, record, state),
                }
                item["last_known"] = deepcopy(record) if record is not None else None

            summary["known_ppus"] = known_ppus
            summary["stale_ppus"] = stale_ppus
            summary["unknown_ppus"] = unknown_ppus
            records_to_persist = deepcopy(self._last_known_by_endpoint)

        self._persist_records(records_to_persist)
        snapshot["observation_store"] = self._persistence_status()
        return snapshot

    def _restore_persisted_records(self) -> None:
        if self.persistence is None:
            return
        try:
            records = self.persistence.load()
        except Exception as exc:
            self._persistence_error = f"{type(exc).__name__}: {exc}"
            return
        self._last_known_by_endpoint = deepcopy(records)
        self._persistence_error = None

    def _persist_records(self, records: dict[str, dict[str, Any]]) -> None:
        if self.persistence is None:
            return
        try:
            self.persistence.replace(records)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = None
        with self._lock:
            self._persistence_error = error

    def _persistence_status(self) -> dict[str, Any]:
        with self._lock:
            error = self._persistence_error
        return {
            "mode": self.persistence.mode if self.persistence is not None else "memory",
            "healthy": error is None,
            "last_error": error,
        }

    @staticmethod
    def _is_trusted_current_observation(item: dict[str, Any]) -> bool:
        return (
            item.get("gateway_live") is True
            and item.get("execution_ready") is True
            and item.get("contract_compatible") is True
            and item.get("identity_conflict") is False
            and isinstance(item.get("ppu"), dict)
            and isinstance(item.get("sites"), list)
            and not item.get("errors")
        )

    @staticmethod
    def _stale_age_s(
        observed_at: str,
        record: dict[str, Any] | None,
        state: str,
    ) -> float | None:
        if state == "unknown" or record is None:
            return None
        if state == "current":
            return 0.0
        try:
            current_time = datetime.fromisoformat(observed_at)
            last_success = datetime.fromisoformat(record["observed_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("fleet observation timestamps must be ISO 8601") from exc
        return round(max(0.0, (current_time - last_success).total_seconds()), 3)
