#!/usr/bin/env python3
"""Deploy/upgrade z2like-demo QEMU Runtime through the persistent internal Manager.

This is an operator-maintenance helper. It deliberately uses the SWPC-local
Manager on 127.0.0.1:18380 only for Bootstrap lifecycle/pairing/upload/deploy.
It is not the public z2like-demo Control Station. The public Control Station
remains Render-hosted and reaches the QEMU Runtime through ppu-managed-lab.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

CHUNK_BYTES = 1024 * 1024


class DeployError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_request(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    timeout_s: float = 15.0,
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
        raise DeployError(f"request failed for {url}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeployError(f"invalid JSON from {url}: HTTP {status}") from exc
    if not isinstance(payload, dict):
        raise DeployError(f"non-object JSON from {url}: HTTP {status}")
    return status, payload


def _expect(status: int, expected: int, payload: Mapping[str, Any], operation: str) -> None:
    if status != expected:
        raise DeployError(f"{operation} returned HTTP {status}, expected {expected}: {payload!r}")


def _wait_json(url: str, predicate, *, timeout_s: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload = _json_request(url, timeout_s=3.0)
            if status == 200 and predicate(payload):
                return payload
            last = f"HTTP {status}: {payload!r}"
        except DeployError as exc:
            last = str(exc)
        time.sleep(0.5)
    raise DeployError(f"deadline exceeded for {url}: {last}")


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
        raise DeployError("cannot read a valid local QEMU Bootstrap pairing token")
    return token


def _registry_entry(manager: str, alias: str, endpoint: str) -> dict[str, Any]:
    status, payload = _json_request(f"{manager}/api/registry")
    _expect(status, 200, payload, "registry read")
    ppus = payload.get("ppus")
    if not isinstance(ppus, list):
        raise DeployError("Manager registry response omitted ppus list")
    matches = [item for item in ppus if isinstance(item, dict) and item.get("alias") == alias]
    if not matches:
        status, created = _json_request(
            f"{manager}/api/registry",
            method="POST",
            body={"alias": alias, "endpoint": endpoint},
        )
        _expect(status, 201, created, "registry add")
        entry = created.get("entry")
        if not isinstance(entry, dict):
            raise DeployError("registry add omitted entry")
        return entry
    if len(matches) != 1 or matches[0].get("endpoint") != endpoint:
        raise DeployError("z2like-demo Manager registry alias does not match the canonical QEMU endpoint")
    return matches[0]


def _set_lifecycle(manager: str, alias: str, lifecycle: str, *, retry_s: float = 0.0) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, retry_s)
    last: dict[str, Any] | None = None
    while True:
        status, payload = _json_request(
            f"{manager}/api/registry/{alias}",
            method="PATCH",
            body={"lifecycle": lifecycle},
        )
        if status == 200:
            entry = payload.get("entry")
            if not isinstance(entry, dict) or entry.get("lifecycle") != lifecycle:
                raise DeployError(f"Manager did not persist lifecycle {lifecycle!r}: {payload!r}")
            return entry
        last = payload
        if time.monotonic() >= deadline:
            raise DeployError(f"cannot set PPU lifecycle to {lifecycle!r}: HTTP {status} {payload!r}")
        time.sleep(1.0)


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    kit = args.kit.expanduser().resolve()
    sidecar = args.sidecar.expanduser().resolve()
    if not kit.is_file() or not sidecar.is_file():
        raise DeployError("kit artifact and sidecar are required")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    kit_sha = _sha256(kit)
    if len(fields) != 2 or fields[1].lstrip("*") != kit.name or fields[0].lower() != kit_sha:
        raise DeployError("kit detached SHA-256 sidecar is invalid")

    manager = args.manager.rstrip("/")
    _wait_json(f"{manager}/api/health/live", lambda payload: payload.get("ok") is True, timeout_s=30.0)
    endpoint = f"http://{args.ppu_ip}:18080"
    entry = _registry_entry(manager, args.alias, endpoint)
    lifecycle_before = entry.get("lifecycle")
    if lifecycle_before == "commissioned":
        _set_lifecycle(manager, args.alias, "disabled", retry_s=15.0)
    elif lifecycle_before not in {"pending", "disabled"}:
        raise DeployError(f"unsupported Manager lifecycle before maintenance: {lifecycle_before!r}")

    bootstrap_url = f"{manager}/api/registry/{args.alias}/bootstrap"
    status, before = _json_request(bootstrap_url)
    _expect(status, 200, before, "Bootstrap status")
    bootstrap = before.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise DeployError("Manager Bootstrap status omitted target document")
    runtime = bootstrap.get("runtime")
    runtime_state_before = runtime.get("state") if isinstance(runtime, dict) else None
    if runtime_state_before not in {"runtime_absent", "runtime_active"}:
        raise DeployError(f"unsafe Bootstrap runtime state before deploy: {runtime_state_before!r}")
    pairing = before.get("pairing")
    if not isinstance(pairing, dict):
        raise DeployError("Manager Bootstrap status omitted pairing state")
    if pairing.get("device_match") is False:
        raise DeployError("stored Bootstrap credential is bound to a different device identity")
    if pairing.get("paired") is not True:
        token = _read_pairing_token(args.container)
        status, paired = _json_request(
            f"{bootstrap_url}/pair",
            method="POST",
            body={"token": token},
        )
        token = ""
        _expect(status, 200, paired, "Bootstrap pairing")

    size = kit.stat().st_size
    status, created = _json_request(
        f"{bootstrap_url}/uploads",
        method="POST",
        body={"size": size, "sha256": kit_sha},
    )
    _expect(status, 201, created, "upload create")
    upload = created.get("upload")
    upload_id = upload.get("upload_id") if isinstance(upload, dict) else None
    if not isinstance(upload_id, str) or len(upload_id) != 32:
        raise DeployError("upload create did not return a valid upload_id")

    offset = 0
    with kit.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            status, response = _json_request(
                f"{bootstrap_url}/uploads/{upload_id}/chunks",
                method="POST",
                body={
                    "offset": offset,
                    "data_base64": base64.b64encode(chunk).decode("ascii"),
                    "sha256": hashlib.sha256(chunk).hexdigest(),
                },
                timeout_s=30.0,
            )
            _expect(status, 200, response, "upload chunk")
            offset += len(chunk)
    if offset != size:
        raise DeployError("uploaded byte count does not match kit size")

    status, committed = _json_request(
        f"{bootstrap_url}/uploads/{upload_id}/commit",
        method="POST",
        body={"action": "commit"},
        timeout_s=30.0,
    )
    _expect(status, 200, committed, "upload commit")

    status, started = _json_request(
        f"{bootstrap_url}/deployments",
        method="POST",
        body={
            "upload_id": upload_id,
            "ppu_id": args.ppu_id,
            "facility_id": args.facility_id,
            "display_name": args.display_name,
        },
    )
    _expect(status, 202, started, "deployment start")

    after = _wait_json(
        bootstrap_url,
        lambda payload: (
            isinstance(payload.get("bootstrap"), dict)
            and isinstance(payload["bootstrap"].get("deployment"), dict)
            and payload["bootstrap"]["deployment"].get("state")
            in {"succeeded", "failed", "recovery_required"}
        ),
        timeout_s=240.0,
    )
    target = after["bootstrap"]
    deployment = target.get("deployment")
    if not isinstance(deployment, dict) or deployment.get("state") != "succeeded":
        raise DeployError(f"QEMU Bootstrap deployment did not succeed: {deployment!r}")
    runtime = target.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("state") != "runtime_active":
        raise DeployError(f"QEMU target did not report runtime_active: {runtime!r}")

    ready_status, ready = _json_request(f"http://{args.ppu_ip}:18080/api/health/ready")
    _expect(ready_status, 200, ready, "QEMU Gateway readiness")
    if not (ready.get("ok") is True and ready.get("gateway") == "alive" and ready.get("execution") == "ready"):
        raise DeployError(f"QEMU Gateway readiness contract failed: {ready!r}")

    # Re-enable only after the Manager itself has a current trusted observation.
    commissioned = _set_lifecycle(manager, args.alias, "commissioned", retry_s=45.0)

    return {
        "result": "PASS",
        "simulation_environment": "SWPC",
        "backend": "QEMU ARMv7 simulated Z2",
        "manager_role": "SWPC-local maintenance/bootstrap only",
        "manager_origin": manager,
        "alias": args.alias,
        "lifecycle_before": lifecycle_before,
        "lifecycle_after": commissioned.get("lifecycle"),
        "runtime_state_before": runtime_state_before,
        "runtime_state_after": "runtime_active",
        "deployment_state": "succeeded",
        "gateway_readiness": "PASS",
        "kit_sha256": kit_sha,
        "not_claimed": [
            "Render deployment state",
            "Cloudflare route correctness",
            "PYNQ-Z2 hardware",
            "PL/FPGA",
            "real IC programming",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely deploy/upgrade the SWPC/QEMU z2like-demo Runtime")
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--manager", default="http://127.0.0.1:18380")
    parser.add_argument("--ppu-ip", default="172.30.77.2")
    parser.add_argument("--alias", default="z2like-qemu")
    parser.add_argument("--ppu-id", default="z2like-qemu-01")
    parser.add_argument("--facility-id", default="swpc-simulation")
    parser.add_argument("--display-name", default="SWPC QEMU ARMv7 Z2 Simulation")
    parser.add_argument("--container", default="plasma-z2like-demo-qemu")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = deploy(args)
    except (DeployError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"z2like-demo-qemu-deploy: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
