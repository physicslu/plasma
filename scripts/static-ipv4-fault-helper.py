#!/usr/bin/env python3
"""Privileged test-only network helper for Static IPv4 fault injection.

The production Gateway still sees the normal snapshot/apply/restore Unix-socket
contract. Fault behavior exists only in this acceptance helper and never enters
the packaged PPU runtime or production Manager/Gateway APIs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import socket
import sys
from pathlib import Path
from typing import Any, Mapping

MAX_HELPER_REQUEST = 1024 * 1024


class FaultHelperError(RuntimeError):
    pass


def _load_phase2(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("_plasma_phase2_acceptance", path)
    if spec is None or spec.loader is None:
        raise FaultHelperError(f"cannot load Phase 2 acceptance module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManagedAddress:
    def __init__(self, phase2: Any, interface: str, address: str, prefix: int) -> None:
        self.phase2 = phase2
        self.interface = interface
        self.address = address
        self.prefix = prefix
        self.present = False
        self._add(address, prefix)

    def _add(self, address: str, prefix: int) -> None:
        self.phase2._address_message(
            self.interface,
            address,
            prefix,
            self.phase2.RTM_NEWADDR,
            create=True,
        )
        self.address = address
        self.prefix = prefix
        self.present = True

    def _delete(self) -> None:
        if not self.present:
            return
        self.phase2._address_message(
            self.interface,
            self.address,
            self.prefix,
            self.phase2.RTM_DELADDR,
        )
        self.present = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "address": self.address,
            "prefix_length": self.prefix,
        }

    def replace(self, address: str, prefix: int) -> dict[str, Any]:
        self._delete()
        self._add(address, prefix)
        return self.snapshot()

    def drop(self) -> None:
        self._delete()

    def restore(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        address = snapshot.get("address")
        prefix = snapshot.get("prefix_length")
        if snapshot.get("interface") != self.interface or not isinstance(address, str) or not isinstance(prefix, int):
            raise FaultHelperError("invalid restore snapshot")
        return self.replace(address, prefix)


def _desired_result(interface: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "interface": interface,
        "address": str(settings["address"]),
        "prefix_length": int(settings["prefix_length"]),
    }


def _validate_apply(interface: str, settings: object) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise FaultHelperError("settings must be an object")
    if settings.get("interface") != interface or settings.get("mode") != "static":
        raise FaultHelperError("fault helper accepts static eth0 only")
    address = settings.get("address")
    prefix = settings.get("prefix_length")
    if not isinstance(address, str) or not isinstance(prefix, int):
        raise FaultHelperError("static address/prefix are required")
    return settings


def _serve(args: argparse.Namespace, phase2: Any) -> int:
    if platform.machine().lower() not in {"armv7", "armv7l"}:
        raise FaultHelperError("fault helper requires ARMv7")
    managed = ManagedAddress(
        phase2,
        args.interface,
        args.managed_initial_address,
        args.managed_prefix,
    )
    path = args.helper_socket.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(8)
        while True:
            connection, _ = server.accept()
            with connection:
                raw = bytearray()
                while b"\n" not in raw:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_HELPER_REQUEST:
                        break
                try:
                    request = json.loads(bytes(raw).split(b"\n", 1)[0].decode("utf-8"))
                    operation = request.get("operation")
                    if operation == "snapshot":
                        result = managed.snapshot()
                    elif operation == "apply":
                        settings = _validate_apply(args.interface, request.get("settings"))
                        if args.fault_mode == "apply-error":
                            raise FaultHelperError("injected apply failure")
                        if args.fault_mode == "apply-noop":
                            result = _desired_result(args.interface, settings)
                        elif args.fault_mode == "apply-drop":
                            managed.drop()
                            result = _desired_result(args.interface, settings)
                        else:
                            result = managed.replace(str(settings["address"]), int(settings["prefix_length"]))
                    elif operation == "restore":
                        if args.fault_mode == "restore-error":
                            raise FaultHelperError("injected restore failure")
                        snapshot = request.get("snapshot")
                        if not isinstance(snapshot, dict):
                            raise FaultHelperError("invalid restore snapshot")
                        result = managed.restore(snapshot)
                    else:
                        raise FaultHelperError(f"unsupported helper operation: {operation!r}")
                    response = {"ok": True, "result": result}
                except Exception as exc:
                    response = {
                        "ok": False,
                        "error": {
                            "error_type": "STATIC_IPV4_FAULT_HELPER_ERROR",
                            "message": str(exc),
                        },
                    }
                connection.sendall((json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))
    return 0


def _oneshot_add(args: argparse.Namespace, phase2: Any) -> int:
    phase2._address_message(
        args.interface,
        args.oneshot_add,
        args.managed_prefix,
        phase2.RTM_NEWADDR,
        create=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Static IPv4 fault-injection helper")
    parser.add_argument("--phase2-script", type=Path, default=Path("/acceptance.py"))
    parser.add_argument("--helper-socket", type=Path, default=Path("/work/network-helper.sock"))
    parser.add_argument("--interface", default="eth0")
    parser.add_argument("--managed-initial-address", default="192.168.78.10")
    parser.add_argument("--managed-prefix", type=int, default=24)
    parser.add_argument(
        "--fault-mode",
        choices=("normal", "apply-error", "apply-noop", "apply-drop", "restore-error"),
        default="normal",
    )
    parser.add_argument("--oneshot-add")
    args = parser.parse_args()
    try:
        phase2 = _load_phase2(args.phase2_script)
        if args.oneshot_add:
            return _oneshot_add(args, phase2)
        return _serve(args, phase2)
    except Exception as exc:
        print(f"static-ipv4-fault-helper: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
