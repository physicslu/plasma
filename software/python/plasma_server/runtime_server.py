from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from plasma_core.config import load_config
from plasma_core.protocol import PROTOCOL_VERSION

from .runtime_control import RuntimeControlServer
from .server import PlasmaServer


async def _run(config_path: Path, control_socket: Path | None,
               package_actions_config: Path | None = None,
               mock_asset_set: tuple[Path, Path] | None = None) -> None:
    server = PlasmaServer(load_config(config_path))
    package_actions = None
    if mock_asset_set is not None:
        if control_socket is None or package_actions_config is not None:
            raise SystemExit("--mock-asset-set-product-root requires --runtime-control-socket "
                             "and no package actions")
        from .mock_resources import install_bootstrap_asset_set
        install_bootstrap_asset_set(server.manager, product_root=mock_asset_set[0],
                                    control_plane=mock_asset_set[1])
    if package_actions_config is not None:
        if control_socket is None:
            raise SystemExit("--package-actions-config requires --runtime-control-socket")
        from .package_actions import from_config
        package_actions = from_config(server.manager, package_actions_config)
    control = (RuntimeControlServer(server.manager, control_socket, package_actions)
               if control_socket is not None else None)
    await server.start()
    if package_actions is not None:
        print("Stage C package actions reconcile:", package_actions.reconcile_on_start())
    if control is not None:
        await control.start()
    print(
        f"Plasma Server v{PROTOCOL_VERSION} listening on "
        f"{server.address[0]}:{server.address[1]}"
    )
    try:
        await server.serve_forever()
    finally:
        if control is not None:
            await control.close()
        await server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma multi-site programming server")
    parser.add_argument("--config", type=Path, default=Path("config/plasma.yaml"))
    parser.add_argument("--runtime-control-socket", type=Path)
    parser.add_argument("--package-actions-config", type=Path,
                        help="Stage C plasma.ppu.package-actions-config.v1 (default: disabled)")
    # Mock PPU only (U10): every Site must be a Mock Site. The Active Set comes
    # from the PPU Bootstrap product root that B3 publishes, read through the
    # control plane's ppu_asset_set.py, exactly as a Z2 Runtime is wired.
    parser.add_argument("--mock-asset-set-product-root", type=Path,
                        help="Mock PPU: Bootstrap product root holding the B3 Active Set")
    parser.add_argument("--mock-asset-set-control-plane", type=Path,
                        help="Mock PPU: directory holding ppu_asset_set.py")
    args = parser.parse_args()
    mock_asset_set = None
    if (args.mock_asset_set_product_root is None) != (args.mock_asset_set_control_plane is None):
        parser.error("--mock-asset-set-product-root and --mock-asset-set-control-plane go together")
    if args.mock_asset_set_product_root is not None:
        mock_asset_set = (args.mock_asset_set_product_root.resolve(),
                          args.mock_asset_set_control_plane.resolve())
    # The Runtime installer owns ExecStart; the Stage C drop-in enables
    # package actions through this environment variable instead.
    package_actions = args.package_actions_config
    if package_actions is None and os.environ.get("PLASMA_PACKAGE_ACTIONS_CONFIG"):
        package_actions = Path(os.environ["PLASMA_PACKAGE_ACTIONS_CONFIG"])
    try:
        run = (_run(args.config, args.runtime_control_socket, package_actions)
               if mock_asset_set is None else
               _run(args.config, args.runtime_control_socket, package_actions, mock_asset_set))
        asyncio.run(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
