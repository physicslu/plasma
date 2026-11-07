"""Host-only OPF-4A platform-provider Bundle producer and admission regression.

No Z2, SWPC, service restart, FPGA access or DUT interaction.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from contextlib import nullcontext
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator


sys.path.insert(0, str(ROOT / "scripts"))
import ppu_provider_contract  # noqa: E402
import ppu_unified_deployment  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "opf_platform_bundle_v3_builder",
    ROOT / "scripts" / "opf_platform_bundle_v3_build.py",
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

PROVIDER = "openocd-platform-reference"
PROFILE = "stm32f103c8t6-site2"
ICPN = "STM32F103C8T6"
FLASH_SIZE = 65536


def _raw(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def source(tmp_path: Path) -> Path:
    path = tmp_path / "source"
    path.mkdir()
    data = {
        "plasma-provider-options.json": {
            "schema": "plasma.ppu.provider-options.v1",
            "options": {"type": "object", "properties": {}},
        },
        "plasma-provider.json": {
            "schema": "plasma.ppu.provider-capabilities.v1",
            "target": ICPN, "provider_package": PROVIDER,
            "operations": ["flash_cycle"], "sites": [2],
            "transport": "fpga", "driver_abi": "plasma_swd:5",
            "fpga_package": None, "max_image_bytes": FLASH_SIZE,
        },
        "plasma-flash-profile.json": {
            "schema": "plasma.ppu.openocd-flash-profile.v1",
            "icpn": ICPN, "target_config": "target/stm32f1x.cfg",
            "flash_base": 0x08000000, "flash_size": FLASH_SIZE,
            "erase_granularity": 1024,
        },
    }
    for name, value in data.items():
        (path / name).write_bytes(_raw(value))
    return path


def build(path: Path, output: Path) -> str:
    return builder.build_bundle(
        path, output, target=TARGET, provider_id=PROVIDER,
        profile_id=PROFILE, bundle_name="site2-opf-profile-only",
        version="1.0.0",
    )


def test_bundle_is_deterministic_and_has_exact_platform_provider_file_set(tmp_path):
    inputs = source(tmp_path)
    archive = tmp_path / "bundle.zip"
    other = tmp_path / "other.zip"
    digest = build(inputs, archive)
    assert digest == build(inputs, other)
    assert archive.read_bytes() == other.read_bytes()
    verified = ppu_unified_deployment.verify_host_only_bundle(
        archive, expected_sha256=digest, target_profile=TARGET)
    assert verified.archive_sha256 == digest
    with zipfile.ZipFile(archive) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert len(manifest["packages"]) == 2
        provider, profile = manifest["packages"]
        assert provider["id"] == PROVIDER
        assert provider["kind"] == "platform-provider"
        assert profile["requires"] == [PROVIDER]
        assert [entry["path"] for entry in provider["files"]] == [
            f"payload/packages/{PROVIDER}/data/plasma-provider-options.json"
        ]
        assert len(profile["files"]) == 2
        assert all(not entry["executable"]
                   for item in manifest["packages"] for entry in item["files"])
        assert all("plasma-platform-engine.json" not in path
                   for path in package.namelist())
        assert "openocd_root" not in package.read("manifest.json").decode()


def test_produced_bundle_passes_opf_provider_resolution_after_host_only_b3(tmp_path):
    inputs = source(tmp_path)
    archive = tmp_path / "bundle.zip"
    digest = build(inputs, archive)
    co = make_coordinator(tmp_path)
    receipt = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert receipt["result"] == "PASS"
    # Fixture-only, no service or device activation.
    co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    route = ppu_provider_contract.resolve(
        co.paths.product_root, asset_set_sha256=digest, target=ICPN,
        provider=PROVIDER, profile=PROFILE, operation="flash_cycle",
        site_id=2, image_size=18768, options={},
        hardware={
            **TARGET, "sites": [2], "driver_abi": "plasma_swd:5",
            "fpga_identity_proven": True,
            "worker_identity": {"status": "IMAGE", "image_id": "test-image"},
            "loaded_fpga_package": None,
        },
    )
    assert route.provider_package == PROVIDER
    assert route.profile_package == PROFILE
    assert route.options_json == b"{}"


def test_retired_engine_file_refused_before_output(tmp_path):
    inputs = source(tmp_path)
    (inputs / "plasma-platform-engine.json").write_bytes(_raw({
        "schema": "plasma.ppu.platform-openocd-reference.v1",
        "openocd_sha256": "0" * 64,
        "admission_sha256": "0" * 64,
        "driver_abi": "plasma_swd:5",
    }))
    output = tmp_path / "invalid.zip"
    with pytest.raises(builder.BundleBuildDenied, match="SOURCE_FILE_SET_INVALID"):
        build(inputs, output)
    assert not output.exists()


@pytest.mark.parametrize("name,mutation,code", [
    ("plasma-provider.json",
     {"provider_package": "wrong-provider"}, "PROVIDER_DESCRIPTOR_INVALID"),
    ("plasma-provider.json",
     {"fpga_package": "unqualified-fpga"}, "PROVIDER_DESCRIPTOR_INVALID"),
    ("plasma-provider.json",
     {"driver_abi": ""}, "PROVIDER_DESCRIPTOR_INVALID"),
    ("plasma-flash-profile.json",
     {"icpn": "WRONG"}, "FLASH_PROFILE_INVALID"),
    ("plasma-flash-profile.json",
     {"erase_granularity": 0}, "FLASH_PROFILE_INVALID"),
])
def test_invalid_source_contract_fails_before_output(tmp_path, name, mutation, code):
    inputs = source(tmp_path)
    doc = json.loads((inputs / name).read_bytes())
    doc.update(mutation)
    (inputs / name).write_bytes(_raw(doc))
    output = tmp_path / "invalid.zip"
    with pytest.raises(builder.BundleBuildDenied, match=code):
        build(inputs, output)
    assert not output.exists()


def test_duplicate_json_key_denied_before_output(tmp_path):
    inputs = source(tmp_path)
    (inputs / "plasma-provider.json").write_text(
        '{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(builder.BundleBuildDenied,
                       match="SOURCE_JSON_DUPLICATE_KEY"):
        build(inputs, tmp_path / "invalid.zip")


def test_does_not_overwrite_existing_archive(tmp_path):
    inputs = source(tmp_path)
    archive = tmp_path / "bundle.zip"
    build(inputs, archive)
    old_bytes = archive.read_bytes()
    with pytest.raises(FileExistsError):
        build(inputs, archive)
    assert archive.read_bytes() == old_bytes
