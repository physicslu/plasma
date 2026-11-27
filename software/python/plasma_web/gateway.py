from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_base as base
from .engineering_targets import EngineeringPPUProvider
from .gateway_communication import ppu_response_budget_ms, request_with_gateway_policy
from .gateway_settings import GatewayCommunicationPolicy, GatewaySettingsController
from .ppu_network_settings import PPUNetworkSettingsController
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


FLEET_CONTRACT_VERSION = base.FLEET_CONTRACT_VERSION
WEB_REST_CONTRACT_VERSION = base.WEB_REST_CONTRACT_VERSION
GATEWAY_SERVICE_NAME = base.GATEWAY_SERVICE_NAME

# The Device Selector is Catalog-only and owned by Plasma Manager (OPF S5-B).
# The PPU Gateway has no Selector route, imports no Catalog module and answers
# the former Selector path like any unknown route (404).


def _mock_runtime_payload(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "mock_runtime": settings,
    }


def _gateway_settings_payload(settings: dict[str, int]) -> dict[str, Any]:
    policy = GatewayCommunicationPolicy(**settings)
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "gateway_settings": {
            **settings,
            "ppu_response_budget_ms": ppu_response_budget_ms(policy),
        },
    }


def _ppu_network_settings_payload(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "ppu_network_settings": settings,
        "activation": {
            "supported": False,
            "state": "not_implemented",
        },
    }


@dataclass(frozen=True, slots=True)
class TargetDeviceSnapshot:
    """An Engineering Job's exact target CLAIM (never Catalog qualification)."""

    vendor: str
    family: str
    identifier: str
    identifier_kind: str
    icpn: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "family": self.family,
            "identifier": self.identifier,
            "identifier_kind": self.identifier_kind,
            "icpn": self.icpn,
        }


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _validated_target_claim(value: Any, *, label: str) -> str:
    if (not isinstance(value, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}", value)
            or any(part in {".", "..", ""} for part in value.split("/"))):
        raise ValueError(f"{label} must be a valid exact target identifier")
    return value


def _parse_target_device(
    value: Any,
    *,
    label: str = "target_device",
) -> TargetDeviceSnapshot | None:
    if value is None:
        return None
    raw = _require_object(value, label)
    base._require_declared_keys(
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
    # User-supplied target identity is a CLAIM, not Catalog qualification.
    # No Catalog dependency is permitted in Programming Job submission.
    # The selected Runtime Provider must separately resolve exact-target
    # capabilities and refuse unsupported operations before any hardware I/O.
    vendor = vendor.strip()
    identifier = _validated_target_claim(identifier.strip(), label=label)
    if len(vendor) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in vendor):
        raise ValueError(f"{label} target identity is invalid")
    return TargetDeviceSnapshot(
        vendor=vendor,
        family="",
        identifier=identifier,
        identifier_kind="unverified_exact_target_claim",
        icpn=identifier,
    )


