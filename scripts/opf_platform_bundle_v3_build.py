#!/usr/bin/env python3
"""Build a profile-only OPF-4A Bundle v3 for an installed platform OpenOCD engine.

Host-only artifact producer. This does not select an Engine, install/activate a
Bundle, reload FPGA, open a Site Session, or operate a DUT. Source files are
deliberately fixed: extra or retired Engine references fail before ZIP output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

import ppu_provider_options
import ppu_unified_deployment


SOURCE_FILES = frozenset({
    "plasma-provider-options.json",
    "plasma-provider.json",
    "plasma-flash-profile.json",
})
PACKAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class BundleBuildDenied(ValueError):
    """Fixed code; do not include source JSON values in exceptions."""


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise BundleBuildDenied(code)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "SOURCE_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _load_json(raw: bytes):
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError) as exc:
        raise BundleBuildDenied("SOURCE_JSON_INVALID") from exc


def _source(source: Path) -> dict[str, bytes]:
    _need(source.is_dir() and not source.is_symlink(), "SOURCE_DIR_INVALID")
    members = list(source.iterdir())
    _need({p.name for p in members} == SOURCE_FILES
          and len(members) == len(SOURCE_FILES), "SOURCE_FILE_SET_INVALID")
    _need(all(p.is_file() and not p.is_symlink() for p in members),
          "SOURCE_FILE_UNTRUSTED")
    files = {}
    for name in sorted(SOURCE_FILES):
        raw = (source / name).read_bytes()
        _need(0 < len(raw) <= 8192, "SOURCE_FILE_SIZE_INVALID")
        files[name] = raw
    return files


def _check_inputs(files: dict[str, bytes], target: dict,
                  provider_id: str, profile_id: str) -> None:
    _need(type(target) is dict and set(target) == {
        "platform", "board", "fpga_part"} and
        all(type(x) is str and bool(x) for x in target.values()),
        "TARGET_INVALID")
    options = _load_json(files["plasma-provider-options.json"])
    try:
        _need(ppu_provider_options.validate(options, {}) == b"{}",
              "PROVIDER_OPTIONS_INVALID")
    except ppu_provider_options.OptionsDenied as exc:
        raise BundleBuildDenied("PROVIDER_OPTIONS_INVALID") from exc

    descriptor = _load_json(files["plasma-provider.json"])
    _need(type(descriptor) is dict and set(descriptor) == {
        "schema", "target", "provider_package", "operations", "sites",
        "transport", "driver_abi", "fpga_package", "max_image_bytes"},
        "PROVIDER_DESCRIPTOR_INVALID")
    _need(descriptor["schema"] == "plasma.ppu.provider-capabilities.v1"
          and descriptor["provider_package"] == provider_id
          and type(descriptor["target"]) is str and bool(descriptor["target"])
          and descriptor["transport"] == "fpga"
          and descriptor["fpga_package"] is None
          and type(descriptor["driver_abi"]) is str
          and bool(descriptor["driver_abi"])
          and type(descriptor["operations"]) is list
          and "flash_cycle" in descriptor["operations"]
          and type(descriptor["sites"]) is list
          and bool(descriptor["sites"])
          and all(type(s) is int and s > 0 for s in descriptor["sites"])
          and descriptor["sites"] == sorted(set(descriptor["sites"]))
          and type(descriptor["max_image_bytes"]) is int
          and 0 < descriptor["max_image_bytes"] <= 512 * 1024 * 1024,
          "PROVIDER_DESCRIPTOR_INVALID")

    profile = _load_json(files["plasma-flash-profile.json"])
    _need(type(profile) is dict and set(profile) == {
        "schema", "icpn", "target_config", "flash_base",
        "flash_size", "erase_granularity"},
        "FLASH_PROFILE_INVALID")
    _need(profile["schema"] == "plasma.ppu.openocd-flash-profile.v1"
          and profile["icpn"] == descriptor["target"]
          and type(profile["target_config"]) is str
          and bool(profile["target_config"])
          and type(profile["flash_base"]) is int
          and profile["flash_base"] >= 0
          and type(profile["flash_size"]) is int
          and profile["flash_size"] > 0
          and type(profile["erase_granularity"]) is int
          and profile["erase_granularity"] > 0
          and profile["flash_size"] % profile["erase_granularity"] == 0
          and descriptor["max_image_bytes"] <= profile["flash_size"],
          "FLASH_PROFILE_INVALID")


def build_bundle(source: Path, output: Path, *, target: dict,
                 provider_id: str, profile_id: str, bundle_name: str,
                 version: str, source_commit: str | None = None) -> str:
    for value in (provider_id, profile_id, bundle_name):
        _need(type(value) is str and PACKAGE_ID.fullmatch(value) is not None,
              "PACKAGE_OR_BUNDLE_ID_INVALID")
    _need(provider_id != profile_id and type(version) is str
          and VERSION.fullmatch(version) is not None, "PACKAGE_VERSION_INVALID")
    _need(source_commit is None or (
        type(source_commit) is str and SHA40.fullmatch(source_commit) is not None),
        "SOURCE_COMMIT_INVALID")
    files = _source(source)
    _check_inputs(files, target, provider_id, profile_id)

    provider_path = f"payload/packages/{provider_id}/data/plasma-provider-options.json"
    descriptor_path = f"payload/packages/{profile_id}/data/plasma-provider.json"
    flash_path = f"payload/packages/{profile_id}/data/plasma-flash-profile.json"
    members = {
        provider_path: files["plasma-provider-options.json"],
        descriptor_path: files["plasma-provider.json"],
        flash_path: files["plasma-flash-profile.json"],
    }

    def entries(paths):
        return [{
            "path": path, "size": len(members[path]),
            "sha256": hashlib.sha256(members[path]).hexdigest(),
            "executable": False,
        } for path in sorted(paths)]

    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": bundle_name, "version": version,
        "purpose": "programming", "target": dict(target),
        "actions": ["install", "verify"],
        "packages": [
            {"id": provider_id, "kind": "platform-provider", "version": version,
             "requires": [], "files": entries([provider_path])},
            {"id": profile_id, "kind": "programming-profile", "version": version,
             "requires": [provider_id],
             "files": entries([descriptor_path, flash_path])},
        ],
    }
    if source_commit is not None:
        manifest["source_commit"] = source_commit
    contents = {
        "manifest.json": (json.dumps(manifest, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode("utf-8"),
        **members,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with zipfile.ZipFile(output, "x") as archive:
            created = True
            for name, raw in sorted(contents.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, raw)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        ppu_unified_deployment.verify_host_only_bundle(
            output, expected_sha256=digest, target_profile=target)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    target = _load_json(args.target_json.read_bytes())
    digest = build_bundle(
        args.source, args.output, target=target, provider_id=args.provider_id,
        profile_id=args.profile_id, bundle_name=args.name,
        version=args.version, source_commit=args.source_commit)
    print(json.dumps({"bundle_schema": "plasma.ppu.bundle.v3",
                      "archive_sha256": digest, "output": str(args.output),
                      "admission": "GENERIC_HOST_ONLY_PASS",
                      "opf_execution": "NOT_RUN"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
