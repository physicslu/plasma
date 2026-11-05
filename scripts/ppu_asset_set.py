#!/usr/bin/env python3
"""Single Active Asset Set contract for the existing PPU Deployment Engine.

A Bundle v3 archive SHA256 is the *exact* Asset Set identity for this
generation. This module adds no independent Installer, daemon, FPGA loader,
code execution or device authority. Activation must run under the existing
Coordinator lock AND a trusted exclusive Runtime/Job quiescence lease.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "plasma.ppu.active-assets.v1"
BUNDLE = "plasma.ppu.bundle.v3"


class AssetSetError(RuntimeError):
    pass


def _json_file(path: Path, *, max_bytes: int = 65536) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise AssetSetError("ASSET_SET_FILE_UNTRUSTED")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise AssetSetError("ASSET_SET_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise AssetSetError("ASSET_SET_JSON_INVALID")
    return value


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    if path.is_symlink() or not path.is_file():
        raise AssetSetError("ASSET_SET_FILE_UNTRUSTED")
    with path.open("rb") as data:
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _root(product_root: Path) -> tuple[Path, Path, Path]:
    if not isinstance(product_root, Path) or not product_root.is_absolute():
        raise AssetSetError("ASSET_SET_ROOT_INVALID")
    root = product_root / "assets"
    staged = root / "staged"
    active = root / "active.json"
    for directory in (product_root, root, staged):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise AssetSetError("ASSET_SET_ROOT_UNTRUSTED")
    if active.is_symlink():
        raise AssetSetError("ASSET_SET_ACTIVE_SYMLINK_DENIED")
    return root, staged, active


def verify_staged(product_root: Path, asset_set_sha256: str) -> dict[str, Any]:
    """Independently verify an immutable B3 Set before use or activation.

    This validates exact stored files, not the Console's identity claim.
    B3 already checked the complete original ZIP and device-specific target.
    """
    if type(asset_set_sha256) is not str or not HEX64.fullmatch(asset_set_sha256):
        raise AssetSetError("ASSET_SET_SHA_INVALID")
    _assets, staged, _active = _root(product_root)
    target = staged / asset_set_sha256
    if target.is_symlink() or not target.is_dir():
        raise AssetSetError("ASSET_SET_NOT_STAGED")
    receipt = _json_file(target / "b3-install.json")
    manifest = _json_file(target / "manifest.json")
    if (receipt.get("schema") != "plasma.ppu.b3-install.v1"
            or receipt.get("archive_sha256") != asset_set_sha256
            or receipt.get("manifest_sha256") != _digest(target / "manifest.json")
            or receipt.get("bundle_name") != manifest.get("name")
            or receipt.get("source_commit") != manifest.get("source_commit")
            or manifest.get("schema") != BUNDLE
            or manifest.get("actions") != ["install", "verify"]
            or type(manifest.get("packages")) is not list
            or not 1 <= len(manifest["packages"]) <= 32):
        raise AssetSetError("ASSET_SET_MANIFEST_OR_RECEIPT_INVALID")
    expected = {"manifest.json", "b3-install.json"}
    for package in manifest["packages"]:
        if type(package) is not dict or type(package.get("id")) is not str:
            raise AssetSetError("ASSET_SET_PACKAGE_INVALID")
        entries = package.get("files")
        if type(entries) is not list or not entries:
            raise AssetSetError("ASSET_SET_PACKAGE_INVALID")
        for entry in entries:
            if type(entry) is not dict:
                raise AssetSetError("ASSET_SET_FILE_DESCRIPTOR_INVALID")
            name, checksum, size = entry.get("path"), entry.get("sha256"), entry.get("size")
            if (type(name) is not str
                    or not name.startswith("payload/packages/" + package["id"] + "/")
                    or ".." in Path(name).parts or name.startswith("/")
                    or type(checksum) is not str or not HEX64.fullmatch(checksum)
                    or type(size) is not int or size < 0 or name in expected):
                raise AssetSetError("ASSET_SET_FILE_DESCRIPTOR_INVALID")
            dest = target / name
            # Reject symlinked intermediate directories BEFORE reading any
            # content; a leaf-only symlink check would be insufficient.
            parent = target
            for part in Path(name).parts[:-1]:
                parent = parent / part
                if parent.is_symlink() or not parent.is_dir():
                    raise AssetSetError("ASSET_SET_PARENT_UNTRUSTED")
            if (dest.is_symlink() or not dest.is_file()
                    or dest.stat().st_size != size or _digest(dest) != checksum):
                raise AssetSetError("ASSET_SET_FILE_MISMATCH")
            expected.add(name)
    if receipt.get("files_verified") != len(expected) - 2:
        raise AssetSetError("ASSET_SET_FILE_COUNT_MISMATCH")
    # Deny any extra file, symlink or unexpected filesystem object.
    for item in target.rglob("*"):
        if item.is_symlink():
            raise AssetSetError("ASSET_SET_TREE_SYMLINK_DENIED")
        if item.is_file() and str(item.relative_to(target)) not in expected:
            raise AssetSetError("ASSET_SET_FILE_SET_MISMATCH")
        if not item.is_file() and not item.is_dir():
            raise AssetSetError("ASSET_SET_SPECIAL_FILE_DENIED")
    observed = {str(item.relative_to(target)) for item in target.rglob("*") if item.is_file()}
    if observed != expected:
        raise AssetSetError("ASSET_SET_FILE_SET_MISMATCH")
    return {
        "asset_set_sha256": asset_set_sha256,
        "bundle_name": receipt["bundle_name"],
        "bundle_version": receipt["bundle_version"],
        "manifest_sha256": receipt["manifest_sha256"],
        "package_count": len(manifest["packages"]),
        "file_count": receipt["files_verified"],
        "state": "VERIFIED",
    }


def read_active(product_root: Path) -> dict[str, Any]:
    """Report verified Active identity. Never equate ACTIVE with FPGA READY."""
    _assets, _staged, active = _root(product_root)
    if not active.exists():
        return {
            "schema": SCHEMA, "state": "EMPTY",
            "asset_set_sha256": None, "ready": False, "fpga": "NOT_VERIFIED",
        }
    record = _json_file(active)
    if (record.get("schema") != SCHEMA
            or type(record.get("generation")) is not int
            or record["generation"] < 1
            or type(record.get("asset_set_sha256")) is not str
            or not HEX64.fullmatch(record["asset_set_sha256"])):
        raise AssetSetError("ASSET_SET_ACTIVE_RECORD_INVALID")
    verified = verify_staged(product_root, record["asset_set_sha256"])
    return {
        "schema": SCHEMA, "state": "ACTIVE",
        "asset_set_sha256": verified["asset_set_sha256"],
        "generation": record["generation"],
        "ready": False, "fpga": "NOT_VERIFIED",
        "profile": "NOT_VERIFIED",
    }


def _require_trusted_control_socket(socket_path: Path) -> None:
    if (not isinstance(socket_path, Path) or not socket_path.is_absolute()
            or socket_path.is_symlink() or socket_path.parent.is_symlink()):
        raise AssetSetError("ASSET_SET_CONTROL_SOCKET_UNTRUSTED")
    try:
        node = socket_path.stat()
        directory = socket_path.parent.stat()
    except OSError as exc:
        raise AssetSetError("ASSET_SET_CONTROL_SOCKET_UNAVAILABLE") from exc
    if (not stat.S_ISSOCK(node.st_mode) or node.st_mode & 0o077
            or not stat.S_ISDIR(directory.st_mode) or directory.st_mode & 0o022
            or node.st_uid != directory.st_uid):
        raise AssetSetError("ASSET_SET_CONTROL_SOCKET_UNTRUSTED")


@contextmanager
def held_runtime_asset_lease(
    socket_path: Path = Path("/run/plasma-server/control.sock"),
):
    """Borrow the existing Runtime's exclusive Job-admission gate.

    The Runtime owns the gate; holding the Unix stream keeps it active.
    Local Bootstrap must hold this context for the *entire* atomic switch.
    A missing/untrusted socket or busy Sites refuse the switch. This does
    not prove separate FPGA/PL hardware quiescence or IC readiness.
    """
    _require_trusted_control_socket(socket_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
        control.settimeout(5)
        try:
            control.connect(str(socket_path))
            control.sendall(b'{"operation":"hold_asset_activation"}\n')
            buffer = bytearray()
            while b"\n" not in buffer:
                chunk = control.recv(4096)
                if not chunk or len(buffer) + len(chunk) > 8192:
                    raise AssetSetError("ASSET_SET_QUIESCE_REPLY_INVALID")
                buffer.extend(chunk)
            record = json.loads(bytes(buffer).split(b"\n", 1)[0])
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise AssetSetError("ASSET_SET_QUIESCE_TRANSPORT_UNAVAILABLE") from exc
        if (not isinstance(record, dict) or record.get("ok") is not True
                or not isinstance(record.get("result"), dict)
                or record["result"].get("lease_kind") != "connection_held"
                or record["result"].get("active_job_count") != 0
                or type(record["result"].get("ppu_id")) is not str
                or not record["result"]["ppu_id"]):
            raise AssetSetError("ASSET_SET_QUIESCE_NOT_GRANTED")
        # Connection must stay open until the final durable fsync. The
        # Runtime releases the gate in its socket handler's finally block.
        control.settimeout(None)
        yield record["result"]


def bundle_has_fpga_image(product_root: Path, asset_set_sha256: str) -> bool:
    """True when the verified staged Set carries an ``fpga-image`` Package."""
    verify_staged(product_root, asset_set_sha256)
    _, staged, _ = _root(product_root)
    manifest = _json_file(staged / asset_set_sha256 / "manifest.json")
    return any(type(p) is dict and p.get("kind") == "fpga-image"
               for p in manifest["packages"])


def resolve_staged_fpga_handoff(
    product_root: Path, asset_set_sha256: str,
) -> dict[str, Any]:
    """Resolve the FPGA handoff of a just-installed immutable B3 Set.

    The Bundle itself selects the Image: exactly one ``fpga-image`` Package
    and at most one ``programming-profile`` Package (optional). The Set need
    not be Active yet: B3 ``fpga_load`` publishes ``active.json`` only after
    Root Identity PASS. This performs NO installation or load; the protected
    Root re-derives and re-verifies everything independently from the Set
    SHA-256 alone. Never pass Bundle-defined absolute paths to Root.
    """
    stage = verify_staged(product_root, asset_set_sha256)
    _, staged, _ = _root(product_root)
    target = staged / stage["asset_set_sha256"]
    manifest = _json_file(target / "manifest.json")
    packages = manifest["packages"]
    fpga_packages = [p for p in packages if type(p) is dict and p.get("kind") == "fpga-image"]
    profiles = [p for p in packages
                if type(p) is dict and p.get("kind") == "programming-profile"]
    if len(fpga_packages) != 1:
        raise AssetSetError("ASSET_HANDOFF_FPGA_PACKAGE_NOT_UNIQUE_OR_MISSING")
    if len(profiles) > 1:
        raise AssetSetError("ASSET_HANDOFF_PROFILE_NOT_UNIQUE")
    fpga = fpga_packages[0]
    for value in (fpga.get("id"), fpga.get("version")):
        if (type(value) is not str or not 0 < len(value) <= 128
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", value)):
            raise AssetSetError("ASSET_HANDOFF_IDENTITY_INVALID")
    profile_identity = None
    if profiles:
        profile = profiles[0]
        # Bind Profile identity to the full canonical manifest descriptor,
        # not only a file name or semantic version.
        descriptor = {
            "id": profile["id"], "kind": profile["kind"],
            "version": profile["version"], "requires": profile["requires"],
            "files": sorted(({
                "path": item["path"], "sha256": item["sha256"],
                "size": item["size"], "executable": item["executable"],
            } for item in profile["files"]), key=lambda item: item["path"]),
        }
        profile_identity = {
            "package_id": profile["id"],
            "package_version": profile["version"],
            "package_identity_sha256": hashlib.sha256(json.dumps(
                descriptor, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }

    def files_with_suffix(suffix: str) -> list[dict[str, Any]]:
        return [item for item in fpga["files"]
                if type(item) is dict and item.get("path", "").endswith(suffix)]

    binaries = files_with_suffix(".bin")
    bitstreams = files_with_suffix(".bit")
    hwhs = files_with_suffix(".hwh")
    if len(binaries) != 1 or bitstreams or len(hwhs) != 1:
        # Z2 Root's current FPGA Manager expects a pre-converted BIN.
        raise AssetSetError("ASSET_HANDOFF_REQUIRES_PREBUILT_BIN_AND_HWH")
    image = binaries[0]
    hwh = hwhs[0]
    if _digest(target / image["path"]) != image["sha256"]:
        raise AssetSetError("ASSET_HANDOFF_IMAGE_CHANGED")

    candidates = []
    for entry in files_with_suffix(".json"):
        image_manifest = _json_file(target / entry["path"], max_bytes=8192)
        if image_manifest.get("schema") == "plasma.fpga.image.v1":
            candidates.append((entry, image_manifest))
    if len(candidates) != 1:
        raise AssetSetError("ASSET_HANDOFF_FPGA_MANIFEST_NOT_UNIQUE_OR_MISSING")
    entry, paired = candidates[0]
    if (type(paired.get("image_id")) is not str
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", paired["image_id"])
            or paired.get("firmware_name") != Path(image["path"]).name
            or paired.get("firmware_sha256") != image["sha256"]
            or paired.get("board_id") != manifest["target"]["board"]
            or paired.get("fpga_part") != manifest["target"]["fpga_part"]
            or paired.get("recovery_name") != "base.bin"
            or type(paired.get("recovery_sha256")) is not str
            or not HEX64.fullmatch(paired["recovery_sha256"])
            or paired.get("firmware_name") == paired.get("recovery_name")
            or type(paired.get("abi_version")) is not int):
        raise AssetSetError("ASSET_HANDOFF_FPGA_MANIFEST_INCOMPATIBLE")
    # The root loader independently owns the full FPGA Manifest schema,
    # ABI/Identity/UIO validation and actual /lib/firmware authorization.
    # This handoff never replaces or bypasses those protections.
    if _digest(target / entry["path"]) != entry["sha256"]:
        raise AssetSetError("ASSET_HANDOFF_MANIFEST_CHANGED")
    if _digest(target / hwh["path"]) != hwh["sha256"]:
        raise AssetSetError("ASSET_HANDOFF_HWH_CHANGED")
    return {
        "schema": "plasma.ppu.fpga-asset-handoff.v1",
        "status": "VERIFIED_NOT_LOADED",
        "asset_set_sha256": asset_set_sha256,
        "fpga_image": {
            "package_id": fpga["id"],
            "package_version": fpga["version"],
            "image_id": paired["image_id"],
            "bin_relative_path": image["path"],
            "bin_sha256": image["sha256"],
            "hwh_relative_path": hwh["path"],
            "hwh_sha256": hwh["sha256"],
            "manifest_relative_path": entry["path"],
            "manifest_sha256": entry["sha256"],
            "board_id": paired["board_id"],
            "fpga_part": paired["fpga_part"],
            "abi_version_claim": paired["abi_version"],
        },
        "programming_profile": profile_identity,
        "root_hardware_validation": "NOT_RUN",
        "fpga_install": "NOT_RUN",
        "fpga_load": "NOT_RUN",
        "dut": "NOT_RUN",
        "ready": False,
    }


def restore_previous(
    product_root: Path, previous: Mapping[str, Any], candidate: str, *,
    runtime_quiesced: bool = False,
) -> dict[str, Any]:
    """Recover pointer-only publication under the existing lock and lease.

    Never restores PL or claims hardware READY. Refuse unexpected pointer
    drift, corrupt previous assets and legacy transactions without a snapshot.
    Repeating after a crash during rollback is safe.
    """
    if runtime_quiesced is not True:
        raise AssetSetError("ASSET_SET_RUNTIME_QUIESCE_NOT_QUALIFIED")
    if type(candidate) is not str or not HEX64.fullmatch(candidate):
        raise AssetSetError("ASSET_SET_SHA_INVALID")
    old_sha = previous.get("asset_set_sha256")
    old_generation = previous.get("generation", 0)
    if (previous.get("schema") != SCHEMA
            or previous.get("state") not in {"ACTIVE", "EMPTY"}
            or type(old_generation) is not int or old_generation < 0
            or (previous["state"] == "EMPTY" and (old_sha is not None or old_generation != 0))
            or (previous["state"] == "ACTIVE" and
                (type(old_sha) is not str or not HEX64.fullmatch(old_sha) or old_generation < 1))):
        raise AssetSetError("ASSET_SET_PREVIOUS_INVALID")
    if old_sha is not None:
        verify_staged(product_root, old_sha)
    current = read_active(product_root)
    if (current["asset_set_sha256"] == old_sha
            and current.get("generation", 0) in {old_generation, old_generation + 2}):
        return current
    if (current["asset_set_sha256"] != candidate
            or current.get("generation") != old_generation + 1):
        raise AssetSetError("ASSET_SET_ROLLBACK_POINTER_DRIFT")
    if old_sha is not None:
        activate_verified(product_root, old_sha, runtime_quiesced=True)
    else:
        root, _, active = _root(product_root)
        active.unlink()
        directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return read_active(product_root)


def activate_verified(
    product_root: Path, asset_set_sha256: str, *,
    runtime_quiesced: bool = False,
) -> dict[str, Any]:
    """Commit under Coordinator flock PLUS a held trusted runtime quiesce lease.

    runtime_quiesced is INTERNAL ONLY and must never be taken from HTTP/ZIP.
    Production Bootstrap does not expose this function without a trusted
    Runtime/Job lease provider; fail closed until that integration is proven.
    """
    if runtime_quiesced is not True:
        raise AssetSetError("ASSET_SET_RUNTIME_QUIESCE_NOT_QUALIFIED")
    stage = verify_staged(product_root, asset_set_sha256)
    root, _staged, active = _root(product_root)
    old = read_active(product_root)
    if old["asset_set_sha256"] == asset_set_sha256:
        return {
            "result": "PASS", "asset_set_sha256": asset_set_sha256,
            "generation": old["generation"], "already_active": True,
            "fpga": "NOT_RUN", "ready": False,
        }
    if product_root == Path("/opt/plasma") and os.geteuid() != 0:
        raise AssetSetError("ASSET_SET_PRIVILEGE_DENIED")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise AssetSetError("ASSET_SET_ROOT_UNTRUSTED")
    new_record = {
        "schema": SCHEMA, "asset_set_sha256": asset_set_sha256,
        "generation": old.get("generation", 0) + 1,
        "activated_epoch_s": time.time(),
        "previous_asset_set_sha256": old["asset_set_sha256"],
        "manifest_sha256": stage["manifest_sha256"],
    }
    descriptor, temp_name = tempfile.mkstemp(prefix=".active.", dir=root)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(new_record, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Root-owned, read-only for everyone: the non-root Runtime (Stage C
        # Package Actions) must read the Active identity; nothing secret here.
        temp.chmod(0o444)
        if active.is_symlink():
            raise AssetSetError("ASSET_SET_ACTIVE_SYMLINK_DENIED")
        os.replace(temp, active)
        directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp.exists():
            temp.unlink()
    now = read_active(product_root)
    if now["asset_set_sha256"] != asset_set_sha256:
        raise AssetSetError("ASSET_SET_ACTIVATION_NOT_CONFIRMED")
    return {
        "result": "PASS", "asset_set_sha256": asset_set_sha256,
        "generation": now["generation"], "already_active": False,
        "fpga": "NOT_RUN", "ready": False,
    }
