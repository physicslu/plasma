"""Host-only FPGA Handoff from an installed B3 Set: unique Image, no hardware."""
from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT, load
from .test_ppu_b3_z2_install_gate1 import (
    b3_request, build_generic_assets, make_coordinator,
)

assets = load("ppu_fpga_handoff_single_active_gate1", "ppu_asset_set.py")
IMAGE_ID = "z2-custom-swd-v2"
PROFILE_ID = "stm32-profile"
FPGA_PACKAGE_ID = "custom-swd"
TARGET_BIN = "swd.bin"


def fixture(tmp_path: Path):
    data = json.loads(
        (ROOT / "pl/projects/z2-bluepill-rbb/image-manifest.json").read_text()
    )
    bitstream = b"synthetic-no-hardware-fpga-bin-v2"
    data["image_id"] = IMAGE_ID
    data["firmware_name"] = TARGET_BIN
    data["firmware_sha256"] = hashlib.sha256(bitstream).hexdigest()
    image_manifest = json.dumps(data, sort_keys=True).encode()
    archive, digest = build_generic_assets(
        tmp_path / "bundle", bitstream=bitstream,
        fpga_manifest=image_manifest,
    )
    co = make_coordinator(tmp_path)
    receipt = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert receipt["result"] == "PASS"
    co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    root = Path(receipt["install_path"])
    bundle = json.loads((root / "manifest.json").read_text())
    profile = next(p for p in bundle["packages"] if p["id"] == PROFILE_ID)
    desc = {
        "id": profile["id"], "kind": profile["kind"],
        "version": profile["version"], "requires": profile["requires"],
        "files": sorted(profile["files"], key=lambda i: i["path"]),
    }
    profile_sha = hashlib.sha256(
        json.dumps(desc, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return co, digest, data["firmware_sha256"], profile_sha, root


def resolve(co, digest, image_sha=None, profile_sha=None):
    """The Bundle selects its own unique FPGA Image; the Set need not be Active."""
    return assets.resolve_staged_fpga_handoff(co.paths.product_root, digest)


def test_p2_exact_fpga_handoff_returns_inert_plan_not_loaded(tmp_path: Path):
    co, sha, bin_sha, profile_sha, path = fixture(tmp_path)
    result = resolve(co, sha)
    assert result["status"] == "VERIFIED_NOT_LOADED"
    assert result["asset_set_sha256"] == sha
    assert result["fpga_image"]["package_id"] == FPGA_PACKAGE_ID
    assert result["fpga_image"]["image_id"] == IMAGE_ID
    assert result["fpga_image"]["bin_sha256"] == bin_sha
    assert result["fpga_image"]["bin_relative_path"] == "payload/packages/custom-swd/fpga/swd.bin"
    assert result["fpga_image"]["hwh_relative_path"] == "payload/packages/custom-swd/fpga/swd.hwh"
    assert result["fpga_image"]["manifest_relative_path"] == "payload/packages/custom-swd/fpga/image.json"
    assert result["programming_profile"]["package_id"] == PROFILE_ID
    assert result["programming_profile"]["package_identity_sha256"] == profile_sha
    assert result["fpga_install"] == "NOT_RUN"
    assert result["fpga_load"] == "NOT_RUN"
    assert result["root_hardware_validation"] == "NOT_RUN"
    assert result["ready"] is False
    assert not (co.paths.product_root / "current").exists()
    assert not co.paths.systemd_root.exists()
    assert assets.read_active(co.paths.product_root)["asset_set_sha256"] == sha


def test_p2_handoff_resolves_installed_set_before_activation(tmp_path: Path):
    # B3 fpga_load resolves the just-installed Set; active.json is published
    # only after Root Identity PASS.
    co, sha, bin_sha, _profile_sha, _ = fixture(tmp_path)
    (co.paths.product_root / "assets" / "active.json").unlink()
    result = resolve(co, sha)
    assert result["fpga_image"]["bin_sha256"] == bin_sha
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"


def test_p2_handoff_rejects_unknown_or_unstaged_set(tmp_path: Path):
    co, _sha, _bin_sha, _profile_sha, _ = fixture(tmp_path)
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_NOT_STAGED"):
        resolve(co, "a" * 64)


def test_p2_tampered_bin_prevents_handoff_even_if_active_pointer_matches(tmp_path: Path):
    co, sha, bin_sha, profile_sha, path = fixture(tmp_path)
    image = path / "payload/packages/custom-swd/fpga/swd.bin"
    image.chmod(0o600)
    image.write_bytes(b"altered-content")
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_FILE_MISMATCH"):
        resolve(co, sha, bin_sha, profile_sha)


def test_p2_tampered_fpga_manifest_prevents_handoff(tmp_path: Path):
    co, sha, bin_sha, profile_sha, path = fixture(tmp_path)
    metadata = path / "payload/packages/custom-swd/fpga/image.json"
    metadata.chmod(0o600)
    data = json.loads(metadata.read_text())
    data["firmware_sha256"] = "f" * 64
    metadata.write_text(json.dumps(data))
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_FILE_MISMATCH"):
        resolve(co, sha, bin_sha, profile_sha)
