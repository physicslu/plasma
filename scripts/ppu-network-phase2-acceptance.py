#!/usr/bin/env python3
"""One-command packaged ARMv7 acceptance for PPU Network Phase 2.

The host builds and clean-verifies the canonical linux-armv7l PPU release, then
creates an isolated Docker bridge with three roles:

- PPU: packaged Plasma Server/Gateway, no CAP_NET_ADMIN;
- privileged helper sidecar: shares the PPU network namespace, CAP_NET_ADMIN only;
- coordinator probe: reconnects to old/new PPU endpoints and verifies ppu_id.

The lab performs a real static IPv4 mutation inside the isolated container
network. It proves ACK-before-mutation, reconnect to the candidate endpoint,
same-ppu_id verification, explicit commit, and automatic rollback when commit is
omitted. It does not claim PYNQ-Z2 hardware, DHCP activation, DNS/route mutation,
boot persistence, or a final Z2 Linux network-manager backend.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
DEFAULT_WORK_REL = Path(".work/ppu-network-phase2-acceptance")
DEFAULT_REPORT_REL = Path(".work/reports/ppu-network-phase2-acceptance.json")
LAB_SUBNET = "192.168.77.0/24"
LAB_GATEWAY = "192.168.77.1"
INITIAL_IP = "192.168.77.10"
COMMITTED_IP = "192.168.77.21"
ROLLBACK_CANDIDATE_IP = "192.168.77.22"
PROBE_IP = "192.168.77.30"
PPU_ID = "swpc-armv7-phase2"
PPU_PORT = 18080
ROLLBACK_TIMEOUT_S = 2
RESULT_MARKER = "PLASMA_PPU_NETWORK_PHASE2_RESULT="
CAP_NET_ADMIN = 12
SIOCGIFADDR = 0x8915
SIOCSIFADDR = 0x8916
SIOCGIFNETMASK = 0x891B
SIOCSIFNETMASK = 0x891C
MAX_HELPER_REQUEST = 1024 * 1024


class AcceptanceError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, text=True, capture_output=capture, check=check)


def _host_python(repo: Path) -> Path:
    venv = repo / "software/python/.venv/bin/python"
    if venv.is_file():
        return venv
    if sys.version_info < (3, 11):
        raise AcceptanceError(f"Python >=3.11 is required, got {platform.python_version()}")
    return Path(sys.executable).resolve()


def _git_sha(repo: Path) -> str:
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    if len(sha) != 40:
        raise AcceptanceError(f"unexpected git SHA: {sha!r}")
    return sha


def _product_version(repo: Path) -> str:
    payload = json.loads((repo / "release/product.json").read_text(encoding="utf-8"))
    version = payload.get("product_version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version:
        raise AcceptanceError("release/product.json is missing product_version")
    return version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_sidecar(archive: Path, sidecar: Path) -> str:
    line = sidecar.read_text(encoding="utf-8").strip()
    parts = line.split()
    if len(parts) != 2 or parts[1] != archive.name or len(parts[0]) != 64:
        raise AcceptanceError(f"invalid release sidecar: {line!r}")
    actual = _sha256(archive)
    if actual != parts[0]:
        raise AcceptanceError(f"release SHA-256 mismatch: expected {parts[0]}, got {actual}")
    return actual


def _docker_preflight() -> bool:
    if shutil.which("docker") is None:
        raise AcceptanceError("docker is not available on PATH")
    probe = [
        "docker", "run", "--rm", "--platform", "linux/arm/v7", ARM_IMAGE,
        "python3", "-c", "import platform; print(platform.machine())",
    ]
    installed = False
    result = _run(probe, check=False)
    if result.returncode != 0:
        install = _run(
            ["docker", "run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm"],
            check=False,
        )
        if install.returncode != 0:
            raise AcceptanceError("ARM binfmt installation failed:\n" + install.stdout + install.stderr)
        installed = True
        result = _run(probe, check=False)
    if result.returncode != 0 or result.stdout.strip().lower() not in {"armv7", "armv7l"}:
        raise AcceptanceError("ARMv7 Docker preflight failed:\n" + result.stdout + result.stderr)
    return installed


def _build_release(repo: Path, work: Path, python: Path, git_sha: str, version: str) -> tuple[Path, Path, str]:
    runtime = work / "build-runtime"
    release_dir = work / "release"
    extracted = work / "extracted"
    _run([str(python), "scripts/ppu-runtime.py", "build", "--output-dir", str(runtime)], cwd=repo)
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(runtime)], cwd=repo)
    _run(
        [
            str(python), "scripts/ppu-release.py",
            "--runtime-dir", str(runtime),
            "--output-dir", str(release_dir),
            "--git-sha", git_sha,
        ],
        cwd=repo,
    )
    archive = release_dir / f"plasma-ppu-{version}-linux-armv7l.tar.gz"
    sidecar = Path(f"{archive}.sha256")
    if not archive.is_file() or not sidecar.is_file():
        raise AcceptanceError("canonical PPU linux-armv7l release was not produced")
    release_sha = _verify_sidecar(archive, sidecar)
    _run(
        [
            str(python), "scripts/product-release.py", "verify", str(archive),
            "--sidecar", str(sidecar),
            "--extract-to", str(extracted),
            "--expect-role", "ppu",
            "--expect-platform", "linux",
            "--expect-architecture", "armv7l",
            "--expect-version", version,
        ],
        cwd=repo,
    )
    clean_runtime = extracted / "plasma-release/runtime"
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(clean_runtime)], cwd=repo)
    return clean_runtime, archive, release_sha


def _write_ppu_config(work: Path) -> None:
    (work / "ppu.yaml").write_text(
        "ppu:\n"
        f"  id: {PPU_ID}\n"
        "  facility_id: swpc-qemu\n"
        "  model: qemu-armv7-phase2\n"
        "  display_name: Plasma Phase 2 ARMv7 Lab\n\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        "  port: 9900\n"
        "  max_supported_sites: 8\n"
        "  max_concurrent_jobs: 1\n"
        "  max_queue_depth_per_site: 16\n"
        "  output_root: /work/server-output\n"
        "  log_root: /work/logs\n"
        "  max_metadata_bytes: 65536\n"
        "  max_map_bytes: 1048576\n"
        "  max_binary_bytes: 67108864\n\n"
        "sites: []\n",
        encoding="utf-8",
    )


def _docker_rm(name: str) -> None:
    _run(["docker", "rm", "-f", name], check=False)


def _docker_network_rm(name: str) -> None:
    _run(["docker", "network", "rm", name], check=False)


def _container_diagnostics(name: str) -> str:
    state = _run(
        [
            "docker", "inspect", "-f",
            "status={{.State.Status}} exit={{.State.ExitCode}} error={{.State.Error}}",
            name,
        ],
        check=False,
    )
    logs = _run(["docker", "logs", name], check=False)
    state_text = (state.stdout + state.stderr).strip() or f"inspect rc={state.returncode}"
    logs_text = (logs.stdout + logs.stderr).strip() or "<no logs>"
    return f"{name}: {state_text}\n{logs_text}"


def _cap_eff(container: str) -> int:
    result = _run(["docker", "exec", container, "cat", "/proc/1/status"])
    for line in result.stdout.splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    raise AcceptanceError(f"cannot read CapEff from {container}")


def _has_cap(value: int, cap: int) -> bool:
    return bool(value & (1 << cap))


PROBE_CODE = r'''
import json, sys, urllib.error, urllib.request
url, method, body_json = sys.argv[1:4]
data = None if body_json == "" else body_json.encode("utf-8")
headers = {"Accept":"application/json"}
if data is not None:
    headers["Content-Type"] = "application/json"
request = urllib.request.Request(url, data=data, headers=headers, method=method)
try:
    with urllib.request.urlopen(request, timeout=1.2) as response:
        raw = response.read()
        payload = json.loads(raw) if raw else None
        print(json.dumps({"reachable": True, "status": response.status, "payload": payload}, sort_keys=True))
except urllib.error.HTTPError as exc:
    raw = exc.read()
    try:
        payload = json.loads(raw) if raw else None
    except Exception:
        payload = {"raw": raw.decode("utf-8", "replace")}
    print(json.dumps({"reachable": True, "status": exc.code, "payload": payload}, sort_keys=True))
except Exception as exc:
    print(json.dumps({"reachable": False, "error": type(exc).__name__ + ": " + str(exc)}, sort_keys=True))
'''


def _probe(container: str, ip: str, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body_json = json.dumps(dict(body), separators=(",", ":"), sort_keys=True) if body is not None else ""
    result = _run(
        [
            "docker", "exec", container, "python3", "-c", PROBE_CODE,
            f"http://{ip}:{PPU_PORT}{path}", method, body_json,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise AcceptanceError(f"probe process failed: {result.stdout}{result.stderr}")
    try:
        value = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"invalid probe output: {result.stdout!r}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError("probe output is not an object")
    return value


def _expect_json(container: str, ip: str, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None, status: int = 200) -> dict[str, Any]:
    result = _probe(container, ip, path, method=method, body=body)
    if result.get("reachable") is not True or result.get("status") != status or not isinstance(result.get("payload"), dict):
        raise AcceptanceError(f"unexpected HTTP result for {ip}{path}: {result!r}")
    return result["payload"]


def _wait_reachable(container: str, ip: str, path: str = "/api/node", *, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = _probe(container, ip, path)
        if last.get("reachable") is True and last.get("status") == 200 and isinstance(last.get("payload"), dict):
            return last["payload"]
        time.sleep(0.1)
    raise AcceptanceError(f"endpoint {ip}{path} did not become reachable: {last!r}")


def _wait_unreachable(container: str, ip: str, path: str = "/api/node", *, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = _probe(container, ip, path)
        if result.get("reachable") is not True:
            return
        time.sleep(0.1)
    raise AcceptanceError(f"endpoint {ip}{path} remained reachable")


def _wait_activation_state(container: str, ip: str, state: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = _expect_json(container, ip, "/api/settings/ppu-network/activation")
        activation = payload.get("activation")
        if isinstance(activation, dict):
            last = activation
            if activation.get("state") == state:
                return activation
        time.sleep(0.1)
    raise AcceptanceError(f"activation did not reach {state}: {last!r}")


def _node_ppu_id(payload: Mapping[str, Any]) -> str:
    ppu = payload.get("ppu")
    ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
    if not isinstance(ppu_id, str) or not ppu_id:
        raise AcceptanceError(f"/api/node is missing canonical ppu_id: {payload!r}")
    return ppu_id


def _desired(address: str) -> dict[str, Any]:
    return {
        "mode": "static",
        "address": address,
        "prefix_length": 24,
        "gateway": LAB_GATEWAY,
        "dns_servers": [LAB_GATEWAY],
    }


def _host_mode(args: argparse.Namespace) -> int:
    repo = _repo_root()
    python = _host_python(repo)
    git_sha = _git_sha(repo)
    version = _product_version(repo)
    work = (repo / args.work_dir).resolve() if not args.work_dir.is_absolute() else args.work_dir.resolve()
    report_path = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # The lab deliberately drops every capability from the PPU container. A
    # host-owned 0755 bind mount is therefore not writable even by container
    # uid 0 after DAC_OVERRIDE is removed. Keep the build/report tree private,
    # but expose one dedicated ephemeral container work tree with explicit write
    # permission. This preserves the capability boundary instead of weakening it.
    container_work = work / "container-work"
    container_work.mkdir()
    container_work.chmod(0o777)
    for directory in (container_work / "server-output", container_work / "gateway-output", container_work / "logs"):
        directory.mkdir()
        directory.chmod(0o777)
    _write_ppu_config(container_work)

    installed_binfmt = _docker_preflight()
    runtime, archive, release_sha = _build_release(repo, work, python, git_sha, version)

    suffix = f"{os.getpid()}-{int(time.time())}"
    network = f"plasma-phase2-{suffix}"
    ppu = f"plasma-phase2-ppu-{suffix}"
    helper = f"plasma-phase2-helper-{suffix}"
    probe = f"plasma-phase2-probe-{suffix}"
    script = Path(__file__).resolve()
    checks: dict[str, str] = {}

    try:
        _run(["docker", "network", "create", "--subnet", LAB_SUBNET, "--gateway", LAB_GATEWAY, network])
        checks["isolated_network"] = "PASS"

        _run([
            "docker", "run", "-d", "--name", ppu,
            "--platform", "linux/arm/v7",
            "--network", network, "--ip", INITIAL_IP,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "-v", f"{runtime}:/runtime:ro",
            "-v", f"{container_work}:/work",
            "-v", f"{script}:/acceptance.py:ro",
            ARM_IMAGE,
            "python3", "/acceptance.py", "--inside-ppu",
            "--runtime-dir", "/runtime", "--work-dir", "/work",
        ])
        _run([
            "docker", "run", "-d", "--name", helper,
            "--platform", "linux/arm/v7",
            "--network", f"container:{ppu}",
            "--cap-drop", "ALL", "--cap-add", "NET_ADMIN",
            "--security-opt", "no-new-privileges:true",
            "-v", f"{container_work}:/work",
            "-v", f"{script}:/acceptance.py:ro",
            ARM_IMAGE,
            "python3", "/acceptance.py", "--helper",
            "--helper-socket", "/work/network-helper.sock",
        ])
        _run([
            "docker", "run", "-d", "--name", probe,
            "--platform", "linux/arm/v7",
            "--network", network, "--ip", PROBE_IP,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            ARM_IMAGE,
            "python3", "-c", "import time; time.sleep(3600)",
        ])

        helper_socket = container_work / "network-helper.sock"
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not helper_socket.exists():
            time.sleep(0.05)
        if not helper_socket.exists():
            diagnostics = "\n\n".join(_container_diagnostics(name) for name in (ppu, helper))
            raise AcceptanceError(f"privileged helper Unix socket did not appear\n{diagnostics}")
        checks["helper_socket_ready"] = "PASS"

        ppu_cap = _cap_eff(ppu)
        helper_cap = _cap_eff(helper)
        if _has_cap(ppu_cap, CAP_NET_ADMIN):
            raise AcceptanceError("PPU Gateway container unexpectedly has CAP_NET_ADMIN")
        if not _has_cap(helper_cap, CAP_NET_ADMIN):
            raise AcceptanceError("privileged helper is missing CAP_NET_ADMIN")
        checks["gateway_no_net_admin"] = "PASS"
        checks["helper_has_net_admin"] = "PASS"

        initial_node = _wait_reachable(probe, INITIAL_IP)
        initial_ppu_id = _node_ppu_id(initial_node)
        if initial_ppu_id != PPU_ID:
            raise AcceptanceError(f"unexpected initial ppu_id: {initial_ppu_id}")
        checks["initial_endpoint"] = "PASS"

        network_payload = _expect_json(probe, INITIAL_IP, "/api/settings/ppu-network")
        activation = network_payload.get("activation")
        if not isinstance(activation, dict) or activation.get("supported") is not True or activation.get("state") != "idle":
            raise AcceptanceError(f"Phase 2 activation is not ready: {activation!r}")
        checks["activation_supported"] = "PASS"

        desired2 = _expect_json(
            probe, INITIAL_IP, "/api/settings/ppu-network",
            method="POST", body=_desired(COMMITTED_IP),
        )
        revision2 = desired2["ppu_network_settings"]["revision"]
        if revision2 != 2:
            raise AcceptanceError(f"expected desired revision 2, got {revision2}")
        checks["desired_revision_2"] = "PASS"

        scheduled = _expect_json(
            probe, INITIAL_IP, "/api/settings/ppu-network/activation",
            method="POST",
            body={
                "action": "apply",
                "expected_revision": revision2,
                "expected_ppu_id": initial_ppu_id,
                "rollback_timeout_s": ROLLBACK_TIMEOUT_S,
            },
            status=202,
        )
        activation_id = scheduled["activation"]["activation_id"]
        if not isinstance(activation_id, str) or not activation_id:
            raise AcceptanceError("activation ACK is missing activation_id")
        checks["ack_before_mutation"] = "PASS"

        candidate_node = _wait_reachable(probe, COMMITTED_IP)
        candidate_ppu_id = _node_ppu_id(candidate_node)
        if candidate_ppu_id != initial_ppu_id:
            raise AcceptanceError(f"candidate endpoint ppu_id changed: {candidate_ppu_id}")
        _wait_unreachable(probe, INITIAL_IP)
        waiting = _wait_activation_state(probe, COMMITTED_IP, "applied_waiting_commit")
        if waiting.get("revision") != revision2:
            raise AcceptanceError("activation waiting state has wrong revision")
        checks["candidate_reconnect"] = "PASS"
        checks["same_ppu_id_revalidation"] = "PASS"
        checks["old_endpoint_removed"] = "PASS"

        committed = _expect_json(
            probe, COMMITTED_IP,
            f"/api/settings/ppu-network/activation/{activation_id}/commit",
            method="POST",
            body={"expected_revision": revision2, "expected_ppu_id": candidate_ppu_id},
        )
        committed_activation = committed["activation"]
        if committed_activation.get("state") != "committed" or committed_activation.get("committed_revision") != revision2:
            raise AcceptanceError(f"commit did not finalize revision 2: {committed_activation!r}")
        time.sleep(ROLLBACK_TIMEOUT_S + 0.4)
        still_committed = _wait_reachable(probe, COMMITTED_IP)
        if _node_ppu_id(still_committed) != initial_ppu_id:
            raise AcceptanceError("committed endpoint identity drifted")
        _wait_unreachable(probe, INITIAL_IP, timeout_s=1.5)
        checks["explicit_commit"] = "PASS"
        checks["commit_survives_deadline"] = "PASS"

        desired3 = _expect_json(
            probe, COMMITTED_IP, "/api/settings/ppu-network",
            method="POST", body=_desired(ROLLBACK_CANDIDATE_IP),
        )
        revision3 = desired3["ppu_network_settings"]["revision"]
        if revision3 != 3:
            raise AcceptanceError(f"expected desired revision 3, got {revision3}")
        second = _expect_json(
            probe, COMMITTED_IP, "/api/settings/ppu-network/activation",
            method="POST",
            body={
                "action": "apply",
                "expected_revision": revision3,
                "expected_ppu_id": initial_ppu_id,
                "rollback_timeout_s": ROLLBACK_TIMEOUT_S,
            },
            status=202,
        )
        second_id = second["activation"]["activation_id"]
        if second_id == activation_id:
            raise AcceptanceError("second activation reused activation_id")
        second_node = _wait_reachable(probe, ROLLBACK_CANDIDATE_IP)
        if _node_ppu_id(second_node) != initial_ppu_id:
            raise AcceptanceError("rollback candidate endpoint ppu_id changed")
        _wait_unreachable(probe, COMMITTED_IP)
        _wait_activation_state(probe, ROLLBACK_CANDIDATE_IP, "applied_waiting_commit")
        checks["second_candidate_reconnect"] = "PASS"

        # Intentionally do not commit revision 3. The PPU-side transaction must
        # restore the previous committed .21 snapshot without coordinator help.
        restored_node = _wait_reachable(probe, COMMITTED_IP, timeout_s=ROLLBACK_TIMEOUT_S + 5)
        if _node_ppu_id(restored_node) != initial_ppu_id:
            raise AcceptanceError("restored endpoint ppu_id changed")
        _wait_unreachable(probe, ROLLBACK_CANDIDATE_IP, timeout_s=2)
        rolled_back = _wait_activation_state(probe, COMMITTED_IP, "rolled_back")
        if rolled_back.get("reason") != "commit_deadline_expired":
            raise AcceptanceError(f"unexpected rollback reason: {rolled_back!r}")
        if rolled_back.get("committed_revision") != revision2:
            raise AcceptanceError(f"rollback lost committed revision: {rolled_back!r}")
        final_settings = _expect_json(probe, COMMITTED_IP, "/api/settings/ppu-network")
        if final_settings["ppu_network_settings"]["revision"] != revision3:
            raise AcceptanceError("rollback incorrectly rewrote desired revision")
        if final_settings["ppu_network_settings"]["address"] != ROLLBACK_CANDIDATE_IP:
            raise AcceptanceError("rollback incorrectly rewrote desired candidate")
        checks["automatic_rollback"] = "PASS"
        checks["committed_revision_preserved"] = "PASS"
        checks["desired_revision_preserved"] = "PASS"

        journal = container_work / "gateway-output" / "ppu-network-activation.json"
        if not journal.is_file():
            raise AcceptanceError("activation journal was not persisted")
        checks["durable_journal"] = "PASS"

        result = {
            "overall_result": "PASS",
            "transaction_result": "PASS",
            "evidence_level": "swpc-qemu-armv7-isolated-static-ipv4",
            "git_sha": git_sha,
            "product_version": version,
            "architecture": "armv7l",
            "release_artifact": archive.name,
            "release_sha256": release_sha,
            "arm_binfmt_installed_now": installed_binfmt,
            "initial_ipv4": INITIAL_IP,
            "committed_ipv4": COMMITTED_IP,
            "rollback_candidate_ipv4": ROLLBACK_CANDIDATE_IP,
            "ppu_id": initial_ppu_id,
            "committed_revision": revision2,
            "desired_revision_after_rollback": revision3,
            "checks": checks,
            "actual_network_mutation": "isolated-lab-static-ipv4",
            "privilege_separation": {
                "gateway_cap_net_admin": False,
                "helper_cap_net_admin": True,
            },
            "not_claimed": [
                "PYNQ-Z2 hardware",
                "final Z2 Linux network-manager backend",
                "DHCP activation",
                "DNS mutation",
                "default-route mutation",
                "boot-time network persistence",
                "Manager production integration",
                "PS-to-PL",
                "Site I/O",
                "real IC programming",
            ],
        }
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _print_summary(result, report_path)
        return 0
    finally:
        for name in (helper, probe, ppu):
            _docker_rm(name)
        _docker_network_rm(network)


def _print_summary(result: Mapping[str, Any], report_path: Path) -> None:
    checks = result["checks"]
    print("=" * 72)
    print("Plasma PPU Network Phase 2 Acceptance")
    print("=" * 72)
    print(f"Git SHA                    : {result['git_sha']}")
    print(f"Product Version            : {result['product_version']}")
    print(f"Architecture               : {result['architecture']}")
    print(f"Release Artifact           : {result['release_artifact']}")
    print(f"Release SHA-256            : {result['release_sha256']}")
    print()
    for name, value in checks.items():
        print(f"[{value}] {name.replace('_', ' ').title()}")
    print()
    print(f"PPU ID                     : {result['ppu_id']}")
    print(f"Initial IPv4               : {result['initial_ipv4']}")
    print(f"Committed IPv4             : {result['committed_ipv4']}")
    print(f"Rollback Candidate IPv4    : {result['rollback_candidate_ipv4']}")
    print(f"Committed Revision         : {result['committed_revision']}")
    print(f"Desired Revision After RB  : {result['desired_revision_after_rollback']}")
    print("-" * 72)
    print("PHASE 2 TRANSACTION RESULT : PASS")
    print("ACTUAL NETWORK MUTATION     : LAB STATIC IPV4")
    print("PRIVILEGE SEPARATION        : PASS")
    print("SAME PPU_ID REVALIDATION    : PASS")
    print("AUTOMATIC ROLLBACK          : PASS")
    print("Z2 NETWORK BACKEND CLAIM    : NONE")
    print("Z2 HARDWARE CLAIM           : NONE")
    print("OVERALL RESULT              : PASS")
    print("-" * 72)
    print(f"JSON report                 : {report_path}")
    print("=" * 72)
    print(RESULT_MARKER + json.dumps(dict(result), sort_keys=True))


def _inside_ppu(args: argparse.Namespace) -> int:
    if platform.machine().lower() not in {"armv7", "armv7l"}:
        raise AcceptanceError(f"inside PPU mode requires ARMv7, got {platform.machine()}")
    runtime = args.runtime_dir.resolve()
    work = args.work_dir.resolve()
    app = runtime / "ppu/ppu.pyz"
    if not app.is_file():
        raise AcceptanceError(f"packaged PPU zipapp missing: {app}")
    manifest = json.loads((runtime / "ppu-runtime.json").read_text(encoding="utf-8"))
    catalog_relative = (manifest.get("data") or {}).get("device_catalog_manifest")
    catalog = runtime / str(catalog_relative)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)
    for directory in (work / "server-output", work / "gateway-output", work / "logs"):
        directory.mkdir(parents=True, exist_ok=True)
    server = gateway = None
    try:
        server = subprocess.Popen(
            [sys.executable, str(app), "server", "--config", str(work / "ppu.yaml")],
            cwd=work, env=env,
        )
        gateway = subprocess.Popen(
            [
                sys.executable, str(app), "gateway",
                "--host", "0.0.0.0", "--port", str(PPU_PORT),
                "--plasma-host", "127.0.0.1", "--plasma-port", "9900",
                "--output-root", str(work / "gateway-output"),
                "--network-activation-socket", str(work / "network-helper.sock"),
            ],
            cwd=work, env=env,
        )
        while True:
            if server.poll() is not None:
                raise AcceptanceError(f"packaged Plasma Server exited: {server.returncode}")
            if gateway.poll() is not None:
                raise AcceptanceError(f"packaged PPU Gateway exited: {gateway.returncode}")
            time.sleep(0.2)
    finally:
        for process in (gateway, server):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def _ifreq_name(interface: str) -> bytes:
    encoded = interface.encode("ascii")
    if not encoded or len(encoded) > 15:
        raise AcceptanceError("helper interface name must be 1..15 ASCII bytes")
    return encoded


def _get_ipv4(interface: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        request = struct.pack("256s", _ifreq_name(interface))
        response = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, request)
        return socket.inet_ntoa(response[20:24])


def _get_netmask(interface: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        request = struct.pack("256s", _ifreq_name(interface))
        response = fcntl.ioctl(sock.fileno(), SIOCGIFNETMASK, request)
        return socket.inet_ntoa(response[20:24])


def _prefix_from_netmask(netmask: str) -> int:
    network = ipaddress.IPv4Network(f"0.0.0.0/{netmask}")
    return network.prefixlen


def _set_sockaddr(interface: str, command: int, address: str) -> None:
    packed = struct.pack(
        "16sH2s4s8s",
        _ifreq_name(interface),
        socket.AF_INET,
        b"\x00\x00",
        socket.inet_aton(address),
        b"\x00" * 8,
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        fcntl.ioctl(sock.fileno(), command, packed)


def _set_ipv4(interface: str, address: str, prefix_length: int) -> None:
    ipaddress.IPv4Address(address)
    if not 1 <= prefix_length <= 32:
        raise AcceptanceError("helper prefix_length must be 1..32")
    netmask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix_length}").netmask)

    # Linux SIOCSIFADDR may leave the previous AF_INET address present when a
    # new address is applied. netdevice(7) defines deletion of an IPv4 address
    # by setting it to 0.0.0.0 through SIOCSIFADDR. Do that first so this helper
    # implements replace semantics: after apply, the old PPU endpoint must no
    # longer be routable. The helper is local over a Unix socket, so the brief
    # address-less interval does not break the transaction channel.
    _set_sockaddr(interface, SIOCSIFADDR, "0.0.0.0")
    _set_sockaddr(interface, SIOCSIFADDR, address)
    _set_sockaddr(interface, SIOCSIFNETMASK, netmask)


def _snapshot(interface: str) -> dict[str, Any]:
    return {
        "interface": interface,
        "address": _get_ipv4(interface),
        "prefix_length": _prefix_from_netmask(_get_netmask(interface)),
    }


def _helper_operation(interface: str, request: Mapping[str, Any]) -> dict[str, Any]:
    operation = request.get("operation")
    if operation == "snapshot":
        return _snapshot(interface)
    if operation == "apply":
        settings = request.get("settings")
        if not isinstance(settings, dict):
            raise AcceptanceError("helper apply settings must be an object")
        if settings.get("interface") != interface or settings.get("mode") != "static":
            raise AcceptanceError("lab helper supports only static eth0 settings")
        address = settings.get("address")
        prefix = settings.get("prefix_length")
        if not isinstance(address, str) or isinstance(prefix, bool) or not isinstance(prefix, int):
            raise AcceptanceError("lab helper received invalid static settings")
        _set_ipv4(interface, address, prefix)
        return _snapshot(interface)
    if operation == "restore":
        snapshot = request.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("interface") != interface:
            raise AcceptanceError("helper restore snapshot is invalid")
        address = snapshot.get("address")
        prefix = snapshot.get("prefix_length")
        if not isinstance(address, str) or isinstance(prefix, bool) or not isinstance(prefix, int):
            raise AcceptanceError("helper restore snapshot address/prefix is invalid")
        _set_ipv4(interface, address, prefix)
        return _snapshot(interface)
    raise AcceptanceError(f"unsupported helper operation: {operation!r}")


def _helper_mode(args: argparse.Namespace) -> int:
    if platform.machine().lower() not in {"armv7", "armv7l"}:
        raise AcceptanceError(f"helper mode requires ARMv7, got {platform.machine()}")
    path = args.helper_socket.resolve()
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
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
                    if not isinstance(request, dict):
                        raise AcceptanceError("helper request must be an object")
                    result = _helper_operation(args.interface, request)
                    response = {"ok": True, "result": result}
                except Exception as exc:
                    response = {
                        "ok": False,
                        "error": {
                            "error_type": "LAB_NETWORK_HELPER_ERROR",
                            "message": str(exc),
                        },
                    }
                connection.sendall((json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plasma PPU Network Phase 2 acceptance")
    parser.add_argument("--inside-ppu", action="store_true")
    parser.add_argument("--helper", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=Path("/runtime"))
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    parser.add_argument("--helper-socket", type=Path, default=Path("/work/network-helper.sock"))
    parser.add_argument("--interface", default="eth0")
    args = parser.parse_args(argv)
    try:
        if args.helper:
            return _helper_mode(args)
        if args.inside_ppu:
            return _inside_ppu(args)
        return _host_mode(args)
    except (AcceptanceError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"ppu-network-phase2-acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
