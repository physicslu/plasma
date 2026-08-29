from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .client import PPUHTTPError, PPUTransportError, PPUHttpClient
from .config import ManagerConfig, PPURegistryEntry, load_manager_config
from .fleet import MANAGER_CONTRACT_VERSION, MANAGER_SERVICE_NAME, FleetAggregator
from .observation import FleetObservationStore, FleetSnapshotSource
from .persistence import SQLiteObservationPersistence
from .poller import FleetPoller


PS_LOOPBACK_ROUTE_PREFIX = "/api/ppus/"
PS_LOOPBACK_ROUTE_SUFFIX = "/diagnostics/loopback"
MAX_MANAGER_REQUEST_BYTES = 6 * 1024 * 1024


class PlasmaManagerHandler(BaseHTTPRequestHandler):
    aggregator: FleetAggregator | None = None
    poller: FleetPoller | None = None
    config: ManagerConfig | None = None

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

    def _read_json_object(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "0")
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if content_length <= 0 or content_length > MAX_MANAGER_REQUEST_BYTES:
            raise ValueError("request body size is invalid")
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _resolve_ppu_alias(self, alias: str) -> PPURegistryEntry | None:
        matches = [entry for entry in self._config().ppus if entry.alias == alias]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _parse_ps_loopback_alias(path: str) -> str | None:
        if not path.startswith(PS_LOOPBACK_ROUTE_PREFIX) or not path.endswith(PS_LOOPBACK_ROUTE_SUFFIX):
            return None
        encoded = path[len(PS_LOOPBACK_ROUTE_PREFIX) : -len(PS_LOOPBACK_ROUTE_SUFFIX)]
        if not encoded or "/" in encoded:
            return None
        alias = unquote(encoded)
        if not alias or alias in {".", ".."} or "/" in alias or "\\" in alias:
            return None
        return alias

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
        if parsed.path == "/api/registry":
            self._json(HTTPStatus.OK, self._aggregator().registry_snapshot())
            return
        if parsed.path == "/api/fleet":
            self._json(HTTPStatus.OK, self._poller().snapshot())
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
        try:
            body = self._read_json_object()
        except ValueError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}},
            )
            return

        endpoint = body.get("endpoint")
        if endpoint != "ps":
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
            self._json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"ok": False, "error": {"code": "ppu_transport_error", "message": "PPU loopback transport failed"}},
            )
            return
        except PPUHTTPError:
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"code": "ppu_protocol_error", "message": "PPU loopback response was invalid"}},
            )
            return

        manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
        if status == HTTPStatus.OK and payload.get("ok") is True:
            manager_meta = {
                "relay": "pass-through",
                "ppu_alias": alias,
                "manager_rtt_ms": manager_rtt_ms,
            }
            payload = dict(payload)
            payload["manager"] = manager_meta
        self._json(status, payload)

    def _read_only(self) -> None:
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {
                "ok": False,
                "error": {"message": "Plasma Manager contract is read-only except for the approved PS loopback pass-through route"},
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        alias = self._parse_ps_loopback_alias(parsed.path)
        if alias is not None:
            self._relay_ps_loopback(alias)
            return
        self._read_only()

    def do_PUT(self) -> None:
        self._read_only()

    def do_PATCH(self) -> None:
        self._read_only()

    def do_DELETE(self) -> None:
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
    aggregator = FleetAggregator(config)
    observations = _build_observation_store(config, aggregator)
    poller = FleetPoller(observations, config.poll_interval_s)
    PlasmaManagerHandler.aggregator = aggregator
    PlasmaManagerHandler.poller = poller
    PlasmaManagerHandler.config = config
    server = ThreadingHTTPServer((config.host, config.port), PlasmaManagerHandler)
    poller.start()
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
