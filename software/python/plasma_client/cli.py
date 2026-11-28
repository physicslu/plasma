"""`plasma`: PPU-local Gateway debug client (direct, single PPU): status and cancel.

It submits no Programming Job: every Programming Job runs under a Manager
Batch Resource Reservation (U7), through the Unified CLI `plasmactl program`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from plasma_core.errors import PlasmaError

from .client import PlasmaClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plasma",
        description="Plasma PPU debug client (protocol v3.3): status and cancel",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9900)
    subcommands = parser.add_subparsers(dest="command", required=True)

    status = subcommands.add_parser("status")
    status.add_argument("--site", dest="site", type=int, help="one-based Programming Site ID (1..N)")
    status.add_argument("--job")

    cancel = subcommands.add_parser("cancel")
    cancel.add_argument("--job", required=True)
    return parser


async def _execute(args: argparse.Namespace) -> dict[str, Any]:
    client = PlasmaClient(args.host, args.port)
    if args.command == "status":
        return await client.status(site_id=args.site, job_id=args.job)
    return await client.cancel(args.job)


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(_execute(args))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": {"message": "cancel interrupted"}}), file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, json.JSONDecodeError, PlasmaError) as exc:
        if isinstance(exc, PlasmaError):
            error = {
                "error_code": exc.code.value,
                "error_type": exc.error_type,
                "message": exc.message,
                "recoverable": exc.recoverable,
                "context": exc.context,
            }
        else:
            error = {"error_type": type(exc).__name__, "message": str(exc)}
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
