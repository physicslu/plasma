#!/usr/bin/env python3
"""Build, verify, and install a Plasma-owned OpenOCD runtime artifact.

The runtime is versioned independently from the PPU application release and is
installed below /opt/plasma/programming-engines/openocd. Packaging and
installation do not enable physical programming. The artifact manifest keeps
hardware_runtime_ready false until a later Z2/adapter/target qualification
explicitly promotes that boundary.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Sequence

ROOT_NAME = "plasma-openocd"
SCHEMA_VERSION = 1
SUPPORTED_ARCHITECTURES = {"x86_64": 62, "armv7l": 40}
MAX_ARCHIVE_FILES = 50000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
VERSION_PATTERN = re.compile(r"Open On-Chip Debugger\s+([0-9]+\.[0-9]+\.[0-9]+)")


class OpenOCDRuntimeArtifactError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_architecture(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "armv7": "armv7l",
        "armv7l": "armv7l",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise OpenOCDRuntimeArtifactError(
            f"unsupported OpenOCD runtime architecture: {value!r}"
        ) from exc


def _probe_openocd(path: Path) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot execute OpenOCD {path}: {exc}") from exc
    output = completed.stdout.strip()
    if completed.returncode != 0:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD version probe failed for {path}: {output}"
        )
    match = VERSION_PATTERN.search(output)
    if match is None:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD version probe returned an unexpected banner: {output!r}"
        )
    return match.group(1), output


def _ldd_dependencies(path: Path) -> list[str]:
    try:
        completed = subprocess.run(
            ["ldd", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot inspect OpenOCD shared libraries: {exc}") from exc
    output = completed.stdout.strip()
    if completed.returncode != 0:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD shared-library inspection failed: {output}"
        )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise OpenOCDRuntimeArtifactError("OpenOCD shared-library inspection returned no data")
    missing = [line for line in lines if "not found" in line]
    if missing:
        raise OpenOCDRuntimeArtifactError(
            "OpenOCD has unresolved shared-library dependencies: " + "; ".join(missing)
        )
    return lines


def _elf_architecture(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
    except OSError as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot read OpenOCD ELF header: {exc}") from exc
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise OpenOCDRuntimeArtifactError("OpenOCD executable is not an ELF binary")
    endian = header[5]
    if endian == 1:
        machine = struct.unpack("<H", header[18:20])[0]
    elif endian == 2:
        machine = struct.unpack(">H", header[18:20])[0]
    else:
        raise OpenOCDRuntimeArtifactError("OpenOCD ELF header has an invalid endianness")
    for architecture, expected_machine in SUPPORTED_ARCHITECTURES.items():
        if machine == expected_machine:
            return architecture
    raise OpenOCDRuntimeArtifactError(f"unsupported OpenOCD ELF machine: {machine}")


def _iter_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise OpenOCDRuntimeArtifactError(
                f"OpenOCD runtime staging contains a symlink after dereference: {path}"
            )
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise OpenOCDRuntimeArtifactError(
                f"OpenOCD runtime staging contains an unsupported file type: {path}"
            )
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


def _normalized_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove host/time ownership metadata without changing payload permissions."""

    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.pax_headers = {}
    return info


def _write_reproducible_archive(root: Path, artifact: Path) -> None:
    """Create stable tar+gzip bytes for an identical staged payload tree."""

    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                archive.add(
                    root,
                    arcname=ROOT_NAME,
                    recursive=True,
                    filter=_normalized_tarinfo,
                )


def _validate_source_commit(value: str) -> str:
    commit = value.strip().lower()
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        raise OpenOCDRuntimeArtifactError("OpenOCD source commit must be a full 40-character SHA")
    return commit


def _validate_version(value: str) -> str:
    version = value.strip()
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise OpenOCDRuntimeArtifactError(f"invalid OpenOCD version: {value!r}")
    return version


