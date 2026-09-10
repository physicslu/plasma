#!/usr/bin/env python3
"""Derive a qualification-only Z2 kit that deterministically fails readiness.

The output is for controlled Bootstrap rollback HIL only.  The source Z2 kit and
its inner PPU release are verified first.  The derived release keeps the source
Git SHA, receives a distinct SemVer prerelease identity, and replaces only the
PPU process entrypoint with a fixed process that exits immediately.  All inner
and outer SHA-256 manifests/sidecars are rebuilt and the result is verified again.

This tool does not deploy, activate, reboot, modify systemd, access FPGA/Site
hardware, or contact a PPU.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

QUALIFICATION_SUFFIX = "hil.rollback.negative"
FAILURE_EXIT_CODE = 86
QUALIFICATION_MARKER = "QUALIFICATION_ONLY.json"


class HILNegativeError(RuntimeError):
    pass


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HILNegativeError(f"cannot load verifier module: {path}")
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


def _negative_version(version: str) -> str:
    if not version or QUALIFICATION_SUFFIX in version:
        raise HILNegativeError("source product_version is invalid or already qualification-only")
    core, plus, build = version.partition("+")
    if "-" in core:
        negative = f"{core}.{QUALIFICATION_SUFFIX}"
    else:
        negative = f"{core}-{QUALIFICATION_SUFFIX}"
    return negative + (f"+{build}" if plus else "")


def _write_hash_manifest(root: Path) -> None:
    sums = root / "SHA256SUMS"
    sums.unlink(missing_ok=True)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    lines = [f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in files]
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _write_deterministic_tar_gz(root: Path, artifact: Path) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if artifact.exists():
        raise HILNegativeError(f"refusing to overwrite output artifact: {artifact}")
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                archive.add(root, arcname=root.name, recursive=True, filter=_tar_filter)
    sidecar = Path(str(artifact) + ".sha256")
    sidecar.write_text(f"{_sha256(artifact)}  {artifact.name}\n", encoding="utf-8")


def _failure_program() -> str:
    return (
        "from __future__ import annotations\n"
        "import sys\n"
        "sys.stderr.write('PLASMA HIL NEGATIVE: intentional Runtime startup failure\\n')\n"
        f"raise SystemExit({FAILURE_EXIT_CODE})\n"
    )


def _make_owner_writable(path: Path) -> None:
    """Permit mutation only inside the isolated qualification derivation copy."""
    try:
        mode = path.stat().st_mode & 0o777
        path.chmod(mode | 0o200)
    except OSError as exc:
        raise HILNegativeError(f"cannot make qualification derivation file writable: {path}: {exc}") from exc


def _derive_release(
    source_release: Any,
    *,
    destination_parent: Path,
    installer: ModuleType,
) -> tuple[Path, Path, str, dict[str, Any]]:
    source_manifest = dict(source_release.manifest)
    source_version = source_manifest.get("product_version")
    if not isinstance(source_version, str):
        raise HILNegativeError("source release product_version is missing")
    negative_version = _negative_version(source_version)
    git_sha = source_manifest.get("git_sha")
    if not isinstance(git_sha, str):
        raise HILNegativeError("source release git_sha is missing")
    negative_release_id = f"{negative_version}-{git_sha[:12].lower()}"

    root = destination_parent / "plasma-release"
    shutil.copytree(source_release.root, root)
    manifest_path = root / "release.json"
    _make_owner_writable(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["product_version"] = negative_version
    manifest["qualification_only"] = {
        "schema_version": 1,
        "purpose": "bootstrap-automatic-rollback-hil",
        "production_eligible": False,
        "source_release_id": source_release.release_id,
        "failure_mode": "ppu-process-exits-before-gateway-readiness",
        "failure_exit_code": FAILURE_EXIT_CODE,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    app = root / "runtime" / "ppu" / "ppu.pyz"
    if not app.is_file():
        raise HILNegativeError("verified source release is missing ppu/ppu.pyz")
    _make_owner_writable(app)
    app.write_text(_failure_program(), encoding="utf-8")
    app.chmod(0o644)
    _write_hash_manifest(root)

    artifact = destination_parent / f"plasma-ppu-{negative_release_id}-linux-armv7l.tar.gz"
    _write_deterministic_tar_gz(root, artifact)
    sidecar = Path(str(artifact) + ".sha256")

    with tempfile.TemporaryDirectory(prefix="plasma-hil-negative-release-verify-") as temporary:
        verified = installer.verify_release(
            artifact,
            sidecar=sidecar,
            extract_to=Path(temporary) / "release",
        )
        if verified.release_id != negative_release_id:
            raise HILNegativeError("derived PPU release identity failed verification")

    marker = {
        "schema_version": 1,
        "qualification_only": True,
        "purpose": "bootstrap-automatic-rollback-hil",
        "production_eligible": False,
        "source_release_id": source_release.release_id,
        "negative_release_id": negative_release_id,
        "source_git_sha": git_sha.lower(),
        "failure_mode": "ppu-process-exits-before-gateway-readiness",
        "failure_exit_code": FAILURE_EXIT_CODE,
        "expected_result": "activation-readiness-failure-followed-by-automatic-rollback",
    }
    return artifact, sidecar, negative_release_id, marker


def derive_negative_kit(
    source_kit: Path,
    *,
    sidecar: Path,
    output_dir: Path,
    kit_tool_path: Path,
    installer_path: Path,
) -> dict[str, Any]:
    kit_tool = _load(kit_tool_path, "plasma_hil_negative_kit_verifier")
    installer = _load(installer_path, "plasma_hil_negative_release_verifier")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="plasma-hil-negative-") as temporary:
        temp = Path(temporary)
        source = kit_tool.verify_kit(
            source_kit.resolve(),
            sidecar=sidecar.resolve(),
            extract_to=temp / "source-kit",
        )
        source_release = installer.verify_release(
            source.ppu_artifact,
            sidecar=source.ppu_sidecar,
            extract_to=temp / "source-release",
        )
        if source_release.release_id != source.release_id:
            raise HILNegativeError("source kit and inner PPU release identities do not match")

        derived_release_dir = temp / "derived-release"
        derived_release_dir.mkdir()
        negative_ppu, negative_ppu_sidecar, negative_release_id, marker = _derive_release(
            source_release,
            destination_parent=derived_release_dir,
            installer=installer,
        )

        negative_root = temp / f"plasma-z2-ps-kit-{negative_release_id}"
        shutil.copytree(source.root, negative_root)
        artifacts = negative_root / "artifacts"
        source_ppu = artifacts / source.ppu_artifact.name
        source_ppu_sidecar = artifacts / source.ppu_sidecar.name
        source_ppu.unlink()
        source_ppu_sidecar.unlink()
        shutil.copy2(negative_ppu, artifacts / negative_ppu.name)
        shutil.copy2(negative_ppu_sidecar, artifacts / negative_ppu_sidecar.name)
        (negative_root / QUALIFICATION_MARKER).write_text(
            json.dumps(
                {
                    **marker,
                    "source_kit_release_id": source.release_id,
                    "source_kit_sha256": source.kit_sha256,
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        _write_hash_manifest(negative_root)

        output = output_dir / f"plasma-z2-ps-kit-{negative_release_id}.tar.gz"
        _write_deterministic_tar_gz(negative_root, output)
        output_sidecar = Path(str(output) + ".sha256")

        with tempfile.TemporaryDirectory(prefix="plasma-hil-negative-kit-verify-") as verify_temp:
            verified_kit = kit_tool.verify_kit(
                output,
                sidecar=output_sidecar,
                extract_to=Path(verify_temp) / "kit",
            )
            if verified_kit.release_id != negative_release_id:
                raise HILNegativeError("derived Z2 kit identity failed verification")
            verified_release = installer.verify_release(
                verified_kit.ppu_artifact,
                sidecar=verified_kit.ppu_sidecar,
                extract_to=Path(verify_temp) / "release",
            )
            if verified_release.release_id != negative_release_id:
                raise HILNegativeError("derived kit inner PPU release identity failed verification")

    evidence = {
        "schema_version": 1,
        "result": "PASS",
        "qualification_only": True,
        "production_eligible": False,
        "purpose": "bootstrap-automatic-rollback-hil",
        "source_kit": str(source_kit.resolve()),
        "source_kit_sha256": _sha256(source_kit.resolve()),
        "source_release_id": source.release_id,
        "negative_release_id": negative_release_id,
        "negative_kit": str(output),
        "negative_kit_sha256": _sha256(output),
        "negative_kit_sidecar": str(output_sidecar),
        "failure_mode": marker["failure_mode"],
        "failure_exit_code": FAILURE_EXIT_CODE,
        "expected_result": marker["expected_result"],
        "not_performed": [
            "deployment",
            "systemd mutation",
            "reboot",
            "network mutation",
            "FPGA/PL access",
            "Site/power access",
            "real IC programming",
        ],
    }
    evidence_path = output_dir / f"plasma-z2-ps-kit-{negative_release_id}.qualification.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence["evidence"] = str(evidence_path)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build qualification-only Z2 rollback HIL negative kit")
    parser.add_argument("source_kit", type=Path)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--kit-tool",
        type=Path,
        default=Path(__file__).with_name("ppu-bootstrap-kit.py"),
    )
    parser.add_argument(
        "--installer",
        type=Path,
        default=Path(__file__).with_name("ppu-z2-installer.py"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = derive_negative_kit(
            args.source_kit,
            sidecar=args.sidecar,
            output_dir=args.output_dir,
            kit_tool_path=args.kit_tool,
            installer_path=args.installer,
        )
    except (HILNegativeError, OSError, ValueError) as exc:
        print(f"ppu-bootstrap-hil-negative: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
