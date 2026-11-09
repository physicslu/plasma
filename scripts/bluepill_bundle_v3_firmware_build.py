#!/usr/bin/env python3
"""Offline reproducible Blue Pill v0.1/v0.2 Bundle v3 fixture builder.

Thin wrapper over the shared ``plasma_opf.bundle_v3`` writer and the committed
first-party Programming Route; it only pins the historical firmware digests and
package names so the two fixture Bundles stay byte-identical.
This developer tool does not deploy a Bundle, select FPGA, or operate a DUT.
Only original firmware bytes matching the historical CI digest are accepted.
The two versions each produce a distinct whole Active Asset Set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import ppu_unified_deployment

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "software" / "python"))
from plasma_opf import bundle_v3  # noqa: E402  single shared Bundle v3 writer

ROUTE_FILE = _ROOT / "data/opf/programming-routes/z2-site2-stm32f103c8t6.json"
_ROUTE = bundle_v3.load_route(ROUTE_FILE)
TARGET = dict(_ROUTE.target)
PROVIDER = _ROUTE.provider_id
PROFILE = _ROUTE.profile_id
ICPN = _ROUTE.icpn
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
    built = bundle_v3.build_image_bundle(
        _ROUTE, contents, image_filename=source["filename"],
        asset_package_id=asset_id, bundle_name=f"bluepill-site2-fw-{variant_id}")
    try:
        with output.open("xb") as stream:
            stream.write(built.archive)
        digest = _sha(output.read_bytes())
        if digest != built.archive_sha256:
            raise FixtureDenied("OUTPUT_WRITE_MISMATCH")
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
