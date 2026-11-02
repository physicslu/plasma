"""Host-only binding of the deployable ABI-v5 devmem Manifest.

The deploy Manifest differs from the historical fixture ONLY in the Linux
owner declaration (``expected_uio`` -> audited devmem conflict owner, and no
``uio_name``). BIN/Recovery/ABI/Identity/geometry must stay byte-identical in
meaning, and the protected Root parser must accept it. This is not HIL.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pl.hil import fpga_image_root as root  # noqa: E402
from pl.hil import swd_independent_image_contract as contract  # noqa: E402

DEPLOY = ROOT / "pl/hil/releases/swd-independent-ab79b04e/plasma-image-manifest.json"
FIXTURE = ROOT / "pl/tests/fixtures/swd-independent-ab79b04e/plasma-image-manifest.json"
DEPLOY_SHA = "f470a4fac8accd0b1fcfb50243d4d663e1ddee209bc1c506e8e587c1f5ff859c"


def test_deploy_manifest_pinned_bytes():
    assert hashlib.sha256(DEPLOY.read_bytes()).hexdigest() == DEPLOY_SHA


def test_only_owner_declaration_differs_from_historical_fixture():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == contract.MANIFEST_SHA
    old = json.loads(FIXTURE.read_text())
    new = json.loads(DEPLOY.read_text())
    assert old.pop("uio_name") == "uio1"
    old_owner = old.pop("expected_uio")
    new_owner = new.pop("expected_uio")
    assert old == new
    assert new_owner == {
        "backend": "devmem",
        "platform_node": "43c00000.audio-codec-ctrl",
        "driver": "uio_pdrv_genirq",
        "maps": [[0x43C00000, 0x10000]],
        "runtime": "suspended",
    }
    assert old_owner["maps"] == new_owner["maps"]


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
    fixture_dir = FIXTURE.parent
    result = contract.verify(fixture_dir / "system.hwh", FIXTURE)
    assert result["identity_addresses"] == [0x43C01000, 0x43C02000]
