from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from plasma_client.client import PlasmaClient
from plasma_core.assets import ProgrammingAsset
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest, validate_job_id

from .diagnostics import execute_ps_loopback
from .engineering_targets import EngineeringPPUProvider, MockEngineeringPPUProvider


FLEET_CONTRACT_VERSION = "1"
WEB_REST_CONTRACT_VERSION = "3"
GATEWAY_SERVICE_NAME = "plasma-web-rest-gateway"


def _gateway_diagnostic(event: str, **fields: Any) -> None:
    print(
        json.dumps(
            {"component": GATEWAY_SERVICE_NAME, "event": event, **fields},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


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


def _with_rest_version(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "rest_contract_version": WEB_REST_CONTRACT_VERSION}


def _require_declared_keys(
    values: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str] | None = None,
    label: str = "request",
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unexpected fields: {', '.join(unknown)}")
    missing = sorted((required or set()) - set(values))
    if missing:
        raise ValueError(f"{label} is missing required fields: {', '.join(missing)}")


def _query_value(query: dict[str, list[str]], name: str, *, required: bool = False) -> str | None:
    values = query.get(name)
    if not values:
        if required:
            raise ValueError(f"query parameter {name} is required")
        return None
    if len(values) != 1:
        raise ValueError(f"query parameter {name} must appear exactly once")
    if required and values[0] == "":
        raise ValueError(f"query parameter {name} is required")
    return values[0]


class PlasmaWebHandler(BaseHTTPRequestHandler):
    client_factory: Callable[[], PlasmaClient] = PlasmaClient
    engineering_provider: EngineeringPPUProvider | None = None
    max_body_bytes = 24 * 1024 * 1024
    allowed_origins = frozenset({"*"})
    output_root = Path("output")
    static_root: Path | None = None

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

    def _static(self, request_path: str) -> bool:
        if self.static_root is None:
            return False

        root = self.static_root.resolve()
        relative_path = unquote(request_path).lstrip("/")
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
            return True

        if candidate.is_dir():
            candidate = candidate / "index.html"
        elif not candidate.is_file() and not Path(relative_path).suffix:
            candidate = root / "index.html"

        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
            return True

        content_type, _ = mimetypes.guess_type(candidate.name)
        if content_type is None:
            content_type = "application/octet-stream"
        elif content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable"
            if candidate.parent.name == "assets"
            else "no-cache",
        )
        self.end_headers()
        self.wfile.write(data)
        return True

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
        _gateway_diagnostic(
            "request_error",
            method=self.command,
            path=urlparse(self.path).path,
            error_type=type(exc).__name__,
            message=str(exc)[:300],
        )
        if isinstance(exc, PlasmaError):
            self._json(
                HTTPStatus.BAD_REQUEST,
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
                    {"ok": True, "service": GATEWAY_SERVICE_NAME, "gateway": "alive"},
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
                        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
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
                self._json(
                    HTTPStatus.OK,
                    _with_rest_version(self.engineering_provider.catalog()),
                )
                return

            engineering = self._engineering_target(parsed.path)
            if engineering is not None:
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                facility_id, ppu_id, tail = engineering
                query = parse_qs(parsed.query, keep_blank_values=True)
                if tail == ["api", "status"]:
                    _require_declared_keys(query, allowed={"job", "site"}, label="status query")
                    job = _query_value(query, "job")
                    site = _query_value(query, "site")
                    site_id = _parse_site_id(site) if site is not None else None
                    ppu_level_observation = job is None and site_id is None
                    started_at = time.monotonic()
                    if ppu_level_observation:
                        _gateway_diagnostic(
                            "engineering_ppu_status_start",
                            facility_id=facility_id,
                            ppu_id=ppu_id,
                        )
                    try:
                        payload = _run(
                            self.engineering_provider.status(
                                facility_id,
                                ppu_id,
                                site_id=site_id,
                                job_id=job,
                            )
                        )
                    except Exception as exc:
                        if ppu_level_observation:
                            _gateway_diagnostic(
                                "engineering_ppu_status_error",
                                facility_id=facility_id,
                                ppu_id=ppu_id,
                                elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
                                error_type=type(exc).__name__,
                            )
                        raise
                    if ppu_level_observation:
                        sites = payload.get("sites") if isinstance(payload, dict) else None
                        _gateway_diagnostic(
                            "engineering_ppu_status_ok",
                            facility_id=facility_id,
                            ppu_id=ppu_id,
                            elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
                            site_count=len(sites) if isinstance(sites, list) else None,
                        )
                    self._json(HTTPStatus.OK, payload)
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
                query = parse_qs(parsed.query, keep_blank_values=True)
                _require_declared_keys(query, allowed={"job", "site"}, label="status query")
                job = _query_value(query, "job")
                site = _query_value(query, "site")
                site_id = _parse_site_id(site) if site is not None else None
                self._json(
                    HTTPStatus.OK,
                    _run(self.client_factory().status(job_id=job, site_id=site_id)),
                )
                return
            parts = parsed.path.split("/")
            if len(parts) == 6 and parts[1:3] == ["api", "jobs"] and parts[4] == "files":
                self._download(parts[3], unquote(parts[5]))
                return
            if parsed.path != "/api" and not parsed.path.startswith("/api/"):
                if self._static(parsed.path):
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

    @staticmethod
    def _inline_asset(body: dict[str, Any]) -> ProgrammingAsset:
        encoded = body.get("asset_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("program and verify require asset_base64")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("asset_base64 is invalid") from exc
        asset = ProgrammingAsset.from_upload(
            name=str(body["asset_name"]),
            asset_type=str(body["asset_type"]),
            asset_format=str(body["asset_format"]),
            data=data,
            sha256=str(body["asset_sha256"]),
        )
        declared_size = body["asset_size"]
        if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size != asset.size:
            raise ValueError("asset_size does not match decoded Asset length")
        return asset

    def _job_request(
        self,
        body: dict[str, Any],
        *,
        client_id: str,
        default_timeout_s: float = 30.0,
        allow_inline_asset: bool = True,
    ) -> JobRequest:
        _require_declared_keys(
            body,
            allowed={
                "site_id",
                "operation",
                "timeout_s",
                "map_data",
                "offset",
                "length",
                "asset_name",
                "asset_type",
                "asset_format",
                "asset_size",
                "asset_sha256",
                "asset_base64",
                "session_id",
            },
            required={"site_id", "operation"},
            label="job request",
        )
        operation = Operation(str(body["operation"]))
        if operation not in {Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ}:
            raise ValueError("web gateway supports erase, program, verify, and read")

        common_fields = {"site_id", "operation", "timeout_s", "map_data"}
        if operation is Operation.READ:
            allowed_fields = common_fields | {"offset", "length"}
        elif operation in {Operation.PROGRAM, Operation.VERIFY}:
            if allow_inline_asset:
                allowed_fields = common_fields | {
                    "asset_name",
                    "asset_type",
                    "asset_format",
                    "asset_size",
                    "asset_sha256",
                    "asset_base64",
                }
                required_fields = {
                    "site_id",
                    "operation",
                    "asset_name",
                    "asset_type",
                    "asset_format",
                    "asset_size",
                    "asset_sha256",
                    "asset_base64",
                }
            else:
                allowed_fields = common_fields | {"session_id", "asset_sha256"}
                required_fields = {"site_id", "operation", "session_id", "asset_sha256"}
            _require_declared_keys(
                body,
                allowed=allowed_fields,
                required=required_fields,
                label="job request",
            )
        else:
            allowed_fields = common_fields

        if operation not in {Operation.PROGRAM, Operation.VERIFY}:
            _require_declared_keys(
                body,
                allowed=allowed_fields,
                required={"site_id", "operation"},
                label="job request",
            )

        map_data = body.get("map_data") or {}
        if operation is Operation.READ:
            map_data = self._read_map(body, map_data)
        site_id = _parse_site_id(body["site_id"])
        image = b""
        metadata: dict[str, Any] = {}
        if operation in {Operation.PROGRAM, Operation.VERIFY} and allow_inline_asset:
            asset = self._inline_asset(body)
            normalized = asset.normalize_image()
            image = normalized.data
            metadata = {
                "image_name": normalized.name,
                "source_asset_name": asset.name,
                "source_asset_sha256": asset.sha256,
                "source_asset_type": asset.asset_type.value,
                "source_asset_format": asset.asset_format.value,
            }
        return JobRequest(
            site_id=site_id,
            operation=operation,
            image=image,
            map_data=map_data,
            timeout_s=float(body.get("timeout_s", default_timeout_s)),
            client_id=client_id,
            metadata=metadata,
        )

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/engineering/diagnostics/loopback":
                try:
                    payload = _run(execute_ps_loopback(self._body(), self.client_factory))
                except PlasmaError as exc:
                    if exc.code in {ErrorCode.CONNECTION_FAILED, ErrorCode.CONNECTION_TIMEOUT}:
                        self._execution_unavailable()
                        return
                    raise
                self._json(HTTPStatus.OK, _with_rest_version(payload))
                return

            if parsed.path == "/api/engineering/session":
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                body = self._body()
                _require_declared_keys(
                    body,
                    allowed={"previous_session_id"},
                    label="Engineering session request",
                )
                previous = body.get("previous_session_id")
                if previous is not None and not isinstance(previous, str):
                    raise ValueError("previous_session_id must be a string")
                self._json(
                    HTTPStatus.CREATED,
                    _with_rest_version(self.engineering_provider.begin_session(previous)),
                )
                return

            engineering = self._engineering_target(parsed.path)
            if engineering is not None:
                if self.engineering_provider is None:
                    self._engineering_unavailable()
                    return
                facility_id, ppu_id, tail = engineering
                if tail == ["api", "programming-assets", "check"]:
                    body = self._body()
                    required = {
                        "session_id",
                        "asset_name",
                        "asset_type",
                        "asset_format",
                        "asset_size",
                        "asset_sha256",
                    }
                    _require_declared_keys(
                        body,
                        allowed=required,
                        required=required,
                        label="Programming Asset check",
                    )
                    self._json(
                        HTTPStatus.OK,
                        _with_rest_version(
                            self.engineering_provider.asset_cache_status(
                                str(body["session_id"]),
                                facility_id,
                                ppu_id,
                                str(body["asset_name"]),
                                str(body["asset_type"]),
                                str(body["asset_format"]),
                                body["asset_size"],
                                str(body["asset_sha256"]),
                            )
                        ),
                    )
                    return
                if tail == ["api", "programming-assets"]:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    allowed_query = {"session_id", "name", "type", "format", "sha256"}
                    _require_declared_keys(
                        query,
                        allowed=allowed_query,
                        required=allowed_query,
                        label="Programming Asset upload query",
                    )
                    session_id = _query_value(query, "session_id", required=True)
                    asset_name = _query_value(query, "name", required=True)
                    asset_type = _query_value(query, "type", required=True)
                    asset_format = _query_value(query, "format", required=True)
                    asset_sha256 = _query_value(query, "sha256", required=True)
                    assert None not in (session_id, asset_name, asset_type, asset_format, asset_sha256)
                    self._json(
                        HTTPStatus.CREATED,
                        _with_rest_version(
                            self.engineering_provider.cache_asset(
                                session_id,
                                facility_id,
                                ppu_id,
                                asset_name,
                                asset_type,
                                asset_format,
                                asset_sha256,
                                self._raw_body(),
                            )
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
                    request = self._job_request(
                        body,
                        client_id="plasma-web-engineering",
                        default_timeout_s=self.engineering_provider.job_timeout_s(facility_id, ppu_id),
                        allow_inline_asset=False,
                    )
                    operation = request.operation
                    session_id = (
                        body["session_id"]
                        if operation in {Operation.PROGRAM, Operation.VERIFY}
                        else None
                    )
                    asset_sha256 = (
                        body["asset_sha256"]
                        if operation in {Operation.PROGRAM, Operation.VERIFY}
                        else None
                    )
                    if session_id is not None and not isinstance(session_id, str):
                        raise ValueError("session_id must be a string")
                    if asset_sha256 is not None and not isinstance(asset_sha256, str):
                        raise ValueError("asset_sha256 must be a string")
                    self._json(
                        HTTPStatus.ACCEPTED,
                        _run(
                            self.engineering_provider.start_job(
                                facility_id,
                                ppu_id,
                                request,
                                session_id=session_id,
                                asset_sha256=asset_sha256,
                            )
                        ),
                    )
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
                return

            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                job_id = parsed.path.split("/")[3]
                body = self._body()
                _require_declared_keys(body, allowed=set(), label="cancel request")
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
    static_root: Path | None = None,
) -> None:
    PlasmaWebHandler.client_factory = staticmethod(lambda: PlasmaClient(plasma_host, plasma_port))
    PlasmaWebHandler.engineering_provider = engineering_provider
    PlasmaWebHandler.allowed_origins = frozenset(cors_origins)
    PlasmaWebHandler.output_root = output_root.resolve()
    PlasmaWebHandler.static_root = static_root.resolve() if static_root is not None else None
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
        "--static-root",
        type=Path,
        help="Serve a built Plasma Web Console and SPA routes from the Gateway origin",
    )
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
    parser.add_argument(
        "--engineering-mock-flash-size",
        type=int,
        default=4 * 1024 * 1024,
        help="Mock Flash bytes per Engineering Site (default: 4 MiB)",
    )
    args = parser.parse_args()

    if args.static_root is not None and not (args.static_root / "index.html").is_file():
        parser.error(f"static root must contain index.html: {args.static_root}")

    provider: MockEngineeringPPUProvider | None = None
    try:
        if args.engineering_mock:
            provider = MockEngineeringPPUProvider(
                args.engineering_mock_root,
                flash_size_bytes=args.engineering_mock_flash_size,
            )
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
            args.static_root,
        )
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    main()
