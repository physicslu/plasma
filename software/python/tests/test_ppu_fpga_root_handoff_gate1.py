"""Host-only Bundle → protected FPGA Root parser Handoff; no FPGA/root IO."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from pl.hil import fpga_image_root as protected_root
from pl.hil import fpga_image_guard as protected_guard

from .test_ppu_active_fpga_handoff_gate1 import fixture, resolve


def prepared(tmp_path: Path):
    co, set_sha, image_sha, profile_sha, root = fixture(tmp_path)
    plan = resolve(co, set_sha, image_sha, profile_sha)
    image = plan["fpga_image"]
    files = {
        "manifest_bytes": (root / image["manifest_relative_path"]).read_bytes(),
        "bin_bytes": (root / image["bin_relative_path"]).read_bytes(),
        "hwh_bytes": (root / image["hwh_relative_path"]).read_bytes(),
    }
    return plan, set_sha, files


def check(plan, sha, files):
    return protected_root.validate_bundle_fpga_handoff(
        plan, expected_active_set_sha256=sha, **files
    )


def test_root_handoff_uses_full_existing_root_parser_without_loading(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    with patch.object(protected_guard, "manager_write") as manager_write, \
         patch.object(protected_guard, "RootZ2TargetPort") as hardware_port:
        receipt = check(plan, sha, files)
        manager_write.assert_not_called()
        hardware_port.assert_not_called()
    assert receipt["result"] == "ROOT_FORMAT_VERIFIED_NOT_INSTALLED"
    assert receipt["asset_set_sha256"] == sha
    assert receipt["fpga_image_id"] == plan["fpga_image"]["image_id"]
    assert receipt["fpga_bin_sha256"] == plan["fpga_image"]["bin_sha256"]
    assert receipt["fpga_hwh_sha256"] == plan["fpga_image"]["hwh_sha256"]
    assert receipt["fpga_manifest_sha256"] == plan["fpga_image"]["manifest_sha256"]
    assert receipt["programming_profile_identity_sha256"] == plan["programming_profile"]["package_identity_sha256"]
    assert receipt["root_source_pin"] == "NOT_VERIFIED"
    assert receipt["golden_recovery"] == "NOT_VERIFIED"
    assert receipt["hardware_ownership"] == "NOT_VERIFIED"
    assert receipt["fpga_installed"] is False
    assert receipt["fpga_loaded"] is False
    assert receipt["ready"] is False


def test_root_parser_is_shared_with_existing_live_loader(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    manifest = protected_root.parse_image_manifest_bytes(files["manifest_bytes"])
    assert manifest.firmware_sha256 == plan["fpga_image"]["bin_sha256"]
    assert manifest.abi_version == plan["fpga_image"]["abi_version_claim"]
    assert check(plan, sha, files)["abi_version"] == manifest.abi_version


@pytest.mark.parametrize("altered", [
    {"asset_set_sha256": "a" * 64},
    {"status": "LOADED"},
    {"ready": True},
    {"fpga_load": "PASS"},
    {"fpga_install": "PASS"},
])
def test_root_handoff_rejects_claimed_activation_or_other_set(tmp_path: Path, altered):
    plan, sha, files = prepared(tmp_path)
    plan = dict(plan, **altered)
    with pytest.raises(protected_root.ImageDeploymentDenied, match="ROOT_HANDOFF_NOT_BOUND_TO_ACTIVE_SET"):
        check(plan, sha, files)


@pytest.mark.parametrize("field", ["bin_bytes", "hwh_bytes", "manifest_bytes"])
def test_root_handoff_rechecks_all_three_bytes(tmp_path: Path, field: str):
    plan, sha, files = prepared(tmp_path)
    changed = dict(files)
    changed[field] += b"tampered"
    with pytest.raises(protected_root.ImageDeploymentDenied):
        check(plan, sha, changed)


@pytest.mark.parametrize("field,value,expected", [
    ("abi_version_claim", 123, "ROOT_HANDOFF_IMAGE_IDENTITY_MISMATCH"),
    ("board_id", "different-board", "ROOT_HANDOFF_IMAGE_IDENTITY_MISMATCH"),
    ("bin_relative_path", "../../escape.bin", "ROOT_HANDOFF_RELATIVE_PATH_INVALID"),
    ("hwh_relative_path", "/tmp/foreign.hwh", "ROOT_HANDOFF_RELATIVE_PATH_INVALID"),
    ("manifest_relative_path", "payload/packages/other/fpga/image.json", "ROOT_HANDOFF_RELATIVE_PATH_INVALID"),
])
def test_root_handoff_rejects_wrong_hardware_or_path_claim(
    tmp_path: Path, field: str, value, expected: str
):
    plan, sha, files = prepared(tmp_path)
    plan = dict(plan)
    plan["fpga_image"] = dict(plan["fpga_image"], **{field: value})
    with pytest.raises(protected_root.ImageDeploymentDenied, match=expected):
        check(plan, sha, files)


@pytest.mark.parametrize("field,value,expected", [
    ("axi_bytes", 0, "IMAGE_RELEASE_APERTURE_DENIED"),
    ("abi_offset", 12, "IMAGE_RELEASE_ABI_DENIED"),
    ("uio_name", "uio7", "IMAGE_RELEASE_UIO_DENIED"),
    # Golden is a device fact: a Bundle Manifest cannot rename or re-hash it.
    ("recovery_name", "forged.bin", "IMAGE_RECOVERY_NOT_DEVICE_GOLDEN"),
    ("recovery_sha256", "d" * 64, "IMAGE_RECOVERY_NOT_DEVICE_GOLDEN"),
])
def test_root_full_loader_contract_rejects_bad_manifest_claim(
    tmp_path: Path, field: str, value, expected: str
):
    plan, sha, files = prepared(tmp_path)
    metadata = json.loads(files["manifest_bytes"])
    metadata[field] = value
    raw = json.dumps(metadata, sort_keys=True).encode()
    plan = dict(plan)
    plan["fpga_image"] = dict(
        plan["fpga_image"], manifest_sha256=hashlib.sha256(raw).hexdigest()
    )
    files = dict(files, manifest_bytes=raw)
    with pytest.raises(protected_root.ImageDeploymentDenied, match=expected):
        check(plan, sha, files)


def test_root_handoff_rejects_duplicate_manifest_fields(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    raw = files["manifest_bytes"]
    assert raw.startswith(b"{")
    duplicates = b'{"image_id":"forged",' + raw[1:]
    plan = dict(plan)
    plan["fpga_image"] = dict(
        plan["fpga_image"], manifest_sha256=hashlib.sha256(duplicates).hexdigest()
    )
    with pytest.raises(protected_root.ImageDeploymentDenied, match="IMAGE_RELEASE_DUPLICATE_FIELD"):
        check(plan, sha, dict(files, manifest_bytes=duplicates))


def test_root_handoff_cannot_authorize_a_new_root_operation(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    assert check(plan, sha, files)["fpga_installed"] is False
    with pytest.raises(protected_root.ImageDeploymentDenied, match="OPERATION_NOT_ALLOWLISTED"):
        protected_root.run("install-from-bundle")


class _FakeExclusiveRoot:
    def exclusive(self):
        return nullcontext()


def _mock_root_firmware_area(tmp_path: Path):
    """Only a private temp directory, no /lib/firmware or Z2 operation."""
    folder = tmp_path / "isolated-firmware"
    folder.mkdir(mode=0o700)
    (folder / "base.bin").write_bytes(b"synthetic-golden-only")
    (folder / "plasma-image-manifest.json").write_bytes(b"existing-active-manifest")
    return folder


def _stage_sandbox(plan, sha, files, folder: Path):
    from contextlib import ExitStack
    with ExitStack() as checks:
        checks.enter_context(patch.object(protected_root, "trusted_local"))
        checks.enter_context(patch.object(protected_guard, "FIRMWARE", folder))
        checks.enter_context(patch.object(protected_guard, "protected"))
        checks.enter_context(patch.object(
            protected_guard, "RootZ2TargetPort", return_value=_FakeExclusiveRoot()
        ))
        golden = checks.enter_context(patch.object(
            protected_guard, "sha_file",
            return_value=json.loads(files["manifest_bytes"])["recovery_sha256"],
        ))
        manager = checks.enter_context(patch.object(
            protected_guard, "manager_write"
        ))
        result = protected_root.stage_bundle_fpga_files_only(
            plan, expected_active_set_sha256=sha, **files,
        )
        manager.assert_not_called()
        golden.assert_called_once_with(
            folder / "base.bin",
            json.loads(files["manifest_bytes"])["recovery_sha256"],
        )
    return result


def test_root_files_only_stage_uses_existing_guard_no_fpga_load(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    dest = _mock_root_firmware_area(tmp_path)
    first = _stage_sandbox(plan, sha, files, dest)
    assert first["result"] == "ROOT_FILES_STAGED_NOT_ACTIVATED"
    assert first["firmware_files_staged"] is True
    assert first["fpga_installed"] is False
    assert first["fpga_loaded"] is False
    assert first["ready"] is False
    assert first["golden_recovery"] == "SHA_VERIFIED"
    name = first["firmware_name"]
    assert (dest / name).read_bytes() == files["bin_bytes"]
    assert (dest / (name + ".hwh")).read_bytes() == files["hwh_bytes"]
    assert (dest / (name + ".manifest.json")).read_bytes() == files["manifest_bytes"]
    assert all((dest / suffix).stat().st_mode & 0o777 == 0o600
               for suffix in (name, name + ".hwh", name + ".manifest.json"))
    assert (dest / "base.bin").read_bytes() == b"synthetic-golden-only"
    assert (dest / "plasma-image-manifest.json").read_bytes() == b"existing-active-manifest"
    again = _stage_sandbox(plan, sha, files, dest)
    assert again["result"] == "ROOT_FILES_STAGED_NOT_ACTIVATED"
    assert (dest / name).read_bytes() == files["bin_bytes"]


def test_root_stage_denies_same_firmware_name_with_different_bytes(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    dest = _mock_root_firmware_area(tmp_path)
    existing = dest / "swd.bin"
    existing.write_bytes(b"different-older-version")
    with pytest.raises(protected_root.ImageDeploymentDenied, match="ROOT_HANDOFF_EXISTING_FILE_CONFLICT"):
        _stage_sandbox(plan, sha, files, dest)
    assert existing.read_bytes() == b"different-older-version"
    assert not (dest / "swd.bin.manifest.json").exists()
    assert (dest / "base.bin").read_bytes() == b"synthetic-golden-only"


def test_root_stage_denies_symlinked_firmware_destination(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    dest = _mock_root_firmware_area(tmp_path)
    other = tmp_path / "external"
    other.write_bytes(b"external-preserved")
    (dest / "swd.bin").symlink_to(other)
    with pytest.raises(protected_root.ImageDeploymentDenied, match="ROOT_HANDOFF_EXISTING_SYMLINK"):
        _stage_sandbox(plan, sha, files, dest)
    assert other.read_bytes() == b"external-preserved"


def test_root_stage_refuses_failed_golden_before_file_mutation(tmp_path: Path):
    plan, sha, files = prepared(tmp_path)
    dest = _mock_root_firmware_area(tmp_path)
    with patch.object(protected_root, "trusted_local"), \
         patch.object(protected_guard, "FIRMWARE", dest), \
         patch.object(protected_guard, "protected"), \
         patch.object(protected_guard, "RootZ2TargetPort", return_value=_FakeExclusiveRoot()), \
         patch.object(protected_guard, "sha_file", side_effect=protected_guard.TargetSafetyDenied("GOLDEN_HASH_DENIED")):
        with pytest.raises(protected_guard.TargetSafetyDenied, match="GOLDEN_HASH_DENIED"):
            protected_root.stage_bundle_fpga_files_only(
                plan, expected_active_set_sha256=sha, **files
            )
    assert not (dest / "swd.bin").exists()
    assert (dest / "base.bin").read_bytes() == b"synthetic-golden-only"
