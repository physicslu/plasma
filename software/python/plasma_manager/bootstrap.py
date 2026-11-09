from __future__ import annotations

import ipaddress
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from . import bootstrap_request_auth as request_auth
from .client import PPUHTTPError, PPUHttpClient
from .config import normalize_endpoint
from .registry import PPURegistryStore, RegistryEntryNotFound, normalize_registry_alias
from .owner_authorization import (
    ADMIT,
    INSTALL,
    ACTIVATE,
    ACTIVATE_FPGA_LOAD,
    OwnerAuthorizationError,
    issue_bundle_operation,
)

# Profile-scoped contract: real z2-ps owns Bootstrap on :18081. SWPC z2-like
# already uses :18081 for restricted diagnostics and is not a Bootstrap target.
BOOTSTRAP_PORT = 18081
# v2 (LOM-P2A-2): adds controller ``generation`` and ``controller_id``; v1 files
# migrate in place to generation 1 (the PPU migrates its P2A-1 token likewise).
BOOTSTRAP_CREDENTIAL_SCHEMA = 2
_LEGACY_CREDENTIAL_SCHEMA = 1
MAX_BOOTSTRAP_RESPONSE_BYTES = 4 * 1024 * 1024
MANAGED_BOOTSTRAP_TRANSPORT_ENV = "PLASMA_MANAGER_BOOTSTRAP_TRANSPORT"
MANAGED_BOOTSTRAP_TRANSPORT = "managed-gateway-prefix-v1"
MANAGED_BOOTSTRAP_PATH_PREFIX = "/__plasma/bootstrap"
MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV = "PLASMA_MANAGER_BOOTSTRAP_RUNTIME_GATEWAY_HOST"


class BootstrapManagerError(RuntimeError):
    """Raised when Manager cannot safely control a registered PPU Bootstrap."""


class BootstrapCredentialError(BootstrapManagerError):
    """Raised when Bootstrap pairing credentials are unavailable or untrustworthy."""


class ControllerReplacedError(BootstrapCredentialError):
    """The PPU now has a newer controller generation: this Manager was replaced.

    All writes stop; nothing is retried automatically. Re-enrollment (button,
    engineering CLI or SD rescue ticket) is the only way back.
    """


@dataclass(frozen=True, slots=True)
class BootstrapCredential:
    alias: str
    device_id: str
    token: str
    updated_at: str
    generation: int = 1
    controller_id: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _managed_bootstrap_transport_enabled() -> bool:
    value = os.environ.get(MANAGED_BOOTSTRAP_TRANSPORT_ENV)
    if value is None:
        return False
    if value != MANAGED_BOOTSTRAP_TRANSPORT:
        raise BootstrapManagerError(
            f"unsupported Manager Bootstrap transport policy: {value!r}"
        )
    return True


def _bootstrap_api_path(path: str) -> str:
    if not path.startswith("/"):
        raise BootstrapManagerError("Bootstrap API path must be absolute")
    if _managed_bootstrap_transport_enabled():
        return f"{MANAGED_BOOTSTRAP_PATH_PREFIX}{path}"
    return path


def _bootstrap_endpoint_policy() -> str:
    if _managed_bootstrap_transport_enabled():
        return MANAGED_BOOTSTRAP_TRANSPORT
    return "z2-ps-same-host:18081"


def bootstrap_endpoint_for_gateway(gateway_endpoint: str) -> str:
    """Resolve Bootstrap transport without changing registry endpoint semantics.

    Direct/private Manager deployments keep the same-host ``:18081`` contract.
    The Render-managed z2like-demo profile instead reuses the exact managed
    Gateway origin and reaches Bootstrap only through the fixed, allowlisted
    ``/__plasma/bootstrap`` prefix. This lets Cloudflare Access remain scoped to
    one origin while keeping the device Bootstrap on its independent :18081
    service behind SWPC.
    """

    canonical = normalize_endpoint(gateway_endpoint)
    parsed = urlsplit(canonical)
    if parsed.hostname is None:
        raise BootstrapManagerError("registered Plasma Gateway endpoint has no host")

    if _managed_bootstrap_transport_enabled():
        if parsed.scheme != "https":
            raise BootstrapManagerError(
                "managed Bootstrap transport requires the protected HTTPS Gateway origin"
            )
        return canonical

    if parsed.scheme != "http":
        raise BootstrapManagerError(
            "Bootstrap transport supports the controlled private HTTP commissioning link only"
        )
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return urlunsplit(("http", f"{host}:{BOOTSTRAP_PORT}", "", "", ""))


