#!/usr/bin/env python3
"""Build and verify immutable Plasma product release bundles.

This is a build/release tool, not an installer. It never changes services,
installs packages, updates Git, touches FPGA/PL state, or programs target ICs.
The build command consumes an already-built runtime payload and wraps it in the
canonical Plasma release format. The verify command is intentionally able to
run without access to the source repository.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DESCRIPTOR_PATH = REPO_ROOT / "release" / "product.json"
RELEASE_ROOT = "plasma-release"
RELEASE_SCHEMA_VERSION = 1
PRODUCT_DESCRIPTOR_SCHEMA_VERSION = 1
MAX_ARCHIVE_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024

ROLE_CONTROL_STATION = "control-station"
ROLE_PPU = "ppu"
ROLE_TARGETS: dict[str, set[tuple[str, str]]] = {
    ROLE_CONTROL_STATION: {
        ("macos", "arm64"),
        ("macos", "x86_64"),
        ("linux", "arm64"),
        ("linux", "x86_64"),
        ("windows", "x86_64"),
    },
    ROLE_PPU: {
        ("linux", "armv7l"),
    },
}
ROLE_CONTRACTS: dict[str, dict[str, str]] = {
    ROLE_CONTROL_STATION: {
        "web_rest_api": "3",
    },
    ROLE_PPU: {
        "plasma_protocol": "3.3",
        "web_rest_api": "3",
    },
}

FORBIDDEN_PATH_SEGMENTS = {
    ".git",
    ".hg",
    ".svn",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "tests",
    "venv",
}
FORBIDDEN_SECRET_BASENAMES = {
    ".env",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReleaseError(ValueError):
    """Raised when a release bundle violates the canonical contract."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_platform(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "darwin": "macos",
        "win32": "windows",
        "win64": "windows",
    }
    return aliases.get(normalized, normalized)


def _normalize_architecture(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "aarch64": "arm64",
        "amd64": "x86_64",
        "x64": "x86_64",
        "armv7": "armv7l",
        "armhf": "armv7l",
    }
    return aliases.get(normalized, normalized)


def _validate_semver(value: str, *, field: str) -> str:
    if not isinstance(value, str) or SEMVER_RE.fullmatch(value) is None:
        raise ReleaseError(f"{field} must be a SemVer-compatible value, got {value!r}")
    return value


def _validate_git_sha(value: str) -> str:
    if GIT_SHA_RE.fullmatch(value or "") is None:
        raise ReleaseError("git_sha must be a full 40-character hexadecimal commit SHA")
    return value.lower()


