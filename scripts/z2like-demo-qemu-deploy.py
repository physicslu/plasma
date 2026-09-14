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
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

CHUNK_BYTES = 1024 * 1024
MAX_SIMULATION_SITE_COUNT = 8
SITE_COUNT_MARKER = "/var/lib/plasma/z2like-demo-site-count"
ACTIVE_SITE_STATES = frozenset(
    {"queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"}
)


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


def _prepare_target_scenario(container: str, site_count: int) -> None:
    if not 1 <= site_count <= MAX_SIMULATION_SITE_COUNT:
        raise DeployError(
            f"z2like-demo Site count must be between 1 and {MAX_SIMULATION_SITE_COUNT}"
        )
    writer = (
        "from pathlib import Path; import sys; "
        f"p=Path({SITE_COUNT_MARKER!r}); "
        "p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_text(sys.argv[1]+'\\n', encoding='utf-8'); "
        "p.chmod(0o600)"
    )
    written = subprocess.run(
        ["docker", "exec", container, "python3", "-c", writer, str(site_count)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
    )
    if written.returncode != 0:
        raise DeployError(f"cannot persist QEMU Site-count marker: {written.stderr.strip()}")
    restarted = subprocess.run(
        ["docker", "restart", container],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=45,
    )
    if restarted.returncode != 0:
        raise DeployError(f"cannot reload QEMU target harness: {restarted.stderr.strip()}")


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
        if time.monotonic() >= deadline:
            raise DeployError(f"cannot set PPU lifecycle to {lifecycle!r}: HTTP {status} {payload!r}")
        time.sleep(1.0)


def _fleet_item_is_trusted_idle(item: Mapping[str, Any], alias: str) -> bool:
    if item.get("alias") != alias:
        return False
    observation = item.get("observation")
    if not isinstance(observation, dict) or observation.get("state") != "current":
        return False
    if item.get("gateway_live") is not True or item.get("identity_conflict") is not False or item.get("errors"):
        return False
    sites = item.get("sites")
    if not isinstance(sites, list):
        return False
    for site in sites:
        if not isinstance(site, dict):
            continue
        state = str(site.get("state", "")).strip().lower()
        if state in ACTIVE_SITE_STATES or site.get("current_job_id"):
            return False
    return True


def _fleet_observed_at(payload: Mapping[str, Any]) -> datetime:
    raw = payload.get("observed_at")
    if not isinstance(raw, str) or not raw:
        raise DeployError("Manager fleet snapshot omitted observed_at generation")
    try:
        observed_at = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DeployError(f"Manager fleet snapshot has invalid observed_at: {raw!r}") from exc
    if observed_at.tzinfo is None:
        raise DeployError("Manager fleet observed_at must be timezone-aware")
    return observed_at


def _read_fleet_generation(manager: str) -> datetime:
    status, payload = _json_request(f"{manager}/api/fleet")
    _expect(status, 200, payload, "Manager fleet snapshot")
    return _fleet_observed_at(payload)


def _fleet_has_trusted_idle_after(
    payload: Mapping[str, Any], alias: str, after_observed_at: datetime
) -> bool:
    try:
        observed_at = _fleet_observed_at(payload)
    except DeployError:
        return False
    if observed_at <= after_observed_at:
        return False
    ppus = payload.get("ppus")
    return isinstance(ppus, list) and any(
        isinstance(item, dict) and _fleet_item_is_trusted_idle(item, alias)
        for item in ppus
    )


def _wait_for_trusted_idle(
    manager: str,
    alias: str,
    *,
    after_observed_at: datetime,
    timeout_s: float = 60.0,
) -> datetime:
    try:
        payload = _wait_json(
            f"{manager}/api/fleet",
            lambda candidate: _fleet_has_trusted_idle_after(candidate, alias, after_observed_at),
            timeout_s=timeout_s,
        )
    except DeployError as exc:
        raise DeployError(
            "Manager did not publish a newer current trusted idle PPU observation required for Runtime maintenance "
            "after the QEMU target restart"
        ) from exc
    return _fleet_observed_at(payload)


def _error_code(payload: Mapping[str, Any]) -> str | None:
    error = payload.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _create_upload_with_idle_retry(
    bootstrap_url: str,
    *,
    manager: str,
    alias: str,
    size: int,
    kit_sha: str,
    trusted_generation: datetime,
    timeout_s: float = 60.0,
) -> tuple[dict[str, Any], datetime]:
    deadline = time.monotonic() + timeout_s
    generation = trusted_generation
    while True:
        status, created = _json_request(
            f"{bootstrap_url}/uploads",
            method="POST",
            body={"size": size, "sha256": kit_sha},
        )
        if status == 201:
            return created, generation
        if status != 409 or _error_code(created) != "ppu_idle_state_unproven":
            _expect(status, 201, created, "upload create")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeployError(
                "upload create remained blocked because the Manager could not prove a current idle PPU observation"
            )
        current_generation = _read_fleet_generation(manager)
        if current_generation > generation:
            generation = current_generation
        generation = _wait_for_trusted_idle(
            manager,
            alias,
            after_observed_at=generation,
            timeout_s=remaining,
        )


def _verify_programming_catalog(payload: Mapping[str, Any], *, site_count: int, ppu_id: str) -> None:
    if payload.get("ok") is not True or payload.get("provider") != "configured_mock":
        raise DeployError(f"QEMU configured Mock Programming provider is unavailable: {payload!r}")
    if payload.get("ppu_count") != 1 or payload.get("site_count") != site_count:
        raise DeployError(
            f"QEMU Programming catalog topology mismatch: expected one PPU/{site_count} Sites, got {payload!r}"
        )
    facilities = payload.get("facilities")
    if not isinstance(facilities, list) or len(facilities) != 1:
        raise DeployError(f"QEMU Programming catalog facility topology is invalid: {payload!r}")
    ppus = facilities[0].get("ppus") if isinstance(facilities[0], dict) else None
    if not isinstance(ppus, list) or len(ppus) != 1 or ppus[0].get("ppu_id") != ppu_id:
        raise DeployError(f"QEMU Programming catalog PPU identity mismatch: {payload!r}")


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    kit = args.kit.expanduser().resolve()
    sidecar = args.sidecar.expanduser().resolve()
    if not kit.is_file() or not sidecar.is_file():
        raise DeployError("kit artifact and sidecar are required")
    if not 1 <= args.site_count <= MAX_SIMULATION_SITE_COUNT:
        raise DeployError(
            f"site-count must be between 1 and {MAX_SIMULATION_SITE_COUNT}"
        )
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    kit_sha = _sha256(kit)
    if len(fields) != 2 or fields[1].lstrip("*") != kit.name or fields[0].lower() != kit_sha:
        raise DeployError("kit detached SHA-256 sidecar is invalid")

    manager = args.manager.rstrip("/")
    _wait_json(f"{manager}/api/health/live", lambda payload: payload.get("ok") is True, timeout_s=30.0)
    endpoint = f"http://{args.ppu_ip}:18080"
    entry = _registry_entry(manager, args.alias, endpoint)
    lifecycle_before = entry.get("lifecycle")
    maintenance_requires_idle = lifecycle_before in {"commissioned", "disabled"}
    baseline_generation: datetime | None = None
    if lifecycle_before == "commissioned":
        _set_lifecycle(manager, args.alias, "disabled", retry_s=15.0)
    elif lifecycle_before not in {"pending", "disabled"}:
        raise DeployError(f"unsupported Manager lifecycle before maintenance: {lifecycle_before!r}")
    if maintenance_requires_idle:
        baseline_generation = _read_fleet_generation(manager)

    # The target remains non-operationally admitted while its simulation profile
    # is updated and the container is restarted. Restarting here also reloads the
    # current bind-mounted target harness after a git update.
    _prepare_target_scenario(args.container, args.site_count)

    # A cached fleet snapshot can still say current immediately after restart.
    # Require a strictly newer completed fleet generation before maintenance so
    # the admission evidence necessarily comes from after the target restart.
    trusted_generation: datetime | None = None
    if maintenance_requires_idle:
        if baseline_generation is None:
            raise DeployError("internal error: maintenance fleet generation baseline is unavailable")
        trusted_generation = _wait_for_trusted_idle(
            manager,
            args.alias,
            after_observed_at=baseline_generation,
            timeout_s=60.0,
        )

    bootstrap_url = f"{manager}/api/registry/{args.alias}/bootstrap"
    before = _wait_json(
        bootstrap_url,
        lambda payload: isinstance(payload.get("bootstrap"), dict),
        timeout_s=60.0,
    )
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
    if maintenance_requires_idle:
        if trusted_generation is None:
            raise DeployError("internal error: trusted maintenance generation is unavailable")
        created, trusted_generation = _create_upload_with_idle_retry(
            bootstrap_url,
            manager=manager,
            alias=args.alias,
            size=size,
            kit_sha=kit_sha,
            trusted_generation=trusted_generation,
            timeout_s=60.0,
        )
    else:
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

    targets_status, targets = _json_request(f"http://{args.ppu_ip}:18080/api/engineering/targets")
    _expect(targets_status, 200, targets, "QEMU Programming catalog")
    _verify_programming_catalog(targets, site_count=args.site_count, ppu_id=args.ppu_id)

    # Re-enable only after Runtime, topology and the configured Programming
    # provider are all coherent and the Manager has a current trusted observation.
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
        "programming_provider": "configured_mock",
        "configured_site_count": args.site_count,
        "kit_sha256": kit_sha,
        "not_claimed": [
            "Render deployment state",
            "Cloudflare route correctness",
            "PYNQ-Z2 hardware",
            "PL/FPGA",
            "real IC programming",
            "physical multi-Site concurrency",
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
    parser.add_argument(
        "--site-count",
        type=int,
        default=os.environ.get("PLASMA_Z2LIKE_DEMO_SITE_COUNT", "8"),
        help="number of enabled Mock Sites to provision (1..8; default 8)",
    )
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
