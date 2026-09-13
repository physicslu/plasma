from __future__ import annotations

import argparse
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import gateway as canonical_gateway
from . import gateway_phase2 as phase2
from .configured_mock_provider import ConfiguredMockEngineeringPPUProvider
from .engineering_targets import EngineeringPPUProvider
from .gateway_runner import serve_handler
from .runtime_activation import (
    RuntimeActivationError,
    RuntimeActivationHelperClient,
    SiteRuntimeActivationController,
    desired_runtime_revision,
)
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


SITE_RUNTIME_ACTIVATION_PATH = "/api/settings/sites/activation"


class SiteRuntimeActivationSupportMixin:
    """PPU-level activation of persisted Site Desired state via bounded restart helper."""

    _runtime_activation_socket: Path | None = None

    @classmethod
    def configure_runtime_activation(cls, socket_path: Path | None) -> None:
        cls._runtime_activation_socket = socket_path.expanduser().resolve() if socket_path is not None else None

    def _site_configuration_payload(
        self,
        *,
        actual_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = actual_snapshot
        if snapshot is None:
            try:
                snapshot = self._local_snapshot()
            except Exception:
                snapshot = None
        payload = super()._site_configuration_payload(actual_snapshot=snapshot)
        configuration = payload["site_configuration"]
        configuration["runtime_apply_supported"] = self._runtime_activation_socket is not None
        configuration["desired_runtime_revision"] = desired_runtime_revision(configuration)
        ppu = snapshot.get("ppu") if isinstance(snapshot, dict) else None
        configuration["runtime_ppu_id"] = ppu.get("ppu_id") if isinstance(ppu, dict) else None
        return payload

    def _runtime_activation_status_payload(self) -> dict[str, Any]:
        try:
            snapshot = self._local_snapshot()
            site_payload = self._site_configuration_payload(actual_snapshot=snapshot)
            configuration = site_payload["site_configuration"]
            reconciliation = configuration["reconciliation"]
            revision = configuration["desired_runtime_revision"]
            ppu_id = configuration["runtime_ppu_id"]
        except Exception:
            desired = self._site_configuration_controller().current()
            revision = desired_runtime_revision(
                {
                    "sites": [
                        {
                            "site_id": site["site_id"],
                            "desired_revision": site["desired_revision"],
                        }
                        for site in desired["sites"]
                    ]
                }
            )
            reconciliation = "actual_unavailable"
            ppu_id = None
        return {
            "ok": True,
            "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
            "runtime_activation": {
                "supported": self._runtime_activation_socket is not None,
                "state": "in_sync" if reconciliation == "in_sync" else "activation_required" if reconciliation == "restart_required" else reconciliation,
                "desired_runtime_revision": revision,
                "ppu_id": ppu_id,
                "reconciliation": reconciliation,
            },
        }

    def _runtime_activation_controller(self) -> SiteRuntimeActivationController:
        socket_path = self._runtime_activation_socket
        if socket_path is None:
            raise RuntimeActivationError(
                "runtime activation helper is not configured",
                error_type="RUNTIME_ACTIVATION_UNAVAILABLE",
                http_status=503,
            )
        site_configuration = self._site_configuration_controller()
        return SiteRuntimeActivationController(
            RuntimeActivationHelperClient(socket_path),
            lambda: self._site_configuration_payload(),
            self._local_snapshot,
            lambda snapshot: self._site_configuration_payload(actual_snapshot=snapshot),
            activation_guard=site_configuration.runtime_activation_guard,
        )

    def _runtime_activation_error(self, exc: RuntimeActivationError) -> None:
        self._json(
            exc.http_status,
            {
                "ok": False,
                "error": {
                    "error_type": exc.error_type,
                    "message": exc.message,
                    "context": dict(exc.context),
                },
            },
        )

    def _handle_runtime_activation_get(self, path: str) -> bool:
        if path.rstrip("/") != SITE_RUNTIME_ACTIVATION_PATH:
            return False
        self._json(HTTPStatus.OK, self._runtime_activation_status_payload())
        return True

    def _handle_runtime_activation_post(self, path: str) -> bool:
        if path.rstrip("/") != SITE_RUNTIME_ACTIVATION_PATH:
            return False
        controller = self._runtime_activation_controller()
        result = controller.activate(self._body())
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
                "runtime_activation": result,
            },
        )
        return True


