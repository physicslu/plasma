#!/usr/bin/env python3
"""B2 static qualification of Bundle v3 FPGA Image Packages (Host-only).

The FPGA Image is an ordinary Bundle Asset: same B2 Admission, same Master
authorization, same B3 Install. This module adds only the FPGA-specific
*static* checks that B2 needs before it may report PASS:

* the Package carries exactly the Z2 Root Loader triple: BIN, HWH and a
  ``plasma.fpga.image.v1`` Image Manifest;
* the Manifest is parsed by the existing protected Root parser
  ``pl/hil/fpga_image_root.py::parse_image_manifest_bytes`` (no second parser);
* BIN name/SHA256 pair with the Manifest;
* the Manifest board/FPGA part equal the device-trusted Target;
* Image identity, ABI, Site identities, Site capabilities and AXI geometry
  equal an *independent* trusted FPGA Image contract shipped with the factory
  Bootstrap, never a value taken from the Bundle itself.

A PASS is a static statement only. It never loads FPGA, reads back Identity,
grants Root, selects an Active Set or authorizes a Programming Job. The live
Root FPGA Loader independently re-verifies everything before any load.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping

CONTRACTS_SCHEMA = "plasma.ppu.fpga-image-contracts.v1"
RESULT_SCHEMA = "plasma.ppu.fpga-static-qualification.v1"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BUILD = re.compile(r"[0-9a-f]{8}\Z")
NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
TARGET_FIELDS = {"platform", "board", "fpga_part"}
CONTRACT_FIELDS = {
    "contract_id", "evidence", "target", "build", "source_commit", "image_id",
    "firmware_name", "bin_sha256", "hwh_sha256", "manifest_sha256",
    "recovery_name", "abi_version", "abi_offset", "site_identities",
    "site_bitmap", "site_bitmap_offset", "axi_base", "axi_bytes",
    "owner_base", "owner_bytes",
}
MAX_BIN_BYTES = 16_000_000
MAX_HWH_BYTES = 4_000_000
MAX_MANIFEST_BYTES = 8192
U32 = 0xFFFFFFFF


class FpgaQualificationDenied(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FpgaQualificationDenied(code)


def _pairs(items):
    data = {}
    for key, value in items:
        _require(key not in data, "FPGA_CONTRACTS_DUPLICATE_FIELD")
        data[key] = value
    return data


def _u32(value: object) -> bool:
    return type(value) is int and 0 <= value <= U32


def load_root_manifest_parser():
    """Import the ONE protected Root Image Manifest parser.

    Factory Bootstrap ships it at ``<bootstrap>/pl/hil``; a source checkout
    has it at ``<repo>/pl/hil``. The imported module must be that exact file.
    """
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


def _validate_contract(item: object, *, seen_ids: set, seen_images: set) -> dict:
    _require(type(item) is dict and set(item) == CONTRACT_FIELDS,
             "FPGA_CONTRACT_INVALID")
    _require(all(type(item[k]) is str and NAME.fullmatch(item[k])
                 for k in ("contract_id", "evidence", "image_id",
                           "firmware_name", "recovery_name"))
             and item["firmware_name"].endswith(".bin")
             and item["firmware_name"] != item["recovery_name"]
             and type(item["target"]) is dict
             and set(item["target"]) == TARGET_FIELDS
             and all(type(v) is str and 0 < len(v) <= 128
                     for v in item["target"].values())
             and type(item["build"]) is str and BUILD.fullmatch(item["build"])
             and type(item["source_commit"]) is str
             and SHA40.fullmatch(item["source_commit"])
             and item["source_commit"].startswith(item["build"])
             and item["build"] in item["image_id"]
             and all(type(item[k]) is str and SHA64.fullmatch(item[k])
                     for k in ("bin_sha256", "hwh_sha256", "manifest_sha256"))
             and all(_u32(item[k]) for k in (
                 "abi_version", "abi_offset", "site_bitmap", "axi_base",
                 "axi_bytes", "owner_base", "owner_bytes"))
             and (item["site_bitmap_offset"] is None
                  or _u32(item["site_bitmap_offset"])),
             "FPGA_CONTRACT_INVALID")
    sites = item["site_identities"]
    _require(type(sites) is list and 1 <= len(sites) <= 16,
             "FPGA_CONTRACT_SITES_INVALID")
    bitmap = 0
    expected_site = 1
    offsets = set()
    for site in sites:
        # One-based Site identity; contiguous and ascending, never Channel 0.
        _require(type(site) is dict and set(site) == {"site_id", "offset", "identity"}
                 and type(site["site_id"]) is int and site["site_id"] == expected_site
                 and _u32(site["offset"]) and site["offset"] % 4 == 0
                 and site["offset"] + 4 <= item["axi_bytes"]
                 and site["offset"] not in offsets
                 and _u32(site["identity"]) and site["identity"] > 0,
                 "FPGA_CONTRACT_SITES_INVALID")
        offsets.add(site["offset"])
        bitmap |= 1 << (site["site_id"] - 1)
        expected_site += 1
    _require(bitmap == item["site_bitmap"]
             and any(s["offset"] == item["abi_offset"]
                     and s["identity"] == item["abi_version"] for s in sites),
             "FPGA_CONTRACT_SITES_INVALID")
    _require(item["contract_id"] not in seen_ids
             and item["image_id"] not in seen_images,
             "FPGA_CONTRACT_DUPLICATE")
    seen_ids.add(item["contract_id"])
    seen_images.add(item["image_id"])
    return item


def read_trusted_contracts(path: Path) -> tuple[dict[str, dict], str]:
    """Factory-Bootstrap-owned contract file; never Bundle, upload or HTTP data."""
    _require(isinstance(path, Path) and path.is_absolute(),
             "FPGA_CONTRACTS_PATH_INVALID")
    _require(not path.is_symlink() and not path.parent.is_symlink(),
             "FPGA_CONTRACTS_UNTRUSTED")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise FpgaQualificationDenied("FPGA_CONTRACTS_NOT_PROVISIONED") from exc
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                 and info.st_mode & 0o022 == 0 and 0 < info.st_size <= 65536,
                 "FPGA_CONTRACTS_UNTRUSTED")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(65537)
    finally:
        os.close(fd)
    _require(0 < len(raw) <= 65536, "FPGA_CONTRACTS_UNTRUSTED")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: _require(
                              False, "FPGA_CONTRACTS_NONFINITE"))
    except (ValueError, UnicodeDecodeError) as exc:
        if isinstance(exc, FpgaQualificationDenied):
            raise
        raise FpgaQualificationDenied("FPGA_CONTRACTS_MALFORMED") from exc
    _require(type(data) is dict and set(data) == {"schema", "contracts"}
             and data["schema"] == CONTRACTS_SCHEMA
             and type(data["contracts"]) is list
             and 1 <= len(data["contracts"]) <= 64,
             "FPGA_CONTRACTS_INVALID")
    seen_ids: set = set()
    seen_images: set = set()
    contracts = {}
    for item in data["contracts"]:
        valid = _validate_contract(item, seen_ids=seen_ids, seen_images=seen_images)
        contracts[valid["image_id"]] = valid
    return contracts, hashlib.sha256(raw).hexdigest()


def _read_member(archive: zipfile.ZipFile, member, limit: int) -> bytes:
    _require(0 < member.size <= limit, "FPGA_IMAGE_FILE_SIZE_DENIED")
    info = archive.getinfo(member.path)
    _require(info.file_size == member.size, "FPGA_IMAGE_FILE_SIZE_DENIED")
    with archive.open(info) as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) == member.size
             and hashlib.sha256(raw).hexdigest() == member.sha256,
             "FPGA_IMAGE_FILE_SHA256_MISMATCH")
    return raw


def _qualify_package(archive, package, *, root, contracts, trusted_target) -> dict:
    prefix = f"payload/packages/{package.id}/fpga/"
    by_suffix = {
        suffix: [f for f in package.files if f.path.endswith(suffix)]
        for suffix in (".bin", ".hwh", ".json")
    }
    _require(all(len(items) == 1 for items in by_suffix.values())
             and len(package.files) == 3
             and all(f.path.startswith(prefix) and not f.executable
                     and NAME.fullmatch(f.path[len(prefix):])
                     for f in package.files),
             "FPGA_IMAGE_TRIPLE_REQUIRED")
    bin_file = by_suffix[".bin"][0]
    hwh_file = by_suffix[".hwh"][0]
    manifest_file = by_suffix[".json"][0]
    manifest_raw = _read_member(archive, manifest_file, MAX_MANIFEST_BYTES)
    bin_raw = _read_member(archive, bin_file, MAX_BIN_BYTES)
    hwh_raw = _read_member(archive, hwh_file, MAX_HWH_BYTES)
    try:
        manifest = root.parse_image_manifest_bytes(manifest_raw)
    except root.ImageDeploymentDenied as exc:
        raise FpgaQualificationDenied(f"FPGA_IMAGE_MANIFEST_DENIED:{exc}") from exc
    bin_sha = hashlib.sha256(bin_raw).hexdigest()
    hwh_sha = hashlib.sha256(hwh_raw).hexdigest()
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    # Pairing inside the Package: BIN is exactly the Manifest firmware.
    _require(bin_file.path == prefix + manifest.firmware_name,
             "FPGA_IMAGE_BIN_NAME_MISMATCH")
    _require(bin_sha == manifest.firmware_sha256, "FPGA_IMAGE_BIN_SHA_MISMATCH")
    # Target from the device, not the Bundle.
    _require(manifest.board_id == trusted_target["board"]
             and manifest.fpga_part == trusted_target["fpga_part"],
             "FPGA_IMAGE_TARGET_MISMATCH")
    # Identity/ABI/Site capability from the independent trusted contract.
    contract = contracts.get(manifest.image_id)
    _require(contract is not None, "FPGA_IMAGE_CONTRACT_UNKNOWN")
    _require(contract["target"] == dict(trusted_target),
             "FPGA_IMAGE_CONTRACT_TARGET_MISMATCH")
    _require(manifest.firmware_name == contract["firmware_name"]
             and bin_sha == contract["bin_sha256"],
             "FPGA_IMAGE_CONTRACT_BIN_MISMATCH")
    _require(hwh_sha == contract["hwh_sha256"], "FPGA_IMAGE_CONTRACT_HWH_MISMATCH")
    _require(manifest_sha == contract["manifest_sha256"],
             "FPGA_IMAGE_CONTRACT_MANIFEST_MISMATCH")
    _require(manifest.abi_version == contract["abi_version"]
             and manifest.abi_offset == contract["abi_offset"],
             "FPGA_IMAGE_ABI_MISMATCH")
    expected_words = tuple(
        (s["offset"], s["identity"], U32) for s in contract["site_identities"]
    )
    _require(manifest.identity_words == expected_words,
             "FPGA_IMAGE_IDENTITY_MISMATCH")
    _require(manifest.site_bitmap == contract["site_bitmap"]
             and manifest.site_bitmap_offset == contract["site_bitmap_offset"],
             "FPGA_IMAGE_SITE_CAPABILITY_MISMATCH")
    _require(manifest.axi_base == contract["axi_base"]
             and manifest.axi_bytes == contract["axi_bytes"]
             and manifest.owner_base == contract["owner_base"]
             and manifest.owner_bytes == contract["owner_bytes"]
             and manifest.recovery_name == contract["recovery_name"],
             "FPGA_IMAGE_GEOMETRY_MISMATCH")
    return {
        "package_id": package.id,
        "package_version": package.version,
        "image_id": manifest.image_id,
        "contract_id": contract["contract_id"],
        "contract_evidence": contract["evidence"],
        "build": contract["build"],
        "image_source_commit": contract["source_commit"],
        "bin_path": bin_file.path,
        "bin_sha256": bin_sha,
        "hwh_path": hwh_file.path,
        "hwh_sha256": hwh_sha,
        "manifest_path": manifest_file.path,
        "manifest_sha256": manifest_sha,
        "board_id": manifest.board_id,
        "fpga_part": manifest.fpga_part,
        "abi_version": manifest.abi_version,
        "site_identities": [dict(s) for s in contract["site_identities"]],
        "site_bitmap": manifest.site_bitmap,
        "result": "STATIC_QUALIFIED",
        "identity_readback": "NOT_RUN",
        "fpga_loaded": False,
    }


def qualify_bundle_fpga(
    archive_path: Path, bundle, *, contracts_path: Path,
    trusted_target: Mapping[str, str],
) -> dict[str, Any] | None:
    """Return the static FPGA qualification for ``bundle`` or fail closed.

    ``bundle`` must already be a canonical Bundle v3 verified against the
    same ``archive_path``. Bundles without an FPGA Image Package return None
    and do not require the contract file.
    """
    _require(getattr(bundle, "schema", None) == "plasma.ppu.bundle.v3"
             and getattr(bundle, "kind", None) == "bundle",
             "FPGA_QUALIFICATION_CANONICAL_ONLY")
    _require(isinstance(trusted_target, Mapping)
             and set(trusted_target) == TARGET_FIELDS
             and dict(trusted_target) == dict(bundle.target),
             "FPGA_QUALIFICATION_TARGET_INVALID")
    fpga = [p for p in bundle.packages if p.kind == "fpga-image"]
    if not fpga:
        return None
    root = load_root_manifest_parser()
    contracts, contracts_sha = read_trusted_contracts(contracts_path)
    _require(isinstance(archive_path, Path) and not archive_path.is_symlink(),
             "FPGA_QUALIFICATION_ARCHIVE_UNTRUSTED")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            images = [
                _qualify_package(archive, package, root=root, contracts=contracts,
                                 trusted_target=trusted_target)
                for package in fpga
            ]
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise FpgaQualificationDenied("FPGA_QUALIFICATION_ARCHIVE_UNREADABLE") from exc
    return {
        "schema": RESULT_SCHEMA,
        "result": "STATIC_QUALIFIED",
        "archive_sha256": bundle.archive_sha256,
        "contracts_sha256": contracts_sha,
        "images": images,
        "fpga_loaded": False,
        "identity_readback": "NOT_RUN",
        "execution_permitted": False,
    }