def _validate_build_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReleaseError("build_timestamp must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReleaseError(f"invalid build_timestamp: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReleaseError("build_timestamp must be UTC")
    return value


def _canonical_build_timestamp(value: str | None) -> str:
    if value is not None:
        return _validate_build_timestamp(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_target(role: str, platform_name: str, architecture: str) -> tuple[str, str, str]:
    if role not in ROLE_TARGETS:
        raise ReleaseError(f"unsupported role: {role}")
    platform_name = _normalize_platform(platform_name)
    architecture = _normalize_architecture(architecture)
    if (platform_name, architecture) not in ROLE_TARGETS[role]:
        supported = ", ".join(
            f"{platform}-{arch}" for platform, arch in sorted(ROLE_TARGETS[role])
        )
        raise ReleaseError(
            f"unsupported release target for {role}: {platform_name}-{architecture}; "
            f"supported targets: {supported}"
        )
    return role, platform_name, architecture


def _load_product_descriptor(repo_root: Path) -> dict[str, object]:
    path = repo_root / "release" / "product.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot load product descriptor {path}: {exc}") from exc

    if payload.get("schema_version") != PRODUCT_DESCRIPTOR_SCHEMA_VERSION:
        raise ReleaseError(
            f"unsupported product descriptor schema: {payload.get('schema_version')!r}"
        )
    if payload.get("product") != "plasma":
        raise ReleaseError("product descriptor must identify product='plasma'")
    _validate_semver(str(payload.get("product_version", "")), field="product_version")

    role_contracts = payload.get("role_contracts")
    if not isinstance(role_contracts, dict):
        raise ReleaseError("product descriptor role_contracts must be an object")
    for role, expected in ROLE_CONTRACTS.items():
        actual = role_contracts.get(role)
        if actual != expected:
            raise ReleaseError(
                f"product descriptor contract drift for {role}: expected {expected}, got {actual}"
            )
    return payload


def _component_versions(repo_root: Path, role: str) -> dict[str, str]:
    python_project = repo_root / "software" / "python" / "pyproject.toml"
    try:
        python_payload = tomllib.loads(python_project.read_text(encoding="utf-8"))
        python_version = str(python_payload["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"cannot determine Python component version: {exc}") from exc
    _validate_semver(python_version, field="components.python")

    components = {"python": python_version}
    if role == ROLE_CONTROL_STATION:
        web_package = repo_root / "software" / "web" / "package.json"
        try:
            web_payload = json.loads(web_package.read_text(encoding="utf-8"))
            web_version = str(web_payload["version"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReleaseError(f"cannot determine Web component version: {exc}") from exc
        _validate_semver(web_version, field="components.web")
        components["web"] = web_version
    return dict(sorted(components.items()))


def _discover_git_sha(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseError(
            "cannot determine Git SHA; pass --git-sha explicitly in non-Git build environments"
        ) from exc
    return _validate_git_sha(completed.stdout.strip())


def _validate_payload_relative_path(relative: Path) -> None:
    if relative.is_absolute() or not relative.parts:
        raise ReleaseError(f"invalid payload path: {relative}")
    lowered_parts = {part.lower() for part in relative.parts}
    forbidden = lowered_parts & FORBIDDEN_PATH_SEGMENTS
    if forbidden:
        raise ReleaseError(
            f"payload path contains build/development-only segment {sorted(forbidden)[0]!r}: {relative}"
        )
    for part in relative.parts:
        if "\n" in part or "\r" in part or "\\" in part:
            raise ReleaseError(f"payload path contains unsupported characters: {relative}")
    basename = relative.name.lower()
    if basename in FORBIDDEN_SECRET_BASENAMES or basename.startswith(".env."):
        raise ReleaseError(f"payload contains a prohibited secret/config filename: {relative}")


def _copy_payload(source: Path, destination: Path) -> int:
    if not source.is_dir():
        raise ReleaseError(f"payload directory does not exist: {source}")
    copied_files = 0
    destination.mkdir(parents=True, exist_ok=True)
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        _validate_payload_relative_path(relative)
        if source_path.is_symlink():
            raise ReleaseError(f"payload symlinks are not allowed: {relative}")
        target_path = destination / relative
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied_files += 1
        else:
            raise ReleaseError(f"unsupported payload filesystem entry: {relative}")
    return copied_files


def _manifest(
    *,
    descriptor: Mapping[str, object],
    role: str,
    platform_name: str,
    architecture: str,
    git_sha: str,
    build_timestamp: str,
    components: Mapping[str, str],
    archive_format: str,
) -> dict[str, object]:
    role_contracts = descriptor["role_contracts"]
    assert isinstance(role_contracts, dict)
    contracts = role_contracts[role]
    assert isinstance(contracts, dict)
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "product": "plasma",
        "product_version": descriptor["product_version"],
        "git_sha": git_sha,
        "role": role,
        "platform": platform_name,
        "architecture": architecture,
        "target": f"{platform_name}-{architecture}",
        "build_timestamp": build_timestamp,
        "archive_format": archive_format,
        "contracts": dict(sorted((str(k), str(v)) for k, v in contracts.items())),
        "components": dict(sorted(components.items())),
        "layout": {
            "runtime": "runtime",
            "config_defaults": "config/defaults",
        },
    }


def _write_sha256sums(root: Path) -> None:
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        relative = path.relative_to(root).as_posix()
        lines.append(f"{_sha256_file(path)}  {relative}")
    if not lines:
        raise ReleaseError("release bundle contains no files to hash")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _archive_format(platform_name: str) -> tuple[str, str]:
    if platform_name == "windows":
        return "zip", ".zip"
    return "tar.gz", ".tar.gz"


def _artifact_name(role: str, version: str, platform_name: str, architecture: str) -> str:
    _, suffix = _archive_format(platform_name)
    return f"plasma-{role}-{version}-{platform_name}-{architecture}{suffix}"


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _build_tar_gz(root: Path, artifact: Path) -> None:
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in [root, *sorted(root.rglob("*"))]:
                    arcname = RELEASE_ROOT
                    if path != root:
                        arcname = f"{RELEASE_ROOT}/{path.relative_to(root).as_posix()}"
                    info = _tar_filter(archive.gettarinfo(str(path), arcname=arcname))
                    if path.is_dir():
                        archive.addfile(info)
                    elif path.is_file():
                        with path.open("rb") as handle:
                            archive.addfile(info, handle)
                    else:
                        raise ReleaseError(f"unsupported staging entry: {path}")


def _build_zip(root: Path, artifact: Path) -> None:
    with zipfile.ZipFile(
        artifact,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            arcname = f"{RELEASE_ROOT}/{path.relative_to(root).as_posix()}"
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def _write_archive_sidecar(artifact: Path) -> Path:
    sidecar = Path(str(artifact) + ".sha256")
    sidecar.write_text(f"{_sha256_file(artifact)}  {artifact.name}\n", encoding="utf-8")
    return sidecar


def _verify_archive_sidecar(artifact: Path, sidecar: Path) -> str:
    try:
        line = sidecar.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ReleaseError(f"cannot read archive SHA-256 sidecar {sidecar}: {exc}") from exc
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
    if match is None:
        raise ReleaseError(f"invalid archive SHA-256 sidecar format: {sidecar}")
    expected, filename = match.groups()
    if filename != artifact.name:
        raise ReleaseError(
            f"archive SHA-256 sidecar names {filename!r}, expected {artifact.name!r}"
        )
    actual = _sha256_file(artifact)
    if actual != expected:
        raise ReleaseError(f"archive SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def _archive_destination(base: Path, member_name: str) -> Path:
    if "\\" in member_name:
        raise ReleaseError(f"archive member uses non-canonical separator: {member_name!r}")
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ReleaseError(f"unsafe archive member path: {member_name!r}")
    if pure.parts[0] != RELEASE_ROOT:
        raise ReleaseError(
            f"archive member must be rooted at {RELEASE_ROOT!r}: {member_name!r}"
        )
    return base.joinpath(*pure.parts)


def _extract_zip(artifact: Path, destination: Path) -> None:
    file_count = 0
    total_size = 0
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(artifact, "r") as archive:
            for info in archive.infolist():
                if info.filename in seen:
                    raise ReleaseError(f"duplicate archive member: {info.filename}")
                seen.add(info.filename)
                target = _archive_destination(destination, info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ReleaseError(f"archive symlink is not allowed: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                file_count += 1
                total_size += info.file_size
                if file_count > MAX_ARCHIVE_FILES or total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ReleaseError("archive exceeds release verification safety limits")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
    except zipfile.BadZipFile as exc:
        raise ReleaseError(f"invalid ZIP artifact: {artifact}") from exc


def _extract_tar_gz(artifact: Path, destination: Path) -> None:
    file_count = 0
    total_size = 0
    seen: set[str] = set()
    try:
        with tarfile.open(artifact, "r:gz") as archive:
            for member in archive.getmembers():
                if member.name in seen:
                    raise ReleaseError(f"duplicate archive member: {member.name}")
                seen.add(member.name)
                target = _archive_destination(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ReleaseError(f"non-regular archive member is not allowed: {member.name}")
                file_count += 1
                total_size += member.size
                if file_count > MAX_ARCHIVE_FILES or total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ReleaseError("archive exceeds release verification safety limits")
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseError(f"cannot read archive member: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
    except (tarfile.TarError, EOFError) as exc:
        raise ReleaseError(f"invalid tar.gz artifact: {artifact}") from exc


def _extract_archive(artifact: Path, destination: Path) -> str:
    if artifact.name.endswith(".tar.gz"):
        _extract_tar_gz(artifact, destination)
        return "tar.gz"
    if artifact.suffix.lower() == ".zip":
        _extract_zip(artifact, destination)
        return "zip"
    raise ReleaseError(f"unsupported release archive extension: {artifact.name}")


def _parse_sha256sums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseError(f"cannot read {path}: {exc}") from exc
    expected: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None:
            raise ReleaseError(f"invalid SHA256SUMS line: {line!r}")
        digest, relative = match.groups()
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            raise ReleaseError(f"unsafe SHA256SUMS path: {relative!r}")
        if relative == "SHA256SUMS" or relative in expected:
            raise ReleaseError(f"invalid or duplicate SHA256SUMS entry: {relative!r}")
        expected[relative] = digest
    if not expected:
        raise ReleaseError("SHA256SUMS must contain at least one entry")
    return expected


def _verify_tree_hashes(root: Path) -> None:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise ReleaseError("release bundle is missing SHA256SUMS")
    expected = _parse_sha256sums(sums_path)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != sums_path
    }
    if actual_files != set(expected):
        missing = sorted(set(expected) - actual_files)
        extra = sorted(actual_files - set(expected))
        raise ReleaseError(f"release file-set mismatch; missing={missing}, extra={extra}")
    for relative, expected_digest in sorted(expected.items()):
        actual_digest = _sha256_file(root / PurePosixPath(relative))
        if actual_digest != expected_digest:
            raise ReleaseError(
                f"release file SHA-256 mismatch for {relative}: "
                f"expected {expected_digest}, got {actual_digest}"
            )


def _validate_manifest(manifest: Mapping[str, object], *, archive_format: str) -> None:
    required = {
        "schema_version",
        "product",
        "product_version",
        "git_sha",
        "role",
        "platform",
        "architecture",
        "target",
        "build_timestamp",
        "archive_format",
        "contracts",
        "components",
        "layout",
    }
    if set(manifest) != required:
        missing = sorted(required - set(manifest))
        extra = sorted(set(manifest) - required)
        raise ReleaseError(f"release.json schema key mismatch; missing={missing}, extra={extra}")
    if manifest["schema_version"] != RELEASE_SCHEMA_VERSION:
        raise ReleaseError(f"unsupported release schema: {manifest['schema_version']!r}")
    if manifest["product"] != "plasma":
        raise ReleaseError("release.json must identify product='plasma'")
    _validate_semver(str(manifest["product_version"]), field="product_version")
    _validate_git_sha(str(manifest["git_sha"]))
    role, platform_name, architecture = _validate_target(
        str(manifest["role"]),
        str(manifest["platform"]),
        str(manifest["architecture"]),
    )
    if manifest["role"] != role or manifest["platform"] != platform_name or manifest["architecture"] != architecture:
        raise ReleaseError("release.json role/platform/architecture must already use canonical names")
    if manifest["target"] != f"{platform_name}-{architecture}":
        raise ReleaseError("release.json target does not match platform/architecture")
    _validate_build_timestamp(str(manifest["build_timestamp"]))
    if manifest["archive_format"] != archive_format:
        raise ReleaseError(
            f"release.json archive_format={manifest['archive_format']!r} does not match {archive_format!r}"
        )
    if manifest["contracts"] != ROLE_CONTRACTS[role]:
        raise ReleaseError(
            f"release contract metadata drift for {role}: {manifest['contracts']!r}"
        )
    components = manifest["components"]
    if not isinstance(components, dict) or not components:
        raise ReleaseError("release.json components must be a non-empty object")
    expected_component_names = {"python", "web"} if role == ROLE_CONTROL_STATION else {"python"}
    if set(components) != expected_component_names:
        raise ReleaseError(
            f"release component set mismatch for {role}: expected {sorted(expected_component_names)}, "
            f"got {sorted(components)}"
        )
    for name, version in components.items():
        _validate_semver(str(version), field=f"components.{name}")
    if manifest["layout"] != {"runtime": "runtime", "config_defaults": "config/defaults"}:
        raise ReleaseError("release.json layout does not match schema v1")


def _load_and_validate_manifest(root: Path, *, archive_format: str) -> dict[str, object]:
    manifest_path = root / "release.json"
    if not manifest_path.is_file():
        raise ReleaseError("release bundle is missing release.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid release.json: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReleaseError("release.json must contain a JSON object")
    _validate_manifest(manifest, archive_format=archive_format)
    runtime = root / "runtime"
    if not runtime.is_dir() or not any(path.is_file() for path in runtime.rglob("*")):
        raise ReleaseError("release runtime payload is missing or empty")
    return manifest


def verify_release(
    artifact: Path,
    *,
    sidecar: Path | None = None,
    extract_to: Path | None = None,
    expect_role: str | None = None,
    expect_platform: str | None = None,
    expect_architecture: str | None = None,
    expect_version: str | None = None,
) -> dict[str, object]:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise ReleaseError(f"release artifact does not exist: {artifact}")
    sidecar = sidecar.resolve() if sidecar is not None else Path(str(artifact) + ".sha256")
    artifact_digest = _verify_archive_sidecar(artifact, sidecar)

    with tempfile.TemporaryDirectory(prefix="plasma-release-verify-") as temporary:
        temporary_root = Path(temporary)
        archive_format = _extract_archive(artifact, temporary_root)
        root = temporary_root / RELEASE_ROOT
        if not root.is_dir():
            raise ReleaseError(f"archive is missing canonical root directory {RELEASE_ROOT!r}")
        _verify_tree_hashes(root)
        manifest = _load_and_validate_manifest(root, archive_format=archive_format)

        if expect_role is not None and manifest["role"] != expect_role:
            raise ReleaseError(f"expected role {expect_role!r}, got {manifest['role']!r}")
        if expect_platform is not None and manifest["platform"] != _normalize_platform(expect_platform):
            raise ReleaseError(
                f"expected platform {_normalize_platform(expect_platform)!r}, got {manifest['platform']!r}"
            )
        if expect_architecture is not None and manifest["architecture"] != _normalize_architecture(expect_architecture):
            raise ReleaseError(
                f"expected architecture {_normalize_architecture(expect_architecture)!r}, "
                f"got {manifest['architecture']!r}"
            )
        if expect_version is not None and manifest["product_version"] != expect_version:
            raise ReleaseError(
                f"expected product_version {expect_version!r}, got {manifest['product_version']!r}"
            )

        if extract_to is not None:
            extract_to = extract_to.resolve()
            destination_root = extract_to / RELEASE_ROOT
            if destination_root.exists():
                raise ReleaseError(f"clean extraction destination already exists: {destination_root}")
            extract_to.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, destination_root)

    result = dict(manifest)
    result["artifact_sha256"] = artifact_digest
    result["artifact"] = str(artifact)
    return result


def build_release(
    *,
    repo_root: Path,
    runtime_dir: Path,
    output_dir: Path,
    role: str,
    platform_name: str,
    architecture: str,
    git_sha: str | None = None,
    config_defaults_dir: Path | None = None,
    build_timestamp: str | None = None,
) -> Path:
    role, platform_name, architecture = _validate_target(role, platform_name, architecture)
    descriptor = _load_product_descriptor(repo_root)
    version = str(descriptor["product_version"])
    git_sha = _validate_git_sha(git_sha) if git_sha is not None else _discover_git_sha(repo_root)
    build_timestamp = _canonical_build_timestamp(build_timestamp)
    components = _component_versions(repo_root, role)
    archive_format, _ = _archive_format(platform_name)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / _artifact_name(role, version, platform_name, architecture)
    sidecar = Path(str(artifact) + ".sha256")
    if artifact.exists() or sidecar.exists():
        raise ReleaseError(
            f"refusing to overwrite immutable release output: {artifact} or {sidecar} already exists"
        )

    with tempfile.TemporaryDirectory(prefix="plasma-release-build-") as temporary:
        root = Path(temporary) / RELEASE_ROOT
        runtime_files = _copy_payload(runtime_dir.resolve(), root / "runtime")
        if runtime_files == 0:
            raise ReleaseError("runtime payload must contain at least one file")
        if config_defaults_dir is not None:
            _copy_payload(config_defaults_dir.resolve(), root / "config" / "defaults")

        manifest = _manifest(
            descriptor=descriptor,
            role=role,
            platform_name=platform_name,
            architecture=architecture,
            git_sha=git_sha,
            build_timestamp=build_timestamp,
            components=components,
            archive_format=archive_format,
        )
        (root / "release.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_sha256sums(root)

        if archive_format == "zip":
            _build_zip(root, artifact)
        else:
            _build_tar_gz(root, artifact)

    _write_archive_sidecar(artifact)
    verify_release(
        artifact,
        expect_role=role,
        expect_platform=platform_name,
        expect_architecture=architecture,
        expect_version=version,
    )
    return artifact


def _print_result(payload: Mapping[str, object]) -> None:
    print(json.dumps(dict(payload), indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and verify immutable Plasma product release bundles"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="wrap an already-built runtime payload")
    build_parser.add_argument("--role", required=True, choices=sorted(ROLE_TARGETS))
    build_parser.add_argument("--platform", required=True)
    build_parser.add_argument("--architecture", required=True)
    build_parser.add_argument("--runtime-dir", required=True, type=Path)
    build_parser.add_argument("--config-defaults-dir", type=Path)
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--git-sha")
    build_parser.add_argument("--build-timestamp")
    build_parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)

    verify_parser = subparsers.add_parser("verify", help="verify an existing release artifact")
    verify_parser.add_argument("artifact", type=Path)
    verify_parser.add_argument("--sidecar", type=Path)
    verify_parser.add_argument("--extract-to", type=Path)
    verify_parser.add_argument("--expect-role", choices=sorted(ROLE_TARGETS))
    verify_parser.add_argument("--expect-platform")
    verify_parser.add_argument("--expect-architecture")
    verify_parser.add_argument("--expect-version")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            artifact = build_release(
                repo_root=args.repo_root.resolve(),
                runtime_dir=args.runtime_dir,
                config_defaults_dir=args.config_defaults_dir,
                output_dir=args.output_dir.resolve(),
                role=args.role,
                platform_name=args.platform,
                architecture=args.architecture,
                git_sha=args.git_sha,
                build_timestamp=args.build_timestamp,
            )
            result = verify_release(artifact)
            _print_result(result)
            return 0
        if args.command == "verify":
            result = verify_release(
                args.artifact,
                sidecar=args.sidecar,
                extract_to=args.extract_to,
                expect_role=args.expect_role,
                expect_platform=args.expect_platform,
                expect_architecture=args.expect_architecture,
                expect_version=args.expect_version,
            )
            _print_result(result)
            return 0
    except (ReleaseError, OSError) as exc:
        print(f"product-release: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