class Phase3PlasmaWebHandler(SiteRuntimeActivationSupportMixin, phase2.Phase2PlasmaWebHandler):
    """Canonical deployed Gateway handler: P3 + P2 + canonical REST features."""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_runtime_activation_get(path):
                return
        except RuntimeActivationError as exc:
            self._runtime_activation_error(exc)
            return
        except Exception as exc:
            self._error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_runtime_activation_post(path):
                return
        except RuntimeActivationError as exc:
            self._runtime_activation_error(exc)
            return
        except Exception as exc:
            self._error(exc)
            return
        super().do_POST()


# Compatibility alias for callers that imported the Phase-3 handler by the
# historical generic name.  Startup no longer mutates this alias or any handler
# variable in gateway_phase2/gateway at runtime.
PlasmaWebHandler = Phase3PlasmaWebHandler


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plasma Phase-3 browser REST gateway")
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
    parser.add_argument("--runtime-activation-socket", type=Path)
    parser.add_argument("--network-activation-socket", type=Path)
    parser.add_argument("--ppu-config", type=Path, default=Path("config/plasma.yaml"))

    provider = parser.add_mutually_exclusive_group()
    provider.add_argument(
        "--engineering-mock",
        action="store_true",
        help="Enable the server-side Engineering mock Facility/PPU provider",
    )
    provider.add_argument(
        "--engineering-configured-mock",
        action="store_true",
        help="Expose the canonical configured local PPU as the Engineering Mock Programming provider",
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
    return parser


def _configure_handler(handler: type[Phase3PlasmaWebHandler], args: argparse.Namespace) -> None:
    if not issubclass(handler, SiteRuntimeActivationSupportMixin):
        raise RuntimeError("configured Phase 3 Gateway handler lacks Site runtime activation support")
    if not issubclass(handler, phase2.PPUNetworkActivationSupportMixin):
        raise RuntimeError("configured Phase 3 Gateway handler lacks PPU network activation support")
    if not issubclass(handler, phase2.SiteConfigurationSupportMixin):
        raise RuntimeError("configured Phase 3 Gateway handler lacks Site configuration support")

    handler.configure_runtime_activation(args.runtime_activation_socket)
    handler.configure_network_activation(
        socket_path=args.network_activation_socket,
        output_root=args.output_root,
        plasma_host=args.plasma_host,
        plasma_port=args.plasma_port,
    )
    handler.configure_site_configuration(args.ppu_config)


def _build_provider(args: argparse.Namespace) -> EngineeringPPUProvider | None:
    if args.engineering_configured_mock:
        provider = ConfiguredMockEngineeringPPUProvider(args.ppu_config)
        provider.start()
        catalog = provider.catalog()
        print(
            "Configured Engineering mock PPU provider ready: "
            f"{catalog['facility_count']} facility / {catalog['ppu_count']} PPU / "
            f"{catalog['site_count']} Sites"
        )
        return provider

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
        return provider

    return None


def main(
    *,
    handler_class: type[Phase3PlasmaWebHandler] = Phase3PlasmaWebHandler,
    argv: list[str] | None = None,
) -> None:
    """Run the deployed Gateway with explicit handler composition.

    The selected handler is passed directly to the HTTP server.  No phase module
    replaces another module's ``PlasmaWebHandler`` variable and Phase 3 no longer
    enters through ``gateway_phase2.main()``.
    """

    parser = _parser()
    args = parser.parse_args(argv)
    if args.static_root is not None and not (args.static_root / "index.html").is_file():
        parser.error(f"static root must contain index.html: {args.static_root}")

    _configure_handler(handler_class, args)
    provider: EngineeringPPUProvider | None = None
    try:
        provider = _build_provider(args)
        serve_handler(
            handler_class,
            host=args.host,
            port=args.port,
            plasma_host=args.plasma_host,
            plasma_port=args.plasma_port,
            cors_origins=tuple(args.cors_origins or ["*"]),
            output_root=args.output_root,
            engineering_provider=provider,
            static_root=args.static_root,
            gateway_settings_path=args.gateway_settings,
        )
    finally:
        if provider is not None:
            provider.close()
        handler_class.close_network_activation()


if __name__ == "__main__":
    main()
