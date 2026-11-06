#!/usr/bin/env python3
"""Static FPGA checks for an already verified, owner authorized Bundle v3."""
from __future__ import annotations

import hashlib
import importlib
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping

RESULT_SCHEMA = "plasma.ppu.fpga-static-qualification.v1"
NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
TARGET_FIELDS = {"platform", "board", "fpga_part"}
LIMITS = {".bin": 16_000_000, ".hwh": 4_000_000, ".json": 8192}
DRIVER_ABI = 0x00050001


class FpgaQualificationDenied(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FpgaQualificationDenied(code)


def load_root_manifest_parser():
    """Import the installed protected Root parser, or the checkout copy."""
    here = Path(__file__).resolve().parent
    for base in (here, here.parent):
        candidate = base / "pl" / "hil" / "fpga_image_root.py"
        if candidate.is_file() and not candidate.is_symlink():
            break
    else:
        raise FpgaQualificationDenied("FPGA_ROOT_MANIFEST_PARSER_MISSING")
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    try:
        module = importlib.import_module("pl.hil.fpga_image_root")
    except ImportError as exc:
        raise FpgaQualificationDenied("FPGA_ROOT_MANIFEST_PARSER_MISSING") from exc
    _require(Path(module.__file__).resolve() == candidate.resolve(),
             "FPGA_ROOT_MANIFEST_PARSER_UNTRUSTED")
    return module


def _read_member(archive: zipfile.ZipFile, member, limit: int) -> bytes:
    _require(0 < member.size <= limit, "FPGA_IMAGE_FILE_SIZE_DENIED")
    info = archive.getinfo(member.path)
    _require(info.file_size == member.size, "FPGA_IMAGE_FILE_SIZE_DENIED")
    with archive.open(info) as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) == member.size and
             hashlib.sha256(raw).hexdigest() == member.sha256,
             "FPGA_IMAGE_FILE_SHA256_MISMATCH")
    return raw


def _qualify_package(archive, package, *, root, trusted_target) -> dict:
    prefix = f"payload/packages/{package.id}/fpga/"
    by_suffix = {suffix: [f for f in package.files if f.path.endswith(suffix)]
                 for suffix in LIMITS}
    _require(all(len(items) == 1 for items in by_suffix.values()) and
             len(package.files) == 3 and
             all(f.path.startswith(prefix) and not f.executable and
                 NAME.fullmatch(f.path[len(prefix):]) for f in package.files),
             "FPGA_IMAGE_TRIPLE_REQUIRED")
    files = {suffix: by_suffix[suffix][0] for suffix in LIMITS}
    raw = {suffix: _read_member(archive, files[suffix], LIMITS[suffix])
           for suffix in LIMITS}
    try:
        manifest = root.parse_image_manifest_bytes(raw[".json"])
        root.validate_hwh_bytes(raw[".hwh"], manifest)
    except root.ImageDeploymentDenied as exc:
        raise FpgaQualificationDenied(f"FPGA_IMAGE_MANIFEST_DENIED:{exc}") from exc
    _require(files[".bin"].path == prefix + manifest.firmware_name,
             "FPGA_IMAGE_BIN_NAME_MISMATCH")
    _require(files[".bin"].sha256 == manifest.firmware_sha256,
             "FPGA_IMAGE_BIN_SHA_MISMATCH")
    _require(manifest.board_id == trusted_target["board"] and
             manifest.fpga_part == trusted_target["fpga_part"],
             "FPGA_IMAGE_TARGET_MISMATCH")
    _require(manifest.abi_version == DRIVER_ABI,
             "FPGA_IMAGE_DRIVER_ABI_UNSUPPORTED")
    return {
        "package_id": package.id, "package_version": package.version,
        "image_id": manifest.image_id,
        "bin_path": files[".bin"].path, "bin_sha256": files[".bin"].sha256,
        "hwh_path": files[".hwh"].path, "hwh_sha256": files[".hwh"].sha256,
        "manifest_path": files[".json"].path,
        "manifest_sha256": files[".json"].sha256,
        "board_id": manifest.board_id, "fpga_part": manifest.fpga_part,
        "abi_version": manifest.abi_version, "site_bitmap": manifest.site_bitmap,
        "result": "STATIC_QUALIFIED", "identity_readback": "NOT_RUN",
        "fpga_loaded": False,
    }


def qualify_bundle_fpga(archive_path: Path, bundle, *,
                        trusted_target: Mapping[str, str]) -> dict[str, Any] | None:
    """Inspect FPGA files in a previously verified canonical Bundle."""
    _require(getattr(bundle, "schema", None) == "plasma.ppu.bundle.v3" and
             getattr(bundle, "kind", None) == "bundle",
             "FPGA_QUALIFICATION_CANONICAL_ONLY")
    _require(isinstance(trusted_target, Mapping) and
             set(trusted_target) == TARGET_FIELDS and
             dict(trusted_target) == dict(bundle.target),
             "FPGA_QUALIFICATION_TARGET_INVALID")
    fpga = [p for p in bundle.packages if p.kind == "fpga-image"]
    if not fpga:
        return None
    _require(len(fpga) == 1, "FPGA_IMAGE_PACKAGE_NOT_UNIQUE")
    root = load_root_manifest_parser()
    _require(isinstance(archive_path, Path) and not archive_path.is_symlink(),
             "FPGA_QUALIFICATION_ARCHIVE_UNTRUSTED")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            images = [_qualify_package(archive, package, root=root,
                                       trusted_target=trusted_target)
                      for package in fpga]
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise FpgaQualificationDenied("FPGA_QUALIFICATION_ARCHIVE_UNREADABLE") from exc
    return {
        "schema": RESULT_SCHEMA, "result": "STATIC_QUALIFIED",
        "archive_sha256": bundle.archive_sha256, "images": images,
        "fpga_loaded": False, "identity_readback": "NOT_RUN",
        "execution_permitted": False,
    }
