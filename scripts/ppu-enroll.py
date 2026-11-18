#!/usr/bin/env python3
"""PPU-local enrollment CLI (``plasma-enroll``), LOM-P2A-2.

Root-only, PPU-local entries of the single enrollment engine
(``ppu_controller.py``):

* ``arm``           Engineering entry: requires root AND the root-owned
                    Engineering Mode policy (``/etc/plasma/ppu-engineering-mode.json``,
                    ``enrollment_cli: true``, unexpired). Prints a one-time
                    ticket once; a CLI flag alone can never enable this.
* ``boot-consume``  SD rescue entry: run once per boot by
                    ``plasma-enroll-boot.service`` before the Bootstrap
                    service; consumes ``plasma-enroll.json`` from the boot
                    partition.
* ``status``        Controller/enrollment state; never prints secrets.

There is no LAN arming endpoint. The PS-GPIO button entry runs inside the
Bootstrap service (board profile ``/etc/plasma/ppu-enrollment-button.json``).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
DEFAULT_POLICY = Path("/etc/plasma/ppu-engineering-mode.json")


def _load(name: str, file_name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / file_name)
    if spec is None or spec.loader is None:
        raise SystemExit(f"plasma-enroll: missing {file_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _NoTakeoverProbe:
    """The CLI arms windows only; takeover is evaluated by the Bootstrap service."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError("the enrollment CLI never evaluates a takeover")


def _engine(args: argparse.Namespace):
    controller = _load("plasma_ppu_controller", "ppu_controller.py")
    identity = _load("plasma_ppu_bootstrap_device_identity", "ppu-bootstrap.py")
    store = controller.ControllerStore(args.state_root)
    engine = controller.EnrollmentEngine(
        store, _NoTakeoverProbe(), device_id=identity._machine_device_id(args.machine_id),
        boot_id=controller.boot_id(), log=lambda line: print(line, file=sys.stderr))
    return controller, engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plasma-enroll", description=__doc__.split("\n")[0])
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument("--machine-id", type=Path, default=Path("/etc/machine-id"))
    sub = parser.add_subparsers(dest="command", required=True)
    arm = sub.add_parser("arm", help="engineering entry: print a one-time ticket")
    arm.add_argument("--engineering-policy", type=Path, default=DEFAULT_POLICY)
    boot = sub.add_parser("boot-consume", help="SD rescue entry (boot-time unit only)")
    boot.add_argument("--boot-partition", type=Path, default=Path("/boot"))
    boot.add_argument("--once-marker-dir", type=Path, default=Path("/run/plasma-bootstrap"))
    sub.add_parser("status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if os.geteuid() != 0:
        print("plasma-enroll: ENGINEERING_MODE_NOT_AUTHORIZED (root required)", file=sys.stderr)
        return 77
    controller, engine = _engine(args)
    try:
        if args.command == "arm":
            authorized, reason = controller.engineering_mode_authorized(args.engineering_policy)
            if not authorized:
                print(f"plasma-enroll: ENGINEERING_MODE_NOT_AUTHORIZED: {reason}", file=sys.stderr)
                return 77
            ticket = engine.engineering_arm(controller.boot_clock(), authorized=True)
            # Printed exactly once, to this root session only. DEVELOPMENT entry.
            print(json.dumps({"source": "engineering-cli", "development": True,
                              "device_id": engine.device_id, "ticket": ticket,
                              "window_s": controller.proto.ENROLLMENT_WINDOW_S}))
            return 0
        if args.command == "boot-consume":
            marker = args.once_marker_dir / f"enroll-boot-consumed-{engine.boot_id}"
            if marker.exists():
                print("plasma-enroll: boot ticket already processed in this boot", file=sys.stderr)
                return 0
            engine.boot_consume(controller.BootPartition(args.boot_partition),
                                controller.boot_clock())
            args.once_marker_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            marker.write_text("\n".join(engine.events) + "\n", encoding="utf-8")
            print(json.dumps({"events": engine.events}))
            return 0
        print(json.dumps(engine.public_status(controller.boot_clock()), sort_keys=True))
        return 0
    except controller.ControllerError as exc:
        print(json.dumps(exc.payload()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
