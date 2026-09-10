#!/usr/bin/env python3
"""Collect read-only evidence for real PYNQ-Z2 Bootstrap lifecycle HIL.

This tool never mutates Runtime, systemd, network, FPGA, Site or IC state.  It
normalizes local appliance facts plus read-only Bootstrap/Gateway HTTP probes so
pre/post reboot and rollback checkpoints can be compared as machine-readable
JSON instead of screenshots or ad-hoc shell transcripts.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
PHASES = {
    "factory",
    "runtime-active",
    "runtime-after-reboot",
    "rollback-restored",
    "rollback-after-reboot",
}
SERVICE_UNITS = (
    "plasma-bootstrap.service",
    "plasma-server.service",
    "plasma-web.service",
)


class EvidenceError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_os_release(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def _service_state(unit: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["systemctl", "is-active", unit],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"state": "probe_failed", "active": False, "error": str(exc)}
    state = completed.stdout.strip() or "unknown"
    return {"state": state, "active": completed.returncode == 0 and state == "active"}


def _http_json(url: str) -> dict[str, Any]:
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - explicit HIL endpoint
            status = int(response.status)
            raw = response.read(4 * 1024 * 1024 + 1)
    except HTTPError as exc:
        try:
            raw = exc.read(4 * 1024 * 1024 + 1)
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        return {"status": int(exc.code), "payload": payload, "error": str(exc)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": None, "payload": None, "error": str(exc)}
    if len(raw) > 4 * 1024 * 1024:
        return {"status": status, "payload": None, "error": "response_too_large"}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": status, "payload": None, "error": f"invalid_json: {exc}"}
    return {"status": status, "payload": payload, "error": None}


def _journal(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        return {"trusted": False, "error": f"cannot stat journal: {exc}"}
    if mode & 0o077:
        return {
            "trusted": False,
            "mode": oct(mode),
            "error": "journal permissions allow group/other access",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"trusted": False, "mode": oct(mode), "error": f"cannot read journal: {exc}"}
    if not isinstance(payload, dict):
        return {"trusted": False, "mode": oct(mode), "error": "journal is not a JSON object"}
    # Journals contain no control token, but keep the evidence surface explicit.
    allowed = {
        "schema_version",
        "transaction_id",
        "state",
        "sequence",
        "started_at_epoch_s",
        "updated_at_epoch_s",
        "release_artifact",
        "release_id",
        "artifact_sha256",
        "previous_release",
        "error_code",
        "error_message",
        "upload_id",
        "error",
        "result",
    }
    return {
        "trusted": True,
        "mode": oct(mode),
        "record": {key: payload[key] for key in sorted(payload) if key in allowed},
    }


def _current_release(product_root: Path) -> dict[str, Any]:
    current = product_root / "current"
    if not current.exists() and not current.is_symlink():
        return {"state": "absent", "path": None, "release_id": None}
    if not current.is_symlink():
        return {"state": "unsafe_non_symlink", "path": str(current), "release_id": None}
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to((product_root / "releases").resolve())
    except (OSError, ValueError) as exc:
        return {"state": "unsafe", "path": None, "release_id": None, "error": str(exc)}
    return {"state": "active", "path": str(resolved), "release_id": resolved.name}


def _payload(probe: Mapping[str, Any]) -> Mapping[str, Any]:
    value = probe.get("payload")
    return value if isinstance(value, dict) else {}


def evaluate_snapshot(snapshot: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    phase = snapshot.get("phase")
    expected = snapshot.get("expected_release_id")
    services = snapshot.get("services") if isinstance(snapshot.get("services"), dict) else {}
    bootstrap_probe = snapshot.get("bootstrap_status") if isinstance(snapshot.get("bootstrap_status"), dict) else {}
    gateway_probe = snapshot.get("gateway_ready") if isinstance(snapshot.get("gateway_ready"), dict) else {}
    bootstrap = _payload(bootstrap_probe)
    runtime = bootstrap.get("runtime") if isinstance(bootstrap.get("runtime"), dict) else {}
    capabilities = bootstrap.get("capabilities") if isinstance(bootstrap.get("capabilities"), dict) else {}
    current = snapshot.get("current_release") if isinstance(snapshot.get("current_release"), dict) else {}
    engine = snapshot.get("deployment_engine_journal")
    api = snapshot.get("deployment_api_journal")

    bootstrap_service = services.get("plasma-bootstrap.service") if isinstance(services, dict) else None
    if not isinstance(bootstrap_service, dict) or bootstrap_service.get("active") is not True:
        failures.append("plasma-bootstrap.service is not active")
    if bootstrap_probe.get("status") != 200:
        failures.append("Bootstrap /v1/status is not HTTP 200")
    bootstrap_state = bootstrap.get("bootstrap") if isinstance(bootstrap.get("bootstrap"), dict) else {}
    if bootstrap_state.get("state") != "bootstrap_ready":
        failures.append("Bootstrap state is not bootstrap_ready")
    if capabilities.get("fpga_update") is not False:
        failures.append("Bootstrap fpga_update boundary is not false")

    if phase == "factory":
        if current.get("state") != "absent":
            failures.append("factory checkpoint unexpectedly has /opt/plasma/current")
        if runtime.get("state") != "runtime_absent":
            failures.append("factory Bootstrap runtime state is not runtime_absent")
        return failures

    if not isinstance(expected, str) or not expected:
        failures.append("expected_release_id is required for non-factory checkpoints")
    for unit in ("plasma-server.service", "plasma-web.service"):
        state = services.get(unit) if isinstance(services, dict) else None
        if not isinstance(state, dict) or state.get("active") is not True:
            failures.append(f"{unit} is not active")
    if current.get("state") != "active":
        failures.append("/opt/plasma/current is not a safe active symlink")
    elif isinstance(expected, str) and current.get("release_id") != expected:
        failures.append("active release does not match expected_release_id")
    if runtime.get("state") != "runtime_active":
        failures.append("Bootstrap runtime state is not runtime_active")
    elif isinstance(expected, str) and runtime.get("release_id") != expected:
        failures.append("Bootstrap runtime release_id does not match expected_release_id")

    if gateway_probe.get("status") != 200:
        failures.append("Gateway /api/health/ready is not HTTP 200")
    gateway = _payload(gateway_probe)
    if (
        gateway.get("ok") is not True
        or gateway.get("gateway") != "alive"
        or gateway.get("execution") != "ready"
    ):
        failures.append("Gateway readiness payload is not ok=true/gateway=alive/execution=ready")

    if phase in {"runtime-active", "runtime-after-reboot"}:
        if not isinstance(engine, dict) or engine.get("trusted") is not True:
            failures.append("deployment engine journal is unavailable or untrusted")
        else:
            record = engine.get("record") if isinstance(engine.get("record"), dict) else {}
            if record.get("state") != "runtime_active":
                failures.append("deployment engine journal is not runtime_active")
        if not isinstance(api, dict) or api.get("trusted") is not True:
            failures.append("deployment API journal is unavailable or untrusted")
        else:
            record = api.get("record") if isinstance(api.get("record"), dict) else {}
            if record.get("state") != "succeeded":
                failures.append("deployment API journal is not succeeded")

    if phase in {"rollback-restored", "rollback-after-reboot"}:
        if not isinstance(engine, dict) or engine.get("trusted") is not True:
            failures.append("deployment engine journal is unavailable or untrusted")
        else:
            record = engine.get("record") if isinstance(engine.get("record"), dict) else {}
            if record.get("state") != "rolled_back":
                failures.append("deployment engine journal is not rolled_back")
        if not isinstance(api, dict) or api.get("trusted") is not True:
            failures.append("deployment API journal is unavailable or untrusted")
        else:
            record = api.get("record") if isinstance(api.get("record"), dict) else {}
            if record.get("state") != "failed":
                failures.append("deployment API journal is not failed after controlled rollback")

    return failures


def collect_snapshot(
    *,
    phase: str,
    ppu_ip: str,
    expected_release_id: str | None,
    product_root: Path,
    bootstrap_state_root: Path,
    os_release: Path,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "observed_at_utc": _utc_now(),
        "phase": phase,
        "expected_release_id": expected_release_id,
        "host": {
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "os_release": _read_os_release(os_release),
        },
        "services": {unit: _service_state(unit) for unit in SERVICE_UNITS},
        "current_release": _current_release(product_root),
        "bootstrap_status": _http_json(f"http://{ppu_ip}:18081/v1/status"),
        "gateway_ready": _http_json(f"http://{ppu_ip}:18080/api/health/ready"),
        "deployment_engine_journal": _journal(bootstrap_state_root / "deployment.json"),
        "deployment_api_journal": _journal(bootstrap_state_root / "deployment-api.json"),
        "proof_boundary": (
            "read-only local real-PPU checkpoint: Linux/architecture + systemd + active release + "
            "Bootstrap status + Gateway readiness + durable deployment journals"
        ),
        "not_proven": [
            "Browser/Manager request that initiated the transaction",
            "publisher authenticity",
            "transport confidentiality",
            "FPGA/PS-to-PL",
            "Site electrical behavior",
            "target power",
            "real IC programming",
            "8-Site physical concurrency",
        ],
    }
    failures = evaluate_snapshot(snapshot)
    snapshot["failures"] = failures
    snapshot["result"] = "PASS" if not failures else "FAIL"
    return snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect read-only real-Z2 Bootstrap HIL evidence")
    parser.add_argument("phase", choices=sorted(PHASES))
    parser.add_argument("--ppu-ip", required=True)
    parser.add_argument("--expected-release-id")
    parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    parser.add_argument("--bootstrap-state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument("--os-release", type=Path, default=Path("/etc/os-release"))
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.phase != "factory" and not args.expected_release_id:
        print("ppu-bootstrap-hil-evidence: --expected-release-id is required", file=sys.stderr)
        return 2
    snapshot = collect_snapshot(
        phase=args.phase,
        ppu_ip=args.ppu_ip,
        expected_release_id=args.expected_release_id,
        product_root=args.product_root,
        bootstrap_state_root=args.bootstrap_state_root,
        os_release=args.os_release,
    )
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".new")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, args.output)
    print(text, end="")
    return 0 if snapshot["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
