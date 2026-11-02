"""Test-only SYNTHETIC FPGA Image triple and trusted contract provisioner.

The BIN/HWH bytes below are deliberately not a Vivado build. They only let
Host-only tests exercise the B2 static-qualification code path with a
Manifest that the protected Root parser accepts. Nothing here is FPGA build,
load, Identity readback or HIL evidence, and none of it ships to a PPU.
The real shipped contract is ``scripts/ppu-fpga-image-contracts.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SYNTHETIC_BIN = b"SYNTHETIC HOST-ONLY FPGA BIN - NOT A BITSTREAM"
SYNTHETIC_HWH = b"<!-- SYNTHETIC HOST-ONLY HWH - NOT A VIVADO HANDOFF -->"
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}

# ABI-v5-shaped geometry (same layout as the ab79b04e contract), synthetic SHAs.
SITES = ({"site_id": 1, "offset": 0, "identity": 0x00050001},
         {"site_id": 2, "offset": 0x1000, "identity": 0x00050002})
GEOMETRY = {"axi_base": 0x43C01000, "axi_bytes": 0x2000,
            "owner_base": 0x43C00000, "owner_bytes": 0x10000}


def synthetic_image(bin_bytes: bytes = SYNTHETIC_BIN, *,
                    hwh_bytes: bytes = SYNTHETIC_HWH, manifest_overrides=None):
    """Return (package files under fpga/, trusted contract entry)."""
    bin_sha = hashlib.sha256(bin_bytes).hexdigest()
    build = bin_sha[:8]
    image_id = f"synthetic-host-only-abi5-{build}"
    firmware = f"synthetic-{build}.bin"
    manifest = {
        "schema": "plasma.fpga.image.v1",
        "image_id": image_id,
        "board_id": "pynq-z2",
        "fpga_part": "xc7z020clg400-1",
        "soc_compatible": "xlnx,zynq-7000",
        "firmware_name": firmware,
        "firmware_sha256": bin_sha,
        "recovery_name": "base.bin",
        "recovery_sha256": "c" * 64,
        "abi_version": SITES[0]["identity"],
        "abi_offset": SITES[0]["offset"],
        "identity_words": [[s["offset"], s["identity"], 0xFFFFFFFF] for s in SITES],
        "site_bitmap": 3,
        "site_bitmap_offset": None,
        **GEOMETRY,
        "uio_name": "uio1",
        "expected_uio": {
            "uio": "uio1", "driver": "uio_pdrv_genirq",
            "maps": [[GEOMETRY["owner_base"], GEOMETRY["owner_bytes"]]],
            "runtime": "suspended", "irq_counts": [0, 0],
        },
    }
    manifest.update(manifest_overrides or {})
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    files = {
        f"fpga/{firmware}": bin_bytes,
        "fpga/system.hwh": hwh_bytes,
        "fpga/plasma-image-manifest.json": manifest_bytes,
    }
    contract = {
        "contract_id": f"synthetic-test-{build}",
        "evidence": "synthetic-host-only-test",
        "target": dict(TARGET),
        "build": build,
        "source_commit": build + "0" * 32,
        "image_id": image_id,
        "firmware_name": firmware,
        "bin_sha256": bin_sha,
        "hwh_sha256": hashlib.sha256(hwh_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "recovery_name": "base.bin",
        "abi_version": SITES[0]["identity"],
        "abi_offset": SITES[0]["offset"],
        "site_identities": [dict(s) for s in SITES],
        "site_bitmap": 3,
        "site_bitmap_offset": None,
        **GEOMETRY,
    }
    return files, contract


def write_contracts(path: Path, *contracts: dict) -> Path:
    """Simulate the factory-Bootstrap-shipped trusted contract file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "plasma.ppu.fpga-image-contracts.v1",
        "contracts": list(contracts),
    }), encoding="utf-8")
    path.chmod(0o644)
    return path


def provision_default_contract(paths) -> dict:
    _files, contract = synthetic_image()
    write_contracts(paths.fpga_image_contracts, contract)
    return contract
