#!/usr/bin/env python3
"""Simulation-only consumer for a canonical Plasma Z2 PS kit.

The outer kit format, internal SHA256SUMS, individual PPU/Python sidecars and
production PPU release are verified. Activation uses the kit-local durable
``ppu-bootstrap-deployment.py``, retained installer core, and QEMU simulation
installer adapter.  The accepted kit therefore pins all deployment logic that
can mutate the simulated target; a mutable host ``/sim`` checkout is not trusted
as the installer source.

This script intentionally does NOT install or qualify the kit's Plasma-owned
Python artifact; the ARMv7 QEMU container interpreter is used instead. That
boundary is explicit in returned evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_MARKER = "PLASMA_Z2LIKE_DEMO_QEMU_TARGET"
CORE_OVERRIDE = "PLASMA_Z2LIKE_DEMO_INSTALLER_CORE"


class QEMUSimulationKitError(RuntimeError):
    pass


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise QEMUSimulationKitError(f"cannot load deployment dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_detached(artifact: Path, sidecar: Path, label: str) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise QEMUSimulationKitError(f"cannot read {label} SHA-256 sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != artifact.name:
        raise QEMUSimulationKitError(f"{label} SHA-256 sidecar does not identify its artifact")
    expected = fields[0].lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise QEMUSimulationKitError(f"{label} SHA-256 sidecar digest is invalid")
    actual = _sha256(artifact)
    if actual != expected:
        raise QEMUSimulationKitError(f"{label} SHA-256 mismatch")
    return actual


def _require_simulation_target() -> None:
    if os.environ.get(TARGET_MARKER) != "1":
        raise QEMUSimulationKitError("QEMU simulation kit tool requires explicit target marker")
    if platform.system() != "Linux" or platform.machine().lower() not in {"armv7", "armv7l"}:
        raise QEMUSimulationKitError(
            f"QEMU simulation kit tool requires Linux ARMv7, got {platform.system()} {platform.machine()}"
        )


def _validated_deployment_release_id(payload: object) -> str:
    if not isinstance(payload, dict) or payload.get("result") != "PASS":
        raise QEMUSimulationKitError("deployment coordinator did not return PASS evidence")
    transaction = payload.get("transaction")
    installer_evidence = payload.get("installer_evidence")
    if not isinstance(transaction, dict) or not isinstance(installer_evidence, dict):
        raise QEMUSimulationKitError("deployment coordinator evidence shape is invalid")
    transaction_release = transaction.get("release_id")
    installer_release = installer_evidence.get("release_id")
    if not isinstance(transaction_release, str) or not transaction_release:
        raise QEMUSimulationKitError("deployment transaction release identity is missing")
    if installer_release != transaction_release:
        raise QEMUSimulationKitError("installer and deployment transaction release identities disagree")
    return transaction_release


def deploy(
    kit_artifact: Path,
    *,
    sidecar: Path,
    gateway_host: str,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    product_root: Path,
) -> dict[str, object]:
    _require_simulation_target()
    kit_module = _load(SCRIPT_DIR / "ppu-bootstrap-kit.py", "plasma_z2like_demo_kit_format")
    with tempfile.TemporaryDirectory(prefix="plasma-z2like-demo-kit-") as temporary:
        verified = kit_module.verify_kit(
            kit_artifact,
            sidecar=sidecar,
            extract_to=Path(temporary) / "kit",
        )
        ppu_sha = _verify_detached(verified.ppu_artifact, verified.ppu_sidecar, "PPU artifact")
        python_sha = _verify_detached(
            verified.python_artifact,
            verified.python_sidecar,
            "Plasma Python artifact",
        )
        kit_scripts = verified.root / "scripts"
        coordinator = kit_scripts / "ppu-bootstrap-deployment.py"
        installer_core = kit_scripts / "ppu-z2-installer-core.py"
        installer = kit_scripts / "z2like-demo-qemu-installer.py"
        for path in (coordinator, installer_core, installer):
            if not path.is_file():
                raise QEMUSimulationKitError(f"QEMU simulation deployment tooling is incomplete: {path}")
        argv = [
            sys.executable,
            str(coordinator),
            "--installer",
            str(installer),
            "--bootstrap-state-root",
            "/var/lib/plasma-bootstrap",
            "--product-root",
            str(product_root),
            "--config-root",
            "/etc/plasma",
            "--runtime-state-root",
            "/var/lib/plasma",
            "--log-root",
            "/var/log/plasma",
            "--systemd-root",
            "/var/lib/plasma/z2like-demo-no-systemd",
            "deploy",
            "--release-artifact",
            str(verified.ppu_artifact),
            "--sidecar",
            str(verified.ppu_sidecar),
            "--plasma-python",
            sys.executable,
            "--gateway-host",
            gateway_host,
            "--ppu-id",
            ppu_id,
            "--facility-id",
            facility_id,
            "--display-name",
            display_name,
        ]
        completed = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=900,
            env={
                **os.environ,
                TARGET_MARKER: "1",
                CORE_OVERRIDE: str(installer_core),
            },
        )
        if completed.returncode != 0:
            tail = completed.stdout[-8000:] if completed.stdout else ""
            raise QEMUSimulationKitError(
                f"QEMU simulation deployment coordinator failed with exit {completed.returncode}: {tail}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise QEMUSimulationKitError("deployment coordinator returned invalid JSON") from exc
        deployed_release_id = _validated_deployment_release_id(payload)
        if deployed_release_id != verified.release_id:
            raise QEMUSimulationKitError("deployed release identity does not match verified kit identity")
        return {
            "schema_version": 1,
            "result": "PASS",
            "simulation": True,
            "evidence_level": "swpc-qemu-armv7-z2like-demo",
            "kit_release_id": verified.release_id,
            "kit_sha256": verified.kit_sha256,
            "ppu_artifact_sha256": ppu_sha,
            "python_artifact_sha256": python_sha,
            "python_artifact_execution": "not_executed_in_qemu-simulation",
            "kit_local_deployment_coordinator": str(coordinator),
            "kit_local_installer_core": str(installer_core),
            "kit_local_simulation_installer": str(installer),
            "deployment": payload,
            "publisher_authenticity": "not_yet_qualified",
            "fpga_update": False,
            "not_claimed": [
                "PYNQ-Z2 hardware",
                "Plasma-owned Python installation",
                "systemd/DAC service topology",
                "reboot persistence",
                "PS-to-PL",
                "Site electrical I/O",
                "target power",
                "real IC programming",
            ],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy a canonical Z2 kit into the SWPC/QEMU Z2-like demo")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("kit", type=Path)
    verify.add_argument("--sidecar", type=Path, required=True)
    deploy_parser = sub.add_parser("deploy")
    deploy_parser.add_argument("kit", type=Path)
    deploy_parser.add_argument("--sidecar", type=Path, required=True)
    deploy_parser.add_argument("--gateway-host", required=True)
    deploy_parser.add_argument("--ppu-id", required=True)
    deploy_parser.add_argument("--facility-id", required=True)
    deploy_parser.add_argument("--display-name", default="Plasma QEMU Z2 Simulation")
    deploy_parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _require_simulation_target()
        kit_module = _load(SCRIPT_DIR / "ppu-bootstrap-kit.py", "plasma_z2like_demo_kit_format_cli")
        if args.command == "verify":
            with tempfile.TemporaryDirectory(prefix="plasma-z2like-demo-kit-verify-") as temporary:
                verified = kit_module.verify_kit(
                    args.kit,
                    sidecar=args.sidecar,
                    extract_to=Path(temporary) / "kit",
                )
                _verify_detached(verified.ppu_artifact, verified.ppu_sidecar, "PPU artifact")
                _verify_detached(verified.python_artifact, verified.python_sidecar, "Plasma Python artifact")
                print(
                    json.dumps(
                        {
                            "result": "PASS",
                            "simulation": True,
                            "release_id": verified.release_id,
                            "kit_sha256": verified.kit_sha256,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
        result = deploy(
            args.kit,
            sidecar=args.sidecar,
            gateway_host=args.gateway_host,
            ppu_id=args.ppu_id,
            facility_id=args.facility_id,
            display_name=args.display_name,
            product_root=args.product_root,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, subprocess.SubprocessError, QEMUSimulationKitError) as exc:
        print(f"z2like-demo-qemu-kit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
