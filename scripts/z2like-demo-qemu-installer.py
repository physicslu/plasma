#!/usr/bin/env python3
"""Simulation-only installer adapter for the SWPC QEMU ARMv7 Z2-like demo.

This module intentionally implements the installer surface consumed by
``ppu-bootstrap-deployment.py`` while reusing the production Z2 release verifier
and immutable release copier.  It replaces only the physical-Z2/systemd
activation layer with a userspace activation handshake owned by
``z2like-demo-qemu-target.py``.

It is NOT a production Z2 installer and must never be used to claim PYNQ-Z2,
systemd/DAC, PS-to-PL, Site electrical, target-power, or real-IC qualification.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_MARKER = "PLASMA_Z2LIKE_DEMO_QEMU_TARGET"
EVIDENCE_LEVEL = "swpc-qemu-armv7-z2like-demo"
ACTIVATION_MARKER = "z2like-demo-activation.json"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load simulation dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_core = _load(SCRIPT_DIR / "ppu-z2-installer-core.py", "plasma_z2like_demo_installer_core")

Z2InstallerError = _core.Z2InstallerError
InstallPaths = _core.InstallPaths
VerifiedRelease = _core.VerifiedRelease
PythonRuntime = _core.PythonRuntime
verify_release = _core.verify_release
_copy_release = _core._copy_release
_previous_current = _core._previous_current


def _require_target_baseline() -> None:
    if os.environ.get(TARGET_MARKER) != "1":
        raise Z2InstallerError("QEMU demo installer requires explicit simulation target marker")
    if platform.system() != "Linux":
        raise Z2InstallerError("QEMU demo installer requires Linux")
    machine = platform.machine().lower()
    if machine not in {"armv7", "armv7l"}:
        raise Z2InstallerError(f"QEMU demo installer requires ARMv7 execution, got {machine}")
    if os.geteuid() != 0:
        raise Z2InstallerError("QEMU demo installer requires container-root privileges")


def validate_plasma_python(path: Path, *, product_root: Path = Path("/opt/plasma")) -> PythonRuntime:
    """Validate the QEMU container interpreter without claiming product Python install.

    Real ``z2-ps`` requires a Plasma-owned interpreter below ``/opt/plasma/python``.
    The QEMU userspace simulation intentionally uses the container interpreter so
    it can exercise the ARMv7 runtime/control path without pretending to validate
    the physical-Z2 Python installation contract.
    """

    del product_root
    resolved = path.resolve()
    if not resolved.is_absolute() or not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise Z2InstallerError(f"QEMU simulation Python is not executable: {resolved}")
    code = (
        "import json,platform,sys;"
        "print(json.dumps({'version':list(sys.version_info[:3]),"
        "'releaselevel':sys.version_info.releaselevel,'machine':platform.machine(),"
        "'executable':sys.executable}))"
    )
    completed = subprocess.run(
        [str(resolved), "-c", code],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise Z2InstallerError(f"QEMU simulation Python probe failed: {completed.stdout.strip()}")
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise Z2InstallerError("QEMU simulation Python probe returned invalid output") from exc
    version = payload.get("version")
    if not isinstance(version, list) or len(version) < 3 or not all(isinstance(v, int) for v in version[:3]):
        raise Z2InstallerError("QEMU simulation Python probe returned invalid version")
    version_tuple = tuple(version[:3])
    if version_tuple < (3, 11, 0):
        raise Z2InstallerError("QEMU simulation Python must be >=3.11")
    if payload.get("releaselevel") != "final":
        raise Z2InstallerError("QEMU simulation Python must be a final release")
    machine = str(payload.get("machine", "")).lower()
    if machine not in {"armv7", "armv7l"}:
        raise Z2InstallerError(f"QEMU simulation Python is not ARMv7: {machine!r}")
    reported = Path(str(payload.get("executable", ""))).resolve()
    if reported != resolved:
        raise Z2InstallerError(
            f"QEMU simulation Python executable drift: requested {resolved}, reported {reported}"
        )
    return PythonRuntime(
        path=resolved,
        version=".".join(str(v) for v in version_tuple),
        architecture=machine,
        releaselevel="final",
    )


def _atomic_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(text, encoding="utf-8")
    temporary.chmod(mode)
    os.replace(temporary, path)


def _atomic_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(link.name + ".new")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    os.symlink(str(target), str(temporary))
    os.replace(temporary, link)


def _simulation_config(
    *,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    state_root: Path,
    log_root: Path,
) -> str:
    for label, value in (("ppu-id", ppu_id), ("facility-id", facility_id), ("display-name", display_name)):
        if not value or "\n" in value or "\r" in value:
            raise Z2InstallerError(f"{label} must be a non-empty single-line value")
    return "\n".join(
        [
            "ppu:",
            f"  id: {json.dumps(ppu_id)}",
            f"  facility_id: {json.dumps(facility_id)}",
            '  model: "QEMU ARMv7 Z2 Simulation"',
            f"  display_name: {json.dumps(display_name)}",
            "",
            "server:",
            "  host: 127.0.0.1",
            "  port: 9900",
            "  max_supported_sites: 8",
            "  max_concurrent_jobs: 1",
            "  max_queue_depth_per_site: 16",
            f"  output_root: {state_root / 'output'}",
            f"  log_root: {log_root}",
            "  max_metadata_bytes: 65536",
            "  max_map_bytes: 1048576",
            "  max_binary_bytes: 67108864",
            "",
            "sites: []",
            "",
        ]
    )


def _health_ready(gateway_host: str, *, deadline_s: float = 40.0) -> Mapping[str, object]:
    return _core._health_ready(gateway_host, deadline_s=deadline_s)


def _restore_current(current: Path, previous: Path | None) -> None:
    if previous is None:
        try:
            current.unlink()
        except FileNotFoundError:
            pass
    else:
        _atomic_symlink(current, previous)


def install_release(
    verified: VerifiedRelease,
    *,
    python_runtime: PythonRuntime,
    gateway_host: str,
    paths: InstallPaths,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    health_check=_health_ready,
    **_: object,
) -> dict[str, object]:
    """Activate one verified ARMv7 release through the userspace supervisor."""

    _require_target_baseline()
    gateway_host = _core._validate_gateway_host(gateway_host)
    release_target = paths.releases_root / verified.release_id
    previous = _previous_current(paths.current)
    config_path = paths.config_root / "ppu.yaml"
    previous_config = config_path.read_bytes() if config_path.is_file() else None

    paths.releases_root.mkdir(parents=True, exist_ok=True)
    paths.install_root.mkdir(parents=True, exist_ok=True)
    paths.config_root.mkdir(parents=True, exist_ok=True)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    paths.log_root.mkdir(parents=True, exist_ok=True)
    for directory in (paths.state_root / "output", paths.state_root / "gateway-output"):
        directory.mkdir(parents=True, exist_ok=True)
    _copy_release(verified, release_target)

    if previous_config is None:
        _atomic_text(
            config_path,
            _simulation_config(
                ppu_id=ppu_id,
                facility_id=facility_id,
                display_name=display_name,
                state_root=paths.state_root,
                log_root=paths.log_root,
            ),
            0o640,
        )

    _atomic_symlink(paths.current, release_target)
    activation_marker = paths.state_root / ACTIVATION_MARKER
    _atomic_text(
        activation_marker,
        json.dumps(
            {
                "schema_version": 1,
                "release_id": verified.release_id,
                "requested_at_epoch_s": time.time(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        0o600,
    )

    try:
        readiness = dict(health_check(gateway_host))
    except Exception as activation_exc:
        _restore_current(paths.current, previous)
        if previous_config is None:
            try:
                config_path.unlink()
            except FileNotFoundError:
                pass
        else:
            temporary = config_path.with_name(config_path.name + ".rollback")
            temporary.write_bytes(previous_config)
            temporary.chmod(0o640)
            os.replace(temporary, config_path)
        raise Z2InstallerError(
            f"QEMU userspace activation failed and previous release/configuration was restored: {activation_exc}"
        ) from activation_exc

    evidence = {
        "schema_version": 1,
        "result": "PASS",
        "evidence_level": EVIDENCE_LEVEL,
        "simulation": True,
        "product_version": verified.product_version,
        "git_sha": verified.git_sha,
        "archive_sha256": verified.archive_sha256,
        "release_id": verified.release_id,
        "release_root": str(release_target),
        "current": str(paths.current),
        "plasma_python": {
            "path": str(python_runtime.path),
            "version": python_runtime.version,
            "architecture": python_runtime.architecture,
            "releaselevel": python_runtime.releaselevel,
            "ownership": "qemu-container-runtime-not-product-install",
        },
        "gateway_host": gateway_host,
        "gateway_readiness": {
            "gateway": readiness.get("gateway"),
            "execution": readiness.get("execution"),
        },
        "site_desired_state": {
            "config_path": str(config_path),
            "upgrade_preserves_existing_config": True,
            "runtime_apply_supported": False,
        },
        "activation": {
            "owner": "z2like-demo-qemu-target userspace supervisor",
            "systemd_qualified": False,
        },
        "previous_release": str(previous) if previous is not None else None,
        "hardware_boundary": dict(_core.EXPECTED_HARDWARE_BOUNDARY),
        "not_claimed": [
            "PYNQ-Z2 hardware",
            "Plasma-owned Python installation",
            "systemd/DAC service topology",
            "reboot persistence",
            "PS-to-PL",
            "FPGA execution",
            "Site electrical I/O",
            "target power",
            "real IC programming",
            "physical multi-Site concurrency",
        ],
    }
    _atomic_text(
        paths.install_root / "last-install.json",
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        0o600,
    )
    return evidence
