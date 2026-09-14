#!/usr/bin/env python3
"""CI/operator acceptance for the SWPC/QEMU z2like-demo Bootstrap path.

This acceptance intentionally starts a temporary current Manager locally, then
drives the same bounded Manager Bootstrap REST surface used by the Console BFF:
registry add -> pair -> chunk upload -> commit -> deploy -> Runtime ready.

It never calls the QEMU Bootstrap mutation API directly. The only direct target
reads are final health/readiness evidence and retrieval of the device-local token
from the local Docker container for the explicit pairing step.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
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

CHUNK_BYTES = 1024 * 1024


class AcceptanceError(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
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


def _wait_json(url: str, predicate, *, timeout_s: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload = _json_request(url, timeout_s=3.0)
            if status == 200 and predicate(payload):
                return payload
            last = f"HTTP {status}: {payload!r}"
        except AcceptanceError as exc:
            last = str(exc)
        time.sleep(0.25)
    raise AcceptanceError(f"deadline exceeded for {url}: {last}")


def _expect(status: int, expected: int, payload: Mapping[str, Any], operation: str) -> None:
    if status != expected:
        raise AcceptanceError(f"{operation} returned HTTP {status}, expected {expected}: {payload!r}")


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


def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    kit = args.kit.resolve()
    sidecar = args.sidecar.resolve()
    if not kit.is_file() or not sidecar.is_file():
        raise AcceptanceError("kit artifact and sidecar are required")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    kit_sha = _sha256_file(kit)
    if len(fields) != 2 or fields[1].lstrip("*") != kit.name or fields[0].lower() != kit_sha:
        raise AcceptanceError("kit detached SHA-256 sidecar is invalid")

    with tempfile.TemporaryDirectory(prefix="plasma-z2like-demo-manager-") as temporary:
        root = Path(temporary)
        config = _write_manager_config(root, args.manager_port)
        manager_process = _start_manager(config)
        manager = f"http://127.0.0.1:{args.manager_port}"
        try:
            _wait_json(
                f"{manager}/api/health/live",
                lambda payload: payload.get("ok") is True,
                timeout_s=30.0,
            )
            endpoint = f"http://{args.ppu_ip}:18080"
            status, payload = _json_request(
                f"{manager}/api/registry",
                method="POST",
                body={"alias": args.alias, "endpoint": endpoint},
            )
            _expect(status, 201, payload, "registry add")
            entry = payload.get("entry")
            if not isinstance(entry, dict) or entry.get("lifecycle") != "pending":
                raise AcceptanceError("fresh QEMU PPU was not admitted as pending")

            bootstrap_url = f"{manager}/api/registry/{args.alias}/bootstrap"
            status, before = _json_request(bootstrap_url)
            _expect(status, 200, before, "Bootstrap status before pairing")
            bootstrap = before.get("bootstrap")
            if not isinstance(bootstrap, dict):
                raise AcceptanceError("Manager Bootstrap status omitted target document")
            runtime = bootstrap.get("runtime")
            if not isinstance(runtime, dict) or runtime.get("state") != "runtime_absent":
                raise AcceptanceError("fresh QEMU target must start with runtime_absent")
            pairing = before.get("pairing")
            if not isinstance(pairing, dict) or pairing.get("paired") is not False:
                raise AcceptanceError("fresh Manager credential store unexpectedly reports paired")

            token = _read_pairing_token(args.container)
            status, paired = _json_request(
                f"{bootstrap_url}/pair",
                method="POST",
                body={"token": token},
            )
            _expect(status, 200, paired, "Bootstrap pairing")
            token = ""  # do not retain or print the device credential after pairing

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
                raise AcceptanceError("upload create did not return a valid upload_id")

            offset = 0
            with kit.open("rb") as stream:
                while True:
                    chunk = stream.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    status, chunk_response = _json_request(
                        f"{bootstrap_url}/uploads/{upload_id}/chunks",
                        method="POST",
                        body={
                            "offset": offset,
                            "data_base64": base64.b64encode(chunk).decode("ascii"),
                            "sha256": _sha256_bytes(chunk),
                        },
                        timeout_s=30.0,
                    )
                    _expect(status, 200, chunk_response, "upload chunk")
                    offset += len(chunk)
            if offset != size:
                raise AcceptanceError("uploaded byte count does not match kit size")

            status, committed = _json_request(
                f"{bootstrap_url}/uploads/{upload_id}/commit",
                method="POST",
                body={"action": "commit"},
                timeout_s=30.0,
            )
            _expect(status, 200, committed, "upload commit")

            status, deployment = _json_request(
                f"{bootstrap_url}/deployments",
                method="POST",
                body={
                    "upload_id": upload_id,
                    "ppu_id": args.ppu_id,
                    "facility_id": args.facility_id,
                    "display_name": "CI QEMU ARMv7 Z2 Simulation",
                },
            )
            _expect(status, 202, deployment, "deployment start")

            after = _wait_json(
                bootstrap_url,
                lambda payload: (
                    isinstance(payload.get("bootstrap"), dict)
                    and isinstance(payload["bootstrap"].get("deployment"), dict)
                    and payload["bootstrap"]["deployment"].get("state") in {"succeeded", "failed", "recovery_required"}
                ),
                timeout_s=180.0,
            )
            target = after["bootstrap"]
            api_deployment = target.get("deployment")
            if not isinstance(api_deployment, dict) or api_deployment.get("state") != "succeeded":
                raise AcceptanceError(f"QEMU Bootstrap deployment did not succeed: {api_deployment!r}")
            runtime = target.get("runtime")
            if not isinstance(runtime, dict) or runtime.get("state") != "runtime_active":
                raise AcceptanceError(f"QEMU target did not report runtime_active: {runtime!r}")

            ready_status, ready = _json_request(f"http://{args.ppu_ip}:18080/api/health/ready")
            _expect(ready_status, 200, ready, "QEMU Gateway readiness")
            if not (
                ready.get("ok") is True
                and ready.get("gateway") == "alive"
                and ready.get("execution") == "ready"
            ):
                raise AcceptanceError(f"QEMU Gateway readiness contract failed: {ready!r}")

            return {
                "result": "PASS",
                "evidence_level": "ci-qemu-armv7-z2like-demo",
                "simulation_environment": "CI Linux host mirroring SWPC topology",
                "backend": "QEMU ARMv7 simulated Z2",
                "manager_bootstrap_path": True,
                "registry_first_state": "pending",
                "pairing": "PASS",
                "chunked_upload": "PASS",
                "kit_sha256": kit_sha,
                "deployment_state": "succeeded",
                "runtime_state": "runtime_active",
                "gateway_readiness": "PASS",
                "not_claimed": [
                    "SWPC host deployment",
                    "public Cloudflare hostname routing",
                    "PYNQ-Z2 hardware",
                    "Plasma-owned Python installation",
                    "systemd/DAC on physical Z2",
                    "real Z2 reboot persistence",
                    "PS-to-PL",
                    "real IC programming",
                ],
            }
        finally:
            _stop(manager_process)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accept Manager -> Bootstrap -> QEMU ARMv7 z2like-demo deployment")
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--ppu-ip", default="172.30.77.2")
    parser.add_argument("--alias", default="z2like-qemu-ci")
    parser.add_argument("--ppu-id", default="z2like-qemu-ci")
    parser.add_argument("--facility-id", default="ci")
    parser.add_argument("--container", default="plasma-z2like-demo-qemu")
    parser.add_argument("--manager-port", type=int, default=18380)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = run_acceptance(args)
    except (AcceptanceError, OSError, subprocess.SubprocessError) as exc:
        print(f"z2like-demo-qemu-e2e: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