class PlasmaWebHandler(base.PlasmaWebHandler):
    """Canonical Plasma Web REST Gateway.

    The PPU no longer runs Batches (U10). Every Batch, including a single
    Programming of 1 Site x 1 Cycle, is owned by the Plasma Manager
    Programming Batch Coordinator (``/api/programming/batches``); the former
    PPU ``/api/batches`` routes answer 410 Gone.
    """

    gateway_settings = GatewaySettingsController()
    ppu_network_settings = PPUNetworkSettingsController()
    engineering_status_retry_backoff_s = 1.0

    @staticmethod
    def _batch_path(path: str) -> list[str] | None:
        parts = [unquote(part) for part in path.strip("/").split("/") if part]
        if len(parts) < 2 or parts[:2] != ["api", "batches"]:
            return None
        return parts[2:]

    def _batch_retired(self) -> None:
        self._json(
            HTTPStatus.GONE,
            {
                "ok": False,
                "error": {
                    "error_code": "PPU_BATCH_RETIRED",
                    "error_type": "PPU_BATCH_RETIRED",
                    "message": ("The PPU no longer runs Batches; submit Programming "
                                "to the Plasma Manager /api/programming/batches"),
                },
            },
        )

    @staticmethod
    def _is_mock_runtime_path(path: str) -> bool:
        return path.rstrip("/") == "/api/mock/runtime"

    @staticmethod
    def _is_gateway_settings_path(path: str) -> bool:
        return path.rstrip("/") == "/api/settings/gateway"

    @staticmethod
    def _is_ppu_network_settings_path(path: str) -> bool:
        return path.rstrip("/") == "/api/settings/ppu-network"

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
            # The Engineering Asset contract normally requires an Asset SHA.
            # Canonical Shared-Image Mock jobs may intentionally omit it so the
            # provider can generate one Synthetic Image from the immutable Mock
            # execution profile. The key is normalized to None only in this
            # Mock-specific handler; non-Mock providers remain fail-closed.
            body["asset_sha256"] = None
        return body

    @staticmethod
    def _validated_rest_owner(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError("execution_owner_id must be a non-empty string of at most 256 characters")
        return value

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
        if normalized.get("target") is not None:
            normalized["target"] = _validated_target_claim(normalized["target"], label="target")
        execution_owner_id = self._validated_rest_owner(normalized.pop("execution_owner_id", None))
        reservation_token = normalized.pop("resource_reservation_token", None)
        if reservation_token is not None and (execution_owner_id is None
                or type(reservation_token) is not str
                or re.fullmatch(r"[0-9a-f]{32}", reservation_token) is None):
            raise ValueError("resource_reservation_token requires a valid execution owner")
        request = super()._job_request(
            normalized,
            client_id=client_id,
            default_timeout_s=default_timeout_s,
            allow_inline_asset=allow_inline_asset,
        )
        if execution_owner_id is not None:
            owner_kind = "engineering_session" if client_id == "plasma-web-engineering" else "rest_client"
            request = replace(
                request,
                metadata={
                    **request.metadata,
                    "execution_owner_kind": owner_kind,
                    "execution_owner_id": execution_owner_id,
                },
            )
        if reservation_token is not None:
            request = replace(request, metadata={**request.metadata,
                                                 "resource_reservation_token": reservation_token})
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

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PlasmaError) and exc.code is ErrorCode.PPU_BUSY:
            base._gateway_diagnostic(
                "request_error",
                method=self.command,
                path=urlparse(self.path).path,
                error_type=exc.error_type,
                message=exc.message[:300],
            )
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "error_code": exc.code.value,
                        "error_type": exc.error_type,
                        "message": exc.message,
                        "recoverable": exc.recoverable,
                        "context": dict(exc.context),
                    },
                },
            )
            return
        super()._error(exc)

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

    def _communication_unavailable(self, exc: PlasmaError) -> None:
        base._gateway_diagnostic(
            "request_error",
            method=self.command,
            path=urlparse(self.path).path,
            error_type=exc.error_type,
            message=exc.message[:300],
        )
        self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "error": {
                    "error_code": exc.code.value,
                    "error_type": exc.error_type,
                    "message": exc.message,
                },
            },
        )

    def _engineering_status_request(self, parsed) -> bool:
        engineering = self._engineering_target(parsed.path)
        if engineering is None or engineering[2] != ["api", "status"]:
            return False
        if self.engineering_provider is None:
            self._engineering_unavailable()
            return True

        facility_id, ppu_id, _ = engineering
        ppu_level_observation = False
        started_at = time.monotonic()
        try:
            query = parse_qs(parsed.query, keep_blank_values=True)
            base._require_declared_keys(query, allowed={"job", "site"}, label="status query")
            job = base._query_value(query, "job")
            site = base._query_value(query, "site")
            site_id = base._parse_site_id(site) if site is not None else None
            ppu_level_observation = job is None and site_id is None
            if ppu_level_observation:
                base._gateway_diagnostic(
                    "engineering_ppu_status_start",
                    facility_id=facility_id,
                    ppu_id=ppu_id,
                )

            policy = self.gateway_settings.snapshot()

            def on_retry(attempt: int, retry_count: int, delay_s: float, error: PlasmaError) -> None:
                if not ppu_level_observation:
                    return
                base._gateway_diagnostic(
                    "engineering_ppu_status_retry",
                    facility_id=facility_id,
                    ppu_id=ppu_id,
                    attempt=attempt,
                    retry_count=retry_count,
                    delay_ms=round(delay_s * 1000, 3),
                    error_code=error.code.value,
                    error_type=error.error_type,
                )

            payload = base._run(
                request_with_gateway_policy(
                    lambda: self.engineering_provider.status(
                        facility_id,
                        ppu_id,
                        site_id=site_id,
                        job_id=job,
                    ),
                    policy,
                    retry_backoff_s=self.engineering_status_retry_backoff_s,
                    on_retry=on_retry,
                )
            )
        except Exception as exc:
            if ppu_level_observation:
                base._gateway_diagnostic(
                    "engineering_ppu_status_error",
                    facility_id=facility_id,
                    ppu_id=ppu_id,
                    elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
                    error_type=exc.error_type if isinstance(exc, PlasmaError) else type(exc).__name__,
                )
            if isinstance(exc, PlasmaError) and exc.code in {
                ErrorCode.CONNECTION_TIMEOUT,
                ErrorCode.CONNECTION_FAILED,
            }:
                self._communication_unavailable(exc)
            else:
                self._error(exc)
            return True

        provider_elapsed_ms = round((time.monotonic() - started_at) * 1000, 3)
        if ppu_level_observation:
            sites = payload.get("sites") if isinstance(payload, dict) else None
            base._gateway_diagnostic(
                "engineering_ppu_status_ok",
                facility_id=facility_id,
                ppu_id=ppu_id,
                elapsed_ms=provider_elapsed_ms,
                provider_elapsed_ms=provider_elapsed_ms,
                site_count=len(sites) if isinstance(sites, list) else None,
            )

        response_started_at = time.monotonic()
        try:
            self._json(HTTPStatus.OK, payload)
        except Exception as exc:
            if ppu_level_observation:
                base._gateway_diagnostic(
                    "engineering_ppu_status_response_error",
                    facility_id=facility_id,
                    ppu_id=ppu_id,
                    provider_elapsed_ms=provider_elapsed_ms,
                    response_write_elapsed_ms=round((time.monotonic() - response_started_at) * 1000, 3),
                    total_elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
                    error_type=type(exc).__name__,
                )
            self._error(exc)
            return True

        if ppu_level_observation:
            base._gateway_diagnostic(
                "engineering_ppu_status_response_sent",
                facility_id=facility_id,
                ppu_id=ppu_id,
                provider_elapsed_ms=provider_elapsed_ms,
                response_write_elapsed_ms=round((time.monotonic() - response_started_at) * 1000, 3),
                total_elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
            )
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if self._is_gateway_settings_path(parsed.path):
            try:
                self._json(HTTPStatus.OK, _gateway_settings_payload(self.gateway_settings.current()))
            except Exception as exc:
                self._error(exc)
            return

        if self._is_ppu_network_settings_path(parsed.path):
            try:
                self._json(
                    HTTPStatus.OK,
                    _ppu_network_settings_payload(self.ppu_network_settings.current()),
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

        if self._engineering_status_request(parsed):
            return

        if self._batch_path(parsed.path) is not None:
            self._batch_retired()
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/resource-reservations":
            try:
                body = self._body()
                base._require_declared_keys(body, allowed={"action", "owner_id", "token", "expected"},
                                            required={"action", "owner_id"}, label="Resource Reservation")
                result = base._run(self.client_factory().resource_reservation(
                    body["action"], body["owner_id"], body.get("token"), body.get("expected")))
                self._json(HTTPStatus.OK, {"ok": True, "reservation": result})
            except Exception as exc:
                self._error(exc)
            return
        if self._is_gateway_settings_path(parsed.path):
            try:
                self._json(
                    HTTPStatus.OK,
                    _gateway_settings_payload(self.gateway_settings.update(self._body())),
                )
            except Exception as exc:
                self._error(exc)
            return

        if self._is_ppu_network_settings_path(parsed.path):
            try:
                self._json(
                    HTTPStatus.OK,
                    _ppu_network_settings_payload(self.ppu_network_settings.update(self._body())),
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

        if self._batch_path(parsed.path) is not None:
            self._batch_retired()
            return
        super().do_POST()


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
    network_settings = PPUNetworkSettingsController(output_root / "ppu-network-settings.yaml")
    PlasmaWebHandler.client_factory = staticmethod(lambda: base.PlasmaClient(plasma_host, plasma_port))
    PlasmaWebHandler.engineering_provider = engineering_provider
    PlasmaWebHandler.gateway_settings = settings
    PlasmaWebHandler.ppu_network_settings = network_settings
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
