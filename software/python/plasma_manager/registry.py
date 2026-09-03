from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

from .config import PPURegistryEntry, normalize_endpoint


REGISTRY_STATE_SCHEMA_VERSION = 1
REGISTRY_LIFECYCLE_PENDING = "pending"
REGISTRY_LIFECYCLE_COMMISSIONED = "commissioned"
REGISTRY_LIFECYCLE_DISABLED = "disabled"
REGISTRY_LIFECYCLES = frozenset(
    {
        REGISTRY_LIFECYCLE_PENDING,
        REGISTRY_LIFECYCLE_COMMISSIONED,
        REGISTRY_LIFECYCLE_DISABLED,
    }
)


class RegistryStateError(RuntimeError):
    """Raised when Manager-owned PPU registry state cannot be trusted or persisted."""


class RegistryValidationError(RegistryStateError):
    """Raised when a requested registry mutation is syntactically invalid."""


class RegistryMutationDisabled(RegistryStateError):
    """Raised when runtime registry mutation is not configured."""


class RegistryConflictError(RegistryStateError):
    """Raised when a registry mutation conflicts with an existing entry."""


class RegistryEntryNotFound(RegistryStateError):
    """Raised when a requested registry alias does not exist."""


@dataclass(frozen=True, slots=True)
class PPURegistryRecord:
    endpoint: str
    alias: str | None
    lifecycle: str
    registered_at: str
    updated_at: str

    def as_entry(self) -> PPURegistryEntry:
        return PPURegistryEntry(endpoint=self.endpoint, alias=self.alias)

    def as_dict(self) -> dict[str, str | None]:
        return {
            "endpoint": self.endpoint,
            "alias": self.alias,
            "lifecycle": self.lifecycle,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }


