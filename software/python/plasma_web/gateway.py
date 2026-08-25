from __future__ import annotations

import argparse
import base64
from dataclasses import replace
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_legacy as legacy
from .batch_runtime import BatchRuntimeManager, BatchTargetDeviceSnapshot
from .device_catalog import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT, get_default_device_catalog
from .engineering_targets import EngineeringPPUProvider
from .gateway_settings import GatewaySettingsController
from .mock_batch_runtime import MockAwareBatchRuntimeManager
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


FLEET_CONTRACT_VERSION = legacy.FLEET_CONTRACT_VERSION
WEB_REST_CONTRACT_VERSION = legacy.WEB_REST_CONTRACT_VERSION
GATEWAY_SERVICE_NAME = legacy.GATEWAY_SERVICE_NAME


def _batch_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "batch": snapshot,
    }


def _mock_runtime_payload(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "mock_runtime": settings,
    }


def _gateway_settings_payload(settings: dict[str, int]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "gateway_settings": settings,
    }


def _device_search_payload(query: str, limit: int) -> dict[str, Any]:
    catalog = get_default_device_catalog()
    matches = catalog.search(query, limit=limit)
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "query": query,
        "catalog_size": catalog.size,
        "count": len(matches),
        "results": [record.to_payload() for record in matches],
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


def _parse_target_device(
    value: Any,
    *,
    label: str = "target_device",
) -> BatchTargetDeviceSnapshot | None:
    if value is None:
        return None
    raw = _require_object(value, label)
    legacy._require_declared_keys(
        raw,
        allowed={"vendor", "identifier"},
        required={"vendor", "identifier"},
        label=label,
    )
    vendor = raw["vendor"]
    identifier = raw["identifier"]
    if not isinstance(vendor, str) or not vendor.strip():
        raise ValueError(f"{label} vendor is required")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError(f"{label} identifier is required")
    record = get_default_device_catalog().resolve(vendor, identifier)
    if record is None:
        raise ValueError(f"{label} must resolve to one canonical Device Catalog record")
    return BatchTargetDeviceSnapshot(
        vendor=record.vendor,
        family=record.family,
        identifier=record.identifier,
        identifier_kind=record.identifier_kind,
        icpn=record.icpn,
    )


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
    gateway_settings = GatewaySettingsController()

    @staticmethod
    def _batch_path(path: str) -> list[str] | None:
        parts = [unquote(part) for part in path.strip("/").split("/") if part]
        if len(parts) < 2 or parts[:2] != ["api", "batches"]:
            return None
        return parts[2:]

    @staticmethod
    def _is_mock_runtime_path(path: str) -> bool:
        return path.rstrip("/") == "/api/mock/runtime"

    @staticmethod
    def _is_gateway_settings_path(path: str) -> bool:
        return path.rstrip("/") == "/api/settings/gateway"

    @staticmethod
    def _is_device_search_path(path: str) -> bool:
        return path.rstrip("/") == "/api/devices/search"

    @classmethod
    def _mock_provider(cls) -> SharedImageMockEngineeringPPUProvider | None:
        provider = cls.engineering_provider
        return provider if isinstance(provider, SharedImageMockEngineeringPPUProvider) else None

    def _body(self) -> dict[str, Any]:
        body = super()._body()
        if self._mock_provider() is None:
            return body
        engineering = self._engineering_target(urlparse(self.path).path)
        if engineering is None or engineering[2] != ["api", "jobs"]:
            return body
        operation = body.get("operation")
        if operation in {Operation.PROGRAM.value, Operation.VERIFY.value} and "asset_sha256" not in body:
            # The legacy Engineering contract normally requires an Asset SHA.
            # Canonical Shared-Image Mock jobs may intentionally omit it so the
            # provider can generate one Synthetic Image from the immutable Mock
            # execution profile. The key is normalized to None only in this
            # Mock-specific handler; non-Mock providers remain fail-closed.
            body["asset_sha256"] = None
        return body

    def _job_request(
        self,
        body: dict[str, Any],
        *,
        client_id: str,
        default_timeout_s: float = 30.0,
        allow_inline_asset: bool = True,
    ):
        normalized = dict(body)
        raw_target_device = normalized.pop("target_device", None)
        request = super()._job_request(
            normalized,
            client_id=client_id,
            default_timeout_s=default_timeout_s,
            allow_inline_asset=allow_inline_asset,
        )
        if raw_target_device is None:
            return request
        if client_id != "plasma-web-engineering":
            raise ValueError("target_device is only valid for an Engineering PPU job")
        target_device = _parse_target_device(
            raw_target_device,
            label="Engineering target_device",
        )
        assert target_device is not None
        return replace(
            request,
            target=target_device.icpn or target_device.identifier,
            metadata={
                **request.metadata,
                "target_device": target_device.to_dict(),
            },
        )

    def _mock_unavailable(self) -> None:
        self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "error": {
                    "error_code": ErrorCode.BATCH_INFRASTRUCTURE_ERROR.value,
                    "error_type": "MOCK_RUNTIME_UNAVAILABLE",
                    "message": "Mock runtime settings are not enabled",
                },
            },
        )

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

    def _batch_error(self, exc: Exception) -> None:
        if isinstance(exc, PlasmaError) and exc.code in {
            ErrorCode.JOB_NOT_FOUND,
            ErrorCode.BATCH_NOT_FOUND,
        }:
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": {
                        "error_code": exc.code.value,
                        "error_type": exc.error_type,
                        "message": exc.message,
                    },
                },
            )
            return
        self._error(exc)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if self._is_gateway_settings_path(parsed.path):
            try:
                self._json(HTTPStatus.OK, _gateway_settings_payload(self.gateway_settings.current()))
            except Exception as exc:
                self._error(exc)
            return

        if self._is_device_search_path(parsed.path):
            try:
                params = parse_qs(parsed.query, keep_blank_values=True)
                query = params.get("q", [""])[0]
                raw_limit = params.get("limit", [str(DEFAULT_SEARCH_LIMIT)])[0]
                limit = int(raw_limit)
                if limit < 1 or limit > MAX_SEARCH_LIMIT:
                    raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
                self._json(HTTPStatus.OK, _device_search_payload(query, limit))
            except (TypeError, ValueError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": {
                            "error_type": "INVALID_DEVICE_SEARCH",
                            "message": str(exc),
                        },
                    },
                )
            except Exception as exc:
                self._error(exc)
            return

        if self._is_mock_runtime_path(parsed.path):
            try:
                provider = self._mock_provider()
                if provider is None:
                    self._mock_unavailable()
                    return
                self._json(HTTPStatus.OK, _mock_runtime_payload(provider.mock_runtime_settings()))
            except Exception as exc:
                self._error(exc)
            return

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
            self._batch_error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if self._is_gateway_settings_path(parsed.path):
            try:
                self._json(
                    HTTPStatus.OK,
                    _gateway_settings_payload(self.gateway_settings.update(self._body())),
                )
            except Exception as exc:
                self._error(exc)
            return

        if self._is_mock_runtime_path(parsed.path):
            try:
                provider = self._mock_provider()
                if provider is None:
                    self._mock_unavailable()
                    return
                body = self._body()
                self._json(
                    HTTPStatus.OK,
                    _mock_runtime_payload(provider.update_mock_runtime_settings(body)),
                )
            except Exception as exc:
                self._error(exc)
            return

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
                        "target_device",
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
                    target_device=_parse_target_device(
                        body.get("target_device"),
                        label="Batch target_device",
                    ),
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
            self._batch_error(exc)


