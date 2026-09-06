#!/usr/bin/env python3
"""Install a verified Plasma PPU release on a PYNQ-Z2 PS-only Linux target.

The bootstrap is deliberately compatible with Python 3.10 so the stock PYNQ
image can launch it. Plasma Server and Plasma Gateway never use that interpreter:
``--plasma-python`` must identify a separate Plasma-owned ARMv7 Python >= 3.11.

This installer keeps the hardware boundary closed. It installs only the PS
software node and cannot load PL, control target power, or program a real IC.
"""

from __future__ import annotations

import argparse
import grp
import hashlib
import ipaddress
import json
import os
import platform
import pwd
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

MIN_PYTHON = (3, 11, 0)
EXPECTED_CONTRACTS = {"plasma_protocol": "3.3", "web_rest_api": "3"}
EXPECTED_HARDWARE_BOUNDARY = {
    "loads_fpga": False,
    "accesses_pl": False,
    "changes_target_power": False,
    "programs_real_ic": False,
}
MAX_ARCHIVE_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
RELEASE_ROOT = "plasma-release"
SERVICE_USER = "plasma"
SERVICE_GROUP = "plasma"


class Z2InstallerError(RuntimeError):
    """Raised when installer verification, activation, or rollback fails."""


@dataclass(frozen=True)
class PythonRuntime:
    path: Path
    version: str
    architecture: str


@dataclass(frozen=True)
class VerifiedRelease:
    root: Path
    manifest: Mapping[str, object]
    runtime_manifest: Mapping[str, object]
    archive_sha256: str

    @property
    def product_version(self) -> str:
        return str(self.manifest["product_version"])

    @property
    def git_sha(self) -> str:
        return str(self.manifest["git_sha"])

    @property
    def release_id(self) -> str:
        return f"{self.product_version}-{self.git_sha[:12]}"


@dataclass(frozen=True)
class InstallPaths:
    product_root: Path = Path("/opt/plasma")
    config_root: Path = Path("/etc/plasma")
    state_root: Path = Path("/var/lib/plasma")
    log_root: Path = Path("/var/log/plasma")
    systemd_root: Path = Path("/etc/systemd/system")

    @property
    def releases_root(self) -> Path:
        return self.product_root / "releases"

    @property
    def current(self) -> Path:
        return self.product_root / "current"

    @property
    def install_root(self) -> Path:
        return self.product_root / "install"


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    mode: int | None
    uid: int | None
    gid: int | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sidecar(artifact: Path, sidecar: Path | None = None) -> str:
    sidecar = Path(str(artifact) + ".sha256") if sidecar is None else sidecar
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise Z2InstallerError(f"cannot read detached SHA-256 sidecar: {exc}") from exc
    if len(fields) != 2 or fields[1].lstrip("*") != artifact.name:
        raise Z2InstallerError("detached SHA-256 sidecar does not identify the release artifact")
    expected = fields[0].lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise Z2InstallerError("detached SHA-256 sidecar contains an invalid digest")
    actual = _sha256(artifact)
    if actual != expected:
        raise Z2InstallerError("release artifact SHA-256 does not match detached sidecar")
    return actual


def _safe_member_name(name: str) -> PurePosixPath:
    canonical_name = name.rstrip("/")
    if not canonical_name or "\\" in canonical_name or canonical_name.startswith("/"):
        raise Z2InstallerError(f"unsafe archive member path: {name!r}")
    pure = PurePosixPath(canonical_name)
    if ".." in pure.parts or not pure.parts or pure.parts[0] != RELEASE_ROOT:
        raise Z2InstallerError(f"archive member escapes canonical release root: {name!r}")
    if pure.as_posix() != canonical_name:
        raise Z2InstallerError(f"archive member is not canonical POSIX form: {name!r}")
    return pure


