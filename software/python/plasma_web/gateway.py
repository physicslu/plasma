from __future__ import annotations

import argparse
import asyncio
import base64
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from plasma_client.client import PlasmaClient
from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest, site_id_from_legacy_channel, validate_job_id

from .engineering_targets import EngineeringPPUProvider, MockEngineeringPPUProvider


FLEET_CONTRACT_VERSION = "1"
GATEWAY_SERVICE_NAME = "plasma-web-rest-gateway"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _parse_site_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("site_id must be a positive integer starting at 1")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value and value.isascii() and value.isdecimal():
        parsed = int(value)
    else:
        raise ValueError("site_id must be a positive integer starting at 1")
    if parsed < 1:
        raise ValueError("site_id must be a positive integer starting at 1")
    return parsed


def _parse_legacy_channel_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("legacy channel_id must be a non-negative integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value and value.isascii() and value.isdecimal():
        parsed = int(value)
    else:
        raise ValueError("legacy channel_id must be a non-negative integer")
    if parsed < 0:
        raise ValueError("legacy channel_id must be a non-negative integer")
    return site_id_from_legacy_channel(parsed)


def _site_value(canonical: Any, legacy: Any) -> int | None:
    if canonical is None and legacy is None:
        return None
    canonical_id = _parse_site_id(canonical) if canonical is not None else None
    legacy_site_id = _parse_legacy_channel_id(legacy) if legacy is not None else None
    if canonical_id is not None and legacy_site_id is not None and canonical_id != legacy_site_id:
        raise ValueError("site_id and legacy channel_id refer to different Sites")
    return canonical_id if canonical_id is not None else legacy_site_id


class PlasmaWebHandler(BaseHTTPRequestHandler):
    client_factory: Callable[[], PlasmaClient] = PlasmaClient
    engineering_provider: EngineeringPPUProvider | None = None
    max_body_bytes = 24 * 1024 * 1024
    allowed_origins = frozenset({"*"})
    output_root = Path("output")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _binary_data(self, data: bytes, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _binary(self, path: Path) -> None:
        self._binary_data(path.read_bytes(), path.name)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if "*" in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > self.max_body_bytes:
            raise ValueError("invalid request body size")
        return self.rfile.read(length)

    def _body(self) -> dict[str, Any]:
        value = json.loads(self._raw_body())
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PlasmaError):
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"error_code": exc.code.value, "message": exc.message}},
            )
        else:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"message": str(exc)}})

    def _local_snapshot(self) -> dict[str, Any]:
        snapshot = _run(self.client_factory().status(job_id=None, site_id=None))
        if not isinstance(snapshot, dict) or snapshot.get("ok") is not True:
            raise RuntimeError("local Plasma Server is not ready")
        ppu = snapshot.get("ppu")
        if not isinstance(ppu, dict) or not ppu.get("ppu_id"):
            raise RuntimeError("local Plasma Server STATUS is missing canonical PPU identity")
        return snapshot

    def _execution_unavailable(self) -> None:
        self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "gateway": "alive",
                "execution": "unavailable",
                "error": {"message": "local Plasma Server is unavailable"},
            },
        )

    def _engineering_unavailable(self) -> None:
        self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "provider": "unavailable",
                "error": {"message": "Engineering PPU provider is not enabled"},
            },
        )

    @staticmethod
    def _engineering_target(path: str) -> tuple[str, str, list[str]] | None:
        parts = path.strip("/").split("/")
        if len(parts) < 5 or parts[:3] != ["api", "engineering", "targets"]:
            return None
        return unquote(parts[3]), unquote(parts[4]), [unquote(part) for part in parts[5:]]

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health/live":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": GATEWAY_SERVICE_NAME,
                        "gateway": "alive",
                    },
                )
                return
            if parsed.path == "/api/health/ready":
                try:
                    snapshot = self._local_snapshot()
                except Exception:
                    self._execution_unavailable()
                    return
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": GATEWAY_SERVICE_NAME,
                        "gateway": "alive",
                        "execution": "ready",
                        "ppu_id": snapshot["ppu"]["ppu_id"],
                    },
                )
                return
            if parsed.path == "/api/node":
                try:
                    snapshot = self._local_snapshot()
                except Exception:
                    self._execution_unavailable()
                    return
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "contract_version": FLEET_CONTRACT_VERSION,
                        "node_role": "ppu",
                        "manager_required": False,
                        "ppu": snapshot["ppu"],
                        "links": {
                            "status": "/api/status",
                            "jobs": "/api/jobs",
                            "liveness": "/api/health/live",
                            "readiness": "/api/health/ready",
                        },
                    },
                )
                return
            if parsed.path == "/api/engineering/targets":
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                self._json(HTTPStatus.OK, self.engineering_provider.catalog())
                return

            engineering = self._engineering_target(parsed.path)
            if engineering is not None:
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                facility_id, ppu_id, tail = engineering
                query = parse_qs(parsed.query)
                if tail == ["api", "status"]:
                    job = query.get("job", [None])[0]
                    site = query.get("site", [None])[0]
                    legacy_channel = query.get("channel", [None])[0]
                    site_id = _site_value(site, legacy_channel)
                    self._json(
                        HTTPStatus.OK,
                        _run(
                            self.engineering_provider.status(
                                facility_id,
                                ppu_id,
                                site_id=site_id,
                                job_id=job,
                            )
                        ),
                    )
                    return
                if len(tail) == 5 and tail[:2] == ["api", "jobs"] and tail[3] == "files":
                    job_id = tail[2]
                    filename = tail[4]
                    data = self.engineering_provider.read_output_file(
                        facility_id, ppu_id, job_id, filename
                    )
                    self._binary_data(data, filename)
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
                return

            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                job = query.get("job", [None])[0]
                site = query.get("site", [None])[0]
                legacy_channel = query.get("channel", [None])[0]
                site_id = _site_value(site, legacy_channel)
                self._json(
                    HTTPStatus.OK,
                    _run(self.client_factory().status(job_id=job, site_id=site_id)),
                )
                return
            parts = parsed.path.split("/")
            if len(parts) == 6 and parts[1:3] == ["api", "jobs"] and parts[4] == "files":
                self._download(parts[3], unquote(parts[5]))
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
        except Exception as exc:
            self._error(exc)

    def _download(self, job_id: str, filename: str) -> None:
        validate_job_id(job_id)
        if not filename or Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("invalid output filename")
        job_directory = (self.output_root / job_id).resolve()
        result_path = job_directory / "result.json"
        if not result_path.is_file():
            raise ValueError("job output is not available")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        allowed: set[str] = set()
        for raw_path in result.get("output_files", []):
            output_path = Path(str(raw_path))
            if output_path.resolve().parent == job_directory:
                allowed.add(output_path.name)
        requested = (job_directory / filename).resolve()
        if requested.parent != job_directory or filename not in allowed or not requested.is_file():
            raise ValueError("output file does not belong to this job")
        self._binary(requested)

    def _job_request(
        self,
        body: dict[str, Any],
        *,
        client_id: str,
        default_timeout_s: float = 30.0,
        allow_firmware_reference: bool = False,
    ) -> JobRequest:
        operation = Operation(str(body["operation"]))
        if operation not in {Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ}:
            raise ValueError("web gateway supports erase, program, verify, and read")
        encoded_firmware = body.get("firmware_base64", "")
        if not isinstance(encoded_firmware, str):
            raise ValueError("firmware_base64 must be a string")
        firmware = base64.b64decode(encoded_firmware, validate=True) if encoded_firmware else b""
        firmware_id = body.get("firmware_id")
        if firmware_id is not None and not isinstance(firmware_id, str):
            raise ValueError("firmware_id must be a string")
        if operation in {Operation.PROGRAM, Operation.VERIFY} and not firmware:
            if not allow_firmware_reference or not firmware_id:
                raise ValueError("program and verify require firmware_base64 or staged firmware_id")
        map_data = body.get("map_data") or {}
        if operation is Operation.READ:
            map_data = self._read_map(body, map_data)
        site_id = _site_value(body.get("site_id"), body.get("channel_id"))
        if site_id is None:
            raise ValueError("job requires site_id")
        return JobRequest(
            site_id=site_id,
            operation=operation,
            firmware=firmware,
            map_data=map_data,
            timeout_s=float(body.get("timeout_s", default_timeout_s)),
            client_id=client_id,
            metadata={"firmware_name": str(body.get("firmware_name", "browser-upload.bin"))},
        )

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            engineering = self._engineering_target(parsed.path)
            if engineering is not None:
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                facility_id, ppu_id, tail = engineering
                if tail == ["api", "firmware"]:
                    query = parse_qs(parsed.query)
                    firmware_name = query.get("name", ["browser-upload.bin"])[0]
                    self._json(
                        HTTPStatus.CREATED,
                        self.engineering_provider.stage_firmware(
                            facility_id,
                            ppu_id,
                            firmware_name,
                            self._raw_body(),
                        ),
                    )
                    return
                if len(tail) == 4 and tail[:2] == ["api", "jobs"] and tail[3] == "cancel":
                    self._json(
                        HTTPStatus.OK,
                        _run(self.engineering_provider.cancel_job(facility_id, ppu_id, tail[2])),
                    )
                    return
                if tail == ["api", "jobs"]:
                    body = self._body()
                    firmware_id = body.get("firmware_id")
                    request = self._job_request(
                        body,
                        client_id="plasma-web-engineering",
                        default_timeout_s=self.engineering_provider.job_timeout_s(facility_id, ppu_id),
                        allow_firmware_reference=True,
                    )
                    self._json(
                        HTTPStatus.ACCEPTED,
                        _run(
                            self.engineering_provider.start_job(
                                facility_id,
                                ppu_id,
                                request,
                                firmware_id=firmware_id if isinstance(firmware_id, str) else None,
                            )
                        ),
                    )
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
                return

            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                job_id = parsed.path.split("/")[3]
                self._json(HTTPStatus.OK, _run(self.client_factory().cancel(job_id)))
                return
            if parsed.path != "/api/jobs":
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"ok": False, "error": {"message": "not found"}},
                )
                return
            request = self._job_request(self._body(), client_id="plasma-web")
            self._json(HTTPStatus.ACCEPTED, _run(self.client_factory().start(request)))
        except Exception as exc:
            self._error(exc)

    @staticmethod
    def _read_map(body: dict[str, Any], map_data: Any) -> dict[str, Any]:
        if not isinstance(map_data, dict):
            raise ValueError("map_data must be an object")
        sections = map_data.get("sections")
        if sections is None:
            sections = [
                {
                    "name": "flash",
                    "offset": body.get("offset", 0),
                    "length": body.get("length", 256),
                }
            ]
        if not isinstance(sections, list) or not sections:
            raise ValueError("map_data.sections must be a non-empty array")
        normalized = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                raise ValueError(f"map section {index} must be an object")
            offset = section.get("offset", section.get("address"))
            length = section.get("length")
            if type(offset) is not int or type(length) is not int:
                raise ValueError(f"map section {index} range is invalid")
            if offset < 0 or length <= 0:
                raise ValueError(f"map section {index} range is invalid")
            normalized.append(
                {
                    "name": str(section.get("name", f"section{index}")),
                    "address": offset,
                    "length": length,
                }
            )
        return {**map_data, "sections": normalized}


