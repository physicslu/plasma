#!/usr/bin/env python3
"""Qualify Platform/Managed PS loopback admission on an active QEMU ARMv7 PPU.

This is an environment-level lifecycle matrix layered after the canonical QEMU
Runtime deployment E2E. It deliberately reuses one Runtime PS loopback endpoint
through two Manager admission contexts:

- pending:      Platform PASS, Managed BLOCKED
- commissioned: Platform PASS, Managed PASS
- disabled:     Platform PASS, Managed BLOCKED

It does not qualify physical PYNQ-Z2 behavior, systemd/DAC, reboot persistence,
PS-to-PL, or real IC programming.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


class AcceptanceError(RuntimeError):
    pass


def _json_request(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_s) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    except (OSError, urllib.error.URLError) as exc:
        raise AcceptanceError(f"request failed for {url}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"invalid JSON from {url}: HTTP {status}") from exc
    if not isinstance(payload, dict):
        raise AcceptanceError(f"non-object JSON from {url}: HTTP {status}")
    return status, payload


def _expect(status: int, expected: int, payload: Mapping[str, Any], operation: str) -> None:
    if status != expected:
        raise AcceptanceError(f"{operation} returned HTTP {status}, expected {expected}: {payload!r}")


def _wait_manager(manager: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload = _json_request(f"{manager}/api/health/live", timeout_s=2.0)
            if status == 200 and payload.get("ok") is True:
                return
            last = f"HTTP {status}: {payload!r}"
        except AcceptanceError as exc:
            last = str(exc)
        time.sleep(0.25)
    raise AcceptanceError(f"Manager did not become ready: {last}")


def _loopback_body(test_id: str) -> dict[str, Any]:
    return {
        "endpoint": "ps",
        "test_id": test_id,
        "sequence": 1,
        "pattern": "zero",
        "seed": "",
        "payload_length": 1,
        "payload_base64": "AA==",
        "tx_crc32": "d202ef8d",
        "timeout_ms": 5000,
    }


def _assert_ps_pass(payload: Mapping[str, Any], operation: str) -> None:
    loopback = payload.get("loopback")
    if payload.get("ok") is not True or not isinstance(loopback, dict):
        raise AcceptanceError(f"{operation} did not PASS: {payload!r}")
    if loopback.get("source") != "ps" or payload.get("payload_base64") != "AA==":
        raise AcceptanceError(f"{operation} did not prove PS echo: {payload!r}")


def _read_pairing_token(container: str) -> str:
    completed = subprocess.run(
        ["docker", "exec", container, "cat", "/var/lib/plasma-bootstrap/control-token"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    token = completed.stdout.strip()
    if completed.returncode != 0 or not 32 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        raise AcceptanceError("cannot read a valid local QEMU Bootstrap pairing token")
    return token


def _write_manager_config(root: Path, port: int) -> Path:
    config = root / "manager.yaml"
    config.write_text(
        "\n".join(
            [
                "manager:",
                '  host: "127.0.0.1"',
                f"  port: {port}",
                "  request_timeout_s: 10.0",
                "  poll_interval_s: 0.25",
                f"  observation_db_path: {json.dumps(str(root / 'observations.sqlite3'))}",
                f"  registry_state_path: {json.dumps(str(root / 'registry.json'))}",
                "ppus: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config


def _start_manager(config: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "plasma_manager.bootstrap_server", "--config", str(config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _set_lifecycle_when_ready(manager: str, alias: str, lifecycle: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, payload = _json_request(
            f"{manager}/api/registry/{alias}",
            method="PATCH",
            body={"lifecycle": lifecycle},
        )
        if status == 200:
            return payload
        last = payload
        error = payload.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        retryable = lifecycle == "commissioned" and status == 409 and code == "ppu_validation_incomplete"
        if not retryable:
            raise AcceptanceError(
                f"lifecycle transition to {lifecycle} failed unexpectedly: HTTP {status}: {payload!r}"
            )
        time.sleep(0.25)
    raise AcceptanceError(f"lifecycle transition to {lifecycle} never became eligible: {last!r}")


def _platform_loop(manager: str, alias: str, label: str) -> dict[str, Any]:
    status, payload = _json_request(
        f"{manager}/api/registry/{alias}/bootstrap/ps-loopback",
        method="POST",
        body=_loopback_body(f"platform-{label}"),
    )
    _expect(status, 200, payload, f"{label} Platform PS Loop Test")
    _assert_ps_pass(payload, f"{label} Platform PS Loop Test")
    proof = payload.get("manager")
    if not isinstance(proof, dict) or proof.get("context") != "platform":
        raise AcceptanceError(f"{label} Platform path omitted admission proof: {payload!r}")
    return payload


def _managed_loop(manager: str, alias: str, label: str, *, allowed: bool) -> dict[str, Any]:
    url = f"{manager}/api/ppus/{alias}/gateway/api/engineering/diagnostics/loopback"
    status, payload = _json_request(url, method="POST", body=_loopback_body(f"managed-{label}"))
    if allowed:
        _expect(status, 200, payload, f"{label} Managed PS Loop Test")
        _assert_ps_pass(payload, f"{label} Managed PS Loop Test")
        proof = payload.get("manager")
        if not isinstance(proof, dict) or proof.get("relay") != "pass-through":
            raise AcceptanceError(f"{label} Managed path omitted relay proof: {payload!r}")
    else:
        _expect(status, 409, payload, f"{label} Managed PS Loop Test block")
        error = payload.get("error")
        if not isinstance(error, dict) or error.get("code") != "ppu_not_enabled":
            raise AcceptanceError(f"{label} Managed path did not fail closed: {payload!r}")
    return payload


def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="plasma-z2like-loopback-matrix-") as temporary:
        root = Path(temporary)
        process = _start_manager(_write_manager_config(root, args.manager_port))
        manager = f"http://127.0.0.1:{args.manager_port}"
        try:
            _wait_manager(manager)
            status, added = _json_request(
                f"{manager}/api/registry",
                method="POST",
                body={"alias": args.alias, "endpoint": f"http://{args.ppu_ip}:18080"},
            )
            _expect(status, 201, added, "registry add")
            entry = added.get("entry")
            if not isinstance(entry, dict) or entry.get("lifecycle") != "pending":
                raise AcceptanceError(f"expected pending registry state: {added!r}")

            token = _read_pairing_token(args.container)
            status, paired = _json_request(
                f"{manager}/api/registry/{args.alias}/bootstrap/pair",
                method="POST",
                body={"token": token},
            )
            _expect(status, 200, paired, "Platform maintenance pairing")
            token = ""

            _platform_loop(manager, args.alias, "pending")
            _managed_loop(manager, args.alias, "pending", allowed=False)

            commissioned = _set_lifecycle_when_ready(manager, args.alias, "commissioned")
            commissioned_entry = commissioned.get("entry")
            if not isinstance(commissioned_entry, dict) or commissioned_entry.get("lifecycle") != "commissioned":
                raise AcceptanceError(f"commissioned transition did not persist: {commissioned!r}")
            _platform_loop(manager, args.alias, "commissioned")
            _managed_loop(manager, args.alias, "commissioned", allowed=True)

            disabled = _set_lifecycle_when_ready(manager, args.alias, "disabled")
            disabled_entry = disabled.get("entry")
            if not isinstance(disabled_entry, dict) or disabled_entry.get("lifecycle") != "disabled":
                raise AcceptanceError(f"disabled transition did not persist: {disabled!r}")
            _platform_loop(manager, args.alias, "disabled")
            _managed_loop(manager, args.alias, "disabled", allowed=False)

            return {
                "result": "PASS",
                "backend": "QEMU ARMv7 simulated Z2",
                "pending": {"platform": "PASS", "managed": "BLOCKED"},
                "commissioned": {"platform": "PASS", "managed": "PASS"},
                "disabled": {"platform": "PASS", "managed": "BLOCKED"},
                "execution_capability": "shared-runtime-ps-loopback",
                "not_claimed": [
                    "PYNQ-Z2 hardware",
                    "physical systemd/DAC",
                    "real Z2 reboot persistence",
                    "PS-to-PL",
                    "real IC programming",
                ],
            }
        finally:
            _stop(process)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qualify Platform/Managed PS loopback lifecycle matrix on QEMU ARMv7")
    parser.add_argument("--ppu-ip", default="172.30.77.2")
    parser.add_argument("--alias", default="z2like-loopback-matrix")
    parser.add_argument("--container", default="plasma-z2like-demo-qemu")
    parser.add_argument("--manager-port", type=int, default=18380)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = run_acceptance(args)
    except (AcceptanceError, OSError, subprocess.SubprocessError) as exc:
        print(f"z2like-demo-qemu-loopback-matrix: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
