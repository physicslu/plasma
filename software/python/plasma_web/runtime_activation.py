from __future__ import annotations

import hashlib
import json
import re
import socket
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, ContextManager, Mapping


DEFAULT_QUIESCE_TTL_S = 20
MAX_HELPER_RESPONSE_BYTES = 64 * 1024
DESIRED_RUNTIME_REVISION_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class RuntimeActivationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "RUNTIME_ACTIVATION_ERROR",
        http_status: int = 400,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.http_status = http_status
        self.context = dict(context or {})


def desired_runtime_revision(site_configuration: Mapping[str, Any]) -> str:
    sites = site_configuration.get("sites")
    if not isinstance(sites, list):
        raise RuntimeActivationError("Site Desired payload is invalid", error_type="RUNTIME_ACTIVATION_STATE_INVALID", http_status=500)
    normalized: list[dict[str, Any]] = []
    for site in sites:
        if not isinstance(site, Mapping):
            raise RuntimeActivationError("Site Desired payload contains invalid Site state", error_type="RUNTIME_ACTIVATION_STATE_INVALID", http_status=500)
        normalized.append(
            {
                "site_id": site.get("site_id"),
                "desired_revision": site.get("desired_revision"),
            }
        )
    try:
        normalized.sort(key=lambda item: int(item["site_id"]))
    except (TypeError, ValueError) as exc:
        raise RuntimeActivationError(
            "Site Desired payload contains invalid Site identity",
            error_type="RUNTIME_ACTIVATION_STATE_INVALID",
            http_status=500,
        ) from exc
    digest = hashlib.sha256(
        json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


class RuntimeActivationHelperClient:
    def __init__(self, socket_path: Path, *, timeout_s: float = 35.0) -> None:
        self.socket_path = socket_path.expanduser().resolve()
        self.timeout_s = timeout_s

    def restart_server(self, *, expected_ppu_id: str, quiesce_ttl_s: int = DEFAULT_QUIESCE_TTL_S) -> dict[str, Any]:
        request = {
            "operation": "restart_server",
            "expected_ppu_id": expected_ppu_id,
            "quiesce_ttl_s": quiesce_ttl_s,
        }
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
                    if len(response) > MAX_HELPER_RESPONSE_BYTES:
                        raise RuntimeActivationError(
                            "runtime activation helper response exceeds limit",
                            error_type="RUNTIME_ACTIVATION_HELPER_PROTOCOL_ERROR",
                            http_status=502,
                        )
        except (OSError, TimeoutError) as exc:
            raise RuntimeActivationError(
                f"runtime activation helper is unavailable: {exc}",
                error_type="RUNTIME_ACTIVATION_HELPER_UNAVAILABLE",
                http_status=503,
            ) from exc
        try:
            payload = json.loads(bytes(response).split(b"\n", 1)[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, IndexError) as exc:
            raise RuntimeActivationError(
                "runtime activation helper returned invalid JSON",
                error_type="RUNTIME_ACTIVATION_HELPER_PROTOCOL_ERROR",
                http_status=502,
            ) from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            error = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), dict) else {}
            raise RuntimeActivationError(
                str(error.get("message") or "runtime activation helper rejected request"),
                error_type=str(error.get("error_type") or "RUNTIME_ACTIVATION_HELPER_ERROR"),
                http_status=409 if "active" in str(error.get("message", "")).lower() else 502,
            )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeActivationError("runtime activation helper response is missing result", error_type="RUNTIME_ACTIVATION_HELPER_PROTOCOL_ERROR", http_status=502)
        return result


