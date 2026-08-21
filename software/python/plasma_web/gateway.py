from __future__ import annotations

import argparse
import base64
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_legacy as legacy
from .batch_runtime import BatchRuntimeManager
from .engineering_targets import EngineeringPPUProvider, MockEngineeringPPUProvider


FLEET_CONTRACT_VERSION = legacy.FLEET_CONTRACT_VERSION
WEB_REST_CONTRACT_VERSION = legacy.WEB_REST_CONTRACT_VERSION
GATEWAY_SERVICE_NAME = legacy.GATEWAY_SERVICE_NAME


def _batch_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "batch": snapshot,
    }


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _parse_policy(body: dict[str, Any]) -> BatchExecutionPolicy:
    raw = _require_object(body.get("execution_policy", {}), "execution_policy")
    legacy._require_declared_keys(
        raw,
        allowed={"repeat_count", "site_retry_limit", "failed_site_stop_threshold"},
        label="Batch execution_policy",
    )
    threshold = raw.get("failed_site_stop_threshold")
    return BatchExecutionPolicy(
        repeat_count=raw.get("repeat_count", 1),
        site_retry_limit=raw.get("site_retry_limit", 0),
        failed_site_stop_threshold=threshold,
    )


def _parse_targets(value: Any) -> tuple[BatchTarget, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Batch targets must be a non-empty array")
    targets: list[BatchTarget] = []
    for index, raw in enumerate(value):
        item = _require_object(raw, f"Batch target {index}")
        legacy._require_declared_keys(
            item,
            allowed={"facility_id", "ppu_id", "site_ids"},
            required={"facility_id", "ppu_id", "site_ids"},
            label=f"Batch target {index}",
        )
        site_ids = item["site_ids"]
        if not isinstance(site_ids, list) or not site_ids:
            raise ValueError(f"Batch target {index} site_ids must be a non-empty array")
        for raw_site_id in site_ids:
            site_id = legacy._parse_site_id(raw_site_id)
            targets.append(
                BatchTarget(
                    facility_id=str(item["facility_id"]),
                    ppu_id=str(item["ppu_id"]),
                    site_id=site_id,
                )
            )
    return tuple(targets)


def _parse_asset(value: Any) -> ProgrammingAsset | None:
    if value is None:
        return None
    raw = _require_object(value, "Batch asset")
    required = {
        "asset_name",
        "asset_type",
        "asset_format",
        "asset_size",
        "asset_sha256",
        "asset_base64",
    }
    legacy._require_declared_keys(raw, allowed=required, required=required, label="Batch asset")
    encoded = raw["asset_base64"]
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Batch asset_base64 is required")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("Batch asset_base64 is invalid") from exc
    asset = ProgrammingAsset.from_upload(
        name=str(raw["asset_name"]),
        asset_type=str(raw["asset_type"]),
        asset_format=str(raw["asset_format"]),
        data=data,
        sha256=str(raw["asset_sha256"]),
    )
    declared_size = raw["asset_size"]
    if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size != asset.size:
        raise ValueError("Batch asset_size does not match decoded Asset length")
    return asset


def _parse_read(value: Any) -> tuple[int, int]:
    if value is None:
        return 0, 256
    raw = _require_object(value, "Batch read")
    legacy._require_declared_keys(raw, allowed={"offset", "length"}, label="Batch read")
    offset = raw.get("offset", 0)
    length = raw.get("length", 256)
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or isinstance(length, bool)
        or not isinstance(length, int)
        or length <= 0
    ):
        raise ValueError("Batch read offset/length is invalid")
    return offset, length


class PlasmaWebHandler(legacy.PlasmaWebHandler):
    """Canonical Plasma Web REST Gateway with server-side Batch orchestration."""

    batch_runtime: BatchRuntimeManager | None = None

    @staticmethod
    def _batch_path(path: str) -> list[str] | None:
        parts = [unquote(part) for part in path.strip("/").split("/") if part]
        if len(parts) < 2 or parts[:2] != ["api", "batches"]:
            return None
        return parts[2:]

    def _batch_unavailable(self) -> None:
        self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "error": {
                    "error_code": ErrorCode.BATCH_INFRASTRUCTURE_ERROR.value,
                    "error_type": "BATCH_INFRASTRUCTURE_ERROR",
                    "message": "Server-side Batch runtime is not enabled",
                },
            },
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        tail = self._batch_path(parsed.path)
        if tail is None:
            super().do_GET()
            return
        try:
            if self.batch_runtime is None:
                self._batch_unavailable()
                return
            if len(tail) == 1:
                self._json(HTTPStatus.OK, _batch_payload(self.batch_runtime.get(tail[0])))
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        tail = self._batch_path(parsed.path)
        if tail is None:
            super().do_POST()
            return
        try:
            if self.batch_runtime is None:
                self._batch_unavailable()
                return
            if not tail:
                body = self._body()
                legacy._require_declared_keys(
                    body,
                    allowed={
                        "session_id",
                        "targets",
                        "operations",
                        "execution_policy",
                        "asset",
                        "read",
                    },
                    required={"targets", "operations", "execution_policy"},
                    label="Batch request",
                )
                session_id = body.get("session_id")
                if session_id is not None and not isinstance(session_id, str):
                    raise ValueError("Batch session_id must be a string")
                operations = body["operations"]
                if not isinstance(operations, list):
                    raise ValueError("Batch operations must be an array")
                read_offset, read_length = _parse_read(body.get("read"))
                snapshot = self.batch_runtime.create_batch(
                    targets=_parse_targets(body["targets"]),
                    operations=operations,
                    policy=_parse_policy(body),
                    session_id=session_id,
                    asset=_parse_asset(body.get("asset")),
                    read_offset=read_offset,
                    read_length=read_length,
                )
                self._json(HTTPStatus.ACCEPTED, _batch_payload(snapshot))
                return
            if len(tail) == 2 and tail[1] == "cancel":
                body = self._body()
                legacy._require_declared_keys(body, allowed=set(), label="Batch cancel request")
                self._json(HTTPStatus.OK, _batch_payload(self.batch_runtime.cancel(tail[0])))
                return
            if len(tail) == 5 and tail[1] == "targets" and tail[4] == "cancel":
                body = self._body()
                legacy._require_declared_keys(body, allowed=set(), label="Batch PPU cancel request")
                self._json(
                    HTTPStatus.OK,
                    _batch_payload(
                        self.batch_runtime.cancel_ppu(
                            tail[0],
                            tail[2],
                            tail[3],
                        )
                    ),
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"message": "not found"}})
        except Exception as exc:
            self._error(exc)


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
    PlasmaWebHandler.client_factory = staticmethod(lambda: legacy.PlasmaClient(plasma_host, plasma_port))
    PlasmaWebHandler.engineering_provider = engineering_provider
    PlasmaWebHandler.batch_runtime = (
        BatchRuntimeManager(engineering_provider) if engineering_provider is not None else None
    )
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
        runtime = PlasmaWebHandler.batch_runtime
        PlasmaWebHandler.batch_runtime = None
        if runtime is not None:
            runtime.close()


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