def normalize_registry_alias(value: object, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise RegistryValidationError("PPU registry alias must be a string")
    alias = value.strip()
    if not alias or len(alias) > 128 or "/" in alias or "\\" in alias:
        raise RegistryValidationError("PPU registry alias must be 1-128 characters and contain no path separators")
    return alias


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PPURegistryStore:
    """Thread-safe Manager-owned runtime registry.

    `manager.yaml` remains deployment/bootstrap configuration. When
    `registry_state_path` is configured, the first start seeds this store from
    `config.ppus`; after that, this state file becomes the runtime inventory
    source of truth for add/remove/admission lifecycle/endpoint changes.
    """

    def __init__(
        self,
        seed_entries: tuple[PPURegistryEntry, ...],
        state_path: Path | None,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._lock = RLock()
        self._clock = clock
        self._state_path = state_path.resolve() if state_path is not None else None
        self._mutable = self._state_path is not None
        if self._state_path is not None and self._state_path.exists():
            self._records = self._load(self._state_path)
        else:
            now = self._clock()
            self._records = tuple(
                PPURegistryRecord(
                    endpoint=entry.endpoint,
                    alias=entry.alias,
                    lifecycle=REGISTRY_LIFECYCLE_COMMISSIONED,
                    registered_at=now,
                    updated_at=now,
                )
                for entry in seed_entries
            )
            self._validate_records(self._records)
            if self._mutable:
                self._persist_locked()

    @property
    def mutable(self) -> bool:
        return self._mutable

    @property
    def storage_mode(self) -> str:
        return "file" if self._mutable else "config"

    def entries(self) -> tuple[PPURegistryEntry, ...]:
        with self._lock:
            return tuple(record.as_entry() for record in self._records)

    def records(self) -> tuple[PPURegistryRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def record_by_alias(self, alias: str) -> PPURegistryRecord | None:
        normalized = normalize_registry_alias(alias)
        with self._lock:
            matches = [record for record in self._records if record.alias == normalized]
            return matches[0] if len(matches) == 1 else None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            records = [record.as_dict() for record in self._records]
        return {
            "mutable": self._mutable,
            "storage": self.storage_mode,
            "ppus": records,
        }

    def add(self, *, alias: str, endpoint: str) -> PPURegistryRecord:
        self._require_mutable()
        normalized_alias = normalize_registry_alias(alias)
        try:
            normalized_endpoint = normalize_endpoint(endpoint)
        except ValueError as exc:
            raise RegistryValidationError(str(exc)) from exc
        with self._lock:
            if any(record.alias == normalized_alias for record in self._records):
                raise RegistryConflictError(f"PPU registry alias already exists: {normalized_alias}")
            if any(record.endpoint == normalized_endpoint for record in self._records):
                raise RegistryConflictError(f"PPU registry endpoint already exists: {normalized_endpoint}")
            now = self._clock()
            record = PPURegistryRecord(
                endpoint=normalized_endpoint,
                alias=normalized_alias,
                lifecycle=REGISTRY_LIFECYCLE_PENDING,
                registered_at=now,
                updated_at=now,
            )
            previous = self._records
            self._records = (*self._records, record)
            try:
                self._persist_locked()
            except Exception:
                self._records = previous
                raise
            return record

    def set_lifecycle(self, alias: str, lifecycle: str) -> PPURegistryRecord:
        self._require_mutable()
        normalized_alias = normalize_registry_alias(alias)
        if lifecycle not in {REGISTRY_LIFECYCLE_COMMISSIONED, REGISTRY_LIFECYCLE_DISABLED}:
            raise RegistryValidationError("registry lifecycle update must be commissioned or disabled")
        with self._lock:
            index = next((i for i, record in enumerate(self._records) if record.alias == normalized_alias), None)
            if index is None:
                raise RegistryEntryNotFound(f"PPU registry alias was not found: {normalized_alias}")
            current = self._records[index]
            updated = PPURegistryRecord(
                endpoint=current.endpoint,
                alias=current.alias,
                lifecycle=lifecycle,
                registered_at=current.registered_at,
                updated_at=self._clock(),
            )
            records = list(self._records)
            records[index] = updated
            previous = self._records
            self._records = tuple(records)
            try:
                self._persist_locked()
            except Exception:
                self._records = previous
                raise
            return updated

    def check_endpoint_available(self, alias: str, endpoint: str) -> str:
        normalized_alias = normalize_registry_alias(alias)
        try:
            normalized_endpoint = normalize_endpoint(endpoint)
        except ValueError as exc:
            raise RegistryValidationError(str(exc)) from exc
        with self._lock:
            if not any(record.alias == normalized_alias for record in self._records):
                raise RegistryEntryNotFound(f"PPU registry alias was not found: {normalized_alias}")
            if any(
                record.alias != normalized_alias and record.endpoint == normalized_endpoint
                for record in self._records
            ):
                raise RegistryConflictError(
                    f"candidate Plasma Gateway Endpoint already belongs to another PPU: {normalized_endpoint}"
                )
        return normalized_endpoint

    def compare_and_swap_endpoint(
        self,
        alias: str,
        *,
        expected_endpoint: str,
        new_endpoint: str,
    ) -> PPURegistryRecord:
        """Durably update one endpoint only if its previous value still matches.

        Commissioning must never overwrite an operator or concurrent transaction
        mutation that occurred after the network transaction started.
        """
        self._require_mutable()
        normalized_alias = normalize_registry_alias(alias)
        try:
            normalized_expected = normalize_endpoint(expected_endpoint)
            normalized_new = normalize_endpoint(new_endpoint)
        except ValueError as exc:
            raise RegistryValidationError(str(exc)) from exc
        with self._lock:
            index = next((i for i, record in enumerate(self._records) if record.alias == normalized_alias), None)
            if index is None:
                raise RegistryEntryNotFound(f"PPU registry alias was not found: {normalized_alias}")
            current = self._records[index]
            if current.endpoint != normalized_expected:
                raise RegistryConflictError(
                    f"PPU registry endpoint changed during commissioning: expected {normalized_expected}, found {current.endpoint}"
                )
            if any(
                i != index and record.endpoint == normalized_new
                for i, record in enumerate(self._records)
            ):
                raise RegistryConflictError(
                    f"candidate Plasma Gateway Endpoint already belongs to another PPU: {normalized_new}"
                )
            if current.endpoint == normalized_new:
                return current
            updated = PPURegistryRecord(
                endpoint=normalized_new,
                alias=current.alias,
                lifecycle=current.lifecycle,
                registered_at=current.registered_at,
                updated_at=self._clock(),
            )
            records = list(self._records)
            records[index] = updated
            previous = self._records
            self._records = tuple(records)
            try:
                self._persist_locked()
            except Exception:
                self._records = previous
                raise
            return updated

    def remove(self, alias: str) -> PPURegistryRecord:
        self._require_mutable()
        normalized_alias = normalize_registry_alias(alias)
        with self._lock:
            index = next((i for i, record in enumerate(self._records) if record.alias == normalized_alias), None)
            if index is None:
                raise RegistryEntryNotFound(f"PPU registry alias was not found: {normalized_alias}")
            removed = self._records[index]
            previous = self._records
            self._records = tuple(record for i, record in enumerate(self._records) if i != index)
            try:
                self._persist_locked()
            except Exception:
                self._records = previous
                raise
            return removed

    def _require_mutable(self) -> None:
        if not self._mutable:
            raise RegistryMutationDisabled(
                "Manager runtime PPU registry mutation is disabled; configure manager.registry_state_path"
            )

    def _persist_locked(self) -> None:
        if self._state_path is None:
            return
        payload = {
            "schema_version": REGISTRY_STATE_SCHEMA_VERSION,
            "ppus": [record.as_dict() for record in self._records],
        }
        parent = self._state_path.parent
        temporary_path: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{self._state_path.name}.", suffix=".tmp", dir=parent)
            temporary_path = Path(temporary_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._state_path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise RegistryStateError(f"cannot persist Manager runtime PPU registry: {self._state_path}") from exc

    @classmethod
    def _load(cls, path: Path) -> tuple[PPURegistryRecord, ...]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryStateError(f"cannot load Manager runtime PPU registry: {path}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != REGISTRY_STATE_SCHEMA_VERSION:
            raise RegistryStateError("unsupported Manager runtime PPU registry schema")
        raw_ppus = raw.get("ppus")
        if not isinstance(raw_ppus, list):
            raise RegistryStateError("Manager runtime PPU registry ppus must be a list")
        records: list[PPURegistryRecord] = []
        for raw_record in raw_ppus:
            if not isinstance(raw_record, dict):
                raise RegistryStateError("Manager runtime PPU registry entry must be an object")
            unexpected = set(raw_record) - {"endpoint", "alias", "lifecycle", "registered_at", "updated_at"}
            if unexpected:
                raise RegistryStateError(
                    f"unsupported Manager runtime PPU registry fields: {', '.join(sorted(unexpected))}"
                )
            try:
                endpoint = normalize_endpoint(raw_record.get("endpoint"))
            except ValueError as exc:
                raise RegistryStateError(str(exc)) from exc
            try:
                alias = normalize_registry_alias(raw_record.get("alias"), allow_none=True)
            except RegistryValidationError as exc:
                raise RegistryStateError(str(exc)) from exc
            lifecycle = raw_record.get("lifecycle")
            if lifecycle not in REGISTRY_LIFECYCLES:
                raise RegistryStateError("Manager runtime PPU registry lifecycle is invalid")
            registered_at = raw_record.get("registered_at")
            updated_at = raw_record.get("updated_at")
            if not isinstance(registered_at, str) or not registered_at:
                raise RegistryStateError("Manager runtime PPU registry registered_at is invalid")
            if not isinstance(updated_at, str) or not updated_at:
                raise RegistryStateError("Manager runtime PPU registry updated_at is invalid")
            records.append(
                PPURegistryRecord(
                    endpoint=endpoint,
                    alias=alias,
                    lifecycle=lifecycle,
                    registered_at=registered_at,
                    updated_at=updated_at,
                )
            )
        result = tuple(records)
        cls._validate_records(result)
        return result

    @staticmethod
    def _validate_records(records: tuple[PPURegistryRecord, ...]) -> None:
        endpoints = [record.endpoint for record in records]
        if len(endpoints) != len(set(endpoints)):
            raise RegistryStateError("Manager runtime PPU registry endpoints must be unique")
        aliases = [record.alias for record in records if record.alias is not None]
        if len(aliases) != len(set(aliases)):
            raise RegistryStateError("Manager runtime PPU registry aliases must be unique")
