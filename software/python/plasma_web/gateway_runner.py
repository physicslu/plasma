from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path

from . import gateway as canonical_gateway
from . import gateway_base as base
from .engineering_targets import EngineeringPPUProvider
from .gateway_settings import GatewaySettingsController
from .ppu_network_settings import PPUNetworkSettingsController


def serve_handler(
    handler_class: type[canonical_gateway.PlasmaWebHandler],
    *,
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
    """Serve one explicit Gateway handler class without mutating module globals.

    Phase-specific and secure Gateway entrypoints compose their handler class
    explicitly, then delegate common runtime wiring here.  This keeps the
    canonical Batch/settings/provider ownership identical while avoiding the
    historical pattern of replacing ``gateway.PlasmaWebHandler`` at runtime.
    """

    settings = GatewaySettingsController(gateway_settings_path or (output_root / "gateway-settings.yaml"))
    network_settings = PPUNetworkSettingsController(output_root / "ppu-network-settings.yaml")
    handler_class.client_factory = staticmethod(lambda: base.PlasmaClient(plasma_host, plasma_port))
    handler_class.engineering_provider = engineering_provider
    handler_class.gateway_settings = settings
    handler_class.ppu_network_settings = network_settings
    handler_class.batch_runtime = canonical_gateway._build_batch_runtime(
        engineering_provider,
        settings=settings,
        output_root=output_root,
    )
    handler_class.allowed_origins = frozenset(cors_origins)
    handler_class.output_root = output_root.resolve()
    handler_class.static_root = static_root.resolve() if static_root is not None else None

    server = ThreadingHTTPServer((host, port), handler_class)
    print(f"Plasma Web REST Gateway listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime = handler_class.batch_runtime
        handler_class.batch_runtime = None
        if runtime is not None:
            runtime.close()
