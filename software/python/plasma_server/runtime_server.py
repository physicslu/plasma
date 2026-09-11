from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from plasma_core.config import load_config
from plasma_core.protocol import PROTOCOL_VERSION

from .runtime_control import RuntimeControlServer
from .server import PlasmaServer


async def _run(config_path: Path, control_socket: Path | None) -> None:
    server = PlasmaServer(load_config(config_path))
    control = RuntimeControlServer(server.manager, control_socket) if control_socket is not None else None
    await server.start()
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
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.config, args.runtime_control_socket))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
