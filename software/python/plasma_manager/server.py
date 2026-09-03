from __future__ import annotations

import argparse
import json
import re
import socketserver
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .client import PPUHTTPError, PPUTransportError, PPUHttpClient
from .config import ManagerConfig, PPURegistryEntry, load_manager_config
from .fleet import MANAGER_CONTRACT_VERSION, MANAGER_SERVICE_NAME, FleetAggregator
from .network_commissioning import (
    DEFAULT_ROLLBACK_TIMEOUT_S,
    NetworkCommissioningCoordinator,
    NetworkCommissioningError,
    NetworkCommissioningStore,
)
from .observation import FleetObservationStore, FleetSnapshotSource
from .persistence import SQLiteObservationPersistence
from .poller import FleetPoller
from .registry import (
    REGISTRY_LIFECYCLE_COMMISSIONED,
    REGISTRY_LIFECYCLE_DISABLED,
    PPURegistryStore,
    RegistryConflictError,
    RegistryEntryNotFound,
    RegistryMutationDisabled,
    RegistryStateError,
    RegistryValidationError,
)


PS_LOOPBACK_ROUTE_PREFIX = "/api/ppus/"
PS_LOOPBACK_ROUTE_SUFFIX = "/diagnostics/loopback"
MANAGED_PPU_ROUTE_PREFIX = "/api/ppus/"
MANAGED_PPU_ROUTE_MARKER = "/gateway"
REGISTRY_ROUTE = "/api/registry"
REGISTRY_ROUTE_PREFIX = "/api/registry/"
NETWORK_COMMISSIONING_SUFFIX = "/network-commissioning"
MAX_MANAGER_REQUEST_BYTES = 24 * 1024 * 1024
MAX_MANAGER_RESPONSE_BYTES = 32 * 1024 * 1024
FORWARDED_REQUEST_HEADERS = frozenset({"authorization", "idempotency-key", "content-type", "accept"})
ACTIVE_SITE_STATES = frozenset({"queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"})

_SEGMENT = r"[^/]+"
_MANAGED_GET_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^/api/health/live$",
        r"^/api/health/ready$",
        r"^/api/node$",
        r"^/api/status$",
        r"^/api/settings/gateway$",
        r"^/api/settings/ppu-network$",
        r"^/api/mock/runtime$",
        r"^/api/security/me$",
        r"^/api/devices/search$",
        r"^/api/engineering/targets$",
        rf"^/api/jobs/{_SEGMENT}/files/{_SEGMENT}$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/status$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/jobs/{_SEGMENT}/files/{_SEGMENT}$",
        rf"^/api/batches/{_SEGMENT}$",
    )
)
_MANAGED_POST_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^/api/settings/gateway$",
        r"^/api/settings/ppu-network$",
        r"^/api/mock/runtime$",
        r"^/api/engineering/diagnostics/loopback$",
        r"^/api/engineering/session$",
        r"^/api/jobs$",
        rf"^/api/jobs/{_SEGMENT}/cancel$",
        r"^/api/batches$",
        rf"^/api/batches/{_SEGMENT}/cancel$",
        rf"^/api/batches/{_SEGMENT}/targets/{_SEGMENT}/{_SEGMENT}/cancel$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/programming-assets/check$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/programming-assets$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/jobs$",
        rf"^/api/engineering/targets/{_SEGMENT}/{_SEGMENT}/api/jobs/{_SEGMENT}/cancel$",
    )
)


