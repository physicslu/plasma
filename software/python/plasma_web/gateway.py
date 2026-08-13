from __future__ import annotations

import argparse
import asyncio
import base64
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from plasma_client.client import PlasmaClient
from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class PlasmaWebHandler(BaseHTTPRequestHandler):
    client_factory: Callable[[], PlasmaClient] = PlasmaClient
    max_body_bytes = 18 * 1024 * 1024

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > self.max_body_bytes:
            raise ValueError("invalid request body size")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PlasmaError):
            self._json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": {"error_code": exc.code.value, "message": exc.message}})
        else:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"message": str(exc)}})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                job = query.get("job", [None])[0]
                channel = query.get("channel", [None])[0]
                self._json(HTTPStatus.OK, _run(self.client_factory().status(job_id=job, channel_id=int(channel) if channel is not None else None)))
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                job_id = parsed.path.split("/")[3]
                self._json(HTTPStatus.OK, _run(self.client_factory().cancel(job_id)))
                return
            if parsed.path != "/api/jobs":
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
                return
            body = self._body()
            operation = Operation(str(body["operation"]))
            if operation not in {Operation.ERASE, Operation.PROGRAM, Operation.VERIFY}:
                raise ValueError("web gateway supports erase, program, and verify")
            firmware = base64.b64decode(body.get("firmware_base64", ""), validate=True)
            if operation in {Operation.PROGRAM, Operation.VERIFY} and not firmware:
                raise ValueError("program and verify require firmware_base64")
            request = JobRequest(
                channel_id=int(body["channel_id"]), operation=operation,
                firmware=firmware, map_data=body.get("map_data") or {},
                timeout_s=float(body.get("timeout_s", 30)),
                client_id="plasma-web",
                metadata={"firmware_name": str(body.get("firmware_name", "browser-upload.bin"))},
            )
            self._json(HTTPStatus.ACCEPTED, _run(self.client_factory().start(request)))
        except Exception as exc:
            self._error(exc)


def serve(host: str, port: int, plasma_host: str, plasma_port: int) -> None:
    PlasmaWebHandler.client_factory = staticmethod(lambda: PlasmaClient(plasma_host, plasma_port))
    server = ThreadingHTTPServer((host, port), PlasmaWebHandler)
    print(f"Plasma Web API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma browser REST gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--plasma-host", default="127.0.0.1")
    parser.add_argument("--plasma-port", type=int, default=9900)
    args = parser.parse_args()
    serve(args.host, args.port, args.plasma_host, args.plasma_port)


if __name__ == "__main__":
    main()
