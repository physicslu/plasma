"""Host-only binding of the deployable ABI-v5 devmem Manifest (d0add58c).

ab79b04e was retired 2026-11-03 (Replace-by-Default): the only trusted
independent Image is d0add58c. Its release Manifest is the exact bytes that the
Root parses, that B2 qualifies and that the HWH contract binds. This is not HIL.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pl.hil import fpga_image_admission as admission  # noqa: E402
from pl.hil import fpga_image_root as root  # noqa: E402
from pl.hil import swd_independent_image_contract as contract  # noqa: E402

DEPLOY = ROOT / "pl/hil/releases/swd-independent-d0add58c/plasma-image-manifest.json"
FIXTURE = ROOT / "pl/tests/fixtures/swd-independent-d0add58c/plasma-image-manifest.json"
DEPLOY_SHA = "4e33fee583611f70c60d30f971cc8499c165486b4621119a6b219da6fd3f1d78"


def test_deploy_manifest_pinned_bytes():
    assert hashlib.sha256(DEPLOY.read_bytes()).hexdigest() == DEPLOY_SHA
    assert DEPLOY_SHA == contract.MANIFEST_SHA
    assert FIXTURE.read_bytes() == DEPLOY.read_bytes()


def test_retired_image_is_not_released_or_trusted():
    for retired in ("ab79b04e", "bd976140"):
        assert not (ROOT / f"pl/hil/releases/swd-independent-{retired}").exists()
    assert set(admission.DEVMEM_INDEPENDENT_IMAGES) == {
        "z2-independent-swd-v5-d0add58c"}


def test_d0add58c_release_pairs_with_root_table():
    """PR #1285 IDLE_CYCLES Image (Vivado run 41648270405): same geometry."""
    rel = ROOT / "pl/hil/releases/swd-independent-d0add58c/plasma-image-manifest.json"
    assert hashlib.sha256(rel.read_bytes()).hexdigest() == (
        "4e33fee583611f70c60d30f971cc8499c165486b4621119a6b219da6fd3f1d78")
    release = root.parse_image_manifest_bytes(rel.read_bytes())
    assert release.image_id == "z2-independent-swd-v5-d0add58c"
    assert admission.DEVMEM_INDEPENDENT_IMAGES[release.image_id] == (
        release.firmware_sha256)
    data = json.loads(rel.read_text())
    # Same two-Site ABI-v5 geometry as the retired bd976140 Image.
    assert data["identity_words"] == [[0, 0x00050001, 0xFFFFFFFF],
                                      [4096, 0x00050002, 0xFFFFFFFF]]
    assert (data["axi_base"], data["axi_bytes"], data["site_bitmap"]) == (
        0x43C01000, 0x2000, 3)


def test_devmem_owner_declaration():
    data = json.loads(DEPLOY.read_text())
    assert "uio_name" not in data
    assert data["expected_uio"] == {
        "backend": "devmem",
        "platform_node": "43c00000.audio-codec-ctrl",
        "driver": "uio_pdrv_genirq",
        "maps": [[0x43C00000, 0x10000]],
        "runtime": "suspended",
    }


def test_root_parser_accepts_devmem_owner_with_exact_identity():
    release = root.parse_image_manifest_bytes(DEPLOY.read_bytes())
    assert release.firmware_sha256 == contract.BIN_SHA
    assert release.expected_uio["backend"] == "devmem"
    assert release.uio_name == ""
    addresses = {release.axi_base + off: val
                 for off, val, _ in release.identity_words}
    assert addresses == {0x43C01000: 0x00050001, 0x43C02000: 0x00050002}
    assert 0x43C00000 not in addresses


def test_hwh_still_binds_identity_addresses():
    result = contract.verify(FIXTURE.parent / "system.hwh", DEPLOY)
    assert result["identity_addresses"] == [0x43C01000, 0x43C02000]