class PlasmaManagerHTTPServer(ThreadingHTTPServer):
    """Threaded Manager HTTP server whose bind path never depends on DNS."""

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class PlasmaManagerHandler(BaseHTTPRequestHandler):
    aggregator: FleetAggregator | None = None
    poller: FleetPoller | None = None
    config: ManagerConfig | None = None
    registry_store: PPURegistryStore | None = None
    network_commissioning: NetworkCommissioningCoordinator | None = None

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _raw_response(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if not any(key.lower() == "cache-control" for key in headers):
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _aggregator(self) -> FleetAggregator:
        if self.aggregator is None:
            raise RuntimeError("Plasma Manager aggregator is not configured")
        return self.aggregator

    def _poller(self) -> FleetPoller:
        if self.poller is None:
            raise RuntimeError("Plasma Manager fleet poller is not configured")
        return self.poller

    def _config(self) -> ManagerConfig:
        if self.config is None:
            raise RuntimeError("Plasma Manager configuration is not configured")
        return self.config

    def _network_commissioning(self) -> NetworkCommissioningCoordinator:
        if self.network_commissioning is None:
            raise NetworkCommissioningError(
                "Manager network commissioning is unavailable",
                code="network_commissioning_unavailable",
                http_status=503,
            )
        return self.network_commissioning

    def _read_raw_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "0")
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if content_length <= 0 or content_length > MAX_MANAGER_REQUEST_BYTES:
            raise ValueError("request body size is invalid")
        return self.rfile.read(content_length)

    def _read_json_object(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._read_raw_body())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _registry_entries(self) -> tuple[PPURegistryEntry, ...]:
        if self.registry_store is not None:
            return self.registry_store.entries()
        return self._config().ppus

    def _resolve_ppu_alias(self, alias: str) -> PPURegistryEntry | None:
        matches = [entry for entry in self._registry_entries() if entry.alias == alias]
        return matches[0] if len(matches) == 1 else None

    def _registry_lifecycle(self, alias: str) -> str:
        if self.registry_store is None:
            return REGISTRY_LIFECYCLE_COMMISSIONED
        record = self.registry_store.record_by_alias(alias)
        return record.lifecycle if record is not None else "missing"

    def _registry_snapshot(self) -> dict[str, Any]:
        if self.registry_store is None:
            return self._aggregator().registry_snapshot()
        snapshot = self.registry_store.snapshot()
        return {
            "ok": True,
            "service": MANAGER_SERVICE_NAME,
            "contract_version": MANAGER_CONTRACT_VERSION,
            **snapshot,
        }

    @staticmethod
    def _valid_alias(encoded: str) -> str | None:
        if not encoded or "/" in encoded:
            return None
        alias = unquote(encoded)
        if not alias or alias in {".", ".."} or "/" in alias or "\\" in alias:
            return None
        return alias

    @classmethod
    def _parse_registry_alias(cls, path: str) -> str | None:
        if not path.startswith(REGISTRY_ROUTE_PREFIX):
            return None
        encoded = path[len(REGISTRY_ROUTE_PREFIX) :]
        if not encoded or "/" in encoded:
            return None
        return cls._valid_alias(encoded)

    @classmethod
    def _parse_network_commissioning_alias(cls, path: str) -> str | None:
        if not path.startswith(REGISTRY_ROUTE_PREFIX) or not path.endswith(NETWORK_COMMISSIONING_SUFFIX):
            return None
        encoded = path[len(REGISTRY_ROUTE_PREFIX) : -len(NETWORK_COMMISSIONING_SUFFIX)]
        if not encoded or "/" in encoded:
            return None
        return cls._valid_alias(encoded)

    @classmethod
    def _parse_ps_loopback_alias(cls, path: str) -> str | None:
        if not path.startswith(PS_LOOPBACK_ROUTE_PREFIX) or not path.endswith(PS_LOOPBACK_ROUTE_SUFFIX):
            return None
        encoded = path[len(PS_LOOPBACK_ROUTE_PREFIX) : -len(PS_LOOPBACK_ROUTE_SUFFIX)]
        return cls._valid_alias(encoded)

    @classmethod
    def _parse_managed_ppu_route(cls, path: str) -> tuple[str, str] | None:
        if not path.startswith(MANAGED_PPU_ROUTE_PREFIX):
            return None
        remainder = path[len(MANAGED_PPU_ROUTE_PREFIX) :]
        encoded_alias, separator, after_alias = remainder.partition("/")
        if not separator:
            return None
        alias = cls._valid_alias(encoded_alias)
        if alias is None:
            return None
        marker = MANAGED_PPU_ROUTE_MARKER.lstrip("/")
        if after_alias == marker or not after_alias.startswith(f"{marker}/"):
            return None
        target_path = "/" + after_alias[len(marker) + 1 :]
        if not target_path.startswith("/api/") and target_path != "/api":
            return None
        return alias, target_path

    @staticmethod
    def _managed_route_allowed(method: str, target_path: str) -> bool:
        patterns = _MANAGED_GET_PATTERNS if method == "GET" else _MANAGED_POST_PATTERNS if method == "POST" else ()
        return any(pattern.fullmatch(target_path) for pattern in patterns)

    def _fleet_item_for_alias(self, alias: str) -> dict[str, Any] | None:
        try:
            snapshot = self._poller().snapshot()
        except RuntimeError:
            return None
        ppus = snapshot.get("ppus")
        if not isinstance(ppus, list):
            return None
        matches = [item for item in ppus if isinstance(item, dict) and item.get("alias") == alias]
        return matches[0] if len(matches) == 1 else None

    def _alias_has_active_execution(self, alias: str) -> bool:
        item = self._fleet_item_for_alias(alias)
        if item is None:
            return False
        sites = item.get("sites")
        if not isinstance(sites, list):
            return False
        for site in sites:
            if not isinstance(site, dict):
                continue
            state = str(site.get("state", "")).strip().lower()
            if state in ACTIVE_SITE_STATES or site.get("current_job_id"):
                return True
        return False

    def _alias_is_trusted_for_enable(self, alias: str) -> bool:
        item = self._fleet_item_for_alias(alias)
        if item is None:
            return False
        observation = item.get("observation")
        return (
            item.get("gateway_live") is True
            and item.get("execution_ready") is True
            and item.get("contract_compatible") is True
            and item.get("identity_conflict") is False
            and isinstance(item.get("ppu"), dict)
            and isinstance(item.get("sites"), list)
            and not item.get("errors")
            and (not isinstance(observation, dict) or observation.get("state") == "current")
        )

    def _registry_error(self, exc: Exception) -> None:
        if isinstance(exc, RegistryMutationDisabled):
            status = HTTPStatus.SERVICE_UNAVAILABLE
            code = "registry_mutation_disabled"
        elif isinstance(exc, RegistryConflictError):
            status = HTTPStatus.CONFLICT
            code = "registry_conflict"
        elif isinstance(exc, RegistryEntryNotFound):
            status = HTTPStatus.NOT_FOUND
            code = "ppu_not_found"
        elif isinstance(exc, RegistryValidationError):
            status = HTTPStatus.BAD_REQUEST
            code = "invalid_registry_request"
        elif isinstance(exc, RegistryStateError):
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            code = "registry_state_error"
        else:
            raise exc
        self._json(status, {"ok": False, "error": {"code": code, "message": str(exc)}})

    def _handle_registry_add(self) -> None:
        if self.registry_store is None:
            self._registry_error(RegistryMutationDisabled("Manager runtime PPU registry is unavailable"))
            return
        try:
            body = self._read_json_object()
            unexpected = set(body) - {"alias", "endpoint"}
            if unexpected:
                raise RegistryValidationError(f"unsupported registry fields: {', '.join(sorted(unexpected))}")
            record = self.registry_store.add(alias=body.get("alias"), endpoint=body.get("endpoint"))
        except (ValueError, RegistryStateError) as exc:
            if isinstance(exc, RegistryStateError):
                self._registry_error(exc)
            else:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
            return
        self._json(
            HTTPStatus.CREATED,
            {"ok": True, "entry": record.as_dict(), "registry": self._registry_snapshot()},
        )

    def _handle_registry_lifecycle(self, alias: str) -> None:
        if self.registry_store is None:
            self._registry_error(RegistryMutationDisabled("Manager runtime PPU registry is unavailable"))
            return
        try:
            body = self._read_json_object()
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
            return
        if set(body) != {"lifecycle"}:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": "registry lifecycle request requires only lifecycle"}},
            )
            return
        lifecycle = body.get("lifecycle")
        if lifecycle == REGISTRY_LIFECYCLE_COMMISSIONED and not self._alias_is_trusted_for_enable(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "code": "ppu_validation_incomplete",
                        "message": "PPU must have a current trusted identity/topology observation before Validate & Enable",
                    },
                },
            )
            return
        if lifecycle == REGISTRY_LIFECYCLE_DISABLED and self._alias_has_active_execution(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_busy", "message": "active PPU Jobs must finish or be cancelled before disabling this PPU"}},
            )
            return
        try:
            record = self.registry_store.set_lifecycle(alias, lifecycle)
        except RegistryStateError as exc:
            self._registry_error(exc)
            return
        self._json(HTTPStatus.OK, {"ok": True, "entry": record.as_dict(), "registry": self._registry_snapshot()})

    def _handle_registry_remove(self, alias: str) -> None:
        if self.registry_store is None:
            self._registry_error(RegistryMutationDisabled("Manager runtime PPU registry is unavailable"))
            return
        if self._alias_has_active_execution(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_busy", "message": "active PPU Jobs must finish or be cancelled before removing this PPU"}},
            )
            return
        try:
            removed = self.registry_store.remove(alias)
        except RegistryStateError as exc:
            self._registry_error(exc)
            return
        self._json(HTTPStatus.OK, {"ok": True, "removed": removed.as_dict(), "registry": self._registry_snapshot()})

    def _handle_network_commissioning_get(self, alias: str) -> None:
        try:
            record = self._network_commissioning().get(alias)
        except NetworkCommissioningError as exc:
            self._json(exc.http_status, {"ok": False, "error": {"code": exc.code, "message": exc.message}})
            return
        if record is None:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "network_commissioning_not_found", "message": "No network commissioning transaction exists for this PPU"}},
            )
            return
        self._json(HTTPStatus.OK, {"ok": True, "commissioning": record.as_dict()})

    def _handle_network_commissioning_post(self, alias: str) -> None:
        if self.registry_store is None:
            self._registry_error(RegistryMutationDisabled("Manager runtime PPU registry is unavailable"))
            return
        if self._registry_lifecycle(alias) != REGISTRY_LIFECYCLE_COMMISSIONED:
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_not_enabled", "message": "PPU must complete Validate & Enable before network commissioning"}},
            )
            return
        if self._alias_has_active_execution(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_busy", "message": "active PPU Jobs must finish or be cancelled before network commissioning"}},
            )
            return
        if not self._alias_is_trusted_for_enable(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_validation_incomplete", "message": "A current trusted PPU identity/topology observation is required before network commissioning"}},
            )
            return
        try:
            body = self._read_json_object()
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
            return
        if set(body) - {"desired", "rollback_timeout_s"} or "desired" not in body:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_network_commissioning_request", "message": "commissioning request accepts only desired and optional rollback_timeout_s"}},
            )
            return
        request_key = self.headers.get("Idempotency-Key", "")
        authorization = self.headers.get("Authorization")
        try:
            record = self._network_commissioning().start(
                alias,
                body.get("desired"),
                rollback_timeout_s=body.get("rollback_timeout_s", DEFAULT_ROLLBACK_TIMEOUT_S),
                request_key=request_key,
                authorization=authorization,
            )
        except NetworkCommissioningError as exc:
            payload: dict[str, Any] = {
                "ok": False,
                "error": {"code": exc.code, "message": exc.message},
            }
            if exc.record is not None:
                payload["commissioning"] = exc.record.as_dict()
            self._json(exc.http_status, payload)
            return
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "commissioning": record.as_dict(),
                "registry": self._registry_snapshot(),
            },
        )

    @staticmethod
    def _log_ps_loopback_relay(
        *,
        alias: str,
        body: dict[str, Any],
        result: str,
        http_status: int,
        manager_rtt_ms: float | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": "manager_ps_loopback_relay",
            "ppu_alias": alias,
            "test_id": body.get("test_id"),
            "sequence": body.get("sequence"),
            "result": result,
            "http_status": int(http_status),
        }
        if manager_rtt_ms is not None:
            event["manager_rtt_ms"] = manager_rtt_ms
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)

    @staticmethod
    def _log_managed_relay(*, alias: str, method: str, target_path: str, result: str, http_status: int) -> None:
        print(
            json.dumps(
                {
                    "event": "manager_managed_ppu_relay",
                    "ppu_alias": alias,
                    "method": method,
                    "path": target_path,
                    "result": result,
                    "http_status": int(http_status),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health/live":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": MANAGER_SERVICE_NAME,
                    "contract_version": MANAGER_CONTRACT_VERSION,
                    "manager": "alive",
                },
            )
            return
        if parsed.path == REGISTRY_ROUTE:
            self._json(HTTPStatus.OK, self._registry_snapshot())
            return
        commissioning_alias = self._parse_network_commissioning_alias(parsed.path)
        if commissioning_alias is not None:
            self._handle_network_commissioning_get(commissioning_alias)
            return
        if parsed.path == "/api/fleet":
            self._json(HTTPStatus.OK, self._poller().snapshot())
            return
        managed = self._parse_managed_ppu_route(parsed.path)
        if managed is not None:
            alias, target_path = managed
            self._relay_managed_ppu_request(alias, target_path, parsed.query)
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})

    def _relay_ps_loopback(self, alias: str) -> None:
        entry = self._resolve_ppu_alias(alias)
        if entry is None:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "ppu_not_found", "message": "configured PPU alias was not found"}},
            )
            return
        if self._registry_lifecycle(alias) != REGISTRY_LIFECYCLE_COMMISSIONED:
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_not_enabled", "message": "PPU must complete Validate & Enable before Manager write operations"}},
            )
            return
        try:
            body = self._read_json_object()
        except ValueError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}},
            )
            return

        if body.get("endpoint") != "ps":
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "unsupported_endpoint", "message": "Manager Phase 0 relays PS loopback only"}},
            )
            return
        timeout_ms = body.get("timeout_ms")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": "timeout_ms must be a positive integer"}},
            )
            return

        client = PPUHttpClient(entry.endpoint, self._config().request_timeout_s)
        relay_timeout_s = min(max(timeout_ms / 1000.0 + 1.0, self._config().request_timeout_s), 121.0)
        started = time.monotonic()
        try:
            status, payload = client.ps_loopback(body, timeout_s=relay_timeout_s)
        except PPUTransportError:
            manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
            self._log_ps_loopback_relay(
                alias=alias,
                body=body,
                result="transport_error",
                http_status=HTTPStatus.GATEWAY_TIMEOUT,
                manager_rtt_ms=manager_rtt_ms,
            )
            self._json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"ok": False, "error": {"code": "ppu_transport_error", "message": "PPU loopback transport failed"}},
            )
            return
        except PPUHTTPError:
            manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
            self._log_ps_loopback_relay(
                alias=alias,
                body=body,
                result="protocol_error",
                http_status=HTTPStatus.BAD_GATEWAY,
                manager_rtt_ms=manager_rtt_ms,
            )
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"code": "ppu_protocol_error", "message": "PPU loopback response was invalid"}},
            )
            return

        manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
        result = "pass" if status == HTTPStatus.OK and payload.get("ok") is True else "ppu_error"
        self._log_ps_loopback_relay(
            alias=alias,
            body=body,
            result=result,
            http_status=status,
            manager_rtt_ms=manager_rtt_ms,
        )
        if result == "pass":
            payload = dict(payload)
            payload["manager"] = {
                "relay": "pass-through",
                "ppu_alias": alias,
                "manager_rtt_ms": manager_rtt_ms,
            }
        self._json(status, payload)

    def _relay_managed_ppu_request(self, alias: str, target_path: str, query: str) -> None:
        if not self._managed_route_allowed(self.command, target_path):
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "managed_route_not_allowed", "message": "Manager PPU route is not allowlisted"}},
            )
            return
        entry = self._resolve_ppu_alias(alias)
        if entry is None:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "ppu_not_found", "message": "configured PPU alias was not found"}},
            )
            return
        if self.command == "POST" and self._registry_lifecycle(alias) != REGISTRY_LIFECYCLE_COMMISSIONED:
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "ppu_not_enabled", "message": "PPU must complete Validate & Enable before Manager write operations"}},
            )
            return

        body: bytes | None = None
        if self.command == "POST":
            try:
                body = self._read_raw_body()
            except ValueError as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}},
                )
                return

        forwarded_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() in FORWARDED_REQUEST_HEADERS
        }
        target = target_path + (f"?{query}" if query else "")
        client = PPUHttpClient(entry.endpoint, self._config().request_timeout_s)
        started = time.monotonic()
        try:
            status, response_headers, response_body = client.relay(
                self.command,
                target,
                headers=forwarded_headers,
                body=body,
                timeout_s=max(125.0, self._config().request_timeout_s),
                max_response_bytes=MAX_MANAGER_RESPONSE_BYTES,
            )
        except PPUTransportError:
            self._log_managed_relay(
                alias=alias,
                method=self.command,
                target_path=target_path,
                result="transport_error",
                http_status=HTTPStatus.GATEWAY_TIMEOUT,
            )
            self._json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"ok": False, "error": {"code": "ppu_transport_error", "message": "PPU transport failed"}},
            )
            return
        except PPUHTTPError:
            self._log_managed_relay(
                alias=alias,
                method=self.command,
                target_path=target_path,
                result="protocol_error",
                http_status=HTTPStatus.BAD_GATEWAY,
            )
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"code": "ppu_protocol_error", "message": "PPU response exceeded Manager relay contract"}},
            )
            return

        manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
        if target_path == "/api/engineering/diagnostics/loopback" and status == HTTPStatus.OK:
            try:
                payload = json.loads(response_body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and payload.get("ok") is True:
                payload = dict(payload)
                payload["manager"] = {
                    "relay": "pass-through",
                    "ppu_alias": alias,
                    "manager_rtt_ms": manager_rtt_ms,
                }
                response_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                response_headers["Content-Type"] = "application/json; charset=utf-8"

        self._log_managed_relay(
            alias=alias,
            method=self.command,
            target_path=target_path,
            result="pass-through",
            http_status=status,
        )
        self._raw_response(status, response_headers, response_body)

    def _read_only(self) -> None:
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {
                "ok": False,
                "error": {"message": "Plasma Manager rejects mutation outside the explicit runtime registry, network commissioning, and allowlisted Managed PPU routes"},
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == REGISTRY_ROUTE:
            self._handle_registry_add()
            return
        commissioning_alias = self._parse_network_commissioning_alias(parsed.path)
        if commissioning_alias is not None:
            self._handle_network_commissioning_post(commissioning_alias)
            return
        managed = self._parse_managed_ppu_route(parsed.path)
        if managed is not None:
            alias, target_path = managed
            self._relay_managed_ppu_request(alias, target_path, parsed.query)
            return
        alias = self._parse_ps_loopback_alias(parsed.path)
        if alias is not None:
            self._relay_ps_loopback(alias)
            return
        self._read_only()

    def do_PUT(self) -> None:
        self._read_only()

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        alias = self._parse_registry_alias(parsed.path)
        if alias is not None:
            self._handle_registry_lifecycle(alias)
            return
        self._read_only()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        alias = self._parse_registry_alias(parsed.path)
        if alias is not None:
            self._handle_registry_remove(alias)
            return
        self._read_only()


def _build_observation_store(
    config: ManagerConfig,
    source: FleetSnapshotSource,
) -> FleetObservationStore:
    persistence = (
        SQLiteObservationPersistence(config.observation_db_path)
        if config.observation_db_path is not None
        else None
    )
    return FleetObservationStore(source, persistence=persistence)


def serve(config: ManagerConfig) -> None:
    registry = PPURegistryStore(config.ppus, config.registry_state_path)
    commissioning_store = NetworkCommissioningStore(
        NetworkCommissioningCoordinator.state_path_for_registry(config.registry_state_path)
    )
    commissioning = NetworkCommissioningCoordinator(
        registry,
        commissioning_store,
        config.request_timeout_s,
    )
    commissioning.recover()
    aggregator = FleetAggregator(config, registry_provider=registry.entries)
    observations = _build_observation_store(config, aggregator)
    poller = FleetPoller(observations, config.poll_interval_s)
    PlasmaManagerHandler.aggregator = aggregator
    PlasmaManagerHandler.poller = poller
    PlasmaManagerHandler.config = config
    PlasmaManagerHandler.registry_store = registry
    PlasmaManagerHandler.network_commissioning = commissioning
    server = PlasmaManagerHTTPServer((config.host, config.port), PlasmaManagerHandler)
    poller.start(prime_cache=False)
    print(f"Plasma Manager listening on http://{config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        poller.stop(timeout_s=max(5.0, config.request_timeout_s * 4 + 1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma Manager fleet control plane")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to an explicit Plasma Manager registry configuration",
    )
    args = parser.parse_args()
    serve(load_manager_config(args.config))


if __name__ == "__main__":
    main()