class SiteRuntimeActivationController:
    """Synchronous bounded restart transaction for applying persisted Site Desired state.

    The optional activation guard is owned by the canonical Site configuration
    controller. Production wiring supplies it so a Desired write cannot race the
    revision check, quiesce, restart, and post-restart reconciliation sequence.
    """

    def __init__(
        self,
        helper: RuntimeActivationHelperClient,
        desired_payload_provider: Callable[[], dict[str, Any]],
        runtime_snapshot_provider: Callable[[], dict[str, Any]],
        reconciliation_provider: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        ready_timeout_s: float = 20.0,
        activation_guard: Callable[[], ContextManager[None]] | None = None,
    ) -> None:
        self.helper = helper
        self.desired_payload_provider = desired_payload_provider
        self.runtime_snapshot_provider = runtime_snapshot_provider
        self.reconciliation_provider = reconciliation_provider
        self.ready_timeout_s = ready_timeout_s
        self.activation_guard = activation_guard or nullcontext

    def current(self) -> dict[str, Any]:
        payload = self.desired_payload_provider()
        configuration = payload["site_configuration"]
        return {
            "supported": True,
            "desired_runtime_revision": desired_runtime_revision(configuration),
            "reconciliation": configuration["reconciliation"],
        }

    def activate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        required = {"action", "expected_revision", "expected_ppu_id"}
        if not isinstance(request, Mapping) or set(request) != required or request.get("action") != "activate":
            raise RuntimeActivationError(
                "runtime activation request fields are invalid",
                error_type="INVALID_RUNTIME_ACTIVATION_REQUEST",
                http_status=400,
            )
        expected_revision = request.get("expected_revision")
        expected_ppu_id = request.get("expected_ppu_id")
        if not isinstance(expected_revision, str) or DESIRED_RUNTIME_REVISION_RE.fullmatch(expected_revision) is None:
            raise RuntimeActivationError("expected_revision is invalid", error_type="INVALID_RUNTIME_ACTIVATION_REQUEST", http_status=400)
        if not isinstance(expected_ppu_id, str) or not expected_ppu_id or len(expected_ppu_id) > 256:
            raise RuntimeActivationError("expected_ppu_id is invalid", error_type="INVALID_RUNTIME_ACTIVATION_REQUEST", http_status=400)

        with self.activation_guard():
            return self._activate_guarded(expected_revision, expected_ppu_id)

    def _activate_guarded(self, expected_revision: str, expected_ppu_id: str) -> dict[str, Any]:
        before_payload = self.desired_payload_provider()
        before_configuration = before_payload["site_configuration"]
        actual_revision = desired_runtime_revision(before_configuration)
        if actual_revision != expected_revision:
            raise RuntimeActivationError(
                "Site Desired state changed before runtime activation",
                error_type="RUNTIME_ACTIVATION_REVISION_CONFLICT",
                http_status=409,
                context={"expected_revision": expected_revision, "actual_revision": actual_revision},
            )
        if before_configuration["reconciliation"] == "in_sync":
            return {
                "supported": True,
                "state": "in_sync",
                "desired_runtime_revision": actual_revision,
                "ppu_id": expected_ppu_id,
                "restarted": False,
            }

        self.helper.restart_server(expected_ppu_id=expected_ppu_id)
        deadline = time.monotonic() + self.ready_timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                snapshot = self.runtime_snapshot_provider()
                ppu = snapshot.get("ppu") if isinstance(snapshot, dict) else None
                actual_ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
                if actual_ppu_id != expected_ppu_id:
                    raise RuntimeActivationError(
                        "PPU identity changed across runtime activation",
                        error_type="RUNTIME_ACTIVATION_IDENTITY_CONFLICT",
                        http_status=409,
                        context={"expected_ppu_id": expected_ppu_id, "actual_ppu_id": actual_ppu_id},
                    )
                reconciled = self.reconciliation_provider(snapshot)
                configuration = reconciled["site_configuration"]
                after_revision = desired_runtime_revision(configuration)
                if after_revision != expected_revision:
                    raise RuntimeActivationError(
                        "Site Desired state changed while runtime activation was in progress",
                        error_type="RUNTIME_ACTIVATION_REVISION_CONFLICT",
                        http_status=409,
                        context={"expected_revision": expected_revision, "actual_revision": after_revision},
                    )
                if configuration["reconciliation"] in {"in_sync", "partially_observable"}:
                    return {
                        "supported": True,
                        "state": "in_sync" if configuration["reconciliation"] == "in_sync" else "partially_observable",
                        "desired_runtime_revision": after_revision,
                        "ppu_id": expected_ppu_id,
                        "restarted": True,
                        "site_configuration": configuration,
                    }
            except RuntimeActivationError:
                raise
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        raise RuntimeActivationError(
            "Plasma Server did not return a reconciled Runtime before the activation deadline",
            error_type="RUNTIME_ACTIVATION_TIMEOUT",
            http_status=503,
            context={"last_error": str(last_error) if last_error else None},
        )
