#!/usr/bin/env python3
"""Qualify eight real OpenOCD workers inside the deployed ARMv7 QEMU PPU.

This is software/control-plane evidence only. Workers use OpenOCD's dummy
adapter. The script never touches SWD/JTAG, PL, target power/reset, target
detection, flash, or a real IC.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence


class AcceptanceError(RuntimeError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"{path} must contain a JSON object")
    return value


def _runtime_paths(product_root: Path) -> tuple[Path, Path, Path]:
    install = product_root / "install"
    release = _read_object(install / "last-install.json")
    openocd = _read_object(install / "openocd-runtime.json")

    release_root = Path(str(release.get("release_root", "")))
    app = release_root / "runtime" / "ppu" / "ppu.pyz"
    binary = Path(str(openocd.get("binary", "")))
    scripts = Path(str(openocd.get("scripts_root", "")))
    if not app.is_file():
        raise AcceptanceError(f"deployed PPU zipapp is missing: {app}")
    if not binary.is_file():
        raise AcceptanceError(f"installed OpenOCD binary is missing: {binary}")
    if not scripts.is_dir():
        raise AcceptanceError(f"installed OpenOCD scripts are missing: {scripts}")
    if openocd.get("hardware_runtime_ready") is not False:
        raise AcceptanceError("OpenOCD install evidence opened the hardware boundary")
    return app, binary, scripts


async def _run(product_root: Path, site_count: int) -> dict[str, Any]:
    if site_count != 8:
        raise AcceptanceError("this qualification requires exactly eight Sites")

    app, binary, scripts = _runtime_paths(product_root)
    sys.path.insert(0, str(app))
    try:
        from plasma_interfaces.openocd_worker import OpenOCDWorker
    except Exception as exc:
        raise AcceptanceError(f"cannot import deployed OpenOCDWorker: {exc}") from exc

    workers = [
        OpenOCDWorker(
            site_id=site_id,
            executable=binary,
            scripts_root=scripts,
            startup_timeout_s=5.0,
            command_timeout_s=2.0,
        )
        for site_id in range(1, site_count + 1)
    ]
    try:
        statuses = await asyncio.gather(*(worker.start() for worker in workers))
        ports = [status.rpc_port for status in statuses]
        if len(set(ports)) != site_count or any(port is None for port in ports):
            raise AcceptanceError(f"workers did not receive isolated RPC ports: {ports!r}")

        versions = await asyncio.gather(*(worker.command("version") for worker in workers))
        if not all("Open On-Chip Debugger" in version for version in versions):
            raise AcceptanceError(f"version probe failed: {versions!r}")

        failed_index = 4
        failed = workers[failed_index]
        process = failed._process
        if process is None:
            raise AcceptanceError("selected failure-injection worker has no process")
        process.kill()
        await process.wait()

        surviving = await asyncio.gather(
            *(worker.command("version") for index, worker in enumerate(workers) if index != failed_index)
        )
        if len(surviving) != 7 or not all("Open On-Chip Debugger" in version for version in surviving):
            raise AcceptanceError("one-Site process failure affected another Site worker")

        restarted = await failed.start()
        if not restarted.running:
            raise AcceptanceError("failed Site worker did not restart")
        if "Open On-Chip Debugger" not in await failed.command("version"):
            raise AcceptanceError("restarted Site worker version probe failed")

        return {
            "result": "PASS",
            "evidence_level": "qemu-armv7-openocd-worker-isolation",
            "architecture": "armv7l",
            "site_count": site_count,
            "isolated_rpc_ports": site_count,
            "failure_injected_site_id": failed_index + 1,
            "surviving_sites_after_failure": 7,
            "failed_site_restart": "PASS",
            "execution_capability": "openocd-control-plane-only",
            "hardware_runtime_ready": False,
            "not_claimed": [
                "SWD/JTAG",
                "FPGA PL",
                "target power/reset",
                "target detection",
                "flash programming",
                "real IC",
            ],
        }
    finally:
        await asyncio.gather(*(worker.stop() for worker in workers), return_exceptions=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify eight OpenOCD workers in ARMv7 QEMU")
    parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    parser.add_argument("--site-count", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        evidence = asyncio.run(_run(args.product_root, args.site_count))
    except (AcceptanceError, OSError) as exc:
        print(f"openocd-control-plane-armv7-acceptance: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
