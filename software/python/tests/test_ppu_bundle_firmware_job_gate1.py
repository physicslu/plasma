"""Host-only contract: Bundle v3 Firmware Asset -> PPU Job bytes, never DUT.

The temporary Active Set is a synthetic B3-receipt fixture, not live B3 proof.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from plasma_core.enums import Operation
from plasma_web.gateway_base import PlasmaWebHandler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_asset_set as assets  # noqa: E402

SET_SHA = "a" * 64
PROFILE = "stm32f103c8t6-site2"
FIRMWARE = "bluepill-cdc-fw-v01"
PROVIDER = "openocd-platform-reference"
PAYLOAD = bytes(range(37))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def raw(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def active_set(tmp_path: Path, *, deps=None, content=PAYLOAD):
    """Build synthetic, structurally B3-verified on-disk Active Set (NO ZIP)."""
    product = tmp_path / "product"
    stage = product / "assets/staged" / SET_SHA
    files = {
        f"payload/packages/{PROVIDER}/data/plasma-provider-options.json":
            raw({"schema": "plasma.ppu.provider-options.v1", "options": {}}),
        f"payload/packages/{PROFILE}/data/plasma-provider.json":
            raw({"schema": "fixture", "target": "STM32F103C8T6"}),
        f"payload/packages/{FIRMWARE}/data/firmware.bin": content,
    }

    def pkg(pid, kind, req):
        entries = []
        for path, blob in files.items():
            if path.startswith(f"payload/packages/{pid}/"):
                entries.append({"path": path, "size": len(blob),
                                "sha256": digest(blob), "executable": False})
        return {"id": pid, "kind": kind, "version": "1.0.0",
                "requires": req, "files": entries}

    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": "hostonly-firmware-fixture", "version": "1.0.0",
        "purpose": "programming", "actions": ["install", "verify"],
        "target": {"platform": "linux-armv7", "board": "pynq-z2",
                   "fpga_part": "xc7z020clg400-1"},
        "packages": [
            pkg(PROVIDER, "platform-provider", []),
            pkg(PROFILE, "programming-profile", [PROVIDER]),
            pkg(FIRMWARE, "firmware-asset", [PROFILE] if deps is None else deps),
        ],
    }
    stage.mkdir(parents=True)
    for name, blob in files.items():
        p = stage / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    manifest_blob = raw(manifest)
    (stage / "manifest.json").write_bytes(manifest_blob)
    receipt = {
        "schema": "plasma.ppu.b3-install.v1",
        "archive_sha256": SET_SHA,
        "manifest_sha256": digest(manifest_blob),
        "bundle_name": manifest["name"],
        "bundle_version": manifest["version"],
        "files_verified": len(files),
    }
    (stage / "b3-install.json").write_bytes(raw(receipt))
    (product / "assets/active.json").write_bytes(raw({
        "schema": assets.SCHEMA, "generation": 1, "asset_set_sha256": SET_SHA,
    }))
    assert assets.read_active(product)["state"] == "ACTIVE"
    return product, stage / f"payload/packages/{FIRMWARE}/data/firmware.bin"


def resolve(product, **kw):
    return assets.resolve_active_firmware(
        product, asset_set_sha256=kw.pop("asset_set_sha256", SET_SHA),
        asset_package_id=kw.pop("asset_package_id", FIRMWARE),
        profile_package_id=kw.pop("profile_package_id", PROFILE),
        asset_sha256=kw.pop("bundle_asset_sha256", digest(PAYLOAD)),
        **kw,
    )


def test_verified_firmware_is_taken_from_only_active_set(tmp_path):
    product, _ = active_set(tmp_path)
    result = resolve(product)
    assert result["image"] == PAYLOAD
    assert result["image_sha256"] == digest(PAYLOAD)
    assert result["asset_set_sha256"] == SET_SHA
    assert result["image_name"] == "firmware.bin"
    assert result["asset_package_id"] == FIRMWARE
    assert result["profile_package_id"] == PROFILE


@pytest.mark.parametrize("override", [
    {"asset_set_sha256": "b" * 64},
    {"asset_set_sha256": "../escape"},
    {"asset_package_id": "../escape"},
    {"asset_package_id": "missing"},
    {"asset_package_id": PROFILE},
    {"profile_package_id": "missing"},
    {"bundle_asset_sha256": "0" * 64},
    {"bundle_asset_sha256": "bad"},
])
def test_bad_reference_never_resolves_firmware(tmp_path, override):
    product, _ = active_set(tmp_path)
    with pytest.raises(assets.AssetSetError):
        resolve(product, **override)


def test_firmware_must_depend_on_selected_profile(tmp_path):
    product, _ = active_set(tmp_path, deps=[])
    with pytest.raises(assets.AssetSetError, match="PACKAGE_OR_PROFILE"):
        resolve(product)


def test_modified_firmware_fails_before_use(tmp_path):
    product, location = active_set(tmp_path)
    location.write_bytes(b"changed")
    with pytest.raises(assets.AssetSetError):
        resolve(product)


def test_active_pointer_drift_fails_closed(tmp_path):
    product, _ = active_set(tmp_path)
    record = product / "assets/active.json"
    record.write_bytes(raw({"schema": assets.SCHEMA,
                            "generation": 2, "asset_set_sha256": "b" * 64}))
    with pytest.raises(assets.AssetSetError):
        resolve(product)


def test_gateway_bundle_reference_carries_no_inline_image():
    handler = object.__new__(PlasmaWebHandler)
    request = handler._job_request({
        "site_id": 2, "operation": "flash_cycle",
        "target": "STM32F103C8T6", "provider": PROVIDER, "profile": PROFILE,
        "asset_set_sha256": SET_SHA, "asset_package_id": FIRMWARE,
        "bundle_asset_sha256": digest(PAYLOAD),
    }, client_id="plasma-web")
    assert request.operation is Operation.FLASH_CYCLE
    assert request.image == b"" and request.image_ref is None
    assert request.metadata["bundle_asset_set_sha256"] == SET_SHA
    assert request.metadata["bundle_asset_package_id"] == FIRMWARE
    assert request.metadata["bundle_asset_sha256"] == digest(PAYLOAD)


@pytest.mark.parametrize("change", [
    {"bundle_asset_sha256": None},
    {"asset_base64": "AA=="},
    {"operation": "verify"},
    {"provider": None},
])
def test_gateway_refuses_incomplete_or_mixed_bundle_source(change):
    body = {
        "site_id": 2, "operation": "flash_cycle",
        "target": "STM32F103C8T6", "provider": PROVIDER, "profile": PROFILE,
        "asset_set_sha256": SET_SHA, "asset_package_id": FIRMWARE,
        "bundle_asset_sha256": digest(PAYLOAD),
    }
    body.update(change)
    if body.get("bundle_asset_sha256") is None:
        body.pop("bundle_asset_sha256", None)
    handler = object.__new__(PlasmaWebHandler)
    with pytest.raises(ValueError):
        handler._job_request(body, client_id="plasma-web")
