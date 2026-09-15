#!/usr/bin/env python3
"""Build a canonical Z2 PS kit for the SWPC/QEMU z2like-demo simulation.

The PPU runtime/release is the real canonical ARMv7 package. The Plasma-owned
Python artifact is an explicit simulation-only integrity fixture because QEMU
uses the container's ARMv7 Python interpreter and does not qualify the physical
Z2 Python installation contract.
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
from pathlib import Path
from typing import Sequence


class BuildError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(argv: Sequence[str], *, cwd: Path) -> None:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.stdout:
        print(completed.stdout, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise BuildError(f"command failed with exit {completed.returncode}: {' '.join(argv)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sidecar(path: Path) -> Path:
    sidecar = Path(f"{path}.sha256")
    sidecar.write_text(f"{_sha256(path)}  {path.name}\n", encoding="utf-8")
    return sidecar


def _require_clean_source(repo: Path) -> str:
    if not (repo / ".git").is_dir():
        raise BuildError(f"repository metadata is missing: {repo}")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if status:
        raise BuildError("repository must be clean before building the z2like-demo kit")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def _product_version(repo: Path) -> str:
    payload = json.loads((repo / "release/product.json").read_text(encoding="utf-8"))
    version = payload.get("product_version")
    if not isinstance(version, str) or not version:
        raise BuildError("release/product.json does not contain product_version")
    return version


def _copy(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise BuildError(f"required kit input is missing: {src}")
    shutil.copy2(src, dst)


def build(output_dir: Path) -> dict[str, str]:
    repo = _repo_root()
    sha = _require_clean_source(repo)
    identity = f"{_product_version(repo)}-{sha[:12]}"
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime = output_dir / "plasma-ppu-runtime"
    release = output_dir / "plasma-ppu-release"
    kit_root = output_dir / f"plasma-z2-ps-kit-{identity}"
    for path in (runtime, release, kit_root):
        if path.exists():
            shutil.rmtree(path)

    python = os.environ.get("PLASMA_Z2LIKE_DEMO_BUILD_PYTHON") or "python3"
    _run([python, "scripts/ppu-runtime.py", "build", "--output-dir", str(runtime)], cwd=repo)
    _run([python, "scripts/ppu-runtime.py", "validate", str(runtime)], cwd=repo)
    _run(
        [
            python,
            "scripts/ppu-release.py",
            "--runtime-dir",
            str(runtime),
            "--output-dir",
            str(release),
            "--git-sha",
            sha,
        ],
        cwd=repo,
    )

    ppu = release / f"plasma-ppu-{identity}-linux-armv7l.tar.gz"
    ppu_sidecar = Path(f"{ppu}.sha256")
    if not ppu.is_file() or not ppu_sidecar.is_file():
        raise BuildError(f"canonical PPU release was not produced: {ppu}")
    _run(
        [
            python,
            "scripts/ppu-z2-installer.py",
            "verify",
            "--release-artifact",
            str(ppu),
            "--sidecar",
            str(ppu_sidecar),
        ],
        cwd=repo,
    )

    scripts_dir = kit_root / "scripts"
    artifacts_dir = kit_root / "artifacts"
    docs_dir = kit_root / "docs"
    scripts_dir.mkdir(parents=True)
    artifacts_dir.mkdir()
    docs_dir.mkdir()

    for name in (
        "plasmactl",
        "plasmactl-z2-ps",
        "ppu-bootstrap-deployment.py",
        "ppu-z2-installer.py",
        "ppu-z2-installer-core.py",
        "z2-python-runtime.py",
        "z2like-demo-qemu-installer.py",
    ):
        _copy(repo / "scripts" / name, scripts_dir / name)
    _copy(ppu, artifacts_dir / ppu.name)
    _copy(ppu_sidecar, artifacts_dir / ppu_sidecar.name)
    _copy(repo / "docs/deployment/z2-ps-installer.md", docs_dir / "README.md")

    fixture_root = output_dir / "python-fixture"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    fixture_root.mkdir()
    (fixture_root / "BOUNDARY.txt").write_text(
        "simulation-only Python artifact fixture; never production-qualified\n",
        encoding="utf-8",
    )
    python_artifact = artifacts_dir / "plasma-python-3.12.13-linux-armv7l.tar.gz"
    with tarfile.open(python_artifact, "w:gz") as archive:
        archive.add(fixture_root / "BOUNDARY.txt", arcname="BOUNDARY.txt")
    _write_sidecar(python_artifact)

    for name in (
        "plasmactl",
        "plasmactl-z2-ps",
        "ppu-bootstrap-deployment.py",
        "ppu-z2-installer.py",
        "z2-python-runtime.py",
        "z2like-demo-qemu-installer.py",
    ):
        (scripts_dir / name).chmod(0o755)

    manifest_lines: list[str] = []
    for root_name in ("scripts", "artifacts", "docs"):
        for path in sorted((kit_root / root_name).rglob("*")):
            if path.is_file():
                manifest_lines.append(f"{_sha256(path)}  {path.relative_to(kit_root).as_posix()}")
    (kit_root / "SHA256SUMS").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    kit = output_dir / f"plasma-z2-ps-kit-{identity}.tar.gz"
    if kit.exists():
        kit.unlink()
    with tarfile.open(kit, "w:gz") as archive:
        archive.add(kit_root, arcname=kit_root.name)
    sidecar = _write_sidecar(kit)

    return {
        "result": "PASS",
        "identity": identity,
        "git_sha": sha,
        "kit": str(kit),
        "sidecar": str(sidecar),
        "python_artifact_execution": "not_executed_in_qemu-simulation",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the SWPC/QEMU z2like-demo Z2 PS kit")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build(args.output_dir)
    except (BuildError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"z2like-demo-qemu-build-kit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
