#!/usr/bin/env python3
"""Build, verify, and install a Plasma-owned ARMv7 Python runtime artifact.

The file format is deliberately independent from the PPU Common Release Format.
PYNQ keeps ownership of System Python; this artifact installs only below
``/opt/plasma/python`` and is consumed by the Z2 PS installer.

The bootstrap code remains compatible with Python 3.10 so a clean PYNQ image can
verify and install the artifact without first replacing its system interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

ROOT_NAME = "plasma-python"
SCHEMA_VERSION = 1
MIN_PYTHON = (3, 11, 0)
TARGET_ARCHITECTURES = {"armv7", "armv7l"}
MAX_ARCHIVE_FILES = 25_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024


class PythonRuntimeArtifactError(RuntimeError):
    """Raised when the Python runtime artifact is unsafe or incompatible."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_python(path: Path) -> dict[str, object]:
    code = (
        "import json,platform,sqlite3,ssl,sys;"
        "print(json.dumps({'version':list(sys.version_info[:3]),"
        "'releaselevel':sys.version_info.releaselevel,'machine':platform.machine(),"
        "'executable':sys.executable,'openssl':ssl.OPENSSL_VERSION,"
        "'sqlite':sqlite3.sqlite_version}))"
    )
    try:
        completed = subprocess.run(
            [str(path), "-c", code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PythonRuntimeArtifactError(f"cannot execute Python runtime {path}: {exc}") from exc
    if completed.returncode != 0:
        raise PythonRuntimeArtifactError(
            f"Python runtime probe failed for {path}: {completed.stdout.strip()}"
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise PythonRuntimeArtifactError("Python runtime probe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PythonRuntimeArtifactError("Python runtime probe did not return an object")
    return payload


def _validated_probe(payload: Mapping[str, object]) -> tuple[str, str]:
    raw_version = payload.get("version")
    if (
        not isinstance(raw_version, list)
        or len(raw_version) < 3
        or not all(isinstance(item, int) for item in raw_version[:3])
    ):
        raise PythonRuntimeArtifactError("Python runtime probe did not report a valid version")
    version_tuple = tuple(int(item) for item in raw_version[:3])
    if version_tuple < MIN_PYTHON:
        raise PythonRuntimeArtifactError(
            f"Python runtime {version_tuple!r} is older than required {MIN_PYTHON!r}"
        )
    if str(payload.get("releaselevel", "")) != "final":
        raise PythonRuntimeArtifactError("Python runtime must be a final release")
    machine = str(payload.get("machine", "")).lower()
    if machine not in TARGET_ARCHITECTURES:
        raise PythonRuntimeArtifactError(f"Python runtime is not ARMv7: {machine!r}")
    version = ".".join(str(item) for item in version_tuple)
    return version, machine


def _find_python(python_root: Path) -> Path:
    preferred = python_root / "bin" / "python3"
    if preferred.is_file() and os.access(preferred, os.X_OK):
        return preferred
    candidates = sorted(python_root.glob("bin/python3.*"))
    candidates = [item for item in candidates if item.is_file() and os.access(item, os.X_OK)]
    if len(candidates) != 1:
        raise PythonRuntimeArtifactError(
            f"expected one executable Python below {python_root / 'bin'}, found {candidates!r}"
        )
    return candidates[0]


def _iter_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PythonRuntimeArtifactError(f"runtime staging contains symlink after dereference: {path}")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise PythonRuntimeArtifactError(f"runtime staging contains unsupported file type: {path}")
    return files


def _write_internal_hashes(root: Path) -> None:
    sums = root / "SHA256SUMS"
    lines = []
    for path in _iter_regular_files(root):
        if path == sums:
            continue
        lines.append(f"{_sha256(path)}  {path.relative_to(root).as_posix()}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sidecar(artifact: Path) -> Path:
    sidecar = Path(str(artifact) + ".sha256")
    sidecar.write_text(f"{_sha256(artifact)}  {artifact.name}\n", encoding="utf-8")
    return sidecar


def build_artifact(*, python_root: Path, output_dir: Path, source_ref: str) -> dict[str, object]:
    python_root = python_root.resolve()
    output_dir = output_dir.resolve()
    if not python_root.is_dir():
        raise PythonRuntimeArtifactError(f"Python prefix does not exist: {python_root}")
    probe = _probe_python(_find_python(python_root))
    version, machine = _validated_probe(probe)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / f"plasma-python-{version}-linux-armv7l.tar.gz"
    if artifact.exists() or Path(str(artifact) + ".sha256").exists():
        raise PythonRuntimeArtifactError(f"refusing to overwrite existing artifact: {artifact}")

    with tempfile.TemporaryDirectory(prefix="plasma-python-runtime-") as temporary:
        root = Path(temporary) / ROOT_NAME
        payload = root / "python"
        root.mkdir(parents=True)
        # Dereference prefix-local symlinks. The transported artifact then contains
        # only regular files/directories, which keeps extraction fail-closed.
        shutil.copytree(python_root, payload, symlinks=False)
        python_rel = _find_python(payload).relative_to(root).as_posix()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "role": "plasma-python-runtime",
            "platform": "linux",
            "architecture": "armv7l",
            "python_version": version,
            "python_executable": python_rel,
            "install_root": f"/opt/plasma/python/{version}",
            "source_ref": source_ref,
            "build_probe": {
                "machine": machine,
                "releaselevel": probe.get("releaselevel"),
                "openssl": probe.get("openssl"),
                "sqlite": probe.get("sqlite"),
            },
            "ownership_boundary": {
                "replaces_system_python": False,
                "replaces_pynq_python": False,
            },
        }
        (root / "runtime.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_internal_hashes(root)
        with tarfile.open(artifact, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            archive.add(root, arcname=ROOT_NAME, recursive=True)
    sidecar = _write_sidecar(artifact)
    return {
        "result": "PASS",
        "artifact": str(artifact),
        "sidecar": str(sidecar),
        "python_version": version,
        "architecture": "armv7l",
        "source_ref": source_ref,
    }


def _verify_sidecar(artifact: Path, sidecar: Path | None) -> str:
    sidecar = Path(str(artifact) + ".sha256") if sidecar is None else sidecar
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise PythonRuntimeArtifactError(f"cannot read detached SHA-256 sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != artifact.name:
        raise PythonRuntimeArtifactError("detached SHA-256 sidecar does not identify the artifact")
    expected = fields[0].lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise PythonRuntimeArtifactError("detached SHA-256 sidecar contains an invalid digest")
    actual = _sha256(artifact)
    if actual != expected:
        raise PythonRuntimeArtifactError("Python runtime artifact SHA-256 mismatch")
    return actual


def _safe_member(name: str) -> PurePosixPath:
    canonical = name.rstrip("/")
    if not canonical or canonical.startswith("/") or "\\" in canonical:
        raise PythonRuntimeArtifactError(f"unsafe archive path: {name!r}")
    pure = PurePosixPath(canonical)
    if ".." in pure.parts or not pure.parts or pure.parts[0] != ROOT_NAME:
        raise PythonRuntimeArtifactError(f"archive member escapes {ROOT_NAME}: {name!r}")
    if pure.as_posix() != canonical:
        raise PythonRuntimeArtifactError(f"archive member is not canonical POSIX form: {name!r}")
    return pure


def _extract_safe(artifact: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    count = 0
    expanded = 0
    try:
        archive = tarfile.open(artifact, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise PythonRuntimeArtifactError(f"cannot open Python runtime artifact: {exc}") from exc
    with archive:
        for member in archive.getmembers():
            pure = _safe_member(member.name)
            name = pure.as_posix()
            if name in seen:
                raise PythonRuntimeArtifactError(f"duplicate archive member: {name}")
            seen.add(name)
            target = destination / Path(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(member.mode & 0o777)
                continue
            if not member.isfile():
                raise PythonRuntimeArtifactError(f"non-regular archive member is forbidden: {name}")
            count += 1
            expanded += int(member.size)
            if count > MAX_ARCHIVE_FILES or expanded > MAX_UNCOMPRESSED_BYTES:
                raise PythonRuntimeArtifactError("Python runtime artifact exceeds extraction safety limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise PythonRuntimeArtifactError(f"cannot read archive member: {name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)
    return destination / ROOT_NAME


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PythonRuntimeArtifactError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PythonRuntimeArtifactError(f"{path.name} must contain a JSON object")
    return payload


def _verify_hashes(root: Path) -> None:
    sums = root / "SHA256SUMS"
    try:
        lines = sums.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PythonRuntimeArtifactError(f"cannot read SHA256SUMS: {exc}") from exc
    expected: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise PythonRuntimeArtifactError("invalid SHA256SUMS entry")
        digest, name = fields
        name = name.lstrip("*").strip()
        pure = PurePosixPath(name)
        if (
            not name
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in name
            or pure.as_posix() != name
            or name == "SHA256SUMS"
        ):
            raise PythonRuntimeArtifactError(f"unsafe SHA256SUMS path: {name!r}")
        digest = digest.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise PythonRuntimeArtifactError(f"invalid SHA256SUMS digest for {name!r}")
        if name in expected:
            raise PythonRuntimeArtifactError(f"duplicate SHA256SUMS entry: {name}")
        expected[name] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if actual != set(expected):
        raise PythonRuntimeArtifactError(
            f"artifact file set does not match SHA256SUMS: extra={sorted(actual-set(expected))}, "
            f"missing={sorted(set(expected)-actual)}"
        )
    for name, digest in expected.items():
        if _sha256(root / name) != digest:
            raise PythonRuntimeArtifactError(f"internal SHA-256 mismatch: {name}")


def verify_artifact(
    artifact: Path, *, sidecar: Path | None = None, extract_to: Path
) -> dict[str, object]:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise PythonRuntimeArtifactError(f"Python runtime artifact is missing: {artifact}")
    archive_sha256 = _verify_sidecar(artifact, sidecar)
    root = _extract_safe(artifact, extract_to)
    _verify_hashes(root)
    manifest = _read_json(root / "runtime.json")
    required = {
        "schema_version": SCHEMA_VERSION,
        "role": "plasma-python-runtime",
        "platform": "linux",
        "architecture": "armv7l",
    }
    for field, expected in required.items():
        if manifest.get(field) != expected:
            raise PythonRuntimeArtifactError(
                f"runtime manifest mismatch for {field}: expected {expected!r}, got {manifest.get(field)!r}"
            )
    version = manifest.get("python_version")
    executable = manifest.get("python_executable")
    if not isinstance(version, str) or not version:
        raise PythonRuntimeArtifactError("runtime manifest is missing python_version")
    if not isinstance(executable, str) or not executable:
        raise PythonRuntimeArtifactError("runtime manifest is missing python_executable")
    pure = PurePosixPath(executable)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != executable:
        raise PythonRuntimeArtifactError("runtime manifest python_executable is unsafe")
    python_path = root / Path(*pure.parts)
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise PythonRuntimeArtifactError("runtime artifact Python executable is missing or not executable")
    boundary = manifest.get("ownership_boundary")
    if boundary != {"replaces_pynq_python": False, "replaces_system_python": False}:
        raise PythonRuntimeArtifactError("runtime ownership boundary is invalid")
    return {
        "result": "PASS",
        "archive_sha256": archive_sha256,
        "manifest": manifest,
        "root": str(root),
        "python_path": str(python_path),
    }


def _require_target() -> None:
    if platform.system() != "Linux":
        raise PythonRuntimeArtifactError("Plasma Python runtime installer requires Linux")
    machine = platform.machine().lower()
    if machine not in TARGET_ARCHITECTURES:
        raise PythonRuntimeArtifactError(f"Plasma Python runtime installer requires ARMv7, got {machine}")
    if os.geteuid() != 0:
        raise PythonRuntimeArtifactError("Plasma Python runtime installation requires root privileges")


def install_artifact(
    artifact: Path,
    *,
    sidecar: Path | None = None,
    product_root: Path = Path("/opt/plasma"),
) -> dict[str, object]:
    _require_target()
    product_root = product_root.resolve()
    with tempfile.TemporaryDirectory(prefix="plasma-python-verify-") as temporary:
        verified = verify_artifact(
            artifact, sidecar=sidecar, extract_to=Path(temporary) / "verified"
        )
        manifest = verified["manifest"]
        assert isinstance(manifest, dict)
        version = str(manifest["python_version"])
        source_root = Path(str(verified["root"])) / "python"
        python_root = product_root / "python"
        target = python_root / version
        python_root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            installed = _find_python(target)
            installed_version, _ = _validated_probe(_probe_python(installed))
            if installed_version != version:
                raise PythonRuntimeArtifactError(
                    f"existing Plasma Python target is incompatible: {target}"
                )
        else:
            staging = python_root / f".{version}.tmp-{os.getpid()}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source_root, staging, symlinks=False)
            os.replace(staging, target)
        installed = _find_python(target)
        installed_probe = _probe_python(installed)
        installed_version, machine = _validated_probe(installed_probe)
        if installed_version != version:
            raise PythonRuntimeArtifactError(
                f"installed runtime version mismatch: expected {version}, got {installed_version}"
            )
        install_root = product_root / "install"
        install_root.mkdir(parents=True, exist_ok=True)
        evidence = {
            "schema_version": 1,
            "result": "PASS",
            "evidence_level": "z2-plasma-python-local-runtime",
            "python_version": version,
            "architecture": machine,
            "python_path": str(installed),
            "artifact": artifact.name,
            "artifact_sha256": verified["archive_sha256"],
            "source_ref": manifest.get("source_ref"),
            "ownership_boundary": manifest.get("ownership_boundary"),
        }
        evidence_path = install_root / "python-runtime.json"
        temporary_evidence = evidence_path.with_name(f".{evidence_path.name}.tmp-{os.getpid()}")
        temporary_evidence.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_evidence, evidence_path)
        return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build, verify, or install the Plasma-owned ARMv7 Python runtime"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--python-root", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--source-ref", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("artifact", type=Path)
    verify.add_argument("--sidecar", type=Path)

    install = sub.add_parser("install")
    install.add_argument("artifact", type=Path)
    install.add_argument("--sidecar", type=Path)
    install.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_artifact(
                python_root=args.python_root,
                output_dir=args.output_dir,
                source_ref=args.source_ref,
            )
        elif args.command == "verify":
            with tempfile.TemporaryDirectory(prefix="plasma-python-verify-") as temporary:
                result = verify_artifact(
                    args.artifact,
                    sidecar=args.sidecar,
                    extract_to=Path(temporary) / "verified",
                )
                result = {key: value for key, value in result.items() if key not in {"root", "python_path"}}
        else:
            result = install_artifact(
                args.artifact,
                sidecar=args.sidecar,
                product_root=args.product_root,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, subprocess.SubprocessError, PythonRuntimeArtifactError) as exc:
        print(f"z2-python-runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
