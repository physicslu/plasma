from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .client import PPUHTTPError, PPUHttpClient
from .config import normalize_endpoint
from .registry import PPURegistryStore, RegistryEntryNotFound, normalize_registry_alias

BOOTSTRAP_PORT = 18081
BOOTSTRAP_CREDENTIAL_SCHEMA = 1
MAX_BOOTSTRAP_RESPONSE_BYTES = 4 * 1024 * 1024


class BootstrapManagerError(RuntimeError):
    """Raised when Manager cannot safely control a registered PPU Bootstrap."""


class BootstrapCredentialError(BootstrapManagerError):
    """Raised when Bootstrap pairing credentials are unavailable or untrustworthy."""


@dataclass(frozen=True, slots=True)
class BootstrapCredential:
    alias: str
    device_id: str
    token: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def bootstrap_endpoint_for_gateway(gateway_endpoint: str) -> str:
    """Derive the fixed Bootstrap endpoint without changing registry semantics.

    ``registry.endpoint`` remains the Plasma Gateway root.  Bootstrap is a
    separate appliance service on the same host at the reserved commissioning
    port.  Phase 3 deliberately limits this to a controlled private HTTP link;
    production transport confidentiality is a separate hardening requirement.
    """

    canonical = normalize_endpoint(gateway_endpoint)
    parsed = urlsplit(canonical)
    if parsed.scheme != "http":
        raise BootstrapManagerError(
            "Phase-3 Bootstrap transport supports the controlled private HTTP commissioning link only"
        )
    if parsed.hostname is None:
        raise BootstrapManagerError("registered Plasma Gateway endpoint has no host")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return urlunsplit(("http", f"{host}:{BOOTSTRAP_PORT}", "", "", ""))


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
    """Manager-owned device secrets, separate from public runtime registry state.

    A secret is bound to immutable Bootstrap ``device_id``, not merely an alias.
    Reusing an alias for another appliance therefore cannot silently reuse an old
    pairing token.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path.resolve() if path is not None else None
        self._lock = RLock()
        self._credentials: dict[str, BootstrapCredential] = {}
        if self.path is not None and self.path.exists():
            self._credentials = self._load(self.path)

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

    def token_for(self, alias: str, device_id: str) -> str:
        normalized = normalize_registry_alias(alias)
        expected_device = _valid_device_id(device_id)
        with self._lock:
            credential = self._credentials.get(normalized)
            if credential is None:
                raise BootstrapCredentialError(f"PPU Bootstrap is not paired: {normalized}")
            if credential.device_id != expected_device:
                raise BootstrapCredentialError(
                    "registered alias now resolves to a different Bootstrap device_id; explicit re-pairing is required"
                )
            return credential.token

    def set(self, alias: str, device_id: str, token: str) -> None:
        if self.path is None:
            raise BootstrapCredentialError(
                "Bootstrap credential persistence is disabled; configure Manager runtime registry state"
            )
        normalized = normalize_registry_alias(alias)
        validated_device = _valid_device_id(device_id)
        validated_token = _valid_token(token)
        with self._lock:
            previous = dict(self._credentials)
            self._credentials[normalized] = BootstrapCredential(
                normalized,
                validated_device,
                validated_token,
                _utc_now(),
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
        if not isinstance(payload, dict) or payload.get("schema_version") != BOOTSTRAP_CREDENTIAL_SCHEMA:
            raise BootstrapCredentialError("unsupported Bootstrap credential schema")
        raw = payload.get("credentials")
        if not isinstance(raw, dict):
            raise BootstrapCredentialError("Bootstrap credentials must be a mapping")
        result: dict[str, BootstrapCredential] = {}
        for alias, record in raw.items():
            normalized = normalize_registry_alias(alias)
            if (
                normalized != alias
                or not isinstance(record, dict)
                or set(record) != {"device_id", "token", "updated_at"}
            ):
                raise BootstrapCredentialError("Bootstrap credential entry is invalid")
            device_id = _valid_device_id(record.get("device_id"))
            token = _valid_token(record.get("token"))
            updated_at = record.get("updated_at")
            if not isinstance(updated_at, str) or not updated_at:
                raise BootstrapCredentialError("Bootstrap credential updated_at is invalid")
            result[normalized] = BootstrapCredential(normalized, device_id, token, updated_at)
        return result


class BootstrapHttpClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.client = PPUHttpClient(endpoint, timeout_s)
        self.timeout_s = timeout_s

    def _json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        raw = None
        if body is not None:
            raw = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            status, response_headers, response_body = self.client.relay(
                method,
                path,
                headers=headers,
                body=raw,
                timeout_s=self.timeout_s if timeout_s is None else timeout_s,
                max_response_bytes=MAX_BOOTSTRAP_RESPONSE_BYTES,
            )
        except PPUHTTPError as exc:
            raise BootstrapManagerError(str(exc)) from exc
        media_type = response_headers.get("Content-Type", response_headers.get("content-type", ""))
        if "application/json" not in media_type:
            raise BootstrapManagerError("PPU Bootstrap returned a non-JSON response")
        try:
            payload = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapManagerError("PPU Bootstrap returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BootstrapManagerError("PPU Bootstrap response must be a JSON object")
        return status, payload

    def status(self) -> tuple[int, dict[str, Any]]:
        return self._json("GET", "/v1/status")

    def create_upload(self, token: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", "/v1/uploads", token=token, body=body, timeout_s=10.0)

    def append_chunk(self, token: str, upload_id: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", f"/v1/uploads/{upload_id}/chunks", token=token, body=body, timeout_s=30.0)

    def commit_upload(self, token: str, upload_id: str) -> tuple[int, dict[str, Any]]:
        return self._json(
            "POST",
            f"/v1/uploads/{upload_id}/commit",
            token=token,
            body={"action": "commit"},
            timeout_s=30.0,
        )

    def start_deployment(self, token: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._json("POST", "/v1/deployments", token=token, body=body, timeout_s=10.0)


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
        if status != 200 or payload.get("bootstrap", {}).get("state") != "bootstrap_ready":
            raise BootstrapManagerError("PPU Bootstrap is not ready")
        device_id = _device_id_from_status(payload)
        return normalized, record, client, payload, device_id

    def _authenticated(self, alias: str):
        normalized, record, client, payload, device_id = self._live(alias)
        token = self.credentials.token_for(normalized, device_id)
        return normalized, record, client, payload, device_id, token

    def status(self, alias: str) -> dict[str, Any]:
        normalized, _record, _client, payload, device_id = self._live(alias)
        pairing = self.credentials.public_state(normalized)
        pairing = dict(pairing)
        pairing["device_match"] = pairing.get("device_id") in {None, device_id}
        return {
            "ok": True,
            "ppu_alias": normalized,
            "bootstrap_endpoint_policy": "same-host:18081",
            "pairing": pairing,
            "bootstrap": payload,
            "upstream_status": 200,
        }

    def pair(self, alias: str, token: str) -> dict[str, Any]:
        normalized, _record, _client, _payload, device_id = self._live(alias)
        # Phase 3 stores a device-bound token after a read-only identity probe.
        # Token correctness is still proven by the first authenticated Bootstrap
        # operation because the current PPU endpoint has no authenticated no-op.
        self.credentials.set(normalized, device_id, token)
        return {
            "ok": True,
            "ppu_alias": normalized,
            "pairing": self.credentials.public_state(normalized),
            "token_verification": "deferred_until_authenticated_operation",
        }

    def create_upload(self, alias: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, _device_id, token = self._authenticated(alias)
        return client.create_upload(token, body)

    def append_chunk(self, alias: str, upload_id: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, _device_id, token = self._authenticated(alias)
        return client.append_chunk(token, upload_id, body)

    def commit_upload(self, alias: str, upload_id: str) -> tuple[int, dict[str, Any]]:
        _normalized, _record, client, _payload, _device_id, token = self._authenticated(alias)
        return client.commit_upload(token, upload_id)

    def start_deployment(self, alias: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        _normalized, record, client, _payload, _device_id, token = self._authenticated(alias)
        allowed = {"upload_id", "ppu_id", "facility_id", "display_name"}
        unexpected = set(body) - allowed
        if unexpected:
            raise BootstrapManagerError(f"unsupported Manager deployment fields: {', '.join(sorted(unexpected))}")
        parsed = urlsplit(record.endpoint)
        if parsed.hostname is None:
            raise BootstrapManagerError("registered Plasma Gateway endpoint has no host")
        request = dict(body)
        request["gateway_host"] = parsed.hostname
        return client.start_deployment(token, request)