def build_artifact(
    *,
    prefix: Path,
    output_dir: Path,
    version: str,
    source_commit: str,
    architecture: str,
) -> dict[str, object]:
    prefix = prefix.resolve()
    output_dir = output_dir.resolve()
    version = _validate_version(version)
    source_commit = _validate_source_commit(source_commit)
    architecture = _normalize_architecture(architecture)
    host_architecture = _normalize_architecture(platform.machine())
    if host_architecture != architecture:
        raise OpenOCDRuntimeArtifactError(
            f"build host architecture mismatch: expected {architecture}, got {host_architecture}"
        )
    binary = prefix / "bin" / "openocd"
    scripts = prefix / "share" / "openocd" / "scripts"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise OpenOCDRuntimeArtifactError(f"OpenOCD executable is missing: {binary}")
    for required in (scripts / "target", scripts / "interface"):
        if not required.is_dir():
            raise OpenOCDRuntimeArtifactError(
                f"OpenOCD installed script directory is missing: {required}"
            )
    elf_architecture = _elf_architecture(binary)
    if elf_architecture != architecture:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD binary architecture mismatch: expected {architecture}, got {elf_architecture}"
        )
    probed_version, version_banner = _probe_openocd(binary)
    if probed_version != version:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD version mismatch: expected {version}, got {probed_version}"
        )
    dependencies = _ldd_dependencies(binary)

    runtime_id = f"{version}-{source_commit[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / f"plasma-openocd-{runtime_id}-linux-{architecture}.tar.gz"
    sidecar = Path(str(artifact) + ".sha256")
    if artifact.exists() or sidecar.exists():
        raise OpenOCDRuntimeArtifactError(f"refusing to overwrite existing artifact: {artifact}")

    with tempfile.TemporaryDirectory(prefix="plasma-openocd-runtime-") as temporary:
        root = Path(temporary) / ROOT_NAME
        payload = root / "payload"
        root.mkdir(parents=True)
        shutil.copytree(prefix, payload, symlinks=False)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "role": "plasma-openocd-runtime",
            "platform": "linux",
            "architecture": architecture,
            "openocd_version": version,
            "source_commit": source_commit,
            "runtime_id": runtime_id,
            "binary": "payload/bin/openocd",
            "scripts_root": "payload/share/openocd/scripts",
            "install_root": f"/opt/plasma/programming-engines/openocd/{runtime_id}",
            "build_probe": {
                "version_banner": version_banner,
                "shared_library_dependencies": dependencies,
            },
            "qualification_boundary": {
                "hardware_runtime_ready": False,
                "starts_openocd_service": False,
                "qualifies_swd_jtag": False,
                "qualifies_target_power_reset": False,
                "qualifies_real_ic": False,
            },
        }
        (root / "runtime.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_internal_hashes(root)
        _write_reproducible_archive(root, artifact)
    _write_sidecar(artifact)
    artifact_sha256 = _sha256(artifact)
    return {
        "result": "PASS",
        "artifact": str(artifact),
        "sidecar": str(sidecar),
        "runtime_id": runtime_id,
        "openocd_version": version,
        "architecture": architecture,
        "source_commit": source_commit,
        "artifact_sha256": artifact_sha256,
        "packaging_policy": "normalized-tar-gzip-v1",
        "hardware_runtime_ready": False,
    }


def _verify_sidecar(artifact: Path, sidecar: Path | None) -> str:
    sidecar = Path(str(artifact) + ".sha256") if sidecar is None else sidecar
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot read detached SHA-256 sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != artifact.name:
        raise OpenOCDRuntimeArtifactError("detached SHA-256 sidecar does not identify the artifact")
    expected = fields[0].lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise OpenOCDRuntimeArtifactError("detached SHA-256 sidecar contains an invalid digest")
    actual = _sha256(artifact)
    if actual != expected:
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime artifact SHA-256 mismatch")
    return actual


def _safe_member(name: str) -> PurePosixPath:
    canonical = name.rstrip("/")
    if not canonical or canonical.startswith("/") or "\\" in canonical:
        raise OpenOCDRuntimeArtifactError(f"unsafe archive path: {name!r}")
    pure = PurePosixPath(canonical)
    if ".." in pure.parts or not pure.parts or pure.parts[0] != ROOT_NAME:
        raise OpenOCDRuntimeArtifactError(f"archive member escapes {ROOT_NAME}: {name!r}")
    if pure.as_posix() != canonical:
        raise OpenOCDRuntimeArtifactError(f"archive member is not canonical POSIX form: {name!r}")
    return pure


def _extract_safe(artifact: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    count = 0
    expanded = 0
    try:
        archive = tarfile.open(artifact, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot open OpenOCD runtime artifact: {exc}") from exc
    with archive:
        for member in archive.getmembers():
            pure = _safe_member(member.name)
            name = pure.as_posix()
            if name in seen:
                raise OpenOCDRuntimeArtifactError(f"duplicate archive member: {name}")
            seen.add(name)
            target = destination / Path(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(member.mode & 0o777)
                continue
            if not member.isfile():
                raise OpenOCDRuntimeArtifactError(
                    f"non-regular archive member is forbidden: {name}"
                )
            count += 1
            expanded += int(member.size)
            if count > MAX_ARCHIVE_FILES or expanded > MAX_UNCOMPRESSED_BYTES:
                raise OpenOCDRuntimeArtifactError(
                    "OpenOCD runtime artifact exceeds extraction safety limits"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise OpenOCDRuntimeArtifactError(f"cannot read archive member: {name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)
    return destination / ROOT_NAME


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenOCDRuntimeArtifactError(f"{path.name} must contain a JSON object")
    return payload


def _verify_hashes(root: Path) -> None:
    sums = root / "SHA256SUMS"
    try:
        lines = sums.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OpenOCDRuntimeArtifactError(f"cannot read SHA256SUMS: {exc}") from exc
    expected: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise OpenOCDRuntimeArtifactError("invalid SHA256SUMS entry")
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
            raise OpenOCDRuntimeArtifactError(f"unsafe SHA256SUMS path: {name!r}")
        digest = digest.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise OpenOCDRuntimeArtifactError(f"invalid SHA256SUMS digest for {name!r}")
        if name in expected:
            raise OpenOCDRuntimeArtifactError(f"duplicate SHA256SUMS entry: {name}")
        expected[name] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if actual != set(expected):
        raise OpenOCDRuntimeArtifactError(
            f"artifact file set does not match SHA256SUMS: "
            f"extra={sorted(actual-set(expected))}, missing={sorted(set(expected)-actual)}"
        )
    for name, digest in expected.items():
        if _sha256(root / name) != digest:
            raise OpenOCDRuntimeArtifactError(f"internal SHA-256 mismatch: {name}")


def _verify_installed_payload(source_root: Path, target: Path) -> None:
    expected = {
        path.relative_to(source_root).as_posix(): _sha256(path)
        for path in _iter_regular_files(source_root)
    }
    actual = {
        path.relative_to(target).as_posix(): _sha256(path)
        for path in _iter_regular_files(target)
        if path.name != "plasma-runtime.json"
    }
    if actual != expected:
        raise OpenOCDRuntimeArtifactError(
            "existing OpenOCD runtime content does not match the verified artifact"
        )


def _safe_relative(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise OpenOCDRuntimeArtifactError(f"runtime manifest is missing {field}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise OpenOCDRuntimeArtifactError(f"runtime manifest {field} is unsafe")
    return pure


def verify_artifact(
    artifact: Path, *, sidecar: Path | None = None, extract_to: Path
) -> dict[str, object]:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise OpenOCDRuntimeArtifactError(f"OpenOCD runtime artifact is missing: {artifact}")
    archive_sha256 = _verify_sidecar(artifact, sidecar)
    root = _extract_safe(artifact, extract_to)
    _verify_hashes(root)
    manifest = _read_json(root / "runtime.json")
    required = {
        "schema_version": SCHEMA_VERSION,
        "role": "plasma-openocd-runtime",
        "platform": "linux",
    }
    for field, expected in required.items():
        if manifest.get(field) != expected:
            raise OpenOCDRuntimeArtifactError(
                f"runtime manifest mismatch for {field}: expected {expected!r}, "
                f"got {manifest.get(field)!r}"
            )
    architecture = _normalize_architecture(str(manifest.get("architecture", "")))
    version = _validate_version(str(manifest.get("openocd_version", "")))
    source_commit = _validate_source_commit(str(manifest.get("source_commit", "")))
    runtime_id = str(manifest.get("runtime_id", ""))
    if runtime_id != f"{version}-{source_commit[:12]}":
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime_id does not match version/source commit")
    expected_install_root = f"/opt/plasma/programming-engines/openocd/{runtime_id}"
    if manifest.get("install_root") != expected_install_root:
        raise OpenOCDRuntimeArtifactError("OpenOCD install_root is not canonical")
    binary_rel = _safe_relative(manifest.get("binary"), field="binary")
    scripts_rel = _safe_relative(manifest.get("scripts_root"), field="scripts_root")
    binary = root / Path(*binary_rel.parts)
    scripts = root / Path(*scripts_rel.parts)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise OpenOCDRuntimeArtifactError("OpenOCD artifact binary is missing or not executable")
    if _elf_architecture(binary) != architecture:
        raise OpenOCDRuntimeArtifactError("OpenOCD artifact ELF architecture does not match manifest")
    for required_dir in (scripts / "target", scripts / "interface"):
        if not required_dir.is_dir():
            raise OpenOCDRuntimeArtifactError(
                f"OpenOCD artifact is missing required scripts: {required_dir}"
            )
    boundary = manifest.get("qualification_boundary")
    expected_boundary = {
        "hardware_runtime_ready": False,
        "starts_openocd_service": False,
        "qualifies_swd_jtag": False,
        "qualifies_target_power_reset": False,
        "qualifies_real_ic": False,
    }
    if boundary != expected_boundary:
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime qualification boundary is invalid")
    probe = manifest.get("build_probe")
    if not isinstance(probe, dict):
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime build_probe is missing")
    dependencies = probe.get("shared_library_dependencies")
    if not isinstance(dependencies, list) or not dependencies or not all(
        isinstance(item, str) and item for item in dependencies
    ):
        raise OpenOCDRuntimeArtifactError(
            "OpenOCD runtime shared-library dependency evidence is invalid"
        )
    if any("not found" in item for item in dependencies):
        raise OpenOCDRuntimeArtifactError(
            "OpenOCD runtime build probe contains unresolved dependencies"
        )
    return {
        "result": "PASS",
        "archive_sha256": archive_sha256,
        "manifest": manifest,
        "root": str(root),
        "binary": str(binary),
        "hardware_runtime_ready": False,
    }


def _require_install_target(architecture: str) -> str:
    if platform.system() != "Linux":
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime installer requires Linux")
    machine = _normalize_architecture(platform.machine())
    if machine != architecture:
        raise OpenOCDRuntimeArtifactError(
            f"OpenOCD runtime installer architecture mismatch: artifact={architecture}, host={machine}"
        )
    if os.geteuid() != 0:
        raise OpenOCDRuntimeArtifactError("OpenOCD runtime installation requires root privileges")
    return machine


def install_artifact(
    artifact: Path,
    *,
    sidecar: Path | None = None,
    product_root: Path = Path("/opt/plasma"),
) -> dict[str, object]:
    product_root = product_root.resolve()
    with tempfile.TemporaryDirectory(prefix="plasma-openocd-verify-") as temporary:
        verified = verify_artifact(
            artifact,
            sidecar=sidecar,
            extract_to=Path(temporary) / "verified",
        )
        manifest = verified["manifest"]
        assert isinstance(manifest, dict)
        architecture = _normalize_architecture(str(manifest["architecture"]))
        _require_install_target(architecture)
        runtime_id = str(manifest["runtime_id"])
        source_root = Path(str(verified["root"])) / "payload"
        engines_root = product_root / "programming-engines" / "openocd"
        target = engines_root / runtime_id
        engines_root.mkdir(parents=True, exist_ok=True)

        if target.exists():
            retained = _read_json(target / "plasma-runtime.json")
            for field in ("runtime_id", "openocd_version", "source_commit", "architecture"):
                if retained.get(field) != manifest.get(field):
                    raise OpenOCDRuntimeArtifactError(
                        f"existing OpenOCD runtime identity mismatch for {field}"
                    )
            _verify_installed_payload(source_root, target)
        else:
            staging = engines_root / f".{runtime_id}.tmp-{os.getpid()}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source_root, staging, symlinks=False)
            (staging / "plasma-runtime.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(staging, target)

        binary = target / "bin" / "openocd"
        scripts = target / "share" / "openocd" / "scripts"
        installed_version, version_banner = _probe_openocd(binary)
        if installed_version != manifest["openocd_version"]:
            raise OpenOCDRuntimeArtifactError(
                f"installed OpenOCD version mismatch: expected {manifest['openocd_version']}, "
                f"got {installed_version}"
            )
        dependencies = _ldd_dependencies(binary)
        for required_dir in (scripts / "target", scripts / "interface"):
            if not required_dir.is_dir():
                raise OpenOCDRuntimeArtifactError(
                    f"installed OpenOCD scripts are missing: {required_dir}"
                )

        install_root = product_root / "install"
        install_root.mkdir(parents=True, exist_ok=True)
        evidence = {
            "schema_version": 1,
            "result": "PASS",
            "evidence_level": "openocd-runtime-local-install",
            "runtime_id": runtime_id,
            "openocd_version": manifest["openocd_version"],
            "source_commit": manifest["source_commit"],
            "architecture": architecture,
            "binary": str(binary),
            "scripts_root": str(scripts),
            "artifact": artifact.name,
            "artifact_sha256": verified["archive_sha256"],
            "version_banner": version_banner,
            "shared_library_dependencies": dependencies,
            "hardware_runtime_ready": False,
            "starts_openocd_service": False,
            "qualification_boundary": dict(manifest["qualification_boundary"]),
        }
        evidence_path = install_root / "openocd-runtime.json"
        temporary_evidence = evidence_path.with_name(f".{evidence_path.name}.tmp-{os.getpid()}")
        temporary_evidence.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_evidence, evidence_path)
        return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build, verify, or install a Plasma-owned OpenOCD runtime"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--prefix", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--version", required=True)
    build.add_argument("--source-commit", required=True)
    build.add_argument("--architecture", required=True)

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
                prefix=args.prefix,
                output_dir=args.output_dir,
                version=args.version,
                source_commit=args.source_commit,
                architecture=args.architecture,
            )
        elif args.command == "verify":
            with tempfile.TemporaryDirectory(prefix="plasma-openocd-verify-") as temporary:
                result = verify_artifact(
                    args.artifact,
                    sidecar=args.sidecar,
                    extract_to=Path(temporary) / "verified",
                )
                manifest = result["manifest"]
                assert isinstance(manifest, dict)
                result = {
                    "result": "PASS",
                    "archive_sha256": result["archive_sha256"],
                    "runtime_id": manifest["runtime_id"],
                    "openocd_version": manifest["openocd_version"],
                    "architecture": manifest["architecture"],
                    "source_commit": manifest["source_commit"],
                    "hardware_runtime_ready": False,
                }
        else:
            result = install_artifact(
                args.artifact,
                sidecar=args.sidecar,
                product_root=args.product_root,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, subprocess.SubprocessError, OpenOCDRuntimeArtifactError) as exc:
        print(f"openocd-runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