def serve(
    host: str,
    port: int,
    plasma_host: str,
    plasma_port: int,
    cors_origins: tuple[str, ...] = ("*",),
    output_root: Path = Path("output"),
    engineering_provider: EngineeringPPUProvider | None = None,
) -> None:
    PlasmaWebHandler.client_factory = staticmethod(lambda: PlasmaClient(plasma_host, plasma_port))
    PlasmaWebHandler.engineering_provider = engineering_provider
    PlasmaWebHandler.allowed_origins = frozenset(cors_origins)
    PlasmaWebHandler.output_root = output_root.resolve()
    server = ThreadingHTTPServer((host, port), PlasmaWebHandler)
    print(f"Plasma Web REST Gateway listening on http://{host}:{port}")
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
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        help="Allowed Web origin; repeat for multiple origins (prototype default: *)",
    )
    parser.add_argument(
        "--engineering-mock",
        action="store_true",
        help="Enable the server-side Engineering mock Facility/PPU provider",
    )
    parser.add_argument(
        "--engineering-mock-root",
        type=Path,
        default=Path("engineering-mock"),
        help="Output/log root for Engineering mock PPU runtimes",
    )
    args = parser.parse_args()

    provider: MockEngineeringPPUProvider | None = None
    try:
        if args.engineering_mock:
            provider = MockEngineeringPPUProvider(args.engineering_mock_root)
            provider.start()
            catalog = provider.catalog()
            print(
                "Engineering mock PPU provider ready: "
                f"{catalog['facility_count']} facilities / {catalog['ppu_count']} PPUs / "
                f"{catalog['site_count']} Sites"
            )
        serve(
            args.host,
            args.port,
            args.plasma_host,
            args.plasma_port,
            tuple(args.cors_origins or ["*"]),
            args.output_root,
            provider,
        )
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    main()
