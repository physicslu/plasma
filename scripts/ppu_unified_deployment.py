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
PACKAGE_ACTIONS = frozenset({"install", "verify", "activate", "rollback"})
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
    actions: tuple[str, ...] = ()  # Declarative intent, never executable authority.


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
    archive_path: Path, *, expected_sha256: str, source_commit: str | None,
    target_profile: Mapping[str, str],
) -> VerifiedPackage:
    """Strict generic archive contract. Never installs, loads PL or runs code.

    The target_profile is provided by the trusted caller, never by the archive.
    SHA-256 proves integrity only; publisher/source approval is a later live gate.
    """
    if (type(expected_sha256) is not str or not SHA64.fullmatch(expected_sha256)
            or (source_commit is not None and
                (type(source_commit) is not str or not SHA40.fullmatch(source_commit)))):
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
            permitted_fields = (expected_fields, expected_fields | {"actions"})
            if (set(manifest) not in permitted_fields or manifest["schema"] != PACKAGE_SCHEMA
                    or kind not in PACKAGE_KINDS
                    or type(manifest["name"]) is not str or not SAFE_NAME.fullmatch(manifest["name"])
                    or type(manifest["version"]) is not str or not SAFE_VERSION.fullmatch(manifest["version"])
                    or type(manifest["source_commit"]) is not str
                    or not SHA40.fullmatch(manifest["source_commit"])
                    or (source_commit is not None and manifest["source_commit"] != source_commit)
                    or not isinstance(manifest["target"], dict)
                    or manifest["target"] != dict(target_profile)
                    or not isinstance(manifest["files"], list)
                    or not 1 <= len(manifest["files"]) <= MAX_PACKAGE_FILES):
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_CONTENT_DENIED")
            actions = manifest.get("actions", [])
            if ("actions" in manifest and
                    (type(actions) is not list or not 1 <= len(actions) <= 4
                     or any(type(action) is not str or action not in PACKAGE_ACTIONS
                            for action in actions)
                     or len(set(actions)) != len(actions))):
                raise UnifiedDeploymentError("PACKAGE_ACTIONS_DENIED")
            verified_files = []
            for entry in manifest["files"]:
                if (not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size", "executable"}
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
                manifest["name"], kind, manifest["version"], manifest["source_commit"],
                expected_sha256, tuple(verified_files), dict(target_profile),
                actions=tuple(actions),
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


# PR2: versioned, multi-component bundle. All semantics here are data-only.
# Unknown component kinds are accepted as opaque NON-EXECUTABLE resources;
# only explicitly qualified, separately reviewed handlers may later use them.
BUNDLE_SCHEMA = "plasma.ppu.bundle.v2"
BUNDLE_KIND = "bundle"
MAX_BUNDLE_COMPONENTS = 32
BUNDLE_KNOWN_KINDS = frozenset({"python", "native-c", "fpga-image"})


@dataclass(frozen=True)
class VerifiedBundleComponent:
    id: str
    kind: str
    version: str
    requires: tuple[str, ...]
    files: tuple[VerifiedPackageFile, ...]


@dataclass(frozen=True)
class VerifiedBundle:
    name: str
    kind: str
    version: str
    source_commit: str
    archive_sha256: str
    files: tuple[VerifiedPackageFile, ...]
    target: Mapping[str, str]
    components: tuple[VerifiedBundleComponent, ...]
    purpose: str
    install_qualified: bool = False
    actions: tuple[str, ...] = ()


def _bundle_component_file_allowed(kind: str, component_id: str, member: VerifiedPackageFile) -> bool:
    prefix = f"payload/components/{component_id}/"
    if not member.path.startswith(prefix):
        return False
    suffix = member.path[len(prefix):]
    if "/" not in suffix or not suffix or suffix.startswith("/"):
        return False
    if kind == "python":
        return (
            suffix.startswith(("python/", "scripts/", "config/"))
            and not member.executable
            and suffix.endswith((".py", ".pyi", ".json", ".toml", ".ini", ".yaml", ".yml", ".txt"))
        )
    if kind == "native-c":
        if suffix.startswith("bin/"):
            return member.executable
        if suffix.startswith("lib/"):
            return not member.executable and suffix.endswith((".so", ".a"))
        if suffix.startswith("include/"):
            return not member.executable and suffix.endswith((".h", ".hpp"))
        return False
    if kind == "fpga-image":
        return (
            suffix.startswith("fpga/") and not member.executable
            and suffix.endswith((".bit", ".bin", ".hwh", ".json"))
        )
    # Open-ended RESOURCE kinds: firmware images, IC profiles, calibration data,
    # catalog files, ML models, OpenOCD configs, etc. No execution entitlement.
    return not member.executable and suffix.startswith(("data/", "assets/"))


def _verify_bundle_dependencies(components: tuple[VerifiedBundleComponent, ...]) -> None:
    by_id = {component.id: component for component in components}
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise UnifiedDeploymentError("BUNDLE_DEPENDENCY_CYCLE")
        if name in visited:
            return
        if name not in by_id:
            raise UnifiedDeploymentError("BUNDLE_DEPENDENCY_UNKNOWN")
        visiting.add(name)
        for dependency in by_id[name].requires:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in by_id:
        visit(name)


def verify_host_only_bundle(
    archive_path: Path, *, expected_sha256: str, source_commit: str | None,
    target_profile: Mapping[str, str],
) -> VerifiedBundle:
    """Verify a v2 multi-component artifact; NEVER install or execute it.

    Publisher provenance, Master authorization, privilege and Site ownership
    are not established by a valid manifest or checksum.
    """
    if (type(expected_sha256) is not str or not SHA64.fullmatch(expected_sha256)
            or (source_commit is not None and
                (type(source_commit) is not str or not SHA40.fullmatch(source_commit)))):
        raise UnifiedDeploymentError("BUNDLE_PROVENANCE_FORMAT_INVALID")
    if (not isinstance(archive_path, Path) or archive_path.is_symlink()
            or not archive_path.is_file() or archive_path.stat().st_size > MAX_PACKAGE_BYTES):
        raise UnifiedDeploymentError("BUNDLE_ARCHIVE_UNTRUSTED")
    if (not isinstance(target_profile, Mapping)
            or set(target_profile) != {"platform", "board", "fpga_part"}
            or any(type(value) is not str or not SAFE_VERSION.fullmatch(value)
                   for value in target_profile.values())):
        raise UnifiedDeploymentError("BUNDLE_TARGET_PROFILE_INVALID")
    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise UnifiedDeploymentError("BUNDLE_ARCHIVE_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names) != len(set(names)) or len(infos) > MAX_PACKAGE_FILES + 1
                    or sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES
                    or "manifest.json" not in names or any(
                        info.is_dir() or info.flag_bits & 1
                        or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                        or (info.filename != "manifest.json"
                            and not _safe_relative_path(info.filename))
                        for info in infos)):
                raise UnifiedDeploymentError("BUNDLE_FILE_SET_DENIED")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 64 * 1024:
                raise UnifiedDeploymentError("BUNDLE_MANIFEST_TOO_LARGE")
            manifest = json.loads(archive.read(manifest_info), object_pairs_hook=_unique_json_pairs)
            if not isinstance(manifest, dict):
                raise UnifiedDeploymentError("BUNDLE_MANIFEST_INVALID")
            fields = {"schema", "name", "version", "source_commit", "target",
                      "purpose", "components"}
            if (set(manifest) not in (fields, fields | {"actions"})
                    or manifest["schema"] != BUNDLE_SCHEMA
                    or type(manifest["name"]) is not str or not SAFE_NAME.fullmatch(manifest["name"])
                    or type(manifest["version"]) is not str or not SAFE_VERSION.fullmatch(manifest["version"])
                    or type(manifest["source_commit"]) is not str
                    or not SHA40.fullmatch(manifest["source_commit"])
                    or (source_commit is not None and source_commit != manifest["source_commit"])
                    or type(manifest["purpose"]) is not str
                    or not SAFE_NAME.fullmatch(manifest["purpose"])
                    or type(manifest["target"]) is not dict
                    or manifest["target"] != dict(target_profile)
                    or type(manifest["components"]) is not list
                    or not 1 <= len(manifest["components"]) <= MAX_BUNDLE_COMPONENTS):
                raise UnifiedDeploymentError("BUNDLE_MANIFEST_CONTENT_DENIED")
            actions = manifest.get("actions", [])
            if (type(actions) is not list or len(actions) > 4
                    or len(actions) != len(set(a for a in actions if type(a) is str))
                    or any(type(a) is not str or a not in PACKAGE_ACTIONS for a in actions)):
                raise UnifiedDeploymentError("BUNDLE_ACTIONS_DENIED")
            components: list[VerifiedBundleComponent] = []
            files: list[VerifiedPackageFile] = []
            ids: set[str] = set()
            for entry in manifest["components"]:
                if (type(entry) is not dict
                        or set(entry) != {"id", "kind", "version", "requires", "files"}
                        or type(entry["id"]) is not str or not SAFE_NAME.fullmatch(entry["id"])
                        or entry["id"] in ids
                        or type(entry["kind"]) is not str or not SAFE_NAME.fullmatch(entry["kind"])
                        or type(entry["version"]) is not str or not SAFE_VERSION.fullmatch(entry["version"])
                        or type(entry["requires"]) is not list
                        or any(type(dep) is not str or not SAFE_NAME.fullmatch(dep)
                               for dep in entry["requires"])
                        or len(entry["requires"]) != len(set(entry["requires"]))
                        or type(entry["files"]) is not list or not entry["files"]):
                    raise UnifiedDeploymentError("BUNDLE_COMPONENT_INVALID")
                ids.add(entry["id"])
                component_files: list[VerifiedPackageFile] = []
                for item in entry["files"]:
                    if (type(item) is not dict
                            or set(item) != {"path", "sha256", "size", "executable"}
                            or type(item["path"]) is not str or not _safe_relative_path(item["path"])
                            or type(item["sha256"]) is not str or not SHA64.fullmatch(item["sha256"])
                            or type(item["size"]) is not int or not 0 <= item["size"] <= MAX_PACKAGE_BYTES
                            or type(item["executable"]) is not bool):
                        raise UnifiedDeploymentError("BUNDLE_FILE_METADATA_DENIED")
                    verified = VerifiedPackageFile(**item)
                    if not _bundle_component_file_allowed(entry["kind"], entry["id"], verified):
                        raise UnifiedDeploymentError("BUNDLE_COMPONENT_FILE_KIND_DENIED")
                    if verified.path not in names:
                        raise UnifiedDeploymentError("BUNDLE_MEMBER_MISSING")
                    info = archive.getinfo(verified.path)
                    if info.file_size != verified.size:
                        raise UnifiedDeploymentError("BUNDLE_FILE_SIZE_MISMATCH")
                    digest = hashlib.sha256()
                    with archive.open(info) as stream:
                        for chunk in iter(lambda: stream.read(65536), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != verified.sha256:
                        raise UnifiedDeploymentError("BUNDLE_FILE_SHA256_MISMATCH")
                    component_files.append(verified)
                    files.append(verified)
                if (entry["kind"] == "python"
                        and not any(f.path.endswith(".py") for f in component_files)):
                    raise UnifiedDeploymentError("BUNDLE_PYTHON_SOURCE_MISSING")
                if (entry["kind"] == "native-c"
                        and not any(f.executable for f in component_files)):
                    raise UnifiedDeploymentError("BUNDLE_NATIVE_BINARY_MISSING")
                if entry["kind"] == "fpga-image":
                    image = [f for f in component_files if f.path.endswith((".bit", ".bin"))]
                    handoff = [f for f in component_files if f.path.endswith(".hwh")]
                    if len(image) != 1 or len(handoff) != 1:
                        raise UnifiedDeploymentError("BUNDLE_FPGA_PAIR_DENIED")
                components.append(VerifiedBundleComponent(
                    entry["id"], entry["kind"], entry["version"],
                    tuple(entry["requires"]), tuple(component_files),
                ))
            if (len(files) > MAX_PACKAGE_FILES or len({f.path for f in files}) != len(files)
                    or set(names) != {"manifest.json"} | {f.path for f in files}):
                raise UnifiedDeploymentError("BUNDLE_UNDECLARED_OR_DUPLICATE_FILES")
            _verify_bundle_dependencies(tuple(components))
            return VerifiedBundle(
                manifest["name"], BUNDLE_KIND, manifest["version"],
                manifest["source_commit"], expected_sha256, tuple(files),
                dict(target_profile), tuple(components), manifest["purpose"],
                actions=tuple(actions),
            )
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, UnifiedDeploymentError):
            raise
        raise UnifiedDeploymentError("BUNDLE_PARSE_DENIED") from exc


def verify_host_only_artifact(
    archive_path: Path, *, expected_sha256: str, source_commit: str | None,
    target_profile: Mapping[str, str],
) -> VerifiedPackage | VerifiedBundle:
    """Select v1/v2 parser by on-disk schema; neither branch grants execution."""
    if not isinstance(archive_path, Path) or archive_path.is_symlink():
        raise UnifiedDeploymentError("PACKAGE_ARCHIVE_UNTRUSTED")
    try:
        if archive_path.stat().st_size > MAX_PACKAGE_BYTES:
            raise UnifiedDeploymentError("PACKAGE_ARCHIVE_UNTRUSTED")
        with zipfile.ZipFile(archive_path) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 64 * 1024:
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_TOO_LARGE")
            probe = json.loads(archive.read(info), object_pairs_hook=_unique_json_pairs)
            if not isinstance(probe, dict):
                raise UnifiedDeploymentError("PACKAGE_MANIFEST_INVALID")
            schema = probe.get("schema")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as exc:
        if isinstance(exc, UnifiedDeploymentError):
            raise
        raise UnifiedDeploymentError("PACKAGE_SCHEMA_PROBE_DENIED") from exc
    if schema == PACKAGE_SCHEMA:
        return verify_host_only_package(
            archive_path, expected_sha256=expected_sha256,
            source_commit=source_commit, target_profile=target_profile,
        )
    if schema == BUNDLE_SCHEMA:
        return verify_host_only_bundle(
            archive_path, expected_sha256=expected_sha256,
            source_commit=source_commit, target_profile=target_profile,
        )
    if schema is None:
        # v1 preflight used to reject an invalid ZIP member before interpreting
        # a malformed/absent schema. Preserve that fail-closed diagnostic.
        return verify_host_only_package(
            archive_path, expected_sha256=expected_sha256,
            source_commit=source_commit, target_profile=target_profile,
        )
    raise UnifiedDeploymentError("PACKAGE_SCHEMA_UNSUPPORTED")
