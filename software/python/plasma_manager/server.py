from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import ManagerConfig, load_manager_config
from .fleet import MANAGER_CONTRACT_VERSION, MANAGER_SERVICE_NAME, FleetAggregator


class PlasmaManagerHandler(BaseHTTPRequestHandler):
    aggregator: FleetAggregator | None = None

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
            self._json(HTTPStatus.OK, self._aggregator().fleet_snapshot())
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})

    def _read_only(self) -> None:
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {
                "ok": False,
                "error": {"message": "Plasma Manager fleet contract is read-only in this release"},
            },
        )

    def do_POST(self) -> None:
        self._read_only()

    def do_PUT(self) -> None:
        self._read_only()

    def do_PATCH(self) -> None:
        self._read_only()

    def do_DELETE(self) -> None:
        self._read_only()


def serve(config: ManagerConfig) -> None:
    PlasmaManagerHandler.aggregator = FleetAggregator(config)
    server = ThreadingHTTPServer((config.host, config.port), PlasmaManagerHandler)
    print(f"Plasma Manager listening on http://{config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma Manager read-only fleet control plane")
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