def _extract_verified_tar(artifact: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    file_count = 0
    expanded = 0
    try:
        archive = tarfile.open(artifact, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise Z2InstallerError(f"cannot open PPU release archive: {exc}") from exc

    with archive:
        for member in archive.getmembers():
            pure = _safe_member_name(member.name)
            canonical = pure.as_posix()
            if canonical in seen:
                raise Z2InstallerError(f"duplicate archive member: {canonical}")
            seen.add(canonical)
            target = destination / Path(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            if not member.isfile():
                raise Z2InstallerError(f"non-regular archive member is forbidden: {canonical}")
            file_count += 1
            expanded += int(member.size)
            if file_count > MAX_ARCHIVE_FILES or expanded > MAX_UNCOMPRESSED_BYTES:
                raise Z2InstallerError("release archive exceeds extraction safety limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise Z2InstallerError(f"cannot read archive member: {canonical}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            # Preserve executable bits and make the verified extraction read-only.
            target.chmod((member.mode & 0o555) | 0o400)
    return destination / RELEASE_ROOT


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Z2InstallerError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Z2InstallerError(f"{label} must be a JSON object")
    return payload


def _verify_internal_hashes(root: Path) -> None:
    sums = root / "SHA256SUMS"
    try:
        lines = sums.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Z2InstallerError(f"cannot read SHA256SUMS: {exc}") from exc

    expected: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise Z2InstallerError("invalid SHA256SUMS entry")
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
            raise Z2InstallerError(f"unsafe SHA256SUMS path: {name!r}")
        digest = digest.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise Z2InstallerError(f"invalid SHA256SUMS digest for {name!r}")
        if name in expected:
            raise Z2InstallerError(f"duplicate SHA256SUMS entry: {name}")
        expected[name] = digest

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(expected) != actual_files:
        unhashed = sorted(actual_files - set(expected))
        missing = sorted(set(expected) - actual_files)
        raise Z2InstallerError(
            f"release file set does not match SHA256SUMS: unhashed={unhashed}, missing={missing}"
        )
    for name, expected_digest in expected.items():
        if _sha256(root / name) != expected_digest:
            raise Z2InstallerError(f"internal SHA-256 mismatch: {name}")


def _verify_release_manifest(root: Path) -> dict[str, object]:
    manifest = _read_object(root / "release.json", "release.json")
    required = {
        "schema_version": 1,
        "product": "plasma",
        "role": "ppu",
        "platform": "linux",
        "architecture": "armv7l",
        "target": "linux-armv7l",
        "archive_format": "tar.gz",
        "contracts": EXPECTED_CONTRACTS,
    }
    for field, expected in required.items():
        if manifest.get(field) != expected:
            raise Z2InstallerError(
                f"release manifest mismatch for {field}: expected {expected!r}, got {manifest.get(field)!r}"
            )
    version = manifest.get("product_version")
    git_sha = manifest.get("git_sha")
    if not isinstance(version, str) or not version:
        raise Z2InstallerError("release product_version is missing")
    if (
        not isinstance(git_sha, str)
        or len(git_sha) != 40
        or any(ch not in "0123456789abcdefABCDEF" for ch in git_sha)
    ):
        raise Z2InstallerError("release git_sha must be a full 40-character hexadecimal SHA")
    layout = manifest.get("layout")
    if not isinstance(layout, dict) or layout.get("runtime") != "runtime":
        raise Z2InstallerError("release runtime layout is invalid")
    return manifest


def _verify_runtime(root: Path) -> dict[str, object]:
    runtime = root / "runtime"
    manifest = _read_object(runtime / "ppu-runtime.json", "PPU runtime manifest")
    if manifest.get("schema_version") != 1 or manifest.get("role") != "ppu":
        raise Z2InstallerError("invalid PPU runtime identity/schema")
    if manifest.get("hardware_boundary") != EXPECTED_HARDWARE_BOUNDARY:
        raise Z2InstallerError("PPU runtime hardware boundary is not closed")

    app = runtime / "ppu" / "ppu.pyz"
    if not app.is_file() or app.stat().st_size <= 0:
        raise Z2InstallerError("PPU runtime is missing ppu/ppu.pyz")

    data = manifest.get("data")
    if not isinstance(data, dict):
        raise Z2InstallerError("PPU runtime data manifest is invalid")
    catalog_rel = data.get("device_catalog_manifest")
    if not isinstance(catalog_rel, str):
        raise Z2InstallerError("PPU runtime Device Catalog manifest path is missing")
    pure = PurePosixPath(catalog_rel)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != catalog_rel:
        raise Z2InstallerError("PPU runtime Device Catalog manifest path is unsafe")
    if not (runtime / Path(*pure.parts)).is_file():
        raise Z2InstallerError("PPU runtime production Device Catalog manifest is missing")
    return manifest


def verify_release(
    artifact: Path,
    *,
    sidecar: Path | None = None,
    extract_to: Path,
) -> VerifiedRelease:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise Z2InstallerError(f"PPU release artifact is missing: {artifact}")
    archive_digest = _verify_sidecar(artifact, sidecar)
    root = _extract_verified_tar(artifact, extract_to)
    _verify_internal_hashes(root)
    manifest = _verify_release_manifest(root)
    runtime_manifest = _verify_runtime(root)
    return VerifiedRelease(root, manifest, runtime_manifest, archive_digest)


def _default_python_probe(path: Path) -> Mapping[str, object]:
    code = (
        "import json,platform,sys;"
        "print(json.dumps({'version':list(sys.version_info[:3]),"
        "'machine':platform.machine(),'executable':sys.executable}))"
    )
    try:
        completed = subprocess.run(
            [str(path), "-c", code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Z2InstallerError(f"cannot execute isolated Plasma Python {path}: {exc}") from exc
    if completed.returncode != 0:
        raise Z2InstallerError(
            f"isolated Plasma Python failed to start: {completed.stdout.strip()}"
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise Z2InstallerError("isolated Plasma Python probe returned invalid output") from exc
    if not isinstance(payload, dict):
        raise Z2InstallerError("isolated Plasma Python probe did not return an object")
    return payload


def validate_plasma_python(
    path: Path,
    *,
    product_root: Path = Path("/opt/plasma"),
    probe: Callable[[Path], Mapping[str, object]] = _default_python_probe,
) -> PythonRuntime:
    if not path.is_absolute():
        raise Z2InstallerError("--plasma-python must be an absolute path")
    resolved = path.resolve()
    python_root = (product_root / "python").resolve()
    try:
        resolved.relative_to(python_root)
    except ValueError as exc:
        raise Z2InstallerError(
            f"isolated Plasma Python must live under {python_root}; got {resolved}"
        ) from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise Z2InstallerError(f"isolated Plasma Python is not executable: {resolved}")

    payload = probe(resolved)
    raw_version = payload.get("version")
    if (
        not isinstance(raw_version, list)
        or len(raw_version) < 3
        or not all(isinstance(item, int) for item in raw_version[:3])
    ):
        raise Z2InstallerError("isolated Plasma Python probe did not report a valid version")
    version_tuple = tuple(int(item) for item in raw_version[:3])
    if version_tuple < MIN_PYTHON:
        raise Z2InstallerError(
            f"isolated Plasma Python {version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]} < required 3.11"
        )
    architecture = str(payload.get("machine", "")).lower()
    if architecture not in {"armv7", "armv7l"}:
        raise Z2InstallerError(
            f"isolated Plasma Python is not running as ARMv7: {architecture!r}"
        )
    probed_executable = Path(str(payload.get("executable", ""))).resolve()
    if probed_executable != resolved:
        raise Z2InstallerError(
            f"isolated Plasma Python executable drift: requested {resolved}, runtime reported {probed_executable}"
        )
    return PythonRuntime(
        path=resolved,
        version=".".join(str(item) for item in version_tuple),
        architecture=architecture,
    )


def _validate_gateway_host(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise Z2InstallerError("--gateway-host must be an explicit IP address") from exc
    if address.version != 4 or address.is_unspecified or address.is_loopback or address.is_multicast:
        raise Z2InstallerError("--gateway-host must be a non-loopback unicast IPv4 address")
    return str(address)


def _catalog_relative(runtime_manifest: Mapping[str, object]) -> str:
    data = runtime_manifest.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("device_catalog_manifest"), str):
        raise Z2InstallerError("runtime manifest is missing Device Catalog identity")
    return str(data["device_catalog_manifest"])


def render_ppu_config(
    *,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    state_root: Path,
    log_root: Path,
) -> str:
    for label, value in (
        ("ppu-id", ppu_id),
        ("facility-id", facility_id),
        ("display-name", display_name),
    ):
        if not value or "\n" in value or "\r" in value:
            raise Z2InstallerError(f"{label} must be a non-empty single-line value")
    return "\n".join(
        [
            "ppu:",
            f"  id: {json.dumps(ppu_id)}",
            f"  facility_id: {json.dumps(facility_id)}",
            '  model: "PYNQ-Z2"',
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


def render_systemd_units(
    *,
    paths: InstallPaths,
    python_runtime: PythonRuntime,
    gateway_host: str,
    catalog_relative: str,
) -> dict[str, str]:
    current_runtime = paths.current / "runtime"
    app = current_runtime / "ppu" / "ppu.pyz"
    config = paths.config_root / "ppu.yaml"
    catalog = current_runtime / Path(*PurePosixPath(catalog_relative).parts)
    common = [
        "User=plasma",
        "Group=plasma",
        "Restart=on-failure",
        "RestartSec=2",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectHome=true",
        "ProtectSystem=strict",
        f"ReadWritePaths={paths.state_root} {paths.log_root}",
        "Environment=PYTHONUNBUFFERED=1",
        f"Environment=PLASMA_DEVICE_CATALOG_MANIFEST={catalog}",
    ]
    server = "\n".join(
        [
            "[Unit]",
            "Description=Plasma PPU Programming Server",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            *common,
            f"ExecStart={python_runtime.path} {app} server --config {config}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    gateway = "\n".join(
        [
            "[Unit]",
            "Description=Plasma Gateway",
            "After=network-online.target plasma-server.service",
            "Wants=network-online.target",
            "Requires=plasma-server.service",
            "",
            "[Service]",
            "Type=simple",
            *common,
            (
                f"ExecStart={python_runtime.path} {app} gateway "
                f"--host {gateway_host} --port 18080 "
                "--plasma-host 127.0.0.1 --plasma-port 9900 "
                f"--output-root {paths.state_root / 'gateway-output'}"
            ),
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    return {"plasma-server.service": server, "plasma-web.service": gateway}


def _ensure_service_account() -> None:
    try:
        user = pwd.getpwnam(SERVICE_USER)
    except KeyError:
        user = None
    try:
        group = grp.getgrnam(SERVICE_GROUP)
    except KeyError:
        group = None

    if user is not None or group is not None:
        if user is None or group is None or user.pw_gid != group.gr_gid:
            raise Z2InstallerError(
                "existing plasma user/group identity is incomplete or mismatched; refusing to mutate it"
            )
        return

    try:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--home-dir",
                "/var/lib/plasma",
                "--shell",
                "/usr/sbin/nologin",
                "--user-group",
                SERVICE_USER,
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Z2InstallerError(f"cannot create plasma service identity: {exc}") from exc

    try:
        user = pwd.getpwnam(SERVICE_USER)
        group = grp.getgrnam(SERVICE_GROUP)
    except KeyError as exc:
        raise Z2InstallerError("plasma service identity was not created") from exc
    if user.pw_gid != group.gr_gid:
        raise Z2InstallerError("created plasma user/group identity is inconsistent")


def _chown_tree(path: Path, user: str, group: str) -> None:
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(group).gr_gid
    for item in [path, *path.rglob("*")]:
        os.chown(item, uid, gid)


def _atomic_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(link.name + ".new")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    os.symlink(str(target), str(temporary))
    os.replace(temporary, link)


def _systemctl(*args: str) -> None:
    try:
        subprocess.run(["systemctl", *args], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Z2InstallerError(f"systemctl {' '.join(args)} failed: {exc}") from exc


def _health_ready(gateway_host: str, *, deadline_s: float = 30.0) -> dict[str, object]:
    """Probe the local Z2 Gateway without inheriting HTTP proxy settings."""
    url = f"http://{gateway_host}:18080/api/health/ready"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + deadline_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=2.0) as response:
                raw = response.read()
                status = int(response.status)
            payload = json.loads(raw.decode("utf-8"))
            if (
                status == 200
                and isinstance(payload, dict)
                and payload.get("ok") is True
                and payload.get("gateway") == "alive"
                and payload.get("execution") == "ready"
            ):
                return payload
            last = f"HTTP {status}: {payload!r}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            last = str(exc)
        time.sleep(0.25)
    raise Z2InstallerError(f"Plasma Gateway readiness deadline exceeded: {last}")


def _write_text_atomic(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(mode)
    os.replace(temporary, path)


def _write_bytes_atomic(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".rollback")
    with temporary.open("wb") as stream:
        stream.write(content)
    temporary.chmod(mode)
    os.replace(temporary, path)


def _snapshot_file(path: Path) -> FileSnapshot:
    if not path.exists() and not path.is_symlink():
        return FileSnapshot(path, False, None, None, None, None)
    if not path.is_file() or path.is_symlink():
        raise Z2InstallerError(f"refusing to overwrite non-regular managed file: {path}")
    metadata = path.stat()
    return FileSnapshot(
        path=path,
        existed=True,
        content=path.read_bytes(),
        mode=stat.S_IMODE(metadata.st_mode),
        uid=metadata.st_uid,
        gid=metadata.st_gid,
    )


def _restore_file(snapshot: FileSnapshot) -> None:
    if not snapshot.existed:
        try:
            snapshot.path.unlink()
        except FileNotFoundError:
            pass
        return
    assert snapshot.content is not None
    assert snapshot.mode is not None
    assert snapshot.uid is not None
    assert snapshot.gid is not None
    _write_bytes_atomic(snapshot.path, snapshot.content, snapshot.mode)
    os.chown(snapshot.path, snapshot.uid, snapshot.gid)


def _copy_release(verified: VerifiedRelease, target: Path) -> None:
    if target.exists():
        if not target.is_dir() or target.is_symlink():
            raise Z2InstallerError(f"release target is not a regular directory: {target}")
        existing = _read_object(target / "release.json", "installed release.json")
        if existing.get("git_sha") != verified.git_sha:
            raise Z2InstallerError(f"release directory collision at {target}")
        _verify_internal_hashes(target)
        _verify_runtime(target)
        return

    staging = target.with_name(target.name + ".staging")
    if staging.exists():
        if staging.is_symlink() or not staging.is_dir():
            raise Z2InstallerError(f"unsafe stale release staging path: {staging}")
        shutil.rmtree(staging)
    shutil.copytree(verified.root, staging)
    for item in [staging, *staging.rglob("*")]:
        if item.is_dir():
            item.chmod(0o755)
        elif item.is_file():
            item.chmod((item.stat().st_mode & 0o555) | 0o400)
    os.replace(staging, target)


def _previous_current(current: Path) -> Path | None:
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise Z2InstallerError(f"managed current path is not a symlink: {current}")
    raw = Path(os.readlink(current))
    return raw if raw.is_absolute() else (current.parent / raw).resolve()


def _rollback_activation(
    *,
    paths: InstallPaths,
    previous: Path | None,
    snapshots: Sequence[FileSnapshot],
    systemctl: Callable[..., None],
) -> None:
    errors: list[str] = []

    if previous is None:
        # Stop while the candidate units still exist, then restore/remove files.
        for service in ("plasma-web.service", "plasma-server.service"):
            try:
                systemctl("disable", "--now", service)
            except Exception as exc:  # rollback is best-effort but reported exactly
                errors.append(f"disable {service}: {exc}")
        try:
            paths.current.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"remove current: {exc}")
    else:
        try:
            _atomic_symlink(paths.current, previous)
        except OSError as exc:
            errors.append(f"restore current: {exc}")

    for snapshot in snapshots:
        try:
            _restore_file(snapshot)
        except OSError as exc:
            errors.append(f"restore {snapshot.path}: {exc}")

    try:
        systemctl("daemon-reload")
    except Exception as exc:
        errors.append(f"daemon-reload: {exc}")

    if previous is not None:
        for service in ("plasma-server.service", "plasma-web.service"):
            try:
                systemctl("restart", service)
            except Exception as exc:
                errors.append(f"restart {service}: {exc}")

    if errors:
        raise Z2InstallerError("rollback incomplete: " + "; ".join(errors))


def install_release(
    verified: VerifiedRelease,
    *,
    python_runtime: PythonRuntime,
    gateway_host: str,
    paths: InstallPaths,
    ppu_id: str,
    facility_id: str,
    display_name: str,
    systemctl: Callable[..., None] = _systemctl,
    health_check: Callable[[str], Mapping[str, object]] = _health_ready,
    ensure_service_account: Callable[[], None] = _ensure_service_account,
) -> dict[str, object]:
    gateway_host = _validate_gateway_host(gateway_host)
    release_target = paths.releases_root / verified.release_id
    previous = _previous_current(paths.current)

    config_path = paths.config_root / "ppu.yaml"
    server_unit = paths.systemd_root / "plasma-server.service"
    gateway_unit = paths.systemd_root / "plasma-web.service"
    snapshots = tuple(_snapshot_file(path) for path in (config_path, server_unit, gateway_unit))

    paths.releases_root.mkdir(parents=True, exist_ok=True)
    paths.install_root.mkdir(parents=True, exist_ok=True)
    paths.config_root.mkdir(parents=True, exist_ok=True)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    paths.log_root.mkdir(parents=True, exist_ok=True)
    ensure_service_account()
    _copy_release(verified, release_target)
    _chown_tree(paths.state_root, SERVICE_USER, SERVICE_GROUP)
    _chown_tree(paths.log_root, SERVICE_USER, SERVICE_GROUP)

    config = render_ppu_config(
        ppu_id=ppu_id,
        facility_id=facility_id,
        display_name=display_name,
        state_root=paths.state_root,
        log_root=paths.log_root,
    )
    units = render_systemd_units(
        paths=paths,
        python_runtime=python_runtime,
        gateway_host=gateway_host,
        catalog_relative=_catalog_relative(verified.runtime_manifest),
    )

    _write_text_atomic(config_path, config, 0o640)
    os.chown(
        config_path,
        pwd.getpwnam(SERVICE_USER).pw_uid,
        grp.getgrnam(SERVICE_GROUP).gr_gid,
    )
    _write_text_atomic(server_unit, units["plasma-server.service"])
    _write_text_atomic(gateway_unit, units["plasma-web.service"])
    _atomic_symlink(paths.current, release_target)

    try:
        systemctl("daemon-reload")
        systemctl("enable", "--now", "plasma-server.service")
        systemctl("enable", "--now", "plasma-web.service")
        readiness = dict(health_check(gateway_host))
    except Exception as activation_exc:
        try:
            _rollback_activation(
                paths=paths,
                previous=previous,
                snapshots=snapshots,
                systemctl=systemctl,
            )
        except Exception as rollback_exc:
            raise Z2InstallerError(
                f"activation failed ({activation_exc}); rollback also failed ({rollback_exc})"
            ) from rollback_exc
        raise Z2InstallerError(
            f"activation failed and previous configuration/release was restored: {activation_exc}"
        ) from activation_exc

    evidence = {
        "schema_version": 1,
        "result": "PASS",
        "evidence_level": "z2-ps-installer-local-health",
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
        },
        "gateway_host": gateway_host,
        "gateway_readiness": {
            "gateway": readiness.get("gateway"),
            "execution": readiness.get("execution"),
        },
        "previous_release": str(previous) if previous is not None else None,
        "hardware_boundary": EXPECTED_HARDWARE_BOUNDARY,
        "not_claimed": [
            "Managed PS Loopback",
            "PS-to-PL",
            "FPGA execution",
            "Site I/O",
            "target power",
            "real IC programming",
            "8-Site hardware concurrency",
        ],
    }
    _write_text_atomic(
        paths.install_root / "last-install.json",
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
    )
    return evidence


def _require_target_baseline() -> None:
    if platform.system() != "Linux":
        raise Z2InstallerError("Z2 installer requires Linux")
    machine = platform.machine().lower()
    if machine not in {"armv7", "armv7l"}:
        raise Z2InstallerError(f"Z2 installer requires ARMv7, got {machine}")
    if not Path("/run/systemd/system").is_dir():
        raise Z2InstallerError("systemd is not running")
    if os.geteuid() != 0:
        raise Z2InstallerError("installation requires root privileges")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install a verified Plasma PPU release on PYNQ-Z2 without replacing PYNQ System Python"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="verify release integrity and PS-only runtime boundary")
    verify.add_argument("--release-artifact", required=True, type=Path)
    verify.add_argument("--sidecar", type=Path)

    install = sub.add_parser("install", help="install and activate one PS-only PPU release")
    install.add_argument("--release-artifact", required=True, type=Path)
    install.add_argument("--sidecar", type=Path)
    install.add_argument("--plasma-python", required=True, type=Path)
    install.add_argument("--gateway-host", required=True)
    install.add_argument("--ppu-id", default="z2-dev-01")
    install.add_argument("--facility-id", default="lab")
    install.add_argument("--display-name", default="Plasma Z2 PS")
    install.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    install.add_argument("--config-root", type=Path, default=Path("/etc/plasma"))
    install.add_argument("--state-root", type=Path, default=Path("/var/lib/plasma"))
    install.add_argument("--log-root", type=Path, default=Path("/var/log/plasma"))
    install.add_argument("--systemd-root", type=Path, default=Path("/etc/systemd/system"))
    args = parser.parse_args(argv)

    try:
        with tempfile.TemporaryDirectory(prefix="plasma-z2-installer-") as temporary:
            verified = verify_release(
                args.release_artifact,
                sidecar=args.sidecar,
                extract_to=Path(temporary) / "verified",
            )
            if args.command == "verify":
                print(
                    json.dumps(
                        {
                            "result": "PASS",
                            "product_version": verified.product_version,
                            "git_sha": verified.git_sha,
                            "archive_sha256": verified.archive_sha256,
                            "hardware_boundary": EXPECTED_HARDWARE_BOUNDARY,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0

            _require_target_baseline()
            paths = InstallPaths(
                product_root=args.product_root,
                config_root=args.config_root,
                state_root=args.state_root,
                log_root=args.log_root,
                systemd_root=args.systemd_root,
            )
            python_runtime = validate_plasma_python(
                args.plasma_python,
                product_root=paths.product_root,
            )
            evidence = install_release(
                verified,
                python_runtime=python_runtime,
                gateway_host=args.gateway_host,
                paths=paths,
                ppu_id=args.ppu_id,
                facility_id=args.facility_id,
                display_name=args.display_name,
            )
            print(json.dumps(evidence, indent=2, sort_keys=True))
            return 0
    except (OSError, subprocess.SubprocessError, Z2InstallerError) as exc:
        print(f"ppu-z2-installer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
