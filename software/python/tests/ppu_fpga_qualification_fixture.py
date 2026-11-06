"""Test-only SYNTHETIC FPGA Image triple.

The BIN/HWH bytes below are deliberately not a Vivado build. They only let
Host-only tests exercise the B2 static-qualification code path with a
Manifest that the protected Root parser accepts. Nothing here is FPGA build,
load, Identity readback or HIL evidence, and none of it ships to a PPU.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SYNTHETIC_BIN = b"SYNTHETIC HOST-ONLY FPGA BIN - NOT A BITSTREAM"
SYNTHETIC_HWH = (b"<ROOT><SYSTEMINFO BOARD='pynq-z2' DEVICE='7z020' "
                 b"PACKAGE='clg400' SPEEDGRADE='-1'/>"
                 b"<MEMRANGE MASTERBUSINTERFACE='M_AXI_GP0' "
                 b"BASEVALUE='0x43c01000' HIGHVALUE='0x43c01fff'/>"
                 b"<MEMRANGE MASTERBUSINTERFACE='M_AXI_GP0' "
                 b"BASEVALUE='0x43c02000' HIGHVALUE='0x43c02fff'/></ROOT>")
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}

# ABI-v5-shaped geometry (same layout as the d0add58c contract), synthetic SHAs.
SITES = ({"site_id": 1, "offset": 0, "identity": 0x00050001},
         {"site_id": 2, "offset": 0x1000, "identity": 0x00050002})
GEOMETRY = {"axi_base": 0x43C01000, "axi_bytes": 0x2000,
            "owner_base": 0x43C00000, "owner_bytes": 0x10000}


def synthetic_image(bin_bytes: bytes = SYNTHETIC_BIN, *,
                    hwh_bytes: bytes = SYNTHETIC_HWH, manifest_overrides=None):
    """Return (package files under fpga/, no factory registry)."""
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
        # Device-pinned Golden (pl/hil/fpga_image_guard.GOLDEN_RECOVERY_SHA256).
        "recovery_sha256": "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c",
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
    return files, None
