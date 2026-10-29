"""Host-only single PPU deployment entry planning; never performs installation.

Both Console and SWPC must target the EXISTING Bootstrap deployment endpoint
and deployment lock/journal. The installed Bootstrap currently only supports
PS runtime: engineering modules and FPGA Image installation are intentionally
NOT_QUALIFIED, not dynamically dispatched or privileged here.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Mapping

DEPLOYMENT_API = "/v1/deployments"
DEPLOYMENT_LOCK = "/var/lib/plasma-bootstrap/deployment.lock"
DEPLOYMENT_JOURNAL = "/var/lib/plasma-bootstrap/deployment.json"
# The first three #1207 modules are acceptance fixtures, not a permanent module
# allowlist. Package admission is based on a reviewed source/publisher and a
# trusted target profile, neither of which is furnished by a module name.
FIRST_ACCEPTANCE_MODULES = ("wordport", "openocd-integration", "abtest")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
SAFE_VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
PACKAGE_SCHEMA = "plasma.ppu.package.v1"
PACKAGE_KINDS = frozenset({"native-c", "python", "fpga-image"})
MAX_PACKAGE_FILES = 128
MAX_PACKAGE_BYTES = 32 * 1024 * 1024


class UnifiedDeploymentError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedPackageFile:
    path: str
    sha256: str
    size: int
    executable: bool


@dataclass(frozen=True)
class VerifiedPackage:
    """Content verified for Host-only simulation; never an execution grant."""

    name: str
    kind: str
    version: str
    source_commit: str
    archive_sha256: str
    files: tuple[VerifiedPackageFile, ...]
    target: Mapping[str, str]
    install_qualified: bool = False


def _unique_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnifiedDeploymentError("PACKAGE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _safe_relative_path(name: str) -> bool:
    if not isinstance(name, str) or "\\" in name or name.startswith("/"):
        return False
    pure = PurePosixPath(name)
    return (len(pure.parts) >= 2 and pure.parts[0] == "payload"
            and ".." not in pure.parts and pure.as_posix() == name
            and not any(part in ("", ".") for part in pure.parts))


def _kind_allows_file(kind: str, file: VerifiedPackageFile) -> bool:
    """Keep the three package formats distinct; a name is never an exec grant."""
    path = file.path
    if kind == "native-c":
        if path.startswith("payload/bin/"):
            return file.executable
        if path.startswith("payload/lib/"):
            return not file.executable and path.endswith((".so", ".a"))
        if path.startswith("payload/include/"):
            return not file.executable and path.endswith((".h", ".hpp"))
        return False
    if kind == "python":
        return (path.startswith(("payload/python/", "payload/scripts/",
                                 "payload/software/python/"))
                and not file.executable
                and path.endswith((".py", ".pyi", ".json", ".toml", ".ini",
                                   ".yaml", ".yml", ".txt")))
    if kind == "fpga-image":
        return (path.startswith("payload/fpga/") and not file.executable
                and path.endswith((".bit", ".bin", ".hwh", ".json")))
    return False


def verify_host_only_package(
    archive_path: Path, *, expected_sha256: str, source_commit: str,
    target_profile: Mapping[str, str],
) -> VerifiedPackage:
    """Strict generic archive contract. Never installs, loads PL or runs code.

    The target_profile is provided by the trusted caller, never by the archive.
    SHA-256 proves integrity only; publisher/source approval is a later live gate.
    """
    if (type(expected_sha256) is not str or not SHA64.fullmatch(expected_sha256)
            or type(source_commit) is not str or not SHA40.fullmatch(source_commit)):
        raise UnifiedDeploymentError("PACKAGE_PROVENANCE_FORMAT_INVALID")
    if (not isinstance(archive_path, Path) or archive_path.is_symlink()
            or not archive_path.is_file() or archive_path.stat().st_size > MAX_PACKAGE_BYTES):
        raise UnifiedDeploymentError("PACKAGE_ARCHIVE_UNTRUSTED")
    if not isinstance(target_profile, Mapping) or set(target_profile) != {"platform", "board", "fpga_part"}:
        raise UnifiedDeploymentError("PACKAGE_TARGET_PROFILE_INVALID")
    if any(type(value) is not str or not SAFE_VERSION.fullmatch(value) for value in target_profile.values()):
        raise UnifiedDeploymentError("PACKAGE_TARGET_PROFILE_INVALID")
    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise UnifiedDeploymentError("PACKAGE_ARCHIVE_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names) != len(set(names)) or len(infos) > MAX_PACKAGE_FILES + 1
                    or sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES
                    or "manifest.json" not in names or any(
                        info.is_dir() or info.flag_bits & 1
                        or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                        or (info.filename != "manifest.json" and not _safe_relative_path(info.filename))
                        for info in infos)):
                raise UnifiedDeploymentError("PACKAGE_FILE_SET_DENIED")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 64 * 1024:
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_TOO_LARGE")
            manifest = json.loads(archive.read(manifest_info), object_pairs_hook=_unique_json_pairs)
            if not isinstance(manifest, dict):
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_INVALID")
            kind = manifest.get("kind")
            expected_fields = {"schema", "name", "kind", "version", "source_commit", "target", "files"}
            if kind == "fpga-image":
                expected_fields.add("fpga_pair")
            if (set(manifest) != expected_fields or manifest["schema"] != PACKAGE_SCHEMA
                    or kind not in PACKAGE_KINDS
                    or type(manifest["name"]) is not str or not SAFE_NAME.fullmatch(manifest["name"])
                    or type(manifest["version"]) is not str or not SAFE_VERSION.fullmatch(manifest["version"])
                    or manifest["source_commit"] != source_commit
                    or not isinstance(manifest["target"], dict)
                    or manifest["target"] != dict(target_profile)
                    or not isinstance(manifest["files"], list)
                    or not 1 <= len(manifest["files"]) <= MAX_PACKAGE_FILES):
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_CONTENT_DENIED")
            verified_files = []
            for entry in manifest["files"]:
                if (not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size", "executable"}
                        or type(entry["path"]) is not str
                        or not _safe_relative_path(entry["path"])
                        or type(entry["sha256"]) is not str or not SHA64.fullmatch(entry["sha256"])
                        or type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_PACKAGE_BYTES
                        or type(entry["executable"]) is not bool):
                    raise UnifiedDeploymentError("PACKAGE_FILE_METADATA_DENIED")
                name = entry["path"]
                if name not in names:
                    raise UnifiedDeploymentError("PACKAGE_MEMBER_MISSING")
                info = archive.getinfo(name)
                if info.file_size != entry["size"]:
                    raise UnifiedDeploymentError("PACKAGE_FILE_SIZE_MISMATCH")
                content_digest = hashlib.sha256()
                with archive.open(info) as member:
                    for chunk in iter(lambda: member.read(64 * 1024), b""):
                        content_digest.update(chunk)
                if content_digest.hexdigest() != entry["sha256"]:
                    raise UnifiedDeploymentError("PACKAGE_FILE_SHA256_MISMATCH")
                verified_files.append(VerifiedPackageFile(**entry))
            file_names = {entry.path for entry in verified_files}
            if file_names | {"manifest.json"} != set(names) or len(file_names) != len(verified_files):
                raise UnifiedDeploymentError("PACKAGE_UNDECLARED_OR_DUPLICATE_FILES")
            if any(not _kind_allows_file(kind, entry) for entry in verified_files):
                raise UnifiedDeploymentError("PACKAGE_KIND_FILE_DENIED")
            if (kind == "native-c" and not any(entry.executable for entry in verified_files)):
                raise UnifiedDeploymentError("PACKAGE_NATIVE_EXECUTABLE_MISSING")
            if kind == "python" and not any(entry.path.endswith(".py") for entry in verified_files):
                raise UnifiedDeploymentError("PACKAGE_PYTHON_SOURCE_MISSING")
            if kind == "fpga-image":
                pair = manifest["fpga_pair"]
                if (not isinstance(pair, dict) or set(pair) != {"image", "handoff"}
                        or pair["image"] not in file_names or pair["handoff"] not in file_names
                        or not pair["image"].endswith((".bin", ".bit"))
                        or not pair["handoff"].endswith(".hwh")
                        or any(entry.executable for entry in verified_files)):
                    raise UnifiedDeploymentError("PACKAGE_FPGA_PAIR_DENIED")
            return VerifiedPackage(
                manifest["name"], kind, manifest["version"], source_commit,
                expected_sha256, tuple(verified_files), dict(target_profile),
            )
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, UnifiedDeploymentError):
            raise
        raise UnifiedDeploymentError("PACKAGE_PARSE_DENIED") from exc


class DeploymentKind(str, Enum):
    PPU_RUNTIME = "ppu-runtime"
    ENGINEERING_MODULE = "engineering-module"
    FPGA_IMAGE = "fpga-image"


class IntegrationState(str, Enum):
    EXISTING_RUNTIME = "existing-runtime"
    BLOCKED_NOT_QUALIFIED = "blocked-not-qualified"


@dataclass(frozen=True)
class UnifiedDeploymentIntent:
    kind: DeploymentKind
    module: str | None
    source_commit: str
    artifact_sha256: str
    state: IntegrationState
    api_path: str = DEPLOYMENT_API
    shared_lock: str = DEPLOYMENT_LOCK
    shared_journal: str = DEPLOYMENT_JOURNAL

    def to_descriptor(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "module": self.module,
            "source_commit": self.source_commit,
            "artifact_sha256": self.artifact_sha256,
            "integration_state": self.state.value,
            "api_path": self.api_path,
            "shared_lock": self.shared_lock,
            "shared_journal": self.shared_journal,
            "no_deployment": True,
        }


def plan_unified_deployment(
    kind: DeploymentKind,
    *,
    source_commit: str,
    artifact_sha256: str,
    module: str | None = None,
) -> UnifiedDeploymentIntent:
    """Construct a typed plan. Not an authorization token or deploy request.

    Actual authentication must be device-derived, bound to the active Master
    generation and checked at dispatch. A verified checksum is not a publisher
    signature; Master-controlled Python must never execute as Root.
    """
    if not isinstance(kind, DeploymentKind):
        raise UnifiedDeploymentError("UNKNOWN_DEPLOYMENT_KIND")
    if not isinstance(source_commit, str) or not SHA40.fullmatch(source_commit):
        raise UnifiedDeploymentError("SOURCE_COMMIT_REQUIRED")
    if not isinstance(artifact_sha256, str) or not SHA64.fullmatch(artifact_sha256):
        raise UnifiedDeploymentError("ARTIFACT_SHA256_REQUIRED")
    if kind is DeploymentKind.ENGINEERING_MODULE:
        if type(module) is not str or not SAFE_NAME.fullmatch(module):
            raise UnifiedDeploymentError("INVALID_ENGINEERING_MODULE_NAME")
        state = IntegrationState.BLOCKED_NOT_QUALIFIED
    elif kind is DeploymentKind.PPU_RUNTIME:
        if module is not None:
            raise UnifiedDeploymentError("RUNTIME_MODULE_SELECTOR_DENIED")
        state = IntegrationState.EXISTING_RUNTIME
    else:
        if module is not None:
            raise UnifiedDeploymentError("FPGA_MODULE_SELECTOR_DENIED")
        state = IntegrationState.BLOCKED_NOT_QUALIFIED
    return UnifiedDeploymentIntent(kind, module, source_commit, artifact_sha256, state)


def admit_existing_bootstrap_request(body: Mapping[str, object]) -> dict[str, str]:
    """Fail-closed admission BEFORE the existing Bootstrap runtime request.

    Only PPU_RUNTIME is deployed by today's Bootstrap Coordinator/Installer.
    Engineers can package all three modules, but must not send them into
    the PS-only Release Installer until a qualified unified Z2 target adapter
    exists, with Source Pin, immutable release and hardware quiescence checks.
    """
    if not isinstance(body, Mapping):
        raise UnifiedDeploymentError("INVALID_DEPLOYMENT_REQUEST")
    kind = body.get("kind", DeploymentKind.PPU_RUNTIME.value)
    if kind != DeploymentKind.PPU_RUNTIME.value:
        if kind == DeploymentKind.ENGINEERING_MODULE.value:
            raise UnifiedDeploymentError("ENGINEERING_INSTALL_NOT_QUALIFIED")
        if kind == DeploymentKind.FPGA_IMAGE.value:
            raise UnifiedDeploymentError("FPGA_IMAGE_INSTALL_NOT_QUALIFIED")
        raise UnifiedDeploymentError("UNKNOWN_DEPLOYMENT_KIND")
    if "module" in body:
        raise UnifiedDeploymentError("MODULE_NOT_ALLOWED_IN_RUNTIME_INSTALL")
    if "source_commit" in body or "artifact_sha256" in body:
        # The runtime upload ID points to a committed archive + sidecar;
        # provenance must be checked by the installed coordinator/installer.
        raise UnifiedDeploymentError("CALLER_PROVIDED_PROVENANCE_DENIED")
    # Strip only one explicitly admitted discriminator, preserving the
    # existing exact field-set validation performed by Bootstrap.
    return {k: v for k, v in body.items() if k != "kind"}
