#!/usr/bin/env python3
"""Offline reproducible Blue Pill v0.1/v0.2 Bundle v3 fixture builder.

This developer tool does not deploy a Bundle, select FPGA, or operate a DUT.
Only original firmware bytes matching the historical CI digest are accepted.
The two versions each produce a distinct whole Active Asset Set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

import ppu_unified_deployment

TARGET = {"platform": "linux-armv7", "board": "pynq-z2",
          "fpga_part": "xc7z020clg400-1"}
PROVIDER = "openocd-platform-reference"
PROFILE = "stm32f103c8t6-site2"
ICPN = "STM32F103C8T6"
SOURCES = {
    "v0.1": {"filename": "plasma-blue-pill-cdc.bin",
             "size": 18768,
             "sha256": "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d"},
    "v0.2": {"filename": "plasma-blue-pill-cdc-v0.2.bin",
             "size": 62800,
             "sha256": "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c"},
}


class FixtureDenied(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(data: object) -> bytes:
    return (json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n").encode()


def build(variant: str, firmware: Path, output: Path) -> dict[str, object]:
    if variant not in SOURCES:
        raise FixtureDenied("VARIANT_UNKNOWN")
    source = SOURCES[variant]
    if (not isinstance(firmware, Path) or firmware.is_symlink()
            or not firmware.is_file()):
        raise FixtureDenied("SOURCE_FIRMWARE_UNTRUSTED")
    contents = firmware.read_bytes()
    if len(contents) != source["size"] or _sha(contents) != source["sha256"]:
        raise FixtureDenied("SOURCE_FIRMWARE_SIZE_OR_SHA_MISMATCH")
    if (not isinstance(output, Path) or output.is_symlink()
            or output.exists() or not output.parent.is_dir()):
        raise FixtureDenied("OUTPUT_EXISTS_OR_UNTRUSTED")
    variant_id = variant.replace(".", "")
    asset_id = f"bluepill-cdc-fw-{variant_id}"
    members = {
        f"payload/packages/{PROVIDER}/data/plasma-provider-options.json":
            _json({"schema": "plasma.ppu.provider-options.v1",
                   "options": {"type": "object", "properties": {}}}),
        f"payload/packages/{PROFILE}/data/plasma-provider.json":
            _json({"schema": "plasma.ppu.provider-capabilities.v1",
                   "target": ICPN, "provider_package": PROVIDER,
                   "operations": ["flash_cycle"], "sites": [2],
                   "transport": "fpga", "driver_abi": "plasma_swd:5",
                   "fpga_package": None, "max_image_bytes": 65536}),
        f"payload/packages/{PROFILE}/data/plasma-flash-profile.json":
            _json({"schema": "plasma.ppu.openocd-flash-profile.v1",
                   "icpn": ICPN, "target_config": "target/stm32f1x.cfg",
                   "flash_base": 0x08000000, "flash_size": 65536,
                   "erase_granularity": 1024}),
        f"payload/packages/{asset_id}/data/{source['filename']}": contents,
    }

    def package(pid: str, kind: str, requires: list[str]) -> dict:
        paths = sorted(p for p in members
                       if p.startswith(f"payload/packages/{pid}/"))
        return {"id": pid, "kind": kind, "version": "1.0.0",
                "requires": requires,
                "files": [{"path": p, "size": len(members[p]),
                           "sha256": _sha(members[p]), "executable": False}
                          for p in paths]}

    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": f"bluepill-site2-fw-{variant_id}", "version": "1.0.0",
        "purpose": "programming", "target": TARGET,
        # The existing B3 verified-set reader requires this exact action set.
        "actions": ["install", "verify"],
        "packages": [
            package(PROVIDER, "platform-provider", []),
            package(PROFILE, "programming-profile", [PROVIDER]),
            package(asset_id, "firmware-asset", [PROFILE]),
        ],
    }
    complete = {"manifest.json": _json(manifest), **members}
    try:
        with zipfile.ZipFile(output, "x") as archive:
            for filename, raw in sorted(complete.items()):
                entry = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                entry.compress_type = zipfile.ZIP_STORED
                archive.writestr(entry, raw)
        digest = _sha(output.read_bytes())
        ppu_unified_deployment.verify_host_only_bundle(
            output, expected_sha256=digest, target_profile=TARGET)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {"bundle_schema": "plasma.ppu.bundle.v3",
            "archive_sha256": digest, "firmware_sha256": source["sha256"],
            "firmware_size": source["size"], "variant": variant,
            "asset_package_id": asset_id,
            "status": "HOST_ONLY_VERIFIED_NOT_DEPLOYED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(SOURCES), required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.variant, args.firmware, args.output),
                     sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