def serve(
    host: str,
    port: int,
    plasma_host: str,
    plasma_port: int,
    cors_origins: tuple[str, ...] = ("*",),
    output_root: Path = Path("output"),
    engineering_provider: EngineeringPPUProvider | None = None,
    static_root: Path | None = None,
    gateway_settings_path: Path | None = None,
) -> None:
    settings = GatewaySettingsController(gateway_settings_path or (output_root / "gateway-settings.yaml"))
    PlasmaWebHandler.client_factory = staticmethod(lambda: legacy.PlasmaClient(plasma_host, plasma_port))
    PlasmaWebHandler.engineering_provider = engineering_provider
    PlasmaWebHandler.gateway_settings = settings
    if isinstance(engineering_provider, SharedImageMockEngineeringPPUProvider):
        PlasmaWebHandler.batch_runtime = MockAwareBatchRuntimeManager(engineering_provider, gateway_settings=settings)
    else:
        PlasmaWebHandler.batch_runtime = (
            BatchRuntimeManager(engineering_provider, gateway_settings=settings)
            if engineering_provider is not None
            else None
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
        "--gateway-settings",
        type=Path,
        help="Persistent Gateway communication settings YAML (default: <output-root>/gateway-settings.yaml)",
    )
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
    parser.add_argument(
        "--engineering-mock-profile",
        type=Path,
        help="Persistent Mock runtime profile YAML (default: <engineering-mock-root>/mock-runtime.yaml)",
    )
    args = parser.parse_args()

    if args.static_root is not None and not (args.static_root / "index.html").is_file():
        parser.error(f"static root must contain index.html: {args.static_root}")

    provider: SharedImageMockEngineeringPPUProvider | None = None
    try:
        if args.engineering_mock:
            profile_path = args.engineering_mock_profile or (args.engineering_mock_root / "mock-runtime.yaml")
            provider = SharedImageMockEngineeringPPUProvider(
                args.engineering_mock_root,
                flash_size_bytes=args.engineering_mock_flash_size,
                mock_profile_path=profile_path,
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
            args.gateway_settings,
        )
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    main()
