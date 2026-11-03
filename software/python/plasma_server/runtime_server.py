from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from plasma_core.config import load_config
from plasma_core.protocol import PROTOCOL_VERSION

from .runtime_control import RuntimeControlServer
from .server import PlasmaServer


async def _run(config_path: Path, control_socket: Path | None,
               package_actions_config: Path | None = None) -> None:
    server = PlasmaServer(load_config(config_path))
    package_actions = None
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
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.config, args.runtime_control_socket, args.package_actions_config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
