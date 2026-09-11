#!/usr/bin/env python3
"""Verify and consume one canonical Plasma Z2 PS release kit.

The factory Bootstrap deals in one product deployment artifact: the existing
``plasma-z2-ps-kit-<release-id>.tar.gz``.  It must not understand the internal
Plasma Runtime filesystem beyond the kit contract.  After independent outer and
inner integrity verification it delegates installation to the kit-local
``plasmactl z2-ps`` tooling.

SHA-256 proves integrity, not publisher authenticity.  Production publisher
signature verification is a separate hardening requirement and this tool does
not claim it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

MAX_KIT_FILES = 20_000
MAX_KIT_UNCOMPRESSED_BYTES = 3 * 1024 * 1024 * 1024
KIT_PREFIX = "plasma-z2-ps-kit-"


class BootstrapKitError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedKit:
    root: Path
    release_id: str
    kit_sha256: str
    ppu_artifact: Path
    ppu_sidecar: Path
    python_artifact: Path
    python_sidecar: Path
    plasmactl: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sidecar(artifact: Path, sidecar: Path) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise BootstrapKitError(f"cannot read kit SHA-256 sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != artifact.name:
        raise BootstrapKitError("kit SHA-256 sidecar does not identify the kit artifact")
    expected = fields[0].lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise BootstrapKitError("kit SHA-256 sidecar digest is invalid")
    actual = _sha256(artifact)
    if actual != expected:
        raise BootstrapKitError("kit SHA-256 does not match detached sidecar")
    return actual


def _safe_member(name: str) -> PurePosixPath:
    canonical = name.rstrip("/")
    if not canonical or "\\" in canonical or canonical.startswith("/"):
        raise BootstrapKitError(f"unsafe kit archive path: {name!r}")
    pure = PurePosixPath(canonical)
    if ".." in pure.parts or pure.as_posix() != canonical:
        raise BootstrapKitError(f"non-canonical kit archive path: {name!r}")
    if not pure.parts[0].startswith(KIT_PREFIX) or len(pure.parts[0]) <= len(KIT_PREFIX):
        raise BootstrapKitError("kit archive root is not canonical")
    return pure


def _extract(artifact: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    roots: set[str] = set()
    seen: set[str] = set()
    files = 0
    expanded = 0
    try:
        archive = tarfile.open(artifact, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise BootstrapKitError(f"cannot open Z2 PS kit: {exc}") from exc
    with archive:
        for member in archive.getmembers():
            pure = _safe_member(member.name)
            roots.add(pure.parts[0])
            canonical = pure.as_posix()
            if canonical in seen:
                raise BootstrapKitError(f"duplicate kit archive member: {canonical}")
            seen.add(canonical)
            target = destination / Path(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            if not member.isfile():
                raise BootstrapKitError(f"non-regular kit archive member is forbidden: {canonical}")
            files += 1
            expanded += int(member.size)
            if files > MAX_KIT_FILES or expanded > MAX_KIT_UNCOMPRESSED_BYTES:
                raise BootstrapKitError("Z2 PS kit exceeds extraction safety limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise BootstrapKitError(f"cannot read kit archive member: {canonical}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod((member.mode & 0o555) | 0o400)
    if len(roots) != 1:
        raise BootstrapKitError("Z2 PS kit must contain exactly one canonical root")
    return destination / next(iter(roots))


def _verify_internal_hashes(root: Path) -> None:
    sums = root / "SHA256SUMS"
    try:
        lines = sums.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BootstrapKitError(f"cannot read kit SHA256SUMS: {exc}") from exc
    expected: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise BootstrapKitError("invalid kit SHA256SUMS entry")
        digest, name = fields
        name = name.lstrip("*").strip()
        pure = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or pure.is_absolute()
            or ".." in pure.parts
            or pure.as_posix() != name
            or name == "SHA256SUMS"
        ):
            raise BootstrapKitError(f"unsafe kit SHA256SUMS path: {name!r}")
        digest = digest.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise BootstrapKitError(f"invalid kit SHA256SUMS digest for {name!r}")
        if name in expected:
            raise BootstrapKitError(f"duplicate kit SHA256SUMS entry: {name}")
        expected[name] = digest
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(expected) != actual_files:
        raise BootstrapKitError("kit file set does not exactly match SHA256SUMS")
    for name, expected_digest in expected.items():
        if _sha256(root / name) != expected_digest:
            raise BootstrapKitError(f"kit internal SHA-256 mismatch: {name}")


def _single_pair(artifacts: Path, pattern: str, label: str) -> tuple[Path, Path]:
    candidates = sorted(
        path for path in artifacts.glob(pattern) if path.is_file() and not path.name.endswith(".sha256")
    )
    if len(candidates) != 1:
        raise BootstrapKitError(f"kit must contain exactly one {label} artifact")
    artifact = candidates[0]
    sidecar = Path(str(artifact) + ".sha256")
    if not sidecar.is_file():
        raise BootstrapKitError(f"kit {label} sidecar is missing")
    return artifact, sidecar


def verify_kit(artifact: Path, *, sidecar: Path, extract_to: Path) -> VerifiedKit:
    artifact = artifact.resolve()
    sidecar = sidecar.resolve()
    if not artifact.is_file() or not sidecar.is_file():
        raise BootstrapKitError("Z2 PS kit artifact and sidecar are required")
    digest = _verify_sidecar(artifact, sidecar)
    root = _extract(artifact, extract_to)
    _verify_internal_hashes(root)
    release_id = root.name[len(KIT_PREFIX) :]
    if not release_id or "/" in release_id or "\\" in release_id:
        raise BootstrapKitError("Z2 PS kit release identity is invalid")
    scripts = root / "scripts"
    artifacts = root / "artifacts"
    plasmactl = scripts / "plasmactl"
    required_scripts = [
        plasmactl,
        scripts / "plasmactl-z2-ps",
        scripts / "ppu-bootstrap-deployment.py",
        scripts / "ppu-z2-installer.py",
        scripts / "z2-python-runtime.py",
    ]
    if not all(path.is_file() for path in required_scripts):
        raise BootstrapKitError("Z2 PS kit is missing required deployment tooling")
    ppu_artifact, ppu_sidecar = _single_pair(artifacts, "plasma-ppu-*-linux-armv7l.tar.gz", "PPU")
    python_artifact, python_sidecar = _single_pair(
        artifacts, "plasma-python-*-linux-armv7l.tar.gz", "Plasma Python"
    )
    return VerifiedKit(
        root=root,
        release_id=release_id,
        kit_sha256=digest,
        ppu_artifact=ppu_artifact,
        ppu_sidecar=ppu_sidecar,
        python_artifact=python_artifact,
        python_sidecar=python_sidecar,
        plasmactl=plasmactl,
    )


def install_verified_kit(
    kit: VerifiedKit,
    *,
    gateway_host: str,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    product_root: Path = Path("/opt/plasma"),
    runner=subprocess.run,
) -> dict[str, object]:
    installed = product_root / "install" / "last-install.json"
    command = "deploy" if installed.is_file() else "install"
    argv = [
        "bash",
        str(kit.plasmactl),
        command,
        "z2-ps",
        "--release-artifact",
        str(kit.ppu_artifact),
        "--release-sidecar",
        str(kit.ppu_sidecar),
        "--gateway-host",
        gateway_host,
        "--ppu-id",
        ppu_id,
        "--facility-id",
        facility_id,
        "--display-name",
        display_name,
    ]
    if command == "install":
        argv.extend(
            [
                "--python-artifact",
                str(kit.python_artifact),
                "--python-sidecar",
                str(kit.python_sidecar),
            ]
        )
    environment = os.environ.copy()
    environment["PLASMA_Z2_PRODUCT_ROOT"] = str(product_root)
    try:
        completed = runner(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=900,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootstrapKitError(f"kit deployment command failed to execute: {exc}") from exc
    if completed.returncode != 0:
        tail = completed.stdout[-8000:] if completed.stdout else ""
        raise BootstrapKitError(f"kit deployment failed with exit {completed.returncode}: {tail}")
    try:
        evidence = json.loads(installed.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapKitError(f"kit deployment did not produce trustworthy install evidence: {exc}") from exc
    if not isinstance(evidence, dict) or evidence.get("result") != "PASS":
        raise BootstrapKitError("kit deployment evidence is not PASS")
    if evidence.get("release_id") != kit.release_id:
        raise BootstrapKitError("installed release identity does not match the verified kit")
    return {
        "schema_version": 1,
        "result": "PASS",
        "operation": command,
        "kit_release_id": kit.release_id,
        "kit_sha256": kit.kit_sha256,
        "install_evidence": evidence,
        "publisher_authenticity": "not_yet_qualified",
        "fpga_update": False,
    }


def deploy_kit(
    artifact: Path,
    *,
    sidecar: Path,
    gateway_host: str,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    product_root: Path = Path("/opt/plasma"),
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="plasma-bootstrap-kit-") as temporary:
        kit = verify_kit(artifact, sidecar=sidecar, extract_to=Path(temporary) / "kit")
        return install_verified_kit(
            kit,
            gateway_host=gateway_host,
            ppu_id=ppu_id,
            facility_id=facility_id,
            display_name=display_name,
            product_root=product_root,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or install one canonical Plasma Z2 PS release kit")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("kit", type=Path)
    verify.add_argument("--sidecar", type=Path, required=True)

    deploy = sub.add_parser("deploy")
    deploy.add_argument("kit", type=Path)
    deploy.add_argument("--sidecar", type=Path, required=True)
    deploy.add_argument("--gateway-host", required=True)
    deploy.add_argument("--ppu-id", required=True)
    deploy.add_argument("--facility-id", required=True)
    deploy.add_argument("--display-name", default="Plasma PPU")
    deploy.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            with tempfile.TemporaryDirectory(prefix="plasma-bootstrap-kit-verify-") as temporary:
                kit = verify_kit(args.kit, sidecar=args.sidecar, extract_to=Path(temporary) / "kit")
                print(
                    json.dumps(
                        {
                            "result": "PASS",
                            "release_id": kit.release_id,
                            "kit_sha256": kit.kit_sha256,
                            "publisher_authenticity": "not_yet_qualified",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
        result = deploy_kit(
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
    except BootstrapKitError as exc:
        print(f"ppu-bootstrap-kit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
