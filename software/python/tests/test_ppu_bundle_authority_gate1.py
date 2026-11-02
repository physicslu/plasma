"""B2 Master authority shared by Python, Native C and FPGA Assets (Host-only)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from .ppu_bundle_authority_fixture import provision_fixture_grant
from .test_ppu_bundle_v3_packages_contract import bundle_v3, contract, TARGET
from .test_ppu_package_receive_admission_pr1 import loopback  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "plasma_bundle_authority_host_only", ROOT / "scripts" / "ppu_bundle_authority.py"
)
assert spec and spec.loader
authority = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = authority
spec.loader.exec_module(authority)


def test_b2_one_master_grant_covers_python_native_c_and_fpga(tmp_path):
    archive, digest = bundle_v3(tmp_path / "input")
    class Paths:
        bundle_authority_policy = tmp_path / "master-grants.json"
    data = provision_fixture_grant(Paths, archive.read_bytes())
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=None, target_profile=TARGET
    )
    result = authority.approve_verified_bundle(
        verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123,
    )
    assert result["status"] == "MASTER_APPROVED"
    assert result["method"] == "root-provisioned-exact-bundle-sha256"
    assert result["archive_sha256"] == digest
    assert {"python", "native-c", "fpga-image"} <= set(result["allowed_kinds"])
    assert result["publisher"] == data["authorizations"][0]["publisher"]
    assert result["master_generation"] == 1


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p["authorizations"][0].__setitem__("archive_sha256", "f"*64),
     "BUNDLE_AUTHORITY_DIGEST_NOT_APPROVED"),
    (lambda p: p["authorizations"][0].__setitem__("source_commit", "f"*40),
     "BUNDLE_AUTHORITY_SCOPE_MISMATCH"),
    (lambda p: p["authorizations"][0].__setitem__("purpose", "other"),
     "BUNDLE_AUTHORITY_SCOPE_MISMATCH"),
    (lambda p: p["authorizations"][0]["target"].__setitem__("board", "other-board"),
     "BUNDLE_AUTHORITY_SCOPE_MISMATCH"),
    (lambda p: p["authorizations"][0].__setitem__("allowed_kinds", ["python"]),
     "BUNDLE_AUTHORITY_KIND_DENIED"),
    (lambda p: p["authorizations"][0].__setitem__("expires_epoch_s", 1),
     "BUNDLE_AUTHORITY_EXPIRED"),
    (lambda p: p["authorizations"].append(dict(p["authorizations"][0])),
     "BUNDLE_AUTHORITY_DUPLICATE_GRANT"),
    (lambda p: p.__setitem__("master_generation", 0),
     "BUNDLE_AUTHORITY_POLICY_INVALID"),
])
def test_b2_policy_exact_digest_source_scope_kind_and_expiration_fail_closed(
    tmp_path, mutation, code
):
    archive, digest = bundle_v3(tmp_path / "input")
    class Paths:
        bundle_authority_policy = tmp_path / "master-grants.json"
    data = provision_fixture_grant(Paths, archive.read_bytes())
    mutation(data)
    Paths.bundle_authority_policy.write_text(json.dumps(data))
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=None, target_profile=TARGET
    )
    with pytest.raises(authority.BundleAuthorityDenied, match=code):
        authority.approve_verified_bundle(
            verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123
        )


def test_b2_policy_missing_or_world_readable_cannot_grant_execution(tmp_path):
    archive, digest = bundle_v3(tmp_path / "input")
    class Paths:
        bundle_authority_policy = tmp_path / "master-grants.json"
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=None, target_profile=TARGET
    )
    with pytest.raises(authority.BundleAuthorityDenied, match="BUNDLE_AUTHORITY_NOT_PROVISIONED"):
        authority.approve_verified_bundle(
            verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123
        )
    provision_fixture_grant(Paths, archive.read_bytes())
    Paths.bundle_authority_policy.chmod(0o644)
    with pytest.raises(authority.BundleAuthorityDenied, match="BUNDLE_AUTHORITY_POLICY_UNTRUSTED"):
        authority.approve_verified_bundle(
            verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123
        )


def test_b2_policy_symlink_and_duplicate_json_fields_denied(tmp_path):
    archive, digest = bundle_v3(tmp_path / "input")
    class Paths:
        bundle_authority_policy = tmp_path / "master-grants.json"
    provision_fixture_grant(Paths, archive.read_bytes())
    actual = tmp_path / "private-real.json"
    Paths.bundle_authority_policy.rename(actual)
    Paths.bundle_authority_policy.symlink_to(actual)
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=None, target_profile=TARGET
    )
    with pytest.raises(authority.BundleAuthorityDenied, match="BUNDLE_AUTHORITY_POLICY_UNTRUSTED"):
        authority.approve_verified_bundle(
            verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123
        )
    Paths.bundle_authority_policy.unlink()
    Paths.bundle_authority_policy.write_text(
        '{"schema":"x","schema":"plasma.ppu.bundle-authority.v1"}'
    )
    Paths.bundle_authority_policy.chmod(0o600)
    with pytest.raises(authority.BundleAuthorityDenied, match="BUNDLE_AUTHORITY_DUPLICATE_FIELD"):
        authority.approve_verified_bundle(
            verified, policy_path=Paths.bundle_authority_policy, now_epoch_s=123
        )


def test_real_b2_refuses_without_independent_grant_and_no_receipt(loopback, tmp_path):
    api, paths, server = loopback
    archive, _digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    paths.bundle_authority_policy.unlink()
    with pytest.raises(Exception, match="BUNDLE_AUTHORITY_NOT_PROVISIONED"):
        server.admit_package({"kind": "bundle", "upload_id": upload_id})
    assert not paths.deployment_record.exists()
    assert not paths.product_root.exists()


def test_real_b2_receipt_separates_source_legality_from_runtime_execution(loopback, tmp_path):
    api, paths, server = loopback
    archive, digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    b2 = server.admit_package({"kind": "bundle", "upload_id": upload_id})
    assert b2["state"] == "admitted" and b2["result"]["result"] == "PASS"
    assert b2["result"]["source_authorized"] is True
    assert b2["result"]["install_qualified"] is False
    assert b2["result"]["plan"]["execution_permitted"] is False
    auth = b2["result"]["plan"]["authorization"]
    assert auth["status"] == "MASTER_APPROVED"
    assert auth["archive_sha256"] == digest
    assert "fpga-image" in auth["allowed_kinds"]
    assert not paths.product_root.exists()


def test_b2_bearer_and_manifest_do_not_supply_master_authority(loopback, tmp_path):
    api, paths, server = loopback
    archive, digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    data = json.loads(paths.bundle_authority_policy.read_text())
    # Wrong complete-archive hash with same Manifest source cannot authorize.
    data["authorizations"][0]["archive_sha256"] = hashlib.sha256(b"other").hexdigest()
    paths.bundle_authority_policy.write_text(json.dumps(data))
    with pytest.raises(Exception, match="BUNDLE_AUTHORITY_DIGEST_NOT_APPROVED"):
        server.admit_package({"kind": "bundle", "upload_id": upload_id})
    assert not paths.deployment_record.exists()
