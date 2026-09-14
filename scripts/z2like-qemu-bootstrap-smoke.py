#!/usr/bin/env python3
"""Drive one private Bootstrap deployment into the SWPC QEMU ARMv7 Z2 simulation.

This helper is for local/CI acceptance only.  It retrieves the device-local token
through Docker exec without printing it, uploads one canonical Z2 PS kit through
the authenticated Bootstrap API, waits for terminal deployment state, then proves
the ARMv7 Gateway is ready.  It does not exercise Render or expose Bootstrap to
the Internet.
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

CONTAINER_NAME = "plasma-z2like-qemu"
APPLIANCE_IP = "172.29.33.21"
BOOTSTRAP_ROOT = f"http://{APPLIANCE_IP}:18081"
GATEWAY_ROOT = f"http://{APPLIANCE_IP}:18080"
MAX_CHUNK = 1024 * 1024


class SmokeError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(MAX_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sidecar(kit: Path, sidecar: Path) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise SmokeError(f"cannot read kit sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != kit.name:
        raise SmokeError("kit sidecar does not identify the kit")
    expected = fields[0].lower()
    actual = _sha256_file(kit)
    if expected != actual:
        raise SmokeError("kit SHA-256 mismatch")
    return actual


def _token() -> str:
    completed = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "python3", "/z2like-qemu-sim.py", "inside-token"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
    )
    token = completed.stdout.strip()
    if completed.returncode != 0 or not 32 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        raise SmokeError("cannot retrieve a valid private Bootstrap token from the simulation container")
    return token


def _request(
    path: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    token: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    raw = None if body is None else json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(BOOTSTRAP_ROOT + path, data=raw, method=method)
    request.add_header("Accept", "application/json")
    if raw is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_s) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"Bootstrap {method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SmokeError(f"Bootstrap {method} {path} failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"Bootstrap {method} {path} returned a non-object")
    return payload


def _gateway_ready() -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{GATEWAY_ROOT}/api/health/ready", timeout=5) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SmokeError(f"QEMU Gateway readiness failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True or payload.get("execution") != "ready":
        raise SmokeError(f"QEMU Gateway is not ready: {payload!r}")
    return payload


def deploy(
    kit: Path,
    *,
    sidecar: Path,
    ppu_id: str,
    facility_id: str,
    display_name: str,
) -> dict[str, Any]:
    kit = kit.resolve()
    sidecar = sidecar.resolve()
    if not kit.is_file() or not sidecar.is_file():
        raise SmokeError("kit and detached sidecar are required")
    digest = _verify_sidecar(kit, sidecar)
    token = _token()
    status = _request("/v1/status")
    capability = status.get("capabilities") if isinstance(status.get("capabilities"), dict) else {}
    if capability.get("runtime_deployment") is not True:
        raise SmokeError("simulation Bootstrap does not advertise runtime_deployment")

    created = _request(
        "/v1/uploads",
        method="POST",
        token=token,
        body={"size": kit.stat().st_size, "sha256": digest},
    )
    upload = created.get("upload") if isinstance(created.get("upload"), dict) else {}
    upload_id = upload.get("upload_id")
    if not isinstance(upload_id, str) or len(upload_id) != 32:
        raise SmokeError("Bootstrap upload did not return a valid upload_id")

    offset = 0
    with kit.open("rb") as stream:
        while True:
            chunk = stream.read(MAX_CHUNK)
            if not chunk:
                break
            response = _request(
                f"/v1/uploads/{upload_id}/chunks",
                method="POST",
                token=token,
                body={
                    "offset": offset,
                    "data_base64": base64.b64encode(chunk).decode("ascii"),
                    "sha256": _sha256_bytes(chunk),
                },
                timeout_s=30,
            )
            uploaded = response.get("upload") if isinstance(response.get("upload"), dict) else {}
            offset = int(uploaded.get("received_bytes", -1))
            if offset < 0:
                raise SmokeError("Bootstrap upload response lost received_bytes")

    committed = _request(
        f"/v1/uploads/{upload_id}/commit",
        method="POST",
        token=token,
        body={"commit": True},
        timeout_s=30,
    )
    commit_state = committed.get("upload") if isinstance(committed.get("upload"), dict) else {}
    if commit_state.get("state") != "committed":
        raise SmokeError(f"Bootstrap upload did not commit: {commit_state!r}")

    accepted = _request(
        "/v1/deployments",
        method="POST",
        token=token,
        body={
            "upload_id": upload_id,
            "gateway_host": APPLIANCE_IP,
            "ppu_id": ppu_id,
            "facility_id": facility_id,
            "display_name": display_name,
        },
    )
    record = accepted.get("deployment") if isinstance(accepted.get("deployment"), dict) else {}
    transaction_id = record.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise SmokeError("Bootstrap deployment did not return transaction identity")

    deadline = time.monotonic() + 180
    terminal: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        current = _request("/v1/deployment")
        deployment = current.get("deployment") if isinstance(current.get("deployment"), dict) else None
        if deployment is not None and deployment.get("transaction_id") == transaction_id:
            state = deployment.get("state")
            if state in {"succeeded", "failed", "recovery_required"}:
                terminal = deployment
                break
        time.sleep(0.25)
    if terminal is None:
        raise SmokeError("Bootstrap deployment did not reach a terminal state")
    if terminal.get("state") != "succeeded":
        raise SmokeError(f"Bootstrap deployment failed: {terminal!r}")
    result = terminal.get("result") if isinstance(terminal.get("result"), dict) else {}
    if result.get("backend") != "qemu-armv7" or result.get("simulation_environment") != "SWPC":
        raise SmokeError(f"deployment result lost canonical simulation identity: {result!r}")
    if result.get("systemd_qualified") is not False or result.get("fpga_update") is not False:
        raise SmokeError("simulation deployment overclaimed systemd or FPGA qualification")

    ready = _gateway_ready()
    final_status = _request("/v1/status")
    runtime = final_status.get("runtime") if isinstance(final_status.get("runtime"), dict) else {}
    if runtime.get("state") != "runtime_active":
        raise SmokeError(f"Bootstrap does not observe the deployed runtime: {runtime!r}")
    return {
        "result": "PASS",
        "simulation_environment": "SWPC",
        "backend": "qemu-armv7",
        "transaction_id": transaction_id,
        "runtime": runtime,
        "gateway_ready": ready,
        "systemd_qualified": False,
        "real_z2_hil": "not_qualified",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy a Z2 PS kit into the SWPC QEMU ARMv7 simulation")
    parser.add_argument("kit", type=Path)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--ppu-id", default="z2-qemu-01")
    parser.add_argument("--facility-id", default="swpc-sim")
    parser.add_argument("--display-name", default="SWPC QEMU ARMv7 Z2 Simulation")
    args = parser.parse_args(argv)
    try:
        result = deploy(
            args.kit,
            sidecar=args.sidecar,
            ppu_id=args.ppu_id,
            facility_id=args.facility_id,
            display_name=args.display_name,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (SmokeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"z2like-qemu-bootstrap-smoke: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
