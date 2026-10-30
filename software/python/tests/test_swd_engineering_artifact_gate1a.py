"""Host-only exact Image Manifest contract; no Root or MMIO operation."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pl.hil import fpga_image_guard as guard
from pl.hil import fpga_image_root as root


REPO = Path(__file__).resolve().parents[3]
EVIDENCE = REPO / "docs/evidence/swd-independent-engineering-gate1-2026-10-30"
MANIFEST = EVIDENCE / "plasma-image-manifest.host-only.json"


def read_candidate(path=MANIFEST):
    # Host tests bypass filesystem root ownership only. The real Root Entry
    # retains root-owned source, protected firmware and live-state checks.
    with patch.object(root, "MANIFEST_FILE", path), patch.object(guard, "protected"):
        return root.read_image_manifest()


def test_host_only_manifest_parses_and_checks_both_fixed_site_ids():
    release = read_candidate()
    assert release.axi_base == 0x43C01000
    assert release.axi_bytes == 0x2000
    assert release.abi_version == 0x00050001
    assert release.site_bitmap == 0b11
    observed_addresses = []

    def read32(address):
        observed_addresses.append(address)
        return {0x43C01000: 0x00050001, 0x43C02000: 0x00050002}[address]

    assert root.read_identity(read32, release) == {
        0: 0x00050001, 0x1000: 0x00050002,
    }
    assert observed_addresses == [0x43C01000, 0x43C02000]
    with pytest.raises(root.ImageDeploymentDenied, match="PL_IDENTITY_MISMATCH"):
        root.read_identity(lambda address: 0x00050001, release)


@pytest.mark.parametrize("field,value,denial", [
    ("board_id", "other-board", "IMAGE_BOARD_PART_MISMATCH"),
    ("firmware_sha256", "not-a-digest", "IMAGE_RELEASE_FIRMWARE_DENIED"),
    ("identity_words", [[0, 0x00050001, 0xFFFFFFFF]], "IMAGE_RELEASE_IDENTITY_DENIED"),
    ("abi_version", 5, "IMAGE_RELEASE_ABI_DENIED"),
    ("axi_bytes", 4096, "IMAGE_RELEASE_IDENTITY_DENIED"),
])
def test_manifest_fails_closed_on_wrong_pairing(tmp_path, field, value, denial):
    data = json.loads(MANIFEST.read_text())
    data[field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with pytest.raises(root.ImageDeploymentDenied, match=denial):
        read_candidate(path)


def test_candidate_evidence_does_not_claim_current_boot_or_deployment():
    data = json.loads((EVIDENCE / "candidate-manifest.json").read_text())
    release = json.loads(MANIFEST.read_text())
    assert data["root_ready_bin_sha256"] == release["firmware_sha256"]
    assert data["root_image_manifest_sha256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert data["root_manifest_status"] == "HOST_ONLY_SCHEMA_PASS_RUNTIME_UNVERIFIED"
    assert data["current_boot_id"] is None
    assert data["current_boot_golden_sha256"] is None
    assert data["z2_driver_backup_sha256"] is None
    assert data["physical_load"] == data["single_site_dpidr"] == "NOT_RUN"
