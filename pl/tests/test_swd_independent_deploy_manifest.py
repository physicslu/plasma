"""Host-only binding of the deployable ABI-v5 devmem Manifest (bd976140).

ab79b04e was retired 2026-11-03 (Replace-by-Default): the only trusted
independent Image is bd976140. Its release Manifest is the exact bytes that the
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

DEPLOY = ROOT / "pl/hil/releases/swd-independent-bd976140/plasma-image-manifest.json"
FIXTURE = ROOT / "pl/tests/fixtures/swd-independent-bd976140/plasma-image-manifest.json"
DEPLOY_SHA = "857228ddff88458edaad040a75a757729b5f2b667c57da7e2c5d245d28fe5222"


def test_deploy_manifest_pinned_bytes():
    assert hashlib.sha256(DEPLOY.read_bytes()).hexdigest() == DEPLOY_SHA
    assert DEPLOY_SHA == contract.MANIFEST_SHA
    assert FIXTURE.read_bytes() == DEPLOY.read_bytes()


def test_retired_image_is_not_released_or_trusted():
    assert not (ROOT / "pl/hil/releases/swd-independent-ab79b04e").exists()
    assert set(admission.DEVMEM_INDEPENDENT_IMAGES) == {
        "z2-independent-swd-v5-bd976140"}


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
