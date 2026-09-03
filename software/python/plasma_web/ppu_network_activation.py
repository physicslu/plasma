from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .ppu_network_settings import PPUNetworkSettingsController


ACTIVE_STATES = frozenset({"scheduled", "applying", "applied_waiting_commit", "rolling_back"})
MIN_ROLLBACK_TIMEOUT_S = 2
MAX_ROLLBACK_TIMEOUT_S = 120
DEFAULT_APPLY_DELAY_S = 0.35
HELPER_SHUTDOWN_WAIT_S = 7.0


class PPUNetworkActivationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "PPU_NETWORK_ACTIVATION_ERROR",
        http_status: int = 400,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.http_status = http_status
        self.context = dict(context or {})


class PPUNetworkActivationHelperClient:
    """Minimal Unix-socket client for the privileged local network helper.

    The Gateway process stays unprivileged. Only the helper may mutate the Linux
    network namespace. Each connection carries one JSON-line request and one
    JSON-line response.
    """

    def __init__(self, socket_path: str | Path, *, timeout_s: float = 5.0) -> None:
        self.socket_path = Path(socket_path).expanduser().resolve()
        self.timeout_s = timeout_s

    def _request(self, operation: str, **payload: Any) -> dict[str, Any]:
        request = {"operation": operation, **payload}
        raw = (json.dumps(request, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout_s)
                client.connect(str(self.socket_path))
                client.sendall(raw)
                response = bytearray()
                while b"\n" not in response:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if len(response) > 1024 * 1024:
                        raise PPUNetworkActivationError(
                            "network helper response exceeds 1 MiB",
                            error_type="PPU_NETWORK_HELPER_PROTOCOL_ERROR",
                            http_status=502,
                        )
        except (OSError, TimeoutError) as exc:
            raise PPUNetworkActivationError(
                f"PPU network activation helper is unavailable: {exc}",
                error_type="PPU_NETWORK_HELPER_UNAVAILABLE",
                http_status=503,
            ) from exc
        try:
            parsed = json.loads(bytes(response).split(b"\n", 1)[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PPUNetworkActivationError(
                "PPU network activation helper returned invalid JSON",
                error_type="PPU_NETWORK_HELPER_PROTOCOL_ERROR",
                http_status=502,
            ) from exc
        if not isinstance(parsed, dict):
            raise PPUNetworkActivationError(
                "PPU network activation helper response must be an object",
                error_type="PPU_NETWORK_HELPER_PROTOCOL_ERROR",
                http_status=502,
            )
        if parsed.get("ok") is not True:
            error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
            raise PPUNetworkActivationError(
                str(error.get("message") or "PPU network activation helper rejected request"),
                error_type=str(error.get("error_type") or "PPU_NETWORK_HELPER_ERROR"),
                http_status=502,
                context=error.get("context") if isinstance(error.get("context"), dict) else None,
            )
        result = parsed.get("result")
        if not isinstance(result, dict):
            raise PPUNetworkActivationError(
                "PPU network activation helper response is missing result",
                error_type="PPU_NETWORK_HELPER_PROTOCOL_ERROR",
                http_status=502,
            )
        return result

    def snapshot(self) -> dict[str, Any]:
        return self._request("snapshot")

    def apply(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("apply", settings=dict(settings))

    def restore(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("restore", snapshot=dict(snapshot))


@dataclass(slots=True)
class _Transaction:
    activation_id: str
    state: str
    ppu_id: str
    revision: int
    candidate: dict[str, Any]
    previous_snapshot: dict[str, Any]
    rollback_timeout_s: int
    scheduled_at_epoch_s: float
    deadline_epoch_s: float | None = None
    committed_revision: int | None = None
    actual_after_apply: dict[str, Any] | None = None
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "state": self.state,
            "ppu_id": self.ppu_id,
            "revision": self.revision,
            "candidate": dict(self.candidate),
            "previous_snapshot": dict(self.previous_snapshot),
            "rollback_timeout_s": self.rollback_timeout_s,
            "scheduled_at_epoch_s": self.scheduled_at_epoch_s,
            "deadline_epoch_s": self.deadline_epoch_s,
            "committed_revision": self.committed_revision,
            "actual_after_apply": dict(self.actual_after_apply) if self.actual_after_apply is not None else None,
            "reason": self.reason,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "_Transaction":
        required = {
            "activation_id",
            "state",
            "ppu_id",
            "revision",
            "candidate",
            "previous_snapshot",
            "rollback_timeout_s",
            "scheduled_at_epoch_s",
            "deadline_epoch_s",
            "committed_revision",
            "actual_after_apply",
            "reason",
            "error",
        }
        if set(raw) != required:
            raise ValueError("activation journal fields are invalid")
        candidate = raw["candidate"]
        previous = raw["previous_snapshot"]
        actual_after = raw["actual_after_apply"]
        if not isinstance(candidate, dict) or not isinstance(previous, dict):
            raise ValueError("activation journal network snapshots must be objects")
        if actual_after is not None and not isinstance(actual_after, dict):
            raise ValueError("activation journal actual_after_apply must be an object or null")
        return cls(
            activation_id=str(raw["activation_id"]),
            state=str(raw["state"]),
            ppu_id=str(raw["ppu_id"]),
            revision=int(raw["revision"]),
            candidate=dict(candidate),
            previous_snapshot=dict(previous),
            rollback_timeout_s=int(raw["rollback_timeout_s"]),
            scheduled_at_epoch_s=float(raw["scheduled_at_epoch_s"]),
            deadline_epoch_s=float(raw["deadline_epoch_s"]) if raw["deadline_epoch_s"] is not None else None,
            committed_revision=int(raw["committed_revision"]) if raw["committed_revision"] is not None else None,
            actual_after_apply=dict(actual_after) if actual_after is not None else None,
            reason=str(raw["reason"]) if raw["reason"] is not None else None,
            error=str(raw["error"]) if raw["error"] is not None else None,
        )


class PPUNetworkActivationController:
    """PPU-owned safe activation transaction with bounded automatic rollback."""

    def __init__(
        self,
        settings: PPUNetworkSettingsController,
        helper: PPUNetworkActivationHelperClient | None,
        journal_path: str | Path | None,
        ppu_id_provider: Callable[[], str],
        *,
        apply_delay_s: float = DEFAULT_APPLY_DELAY_S,
    ) -> None:
        self.settings = settings
        self.helper = helper
        self.journal_path = Path(journal_path).expanduser().resolve() if journal_path else None
        self.ppu_id_provider = ppu_id_provider
        self.apply_delay_s = max(0.0, float(apply_delay_s))
        self._lock = threading.RLock()
        self._commit_event = threading.Event()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._committed_revision: int | None = None
        self._transaction: _Transaction | None = self._load_journal()
        if self._transaction is not None:
            self._committed_revision = self._transaction.committed_revision
            if self._transaction.state in ACTIVE_STATES:
                self._recover_interrupted_transaction()

    @property
    def supported(self) -> bool:
        return self.helper is not None

    def active(self) -> bool:
        with self._lock:
            return self._transaction is not None and self._transaction.state in ACTIVE_STATES

    def status(self) -> dict[str, Any]:
        with self._lock:
            transaction = self._transaction
            if not self.supported:
                return {"supported": False, "state": "not_implemented"}
            if transaction is None:
                return {
                    "supported": True,
                    "state": "idle",
                    "activation_id": None,
                    "revision": None,
                    "ppu_id": None,
                    "deadline_epoch_s": None,
                    "committed_revision": self._committed_revision,
                    "reason": None,
                    "error": None,
                }
            return {
                "supported": True,
                "state": transaction.state,
                "activation_id": transaction.activation_id,
                "revision": transaction.revision,
                "ppu_id": transaction.ppu_id,
                "deadline_epoch_s": transaction.deadline_epoch_s,
                "committed_revision": transaction.committed_revision,
                "reason": transaction.reason,
                "error": transaction.error,
            }

    def schedule(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        if self.helper is None:
            raise PPUNetworkActivationError(
                "PPU network activation helper is not configured",
                error_type="PPU_NETWORK_ACTIVATION_UNAVAILABLE",
                http_status=503,
            )
        required = {"action", "expected_revision", "expected_ppu_id", "rollback_timeout_s"}
        if not isinstance(raw, Mapping):
            raise PPUNetworkActivationError(
                "PPU network activation request must be an object",
                error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST",
                http_status=400,
            )
        if set(raw) != required:
            raise PPUNetworkActivationError(
                "PPU network activation request fields are invalid",
                error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST",
                http_status=400,
                context={
                    "missing_fields": sorted(required - set(raw)),
                    "unknown_fields": sorted(set(raw) - required),
                },
            )
        if raw["action"] != "apply":
            raise PPUNetworkActivationError(
                "PPU network activation action must be apply",
                error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST",
                http_status=400,
            )
        revision = raw["expected_revision"]
        timeout = raw["rollback_timeout_s"]
        expected_ppu_id = raw["expected_ppu_id"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise PPUNetworkActivationError("expected_revision must be a positive integer", error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not MIN_ROLLBACK_TIMEOUT_S <= timeout <= MAX_ROLLBACK_TIMEOUT_S:
            raise PPUNetworkActivationError(
                f"rollback_timeout_s must be {MIN_ROLLBACK_TIMEOUT_S}..{MAX_ROLLBACK_TIMEOUT_S}",
                error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST",
            )
        if not isinstance(expected_ppu_id, str) or not expected_ppu_id:
            raise PPUNetworkActivationError("expected_ppu_id must be a non-empty string", error_type="INVALID_PPU_NETWORK_ACTIVATION_REQUEST")

        with self._lock:
            if self._transaction is not None and self._transaction.state in ACTIVE_STATES:
                raise PPUNetworkActivationError(
                    "another PPU network activation is already active",
                    error_type="PPU_NETWORK_ACTIVATION_BUSY",
                    http_status=409,
                    context={"activation_id": self._transaction.activation_id, "state": self._transaction.state},
                )
            current = self.settings.current()
            if current["revision"] != revision:
                raise PPUNetworkActivationError(
                    "desired PPU network revision changed before activation",
                    error_type="PPU_NETWORK_REVISION_CONFLICT",
                    http_status=409,
                    context={"expected_revision": revision, "actual_revision": current["revision"]},
                )
            actual_ppu_id = self.ppu_id_provider()
            if actual_ppu_id != expected_ppu_id:
                raise PPUNetworkActivationError(
                    "PPU identity does not match activation request",
                    error_type="PPU_NETWORK_IDENTITY_CONFLICT",
                    http_status=409,
                    context={"expected_ppu_id": expected_ppu_id, "actual_ppu_id": actual_ppu_id},
                )
            previous = self.helper.snapshot()
            transaction = _Transaction(
                activation_id=f"netact-{uuid.uuid4().hex}",
                state="scheduled",
                ppu_id=actual_ppu_id,
                revision=revision,
                candidate=dict(current),
                previous_snapshot=previous,
                rollback_timeout_s=timeout,
                scheduled_at_epoch_s=time.time(),
                committed_revision=self._committed_revision,
            )
            self._transaction = transaction
            self._commit_event.clear()
            self._stop_event.clear()
            self._persist_locked()
            self._worker = threading.Thread(target=self._run_transaction, args=(transaction.activation_id,), daemon=True)
            self._worker.start()
            return self.status()

    def commit(self, activation_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        required = {"expected_revision", "expected_ppu_id"}
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise PPUNetworkActivationError(
                "PPU network activation commit fields are invalid",
                error_type="INVALID_PPU_NETWORK_ACTIVATION_COMMIT",
                http_status=400,
            )
        with self._lock:
            transaction = self._transaction
            if transaction is None or transaction.activation_id != activation_id:
                raise PPUNetworkActivationError(
                    "PPU network activation transaction was not found",
                    error_type="PPU_NETWORK_ACTIVATION_NOT_FOUND",
                    http_status=404,
                )
            if transaction.state != "applied_waiting_commit":
                raise PPUNetworkActivationError(
                    "PPU network activation is not waiting for commit",
                    error_type="PPU_NETWORK_ACTIVATION_STATE_CONFLICT",
                    http_status=409,
                    context={"state": transaction.state},
                )
            if raw["expected_revision"] != transaction.revision:
                raise PPUNetworkActivationError(
                    "PPU network activation revision does not match commit",
                    error_type="PPU_NETWORK_REVISION_CONFLICT",
                    http_status=409,
                )
            actual_ppu_id = self.ppu_id_provider()
            if raw["expected_ppu_id"] != transaction.ppu_id or actual_ppu_id != transaction.ppu_id:
                raise PPUNetworkActivationError(
                    "PPU identity does not match activation commit",
                    error_type="PPU_NETWORK_IDENTITY_CONFLICT",
                    http_status=409,
                    context={"transaction_ppu_id": transaction.ppu_id, "actual_ppu_id": actual_ppu_id},
                )
            transaction.state = "committed"
            transaction.committed_revision = transaction.revision
            transaction.reason = "identity_verified_commit"
            self._committed_revision = transaction.revision
            self._persist_locked()
            self._commit_event.set()
            return self.status()

    def _run_transaction(self, activation_id: str) -> None:
        if self._stop_event.wait(self.apply_delay_s):
            return
        try:
            with self._lock:
                transaction = self._transaction
                if transaction is None or transaction.activation_id != activation_id or transaction.state != "scheduled":
                    return
                transaction.state = "applying"
                self._persist_locked()
                candidate = dict(transaction.candidate)
            assert self.helper is not None
            actual = self.helper.apply(candidate)
            shutdown_requested = self._stop_event.is_set()
            with self._lock:
                transaction = self._transaction
                if transaction is None or transaction.activation_id != activation_id:
                    return
                transaction.actual_after_apply = actual
                if not shutdown_requested:
                    transaction.state = "applied_waiting_commit"
                    transaction.deadline_epoch_s = time.time() + transaction.rollback_timeout_s
                self._persist_locked()
                timeout = transaction.rollback_timeout_s
            if shutdown_requested:
                self._rollback(activation_id, "gateway_shutdown")
                return

            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._rollback(activation_id, "commit_deadline_expired")
                    return
                if self._commit_event.wait(min(0.1, remaining)):
                    return
                if self._stop_event.is_set():
                    self._rollback(activation_id, "gateway_shutdown")
                    return
        except Exception as exc:
            try:
                self._rollback(activation_id, "apply_failed", error=str(exc))
            except Exception as rollback_exc:
                with self._lock:
                    transaction = self._transaction
                    if transaction is not None and transaction.activation_id == activation_id:
                        transaction.state = "recovery_required"
                        transaction.reason = "apply_and_rollback_failed"
                        transaction.error = f"apply={exc}; rollback={rollback_exc}"
                        self._persist_locked()

    def _rollback(self, activation_id: str, reason: str, *, error: str | None = None) -> None:
        assert self.helper is not None
        with self._lock:
            transaction = self._transaction
            if transaction is None or transaction.activation_id != activation_id:
                return
            if transaction.state in {"committed", "rolled_back"}:
                return
            transaction.state = "rolling_back"
            transaction.reason = reason
            transaction.error = error
            previous = dict(transaction.previous_snapshot)
            self._persist_locked()
        self.helper.restore(previous)
        with self._lock:
            transaction = self._transaction
            if transaction is None or transaction.activation_id != activation_id:
                return
            transaction.state = "rolled_back"
            transaction.deadline_epoch_s = None
            transaction.reason = reason
            transaction.error = error
            transaction.committed_revision = self._committed_revision
            self._persist_locked()

    def _recover_interrupted_transaction(self) -> None:
        transaction = self._transaction
        assert transaction is not None
        if self.helper is None:
            transaction.state = "recovery_required"
            transaction.reason = "startup_helper_unavailable"
            self._persist_locked()
            return
        try:
            self.helper.restore(transaction.previous_snapshot)
            transaction.state = "rolled_back"
            transaction.deadline_epoch_s = None
            transaction.reason = "startup_recovery"
            transaction.committed_revision = self._committed_revision
            self._persist_locked()
        except Exception as exc:
            transaction.state = "recovery_required"
            transaction.reason = "startup_recovery_failed"
            transaction.error = str(exc)
            self._persist_locked()

    def close(self) -> None:
        with self._lock:
            transaction = self._transaction
            active_id = transaction.activation_id if transaction is not None and transaction.state in ACTIVE_STATES else None
            active_state = transaction.state if active_id is not None else None
            self._stop_event.set()

        # scheduled has not mutated yet; waiting_commit has completed apply. Both
        # can be restored synchronously. During applying, however, restoring now
        # would race a still-running apply, so the worker performs rollback after
        # apply returns and observes _stop_event.
        if active_id is not None and self.helper is not None and active_state in {"scheduled", "applied_waiting_commit"}:
            try:
                self._rollback(active_id, "gateway_shutdown")
            except Exception as exc:
                self._mark_recovery_required(active_id, "gateway_shutdown_rollback_failed", str(exc))

        worker = self._worker
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=HELPER_SHUTDOWN_WAIT_S)
            if worker.is_alive() and active_id is not None:
                self._mark_recovery_required(
                    active_id,
                    "gateway_shutdown_helper_timeout",
                    "network helper did not finish within shutdown bound",
                )

    def _mark_recovery_required(self, activation_id: str, reason: str, error: str) -> None:
        with self._lock:
            transaction = self._transaction
            if transaction is None or transaction.activation_id != activation_id or transaction.state == "committed":
                return
            transaction.state = "recovery_required"
            transaction.reason = reason
            transaction.error = error
            self._persist_locked()

    def _load_journal(self) -> _Transaction | None:
        path = self.journal_path
        if path is None or not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {"schema_version", "transaction"} or raw["schema_version"] != 1:
                raise ValueError("unsupported activation journal schema")
            transaction = raw["transaction"]
            if transaction is None:
                return None
            if not isinstance(transaction, dict):
                raise ValueError("activation journal transaction must be an object")
            return _Transaction.from_dict(transaction)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PPUNetworkActivationError(
                f"cannot load PPU network activation journal: {exc}",
                error_type="PPU_NETWORK_ACTIVATION_JOURNAL_INVALID",
                http_status=500,
            ) from exc

    def _persist_locked(self) -> None:
        path = self.journal_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "transaction": self._transaction.to_dict() if self._transaction is not None else None,
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
