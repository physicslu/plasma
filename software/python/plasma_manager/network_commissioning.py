from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .client import PPUHTTPError, PPUTransportError, PPUHttpClient
from .registry import (
    REGISTRY_LIFECYCLE_COMMISSIONED,
    PPURegistryStore,
    RegistryConflictError,
    RegistryEntryNotFound,
    RegistryMutationDisabled,
    RegistryStateError,
    RegistryValidationError,
)


NETWORK_COMMISSIONING_SCHEMA_VERSION = 1
DEFAULT_ROLLBACK_TIMEOUT_S = 20
MIN_ROLLBACK_TIMEOUT_S = 2
MAX_ROLLBACK_TIMEOUT_S = 120
ACTIVE_COMMISSIONING_STATES = frozenset(
    {
        "requested",
        "desired_saved",
        "apply_requested",
        "reconnecting",
        "identity_verified",
        "activation_committed",
        "registry_reconciled",
        "rollback_wait",
    }
)
BLOCKING_COMMISSIONING_STATES = ACTIVE_COMMISSIONING_STATES | {"recovery_required"}
TERMINAL_COMMISSIONING_STATES = frozenset({"completed", "rolled_back", "failed", "recovery_required"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NetworkCommissioningError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "network_commissioning_error",
        http_status: int = 409,
        record: NetworkCommissioningRecord | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.record = record


@dataclass(frozen=True, slots=True)
class NetworkCommissioningRecord:
    transaction_id: str
    request_key: str
    request_fingerprint: str
    alias: str
    state: str
    old_endpoint: str
    candidate_endpoint: str | None
    ppu_id: str | None
    desired_revision: int | None
    activation_id: str | None
    rollback_timeout_s: int
    rollback_deadline_epoch_s: float | None
    started_at: str
    updated_at: str
    error_code: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, object | None]:
        return asdict(self)


class NetworkCommissioningStore:
    """Durable latest-transaction journal keyed by Manager registry alias."""

    def __init__(
        self,
        state_path: Path | None,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._lock = RLock()
        self._clock = clock
        self._state_path = state_path.resolve() if state_path is not None else None
        self._mutable = self._state_path is not None
        self._records: dict[str, NetworkCommissioningRecord] = {}
        if self._state_path is not None and self._state_path.exists():
            self._records = self._load(self._state_path)

    @property
    def mutable(self) -> bool:
        return self._mutable

    def get(self, alias: str) -> NetworkCommissioningRecord | None:
        with self._lock:
            return self._records.get(alias)

    def records(self) -> tuple[NetworkCommissioningRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

    def put(self, record: NetworkCommissioningRecord) -> NetworkCommissioningRecord:
        if not self._mutable:
            raise RegistryMutationDisabled(
                "Manager network commissioning requires manager.registry_state_path"
            )
        with self._lock:
            previous = dict(self._records)
            self._records[record.alias] = record
            try:
                self._persist_locked()
            except Exception:
                self._records = previous
                raise
            return record

    def _persist_locked(self) -> None:
        if self._state_path is None:
            return
        payload = {
            "schema_version": NETWORK_COMMISSIONING_SCHEMA_VERSION,
            "transactions": {
                alias: record.as_dict()
                for alias, record in sorted(self._records.items())
            },
        }
        parent = self._state_path.parent
        temporary_path: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self._state_path.name}.",
                suffix=".tmp",
                dir=parent,
            )
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
            raise RegistryStateError(
                f"cannot persist Manager network commissioning journal: {self._state_path}"
            ) from exc

    @classmethod
    def _load(cls, path: Path) -> dict[str, NetworkCommissioningRecord]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryStateError(
                f"cannot load Manager network commissioning journal: {path}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != NETWORK_COMMISSIONING_SCHEMA_VERSION:
            raise RegistryStateError("unsupported Manager network commissioning journal schema")
        transactions = raw.get("transactions")
        if not isinstance(transactions, dict):
            raise RegistryStateError("Manager network commissioning transactions must be an object")
        records: dict[str, NetworkCommissioningRecord] = {}
        expected_fields = set(NetworkCommissioningRecord.__dataclass_fields__)
        for alias, payload in transactions.items():
            if not isinstance(alias, str) or not alias or not isinstance(payload, dict):
                raise RegistryStateError("Manager network commissioning journal entry is invalid")
            if set(payload) != expected_fields:
                raise RegistryStateError("Manager network commissioning journal fields are invalid")
            try:
                record = NetworkCommissioningRecord(**payload)
            except TypeError as exc:
                raise RegistryStateError("Manager network commissioning journal entry is invalid") from exc
            if record.alias != alias:
                raise RegistryStateError("Manager network commissioning alias key does not match record")
            records[alias] = record
        return records


class NetworkCommissioningCoordinator:
    """Manager-owned static IPv4 endpoint migration transaction.

    Authorization is accepted only as an in-memory argument to one synchronous
    commissioning request. It is never written to the transaction journal.
    """

    def __init__(
        self,
        registry: PPURegistryStore,
        store: NetworkCommissioningStore,
        request_timeout_s: float,
        *,
        client_factory: Callable[[str, float], PPUHttpClient] = PPUHttpClient,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._registry = registry
        self._store = store
        self._request_timeout_s = request_timeout_s
        self._client_factory = client_factory
        self._sleep = sleeper
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._clock = clock
        self._lock = RLock()

    @staticmethod
    def state_path_for_registry(registry_state_path: Path | None) -> Path | None:
        if registry_state_path is None:
            return None
        return registry_state_path.with_name(
            f"{registry_state_path.stem}-network-commissioning.json"
        )

    def get(self, alias: str) -> NetworkCommissioningRecord | None:
        return self._store.get(alias)

    def recover(self) -> None:
        """Recover only states that are safe without persisted credentials.

        After PPU commit, registry reconciliation is Manager-local and may finish
        after restart. Any earlier ambiguous state becomes recovery_required rather
        than guessing whether a protected PPU command succeeded.
        """
        with self._lock:
            for record in self._store.records():
                if record.state in TERMINAL_COMMISSIONING_STATES:
                    continue
                if record.state in {"activation_committed", "registry_reconciled"}:
                    self._recover_committed(record)
                    continue
                self._transition(
                    record,
                    "recovery_required",
                    error_code="manager_restart_before_commit_boundary",
                    error_message=(
                        "Manager restarted before durable activation-commit evidence; "
                        "automatic endpoint mutation is refused"
                    ),
                )

    def _recover_committed(self, record: NetworkCommissioningRecord) -> None:
        candidate = record.candidate_endpoint
        if candidate is None:
            self._transition(
                record,
                "recovery_required",
                error_code="commissioning_journal_incomplete",
                error_message="Committed commissioning record has no candidate endpoint",
            )
            return
        current = self._registry.record_by_alias(record.alias)
        if current is None:
            self._transition(
                record,
                "recovery_required",
                error_code="registry_entry_missing",
                error_message="PPU registry entry disappeared after activation commit",
            )
            return
        if current.endpoint == candidate:
            reconciled = self._transition(record, "registry_reconciled")
            self._transition(reconciled, "completed", error_code=None, error_message=None)
            return
        if current.endpoint != record.old_endpoint:
            self._transition(
                record,
                "recovery_required",
                error_code="registry_endpoint_changed",
                error_message="Registry endpoint changed outside the commissioning transaction",
            )
            return
        try:
            self._registry.compare_and_swap_endpoint(
                record.alias,
                expected_endpoint=record.old_endpoint,
                new_endpoint=candidate,
            )
        except RegistryStateError as exc:
            self._transition(
                record,
                "recovery_required",
                error_code="registry_reconciliation_failed",
                error_message=str(exc),
            )
            return
        reconciled = self._transition(record, "registry_reconciled")
        self._transition(reconciled, "completed", error_code=None, error_message=None)

    def start(
        self,
        alias: str,
        desired: dict[str, Any],
        *,
        rollback_timeout_s: int = DEFAULT_ROLLBACK_TIMEOUT_S,
        request_key: str,
        authorization: str | None,
    ) -> NetworkCommissioningRecord:
        with self._lock:
            normalized_desired = self._validate_desired(desired)
            timeout = self._validate_timeout(rollback_timeout_s)
            normalized_key = self._validate_request_key(request_key)
            fingerprint = self._fingerprint(normalized_desired, timeout)

            existing = self._store.get(alias)
            if existing is not None and existing.request_key == normalized_key:
                if existing.request_fingerprint != fingerprint:
                    raise NetworkCommissioningError(
                        "Idempotency-Key was reused with different commissioning input",
                        code="idempotency_key_reuse_mismatch",
                        http_status=409,
                        record=existing,
                    )
                if existing.state == "completed":
                    return existing
                raise NetworkCommissioningError(
                    existing.error_message or f"commissioning replay is {existing.state}",
                    code=existing.error_code or "commissioning_replay_not_completed",
                    http_status=409,
                    record=existing,
                )
            if existing is not None and existing.state in BLOCKING_COMMISSIONING_STATES:
                raise NetworkCommissioningError(
                    f"PPU already has a blocking commissioning transaction in state {existing.state}",
                    code="network_commissioning_busy",
                    http_status=409,
                    record=existing,
                )

            entry = self._registry.record_by_alias(alias)
            if entry is None:
                raise NetworkCommissioningError(
                    "PPU registry alias was not found",
                    code="ppu_not_found",
                    http_status=404,
                )
            if entry.lifecycle != REGISTRY_LIFECYCLE_COMMISSIONED:
                raise NetworkCommissioningError(
                    "PPU must complete Validate & Enable before network commissioning",
                    code="ppu_not_enabled",
                    http_status=409,
                )
            if not self._registry.mutable or not self._store.mutable:
                raise NetworkCommissioningError(
                    "Manager runtime registry persistence is required for network commissioning",
                    code="registry_mutation_disabled",
                    http_status=503,
                )

            old_endpoint = entry.endpoint
            old_client = self._client_factory(old_endpoint, self._request_timeout_s)
            try:
                _, node = old_client.node(headers=self._auth_headers(authorization))
                ppu_id = self._ppu_id(node)
            except (PPUHTTPError, PPUTransportError) as exc:
                raise NetworkCommissioningError(
                    "Cannot establish canonical PPU identity on the current Plasma Gateway Endpoint",
                    code="ppu_identity_unavailable",
                    http_status=502,
                ) from exc

            now = self._clock()
            record = NetworkCommissioningRecord(
                transaction_id=str(uuid.uuid4()),
                request_key=normalized_key,
                request_fingerprint=fingerprint,
                alias=alias,
                state="requested",
                old_endpoint=old_endpoint,
                candidate_endpoint=None,
                ppu_id=ppu_id,
                desired_revision=None,
                activation_id=None,
                rollback_timeout_s=timeout,
                rollback_deadline_epoch_s=None,
                started_at=now,
                updated_at=now,
            )
            record = self._store.put(record)

            try:
                _, desired_payload = old_client.update_ppu_network_settings(
                    normalized_desired,
                    headers=self._command_headers(
                        authorization,
                        f"manager-network-{record.transaction_id}-desired",
                    ),
                )
                settings = desired_payload.get("ppu_network_settings")
                if not isinstance(settings, dict):
                    raise NetworkCommissioningError(
                        "PPU desired-state response omitted ppu_network_settings",
                        code="ppu_network_protocol_error",
                        http_status=502,
                    )
                revision = settings.get("revision")
                candidate_address = settings.get("address")
                if (
                    settings.get("mode") != "static"
                    or isinstance(revision, bool)
                    or not isinstance(revision, int)
                    or revision <= 0
                    or not isinstance(candidate_address, str)
                    or candidate_address != normalized_desired["address"]
                ):
                    raise NetworkCommissioningError(
                        "PPU desired-state response does not match the requested static network",
                        code="ppu_network_protocol_error",
                        http_status=502,
                    )
                candidate_endpoint = self._candidate_endpoint(old_endpoint, candidate_address)
                self._registry.check_endpoint_available(alias, candidate_endpoint)
                record = self._transition(
                    record,
                    "desired_saved",
                    desired_revision=revision,
                    candidate_endpoint=candidate_endpoint,
                )

                _, activation_payload = old_client.start_network_activation(
                    {
                        "action": "apply",
                        "expected_revision": revision,
                        "expected_ppu_id": ppu_id,
                        "rollback_timeout_s": timeout,
                    },
                    headers=self._command_headers(
                        authorization,
                        f"manager-network-{record.transaction_id}-apply",
                    ),
                )
                activation = activation_payload.get("activation")
                if not isinstance(activation, dict):
                    raise NetworkCommissioningError(
                        "PPU activation response omitted activation state",
                        code="ppu_network_protocol_error",
                        http_status=502,
                    )
                activation_id = activation.get("activation_id")
                deadline = activation.get("deadline_epoch_s")
                if not isinstance(activation_id, str) or not activation_id:
                    raise NetworkCommissioningError(
                        "PPU activation response omitted activation_id",
                        code="ppu_network_protocol_error",
                        http_status=502,
                    )
                if not isinstance(deadline, (int, float)):
                    deadline = self._wall_time() + timeout
                record = self._transition(
                    record,
                    "apply_requested",
                    activation_id=activation_id,
                    rollback_deadline_epoch_s=float(deadline),
                )
                record = self._transition(record, "reconnecting")

                candidate_client = self._client_factory(candidate_endpoint, self._request_timeout_s)
                self._wait_for_same_identity(
                    candidate_client,
                    expected_ppu_id=ppu_id,
                    deadline_epoch_s=float(deadline),
                    authorization=authorization,
                )
                record = self._transition(record, "identity_verified")

                _, commit_payload = candidate_client.commit_network_activation(
                    activation_id,
                    {
                        "expected_revision": revision,
                        "expected_ppu_id": ppu_id,
                    },
                    headers=self._command_headers(
                        authorization,
                        f"manager-network-{record.transaction_id}-commit",
                    ),
                )
                committed = commit_payload.get("activation")
                if not isinstance(committed, dict) or committed.get("state") != "committed":
                    raise NetworkCommissioningError(
                        "PPU did not return durable committed activation state",
                        code="ppu_network_commit_unconfirmed",
                        http_status=502,
                    )
                record = self._transition(record, "activation_committed")

                try:
                    self._registry.compare_and_swap_endpoint(
                        alias,
                        expected_endpoint=old_endpoint,
                        new_endpoint=candidate_endpoint,
                    )
                except RegistryStateError as exc:
                    record = self._transition(
                        record,
                        "recovery_required",
                        error_code="registry_reconciliation_failed",
                        error_message=str(exc),
                    )
                    raise NetworkCommissioningError(
                        "PPU activation committed but Manager registry reconciliation failed",
                        code="registry_reconciliation_failed",
                        http_status=500,
                        record=record,
                    ) from exc

                record = self._transition(record, "registry_reconciled")
                return self._transition(record, "completed", error_code=None, error_message=None)
            except NetworkCommissioningError as exc:
                if record.state == "recovery_required":
                    raise
                failed = self._handle_precommit_failure(
                    record,
                    error_code=exc.code,
                    error_message=exc.message,
                    authorization=authorization,
                )
                raise NetworkCommissioningError(
                    exc.message,
                    code=exc.code,
                    http_status=exc.http_status,
                    record=failed,
                ) from exc
            except RegistryStateError as exc:
                failed = self._handle_precommit_failure(
                    record,
                    error_code="registry_conflict",
                    error_message=str(exc),
                    authorization=authorization,
                )
                raise NetworkCommissioningError(
                    str(exc),
                    code="registry_conflict",
                    http_status=409,
                    record=failed,
                ) from exc
            except PPUTransportError as exc:
                failed = self._handle_precommit_failure(
                    record,
                    error_code="ppu_transport_error",
                    error_message=str(exc),
                    authorization=authorization,
                )
                raise NetworkCommissioningError(
                    "PPU transport failed during network commissioning",
                    code="ppu_transport_error",
                    http_status=504,
                    record=failed,
                ) from exc
            except PPUHTTPError as exc:
                failed = self._handle_precommit_failure(
                    record,
                    error_code="ppu_protocol_error",
                    error_message=str(exc),
                    authorization=authorization,
                )
                raise NetworkCommissioningError(
                    "PPU rejected or violated the network commissioning contract",
                    code="ppu_protocol_error",
                    http_status=502,
                    record=failed,
                ) from exc

    def _handle_precommit_failure(
        self,
        record: NetworkCommissioningRecord,
        *,
        error_code: str,
        error_message: str,
        authorization: str | None,
    ) -> NetworkCommissioningRecord:
        if record.state in {"activation_committed", "registry_reconciled", "completed"}:
            return self._transition(
                record,
                "recovery_required",
                error_code=error_code,
                error_message=error_message,
            )
        if record.activation_id is None:
            return self._transition(
                record,
                "failed",
                error_code=error_code,
                error_message=error_message,
            )
        waiting = self._transition(
            record,
            "rollback_wait",
            error_code=error_code,
            error_message=error_message,
        )
        return self._wait_for_rollback(waiting, authorization=authorization)

    def _wait_for_rollback(
        self,
        record: NetworkCommissioningRecord,
        *,
        authorization: str | None,
    ) -> NetworkCommissioningRecord:
        client = self._client_factory(record.old_endpoint, self._request_timeout_s)
        deadline = (record.rollback_deadline_epoch_s or self._wall_time()) + 2.0
        while self._wall_time() <= deadline:
            try:
                _, payload = client.network_activation(headers=self._auth_headers(authorization))
                activation = payload.get("activation")
                state = activation.get("state") if isinstance(activation, dict) else None
                if state == "rolled_back":
                    return self._transition(record, "rolled_back")
                if state == "recovery_required":
                    return self._transition(
                        record,
                        "recovery_required",
                        error_code=record.error_code or "ppu_recovery_required",
                        error_message=record.error_message or "PPU requires manual network recovery",
                    )
                if state == "committed":
                    return self._transition(
                        record,
                        "recovery_required",
                        error_code="unexpected_activation_commit",
                        error_message="PPU reports committed activation without Manager identity-verified commit completion",
                    )
            except (PPUHTTPError, PPUTransportError):
                pass
            self._sleep(0.25)
        return self._transition(
            record,
            "recovery_required",
            error_code=record.error_code or "rollback_unconfirmed",
            error_message=(
                f"{record.error_message or 'commissioning failed'}; automatic rollback could not be confirmed"
            ),
        )

    def _wait_for_same_identity(
        self,
        client: PPUHttpClient,
        *,
        expected_ppu_id: str,
        deadline_epoch_s: float,
        authorization: str | None,
    ) -> None:
        while self._wall_time() < deadline_epoch_s - 0.5:
            try:
                _, node = client.node(headers=self._auth_headers(authorization))
                observed = self._ppu_id(node)
                if observed != expected_ppu_id:
                    raise NetworkCommissioningError(
                        "Candidate Plasma Gateway Endpoint belongs to a different PPU",
                        code="candidate_identity_mismatch",
                        http_status=409,
                    )
                return
            except PPUTransportError:
                self._sleep(0.25)
            except PPUHTTPError:
                self._sleep(0.25)
        raise NetworkCommissioningError(
            "Candidate Plasma Gateway Endpoint did not become reachable before rollback deadline",
            code="candidate_endpoint_unreachable",
            http_status=504,
        )

    def _transition(
        self,
        record: NetworkCommissioningRecord,
        state: str,
        **changes: object,
    ) -> NetworkCommissioningRecord:
        updated = replace(record, state=state, updated_at=self._clock(), **changes)
        return self._store.put(updated)

    @staticmethod
    def _auth_headers(authorization: str | None) -> dict[str, str]:
        return {"Authorization": authorization} if authorization else {}

    @staticmethod
    def _command_headers(authorization: str | None, idempotency_key: str) -> dict[str, str]:
        headers = {"Idempotency-Key": idempotency_key}
        if authorization:
            headers["Authorization"] = authorization
        return headers

    @staticmethod
    def _ppu_id(node: dict[str, Any]) -> str:
        ppu = node.get("ppu")
        ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
        if not isinstance(ppu_id, str) or not ppu_id:
            raise PPUHTTPError("/api/node omitted canonical ppu_id")
        return ppu_id

    @staticmethod
    def _validate_request_key(value: object) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
            raise NetworkCommissioningError(
                "Idempotency-Key is required for network commissioning",
                code="idempotency_key_required",
                http_status=400,
            )
        return value.strip()

    @staticmethod
    def _validate_timeout(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not MIN_ROLLBACK_TIMEOUT_S <= value <= MAX_ROLLBACK_TIMEOUT_S:
            raise NetworkCommissioningError(
                f"rollback_timeout_s must be {MIN_ROLLBACK_TIMEOUT_S}..{MAX_ROLLBACK_TIMEOUT_S}",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        return value

    @staticmethod
    def _validate_desired(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise NetworkCommissioningError(
                "network commissioning request must include a desired object",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        required = {"mode", "address", "prefix_length", "gateway", "dns_servers"}
        if set(value) != required or value.get("mode") != "static":
            raise NetworkCommissioningError(
                "static commissioning requires exactly mode/address/prefix_length/gateway/dns_servers",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        address = value.get("address")
        prefix = value.get("prefix_length")
        if not isinstance(address, str):
            raise NetworkCommissioningError(
                "static commissioning requires an IPv4 address",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        try:
            parsed_address = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError as exc:
            raise NetworkCommissioningError(
                "static commissioning address must be valid IPv4",
                code="invalid_network_commissioning_request",
                http_status=400,
            ) from exc
        if isinstance(prefix, bool) or not isinstance(prefix, int) or not 1 <= prefix <= 32:
            raise NetworkCommissioningError(
                "static commissioning prefix_length must be 1..32",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        dns = value.get("dns_servers")
        if not isinstance(dns, list):
            raise NetworkCommissioningError(
                "dns_servers must be a list",
                code="invalid_network_commissioning_request",
                http_status=400,
            )
        return {
            "mode": "static",
            "address": str(parsed_address),
            "prefix_length": prefix,
            "gateway": value.get("gateway"),
            "dns_servers": list(dns),
        }

    @staticmethod
    def _candidate_endpoint(old_endpoint: str, address: str) -> str:
        parsed = urlsplit(old_endpoint)
        netloc = address if parsed.port is None else f"{address}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, "", "", ""))

    @staticmethod
    def _fingerprint(desired: dict[str, Any], timeout: int) -> str:
        payload = json.dumps(
            {"desired": desired, "rollback_timeout_s": timeout},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