def _runtime_gateway_host(gateway_endpoint: str) -> str:
    if _managed_bootstrap_transport_enabled():
        raw = os.environ.get(MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV)
        if raw is None or not raw.strip() or raw != raw.strip():
            raise BootstrapManagerError(
                "managed Bootstrap transport requires a Manager-owned runtime Gateway host"
            )
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise BootstrapManagerError(
                "managed Bootstrap runtime Gateway host must be a private IPv4 address"
            ) from exc
        if (
            address.version != 4
            or not address.is_private
            or address.is_loopback
            or address.is_unspecified
            or address.is_multicast
        ):
            raise BootstrapManagerError(
                "managed Bootstrap runtime Gateway host must be a private non-loopback IPv4 address"
            )
        return str(address)

    parsed = urlsplit(gateway_endpoint)
    if parsed.hostname is None:
        raise BootstrapManagerError("registered Plasma Gateway endpoint has no host")
    return parsed.hostname


def _valid_token(value: object) -> str:
    if not isinstance(value, str):
        raise BootstrapCredentialError("Bootstrap pairing token must be a string")
    token = value.strip()
    if token != value or not 32 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        raise BootstrapCredentialError("Bootstrap pairing token must be 32-256 non-whitespace characters")
    return token


def _valid_device_id(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("ppu-device-") or not 16 <= len(value) <= 128:
        raise BootstrapCredentialError("Bootstrap device_id is invalid")
    if any(ch.isspace() for ch in value):
        raise BootstrapCredentialError("Bootstrap device_id is invalid")
    return value


def _device_id_from_status(payload: Mapping[str, Any]) -> str:
    identity = payload.get("identity")
    if not isinstance(identity, dict):
        raise BootstrapManagerError("PPU Bootstrap status is missing identity")
    try:
        return _valid_device_id(identity.get("device_id"))
    except BootstrapCredentialError as exc:
        raise BootstrapManagerError(str(exc)) from exc


class BootstrapCredentialStore:
    """Manager-owned device secrets, separate from public registry state."""

    def __init__(self, path: Path | None) -> None:
        self.path = path.resolve() if path is not None else None
        self._lock = RLock()
        self._credentials: dict[str, BootstrapCredential] = {}
        if self.path is not None and self.path.exists():
            self._credentials = self._load(self.path)
            self.migrate_in_place()

    @staticmethod
    def path_for_registry(registry_state_path: Path | None) -> Path | None:
        if registry_state_path is None:
            return None
        return registry_state_path.with_name("bootstrap-credentials.json")

    @property
    def mutable(self) -> bool:
        return self.path is not None

    def paired(self, alias: str) -> bool:
        normalized = normalize_registry_alias(alias)
        with self._lock:
            return normalized in self._credentials

    def credential_for(self, alias: str) -> tuple[str, str]:
        """(enrolled device_id, credential); the device is proven per request."""
        record = self.record_for(alias)
        return record.device_id, record.token

    def record_for(self, alias: str) -> BootstrapCredential:
        normalized = normalize_registry_alias(alias)
        with self._lock:
            credential = self._credentials.get(normalized)
            if credential is None:
                raise BootstrapCredentialError(f"PPU is not enrolled with this Control Station: {normalized}")
            return credential

    def set(self, alias: str, device_id: str, token: str, *, generation: int = 1,
            controller_id: str | None = None) -> None:
        if self.path is None:
            raise BootstrapCredentialError(
                "Bootstrap credential persistence is disabled; configure Manager runtime registry state"
            )
        normalized = normalize_registry_alias(alias)
        validated_device = _valid_device_id(device_id)
        validated_token = _valid_token(token)
        with self._lock:
            previous = dict(self._credentials)
            if type(generation) is not int or generation < 1:
                raise BootstrapCredentialError("controller generation is invalid")
            self._credentials[normalized] = BootstrapCredential(
                normalized,
                validated_device,
                validated_token,
                _utc_now(),
                generation,
                controller_id,
            )
            try:
                self._persist_locked()
            except Exception:
                self._credentials = previous
                raise

    def remove(self, alias: str) -> None:
        normalized = normalize_registry_alias(alias)
        if self.path is None:
            return
        with self._lock:
            if normalized not in self._credentials:
                return
            previous = dict(self._credentials)
            del self._credentials[normalized]
            try:
                self._persist_locked()
            except Exception:
                self._credentials = previous
                raise

    def public_state(self, alias: str) -> dict[str, object]:
        normalized = normalize_registry_alias(alias)
        with self._lock:
            credential = self._credentials.get(normalized)
        return {
            "paired": credential is not None,
            "device_id": credential.device_id if credential is not None else None,
            "credential_persistence": "file" if self.path is not None else "disabled",
            "updated_at": credential.updated_at if credential is not None else None,
            "controller_generation": credential.generation if credential is not None else None,
            "controller_id": credential.controller_id if credential is not None else None,
        }

    def _persist_locked(self) -> None:
        if self.path is None:
            return
        payload = {
            "schema_version": BOOTSTRAP_CREDENTIAL_SCHEMA,
            "credentials": {
                alias: {
                    "device_id": credential.device_id,
                    "token": credential.token,
                    "updated_at": credential.updated_at,
                    "generation": credential.generation,
                    "controller_id": credential.controller_id,
                }
                for alias, credential in sorted(self._credentials.items())
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        except OSError as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise BootstrapCredentialError(f"cannot persist Bootstrap credentials: {self.path}") from exc

    @classmethod
    def _load(cls, path: Path) -> dict[str, BootstrapCredential]:
        try:
            mode = path.stat().st_mode & 0o777
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapCredentialError(f"cannot load Bootstrap credentials: {path}") from exc
        if mode & 0o077:
            raise BootstrapCredentialError("Bootstrap credential file must be mode 0600 or stricter")
        schema = payload.get("schema_version") if isinstance(payload, dict) else None
        if schema not in (BOOTSTRAP_CREDENTIAL_SCHEMA, _LEGACY_CREDENTIAL_SCHEMA):
            raise BootstrapCredentialError("unsupported Bootstrap credential schema")
        raw = payload.get("credentials")
        if not isinstance(raw, dict):
            raise BootstrapCredentialError("Bootstrap credentials must be a mapping")
        fields = ({"device_id", "token", "updated_at"} if schema == _LEGACY_CREDENTIAL_SCHEMA
                  else {"device_id", "token", "updated_at", "generation", "controller_id"})
        result: dict[str, BootstrapCredential] = {}
        for alias, record in raw.items():
            normalized = normalize_registry_alias(alias)
            if (
                normalized != alias
                or not isinstance(record, dict)
                or set(record) != fields
            ):
                raise BootstrapCredentialError("Bootstrap credential entry is invalid")
            device_id = _valid_device_id(record.get("device_id"))
            token = _valid_token(record.get("token"))
            updated_at = record.get("updated_at")
            if not isinstance(updated_at, str) or not updated_at:
                raise BootstrapCredentialError("Bootstrap credential updated_at is invalid")
            # v1 (P2A-1 pairing) == controller generation 1 on the migrated PPU.
            generation = record.get("generation", 1)
            controller_id = record.get("controller_id")
            if (type(generation) is not int or generation < 1
                    or (controller_id is not None and type(controller_id) is not str)):
                raise BootstrapCredentialError("Bootstrap credential controller fields are invalid")
            result[normalized] = BootstrapCredential(
                normalized, device_id, token, updated_at, generation, controller_id)
        return result

    def migrate_in_place(self) -> bool:
        """Rewrite a v1 file as v2 (same secrets, generation 1); idempotent."""
        if self.path is None or not self.path.exists():
            return False
        try:
            schema = json.loads(self.path.read_text(encoding="utf-8")).get("schema_version")
        except (OSError, ValueError, AttributeError) as exc:
            raise BootstrapCredentialError(f"cannot load Bootstrap credentials: {self.path}") from exc
        if schema == BOOTSTRAP_CREDENTIAL_SCHEMA:
            return False
        with self._lock:
            self._persist_locked()
        return True


class BootstrapHttpClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.client = PPUHttpClient(endpoint, timeout_s)
        self.timeout_s = timeout_s
        # Enrolled controller generation; set per call by the coordinator.
        self.expected_generation: int | None = None

    def _challenge(self, device_id: str, generation: int | None = None) -> str:
        status, payload, _headers, _body = self._exchange("GET", request_auth.CHALLENGE_PATH)
        return check_challenge(status, payload, device_id=device_id, generation=generation)

    def _exchange(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        raw: bytes | None = None,
        timeout_s: float | None = None,
    ) -> tuple[int, dict[str, Any], dict[str, str], bytes]:
        request_headers = {"Accept": "application/json", **(headers or {})}
        if raw is not None:
            request_headers["Content-Type"] = "application/json"
        try:
            status, response_headers, response_body = self.client.relay(
                method,
                _bootstrap_api_path(path),
                headers=request_headers,
                body=raw,
                timeout_s=self.timeout_s if timeout_s is None else timeout_s,
                max_response_bytes=MAX_BOOTSTRAP_RESPONSE_BYTES,
                extra_response_headers=frozenset({request_auth.RESPONSE_HEADER.lower()}),
            )
        except PPUHTTPError as exc:
            raise BootstrapManagerError(str(exc)) from exc
        return status, self._payload(response_headers, response_body), response_headers, response_body

    def _json(
        self,
        method: str,
        path: str,
        *,
        credential: str | None = None,
        device_id: str | None = None,
        body: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
        generation: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """One Bootstrap call; authenticated calls never send the credential.

        With a credential, the request is MACed under a fresh PPU nonce for the
        paired ``device_id`` and the response is accepted only with the PPU's
        response MAC. An unauthenticated 401/503 refusal is returned as a
        failure status; any other unproven response fails closed.
        """
        raw = None
        if body is not None:
            raw = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        if credential is None:
            status, payload, _headers, _body = self._exchange(method, path, raw=raw, timeout_s=timeout_s)
            return status, payload
        if device_id is None:
            raise BootstrapManagerError("authenticated Bootstrap call requires the paired device_id")
        nonce = self._challenge(device_id, generation if generation is not None
                                else self.expected_generation)
        try:
            header, context = request_auth.sign_request(
                credential=credential, method=method, path=path, body=raw,
                device_id=device_id, nonce=nonce,
            )
        except request_auth.BootstrapRequestAuthError as exc:
            raise BootstrapCredentialError(str(exc)) from exc
        status, payload, response_headers, response_body = self._exchange(
            method, path, headers={"Authorization": header}, raw=raw, timeout_s=timeout_s,
        )
        proof = next((value for key, value in response_headers.items()
                      if key.lower() == request_auth.RESPONSE_HEADER.lower()), None)
        if proof is None and status in (401, 503):
            return status, payload
        try:
            request_auth.verify_response(
                credential=credential, context=context, status=status,
                body=response_body, header=proof,
            )
        except request_auth.BootstrapRequestAuthError as exc:
            raise BootstrapManagerError(
                "PPU Bootstrap response is not authenticated by the paired device") from exc
        return status, payload

    @staticmethod
    def _payload(response_headers: Mapping[str, str], response_body: bytes) -> dict[str, Any]:
        media_type = response_headers.get("Content-Type", response_headers.get("content-type", ""))
        if "application/json" not in media_type:
            raise BootstrapManagerError("PPU Bootstrap returned a non-JSON response")
        try:
            payload = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapManagerError("PPU Bootstrap returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BootstrapManagerError("PPU Bootstrap response must be a JSON object")
        return payload

    def status(self, credential: str | None = None, device_id: str | None = None) -> tuple[int, dict[str, Any]]:
        return self._json("GET", "/v1/status", credential=credential, device_id=device_id)

    def create_upload(self, credential: str, device_id: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", "/v1/uploads", credential=credential, device_id=device_id,
                          body=body, timeout_s=10.0)

    def append_chunk(self, credential: str, device_id: str, upload_id: str,
                     body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", f"/v1/uploads/{upload_id}/chunks", credential=credential,
                          device_id=device_id, body=body, timeout_s=30.0)

    def commit_upload(self, credential: str, device_id: str, upload_id: str) -> tuple[int, dict[str, Any]]:
        return self._json(
            "POST",
            f"/v1/uploads/{upload_id}/commit",
            credential=credential,
            device_id=device_id,
            body={"action": "commit"},
            timeout_s=30.0,
        )

    def start_deployment(self, credential: str, device_id: str,
                         body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", "/v1/deployments", credential=credential, device_id=device_id,
                          body=body, timeout_s=10.0)

    def assets(self, credential: str, device_id: str) -> tuple[int, dict[str, Any]]:
        """PPU-verified Active Asset Set identity (read-only, response MACed)."""
        return self._json("GET", "/v1/assets", credential=credential, device_id=device_id,
                          timeout_s=10.0)


def check_challenge(status: int, payload: Mapping[str, Any], *, device_id: str,
                    generation: int | None) -> str:
    """Validate a P2A-1 challenge (Bootstrap or Gateway) for this enrollment.

    A higher ``controller_generation`` means another Control Station took
    over: stop, never retry. A lower one means the PPU controller state went
    backwards (restored backup / reset): stop as well.
    """
    if (status != 200 or payload.get("ok") is not True
            or payload.get("schema") != request_auth.SCHEMA
            or not request_auth.valid_nonce(payload.get("nonce"))):
        raise BootstrapManagerError("PPU request-authentication challenge is unavailable")
    if payload.get("device_id") != device_id:
        raise BootstrapCredentialError(
            "registered alias now resolves to a different PPU device_id; re-enrollment is required")
    current = payload.get("controller_generation")
    if generation is not None:
        if type(current) is not int:
            raise BootstrapManagerError("PPU did not report its controller generation")
        if current > generation:
            raise ControllerReplacedError(
                f"PPU was enrolled by another Control Station (controller generation {current} > "
                f"{generation}); this Manager stopped all writes")
        if current < generation:
            raise BootstrapCredentialError(
                f"PPU controller generation went backwards ({current} < {generation}); re-enrollment is required")
    return payload["nonce"]


def _hex_field(value: object, length: int, label: str) -> str:
    if (type(value) is not str or len(value) != length
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise BootstrapManagerError(f"{label} is invalid")
    return value


def _issue(token: str, action: str, device_id: str, digest: str, transaction_id: str) -> dict[str, Any]:
    try:
        return issue_bundle_operation(
            credential=token, action=action, device_id=device_id,
            subject_sha256=digest, transaction_id=transaction_id,
        )
    except OwnerAuthorizationError as exc:
        raise BootstrapManagerError(str(exc)) from exc


class ManagerBootstrapCoordinator:
    """Exact Manager policy boundary for PPU Bootstrap operations."""

    def __init__(
        self,
        registry: PPURegistryStore,
        credentials: BootstrapCredentialStore,
        timeout_s: float,
        *,
        client_factory=BootstrapHttpClient,
    ) -> None:
        self.registry = registry
        self.credentials = credentials
        self.timeout_s = timeout_s
        self.client_factory = client_factory

    def _entry(self, alias: str):
        normalized = normalize_registry_alias(alias)
        record = self.registry.record_by_alias(normalized)
        if record is None:
            raise RegistryEntryNotFound(f"PPU registry alias was not found: {normalized}")
        return normalized, record

    def _live(self, alias: str):
        normalized, record = self._entry(alias)
        endpoint = bootstrap_endpoint_for_gateway(record.endpoint)
        client = self.client_factory(endpoint, self.timeout_s)
        status, payload = client.status()
        bootstrap = payload.get("bootstrap")
        if status != 200 or not isinstance(bootstrap, dict) or bootstrap.get("state") != "bootstrap_ready":
            raise BootstrapManagerError("PPU Bootstrap is not ready")
        device_id = _device_id_from_status(payload)
        return normalized, record, client, payload, device_id

    def _authenticated(self, alias: str):
        """Paired device proven by a MACed status, never by an anonymous read."""
        normalized, record = self._entry(alias)
        enrolled = self.credentials.record_for(normalized)
        device_id, token = enrolled.device_id, enrolled.token
        client = self.client_factory(bootstrap_endpoint_for_gateway(record.endpoint), self.timeout_s)
        client.expected_generation = enrolled.generation
        status, payload = client.status(token, device_id)
        if status in (401, 503):
            raise BootstrapCredentialError(
                "PPU Bootstrap rejected the enrolled credential; re-enrollment is required")
        bootstrap = payload.get("bootstrap")
        if status != 200 or not isinstance(bootstrap, dict) or bootstrap.get("state") != "bootstrap_ready":
            raise BootstrapManagerError("PPU Bootstrap is not ready")
        if _device_id_from_status(payload) != device_id:
            raise BootstrapCredentialError(
                "registered alias now resolves to a different Bootstrap device_id; explicit re-pairing is required"
            )
        return normalized, record, client, payload, device_id, token

    def status(self, alias: str) -> dict[str, Any]:
        normalized, _record, _client, payload, device_id = self._live(alias)
        pairing = dict(self.credentials.public_state(normalized))
        # device_match means the paired credential is PROVEN by this device's
        # MACed status, not merely that an anonymous status echoed the ID.
        pairing["device_match"] = pairing.get("device_id") is None
        pairing["device_authenticated"] = False
        if pairing.get("paired"):
            try:
                *_ignored, authenticated, proven_device, _token = self._authenticated(normalized)
            except ControllerReplacedError as exc:
                pairing["controller_replaced"] = True
                pairing["controller_replaced_message"] = str(exc)
            except BootstrapManagerError:
                pass
            else:
                payload, device_id = authenticated, proven_device
                pairing["device_match"] = pairing["device_authenticated"] = True
        return {
            "ok": True,
            "ppu_alias": normalized,
            "bootstrap_endpoint_policy": _bootstrap_endpoint_policy(),
            "pairing": pairing,
            "bootstrap": payload,
            "upstream_status": 200,
        }


    def assets(self, alias: str) -> dict[str, Any]:
        """Read the PPU-verified Active Asset Set identity; fail closed when untrusted."""
        _normalized, _record, client, _payload, device_id, token = self._authenticated(alias)
        status, payload = client.assets(token, device_id)
        record = payload.get("assets") if status == 200 else None
        if (not isinstance(record, dict)
                or record.get("schema") != "plasma.ppu.active-assets.v1"
                or record.get("state") not in {"EMPTY", "ACTIVE", "RECOVERY_REQUIRED"}):
            raise BootstrapManagerError("PPU Active Asset Set status is untrusted")
        digest = record.get("asset_set_sha256")
        if record["state"] == "ACTIVE":
            _hex_field(digest, 64, "Active Asset Set SHA256")
        elif digest is not None:
            raise BootstrapManagerError("PPU Active Asset Set status is untrusted")
        return record

    def create_upload(self, alias: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, device_id, token = self._authenticated(alias)
        return client.create_upload(token, device_id, body)

    def append_chunk(self, alias: str, upload_id: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, device_id, token = self._authenticated(alias)
        return client.append_chunk(token, device_id, upload_id, body)

    def commit_upload(self, alias: str, upload_id: str) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, device_id, token = self._authenticated(alias)
        return client.commit_upload(token, device_id, upload_id)

    def start_deployment(self, alias: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, record, client, _payload, device_id, token = self._authenticated(alias)
        # Generic Bundle B2/B3: the Console's explicit request names the exact
        # archive SHA256 (and, for B3, the B2 transaction) the user confirmed.
        # The Manager turns that ONE choice into a device-bound Owner Operation
        # Authorization; the PPU re-derives every bound fact and re-checks B2,
        # Target, Package DAG, FPGA qualification and its own locks.
        if body.get("kind") == "bundle" and ("fpga_load" in body or "mode" in body):
            if set(body) != {"kind", "upload_id", "archive_sha256",
                             "admission_transaction_id", "mode", "fpga_load"}:
                raise BootstrapManagerError(
                    "Bundle B3 requires kind, upload_id, archive_sha256, "
                    "admission_transaction_id, mode and fpga_load")
            upload_id = _hex_field(body["upload_id"], 32, "generic Bundle upload_id")
            digest = _hex_field(body["archive_sha256"], 64, "Bundle archive_sha256")
            admission = _hex_field(body["admission_transaction_id"], 32,
                                   "Bundle admission_transaction_id")
            if type(body["fpga_load"]) is not bool:
                raise BootstrapManagerError("Bundle B3 fpga_load must be a boolean")
            mode = body["mode"]
            if type(mode) is not str or mode not in {"activate", "stage_only"}:
                raise BootstrapManagerError("Bundle B3 mode is invalid")
            if mode == "stage_only" and body["fpga_load"]:
                raise BootstrapManagerError("Bundle B3 stage_only cannot load FPGA")
            action = (ACTIVATE_FPGA_LOAD if body["fpga_load"] else
                      ACTIVATE if mode == "activate" else INSTALL)
            authorization = _issue(
                token, action,
                device_id, digest, admission,
            )
            status, response = client.start_deployment(token, device_id, {
                "kind": "bundle", "upload_id": upload_id,
                "mode": mode, "fpga_load": body["fpga_load"],
                "authorization": authorization,
            })
            deployment = response.get("deployment") if isinstance(response, dict) else None
            owner = deployment.get("owner_authorization") if isinstance(deployment, dict) else None
            if (
                status not in (200, 202) or response.get("ok") is not True
                or not isinstance(deployment, dict)
                or deployment.get("upload_id") != upload_id
                or deployment.get("state") not in {"queued", "running"}
                or deployment.get("admission_transaction_id") != admission
                or deployment.get("mode") != mode
                or deployment.get("fpga_load") is not body["fpga_load"]
                or not isinstance(owner, dict)
                or owner.get("status") != "OWNER_AUTHORIZED"
                or owner.get("action") != authorization["action"]
                or owner.get("subject_sha256") != digest
            ):
                raise BootstrapManagerError("Bundle B3 submission response is not a queued transaction")
            return status, response
        if body.get("kind") == "bundle":
            if set(body) != {"kind", "upload_id", "archive_sha256"}:
                raise BootstrapManagerError(
                    "generic Bundle requires only kind, upload_id and archive_sha256")
            upload_id = _hex_field(body["upload_id"], 32, "generic Bundle upload_id")
            digest = _hex_field(body["archive_sha256"], 64, "Bundle archive_sha256")
            status, response = client.start_deployment(token, device_id, {
                "kind": "bundle", "upload_id": upload_id,
                "authorization": _issue(token, ADMIT, device_id, digest, upload_id),
            })
            deployment = response.get("deployment") if isinstance(response, dict) else None
            result = deployment.get("result") if isinstance(deployment, dict) else None
            plan = result.get("plan") if isinstance(result, dict) else None
            owner = plan.get("owner_authorization") if isinstance(plan, dict) else None
            if (
                status != 200 or response.get("ok") is not True
                or not isinstance(deployment, dict)
                or deployment.get("state") != "admitted"
                or not isinstance(result, dict)
                or result.get("stage") != "package_admission_only"
                or result.get("install_qualified") is not False
                or not isinstance(plan, dict)
                or plan.get("kind") != "bundle"
                or plan.get("execution_permitted") is not False
                or plan.get("archive_sha256") != digest
                or result.get("owner_authorized") is not True
                or not isinstance(owner, dict)
                or owner.get("status") != "OWNER_AUTHORIZED"
                or owner.get("action") != ADMIT
                or owner.get("subject_sha256") != digest
                or owner.get("transaction_id") != upload_id
            ):
                raise BootstrapManagerError(
                    "generic Bundle admission response is not owner-authorized and non-executing"
                )
            return status, response

        allowed = {"upload_id", "ppu_id", "facility_id", "display_name"}
        unexpected = set(body) - allowed
        if unexpected:
            raise BootstrapManagerError(f"unsupported Manager deployment fields: {', '.join(sorted(unexpected))}")
        request = dict(body)
        request["gateway_host"] = _runtime_gateway_host(record.endpoint)
        return client.start_deployment(token, device_id, request)
