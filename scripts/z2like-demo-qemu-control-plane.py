#!/usr/bin/env python3
"""Reconcile the persistent SWPC/QEMU z2like-demo control plane to one Git commit.

The long-lived QEMU container must not execute Bootstrap/simulation tooling from a
mutable operator checkout.  This helper stages the exact checked-out ``scripts/``
Git tree into an immutable commit-named Docker volume, then recreates only the
simulation container while preserving all durable product/config/bootstrap/runtime
and log volumes.

This is simulation-only infrastructure.  It does not qualify PYNQ-Z2 hardware,
reboot persistence, PL/FPGA behavior, target power/electrical behavior, or real IC
programming.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
TARGET_MARKER = "PLASMA_Z2LIKE_DEMO_QEMU_TARGET"
CONTAINER = "plasma-z2like-demo-qemu"
NETWORK = "plasma-z2like-demo"
PPU_IP = "172.30.77.2"
SCRIPTS_VOLUME_PREFIX = "plasma-z2like-demo-scripts-"
PROVENANCE_FILE = ".plasma-control-plane-provenance.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")

DURABLE_MOUNTS = {
    "/opt/plasma": "plasma-z2like-demo-product",
    "/etc/plasma": "plasma-z2like-demo-config",
    "/var/lib/plasma-bootstrap": "plasma-z2like-demo-bootstrap",
    "/var/lib/plasma": "plasma-z2like-demo-runtime",
    "/var/log/plasma": "plasma-z2like-demo-logs",
}


class ReconcileError(RuntimeError):
    pass


def _run(
    argv: Sequence[str],
    *,
    capture: bool = False,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            check=check,
            text=True,
            capture_output=capture,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReconcileError(f"command failed: {' '.join(argv)}: {exc}") from exc


def _docker(*args: str, capture: bool = False, check: bool = True, timeout: float | None = None):
    return _run(["docker", *args], capture=capture, check=check, timeout=timeout)


def _repo_identity(repo: Path, expected_commit: str) -> tuple[str, str]:
    if not HEX40.fullmatch(expected_commit):
        raise ReconcileError("expected commit must be a full lowercase 40-hex SHA")
    head = _run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture=True).stdout.strip().lower()
    if head != expected_commit:
        raise ReconcileError(f"checked-out HEAD {head!r} does not match expected commit {expected_commit!r}")
    dirty = _run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=normal"],
        capture=True,
    ).stdout.strip()
    if dirty:
        raise ReconcileError("repository must be clean before staging QEMU control-plane scripts")
    scripts_tree = _run(
        ["git", "-C", str(repo), "rev-parse", f"{expected_commit}:scripts"],
        capture=True,
    ).stdout.strip().lower()
    if not HEX40.fullmatch(scripts_tree):
        raise ReconcileError("scripts Git tree identity is invalid")
    return head, scripts_tree


def _volume_name(commit: str) -> str:
    if not HEX40.fullmatch(commit):
        raise ReconcileError("cannot derive scripts volume from invalid commit")
    return f"{SCRIPTS_VOLUME_PREFIX}{commit}"


def _volume_exists(name: str) -> bool:
    return _docker("volume", "inspect", name, capture=True, check=False).returncode == 0


def _provenance(commit: str, scripts_tree: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_commit": commit,
        "scripts_tree_sha": scripts_tree,
        "ownership": "plasma-z2like-demo-commit-pinned-control-plane",
    }


def _read_volume_provenance(volume: str) -> dict[str, Any]:
    code = (
        "import json,pathlib;"
        f"print(pathlib.Path('/sim/{PROVENANCE_FILE}').read_text(encoding='utf-8'))"
    )
    result = _docker(
        "run",
        "--rm",
        "--platform",
        "linux/arm/v7",
        "--volume",
        f"{volume}:/sim:ro",
        ARM_IMAGE,
        "python3",
        "-c",
        code,
        capture=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise ReconcileError(f"cannot read provenance from staged scripts volume {volume}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReconcileError(f"staged scripts volume {volume} has invalid provenance JSON") from exc
    if not isinstance(payload, dict):
        raise ReconcileError(f"staged scripts volume {volume} provenance is not an object")
    return payload


def _stage_scripts(repo: Path, commit: str, scripts_tree: str) -> str:
    volume = _volume_name(commit)
    expected = _provenance(commit, scripts_tree)
    if _volume_exists(volume):
        if _read_volume_provenance(volume) != expected:
            raise ReconcileError(f"existing commit-named scripts volume has provenance drift: {volume}")
        return volume

    _docker("volume", "create", volume, capture=True)
    scripts = (repo / "scripts").resolve()
    payload = json.dumps(expected, sort_keys=True)
    code = "\n".join(
        [
            "import pathlib,shutil,sys",
            "src=pathlib.Path('/source')",
            "dst=pathlib.Path('/sim')",
            "if not src.is_dir(): raise SystemExit('source scripts directory missing')",
            "if any(dst.iterdir()): raise SystemExit('new scripts volume is not empty')",
            "for child in src.iterdir():",
            "    target=dst/child.name",
            "    if child.is_dir(): shutil.copytree(child,target,symlinks=True)",
            "    else: shutil.copy2(child,target,follow_symlinks=False)",
            f"(dst/'{PROVENANCE_FILE}').write_text({payload!r}+'\\n',encoding='utf-8')",
        ]
    )
    result = _docker(
        "run",
        "--rm",
        "--platform",
        "linux/arm/v7",
        "--volume",
        f"{scripts}:/source:ro",
        "--volume",
        f"{volume}:/sim",
        ARM_IMAGE,
        "python3",
        "-c",
        code,
        capture=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        _docker("volume", "rm", "-f", volume, capture=True, check=False)
        raise ReconcileError(f"cannot stage exact scripts tree into {volume}: {result.stderr.strip()}")
    if _read_volume_provenance(volume) != expected:
        _docker("volume", "rm", "-f", volume, capture=True, check=False)
        raise ReconcileError("new scripts volume failed provenance verification")
    return volume


def _inspect_container() -> dict[str, Any]:
    result = _docker("inspect", CONTAINER, capture=True, check=False)
    if result.returncode != 0:
        raise ReconcileError(
            "canonical z2like-demo QEMU container is absent; initial target activation remains an operator action"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReconcileError("Docker returned invalid container inspection JSON") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ReconcileError("Docker returned invalid canonical container inspection data")
    return payload[0]


def _mount_map(inspect: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mounts = inspect.get("Mounts")
    if not isinstance(mounts, list):
        raise ReconcileError("canonical QEMU container mount metadata is unavailable")
    mapped: dict[str, dict[str, Any]] = {}
    for item in mounts:
        if isinstance(item, dict) and isinstance(item.get("Destination"), str):
            mapped[item["Destination"]] = item
    return mapped


def _require_safe_existing_container(inspect: dict[str, Any]) -> str | None:
    bindings = ((inspect.get("HostConfig") or {}).get("PortBindings")) or {}
    if bindings:
        raise ReconcileError("canonical QEMU container publishes host ports; refusing automated replacement")
    networks = ((inspect.get("NetworkSettings") or {}).get("Networks")) or {}
    network = networks.get(NETWORK) if isinstance(networks, dict) else None
    if not isinstance(network, dict) or network.get("IPAddress") != PPU_IP:
        raise ReconcileError("canonical QEMU container network/IP drift; refusing automated replacement")
    mounts = _mount_map(inspect)
    for destination, expected_name in DURABLE_MOUNTS.items():
        item = mounts.get(destination)
        if not isinstance(item, dict) or item.get("Type") != "volume" or item.get("Name") != expected_name:
            raise ReconcileError(
                f"durable mount drift at {destination}; refusing automated container replacement"
            )
    scripts = mounts.get("/sim")
    if not isinstance(scripts, dict):
        raise ReconcileError("canonical QEMU container has no /sim control-plane mount")
    if scripts.get("Type") == "volume" and isinstance(scripts.get("Name"), str):
        return str(scripts["Name"])
    if scripts.get("Type") == "bind":
        return None
    raise ReconcileError("canonical QEMU /sim mount is neither a managed volume nor legacy bind mount")


def _wait_bootstrap(timeout_s: float = 30.0) -> None:
    code = (
        "import json,urllib.request;"
        "p=json.load(urllib.request.urlopen('http://127.0.0.1:18081/v1/health',timeout=2));"
        "assert p.get('ok') is True and p.get('service')=='plasma-ppu-bootstrap'"
    )
    deadline = time.monotonic() + timeout_s
    last = "no probe"
    while time.monotonic() < deadline:
        result = _docker("exec", CONTAINER, "python3", "-c", code, capture=True, check=False, timeout=10)
        if result.returncode == 0:
            return
        last = (result.stderr or result.stdout).strip()
        time.sleep(0.25)
    raise ReconcileError(f"commit-pinned QEMU Bootstrap did not become ready: {last}")


def _create_container(scripts_volume: str) -> None:
    argv = [
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--restart",
        "unless-stopped",
        "--platform",
        "linux/arm/v7",
        "--network",
        NETWORK,
        "--ip",
        PPU_IP,
        "--env",
        f"{TARGET_MARKER}=1",
        "--volume",
        f"{scripts_volume}:/sim:ro",
    ]
    for destination, volume in DURABLE_MOUNTS.items():
        argv.extend(["--volume", f"{volume}:{destination}"])
    argv.extend([ARM_IMAGE, "python3", "/sim/z2like-demo-qemu-target.py"])
    _docker(*argv, capture=True, timeout=120)


def reconcile(repo: Path, expected_commit: str) -> dict[str, Any]:
    commit, scripts_tree = _repo_identity(repo, expected_commit.lower())
    scripts_volume = _stage_scripts(repo, commit, scripts_tree)
    current = _inspect_container()
    previous_scripts_volume = _require_safe_existing_container(current)
    expected_provenance = _provenance(commit, scripts_tree)

    if previous_scripts_volume == scripts_volume:
        if _read_volume_provenance(scripts_volume) != expected_provenance:
            raise ReconcileError("active scripts volume provenance drifted")
        if not ((current.get("State") or {}).get("Running")):
            _docker("start", CONTAINER, capture=True)
        _wait_bootstrap()
        return {
            "result": "PASS",
            "source_commit": commit,
            "scripts_tree_sha": scripts_tree,
            "scripts_volume": scripts_volume,
            "container_recreated": False,
            "legacy_bind_mount_retired": False,
            "durable_state_preserved": True,
        }

    backup = f"{CONTAINER}-rollback-{commit[:12]}"
    if _docker("inspect", backup, capture=True, check=False).returncode == 0:
        raise ReconcileError(f"rollback container name already exists: {backup}")
    was_running = bool((current.get("State") or {}).get("Running"))
    if was_running:
        _docker("stop", "--time", "10", CONTAINER, capture=True, timeout=30)
    _docker("rename", CONTAINER, backup, capture=True)
    try:
        _create_container(scripts_volume)
        _wait_bootstrap()
        active = _inspect_container()
        active_scripts = _require_safe_existing_container(active)
        if active_scripts != scripts_volume:
            raise ReconcileError("recreated QEMU container did not bind the accepted scripts volume")
        if _read_volume_provenance(scripts_volume) != expected_provenance:
            raise ReconcileError("recreated QEMU container scripts provenance mismatch")
    except Exception:
        _docker("rm", "-f", CONTAINER, capture=True, check=False)
        _docker("rename", backup, CONTAINER, capture=True, check=False)
        if was_running:
            _docker("start", CONTAINER, capture=True, check=False)
        raise
    _docker("rm", backup, capture=True, timeout=30)
    return {
        "result": "PASS",
        "source_commit": commit,
        "scripts_tree_sha": scripts_tree,
        "scripts_volume": scripts_volume,
        "previous_scripts_volume": previous_scripts_volume,
        "container_recreated": True,
        "legacy_bind_mount_retired": previous_scripts_volume is None,
        "durable_state_preserved": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile z2like-demo QEMU control-plane scripts to the exact accepted commit"
    )
    parser.add_argument("--expected-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    try:
        result = reconcile(repo, args.expected_commit.lower())
    except ReconcileError as exc:
        print(f"z2like-demo-qemu-control-plane: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
