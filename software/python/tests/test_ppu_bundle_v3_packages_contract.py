"""Canonical Bundle v3: Bundle -> Packages -> Files, retired v1/v2 rejected at admission.

No Z2, SWPC, Installer, FPGA or DUT. Only local ZIP / HTTP / Coordinator mocks.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from .test_ppu_bundle_v2_host_only_pr2 import bundle as legacy_bundle, contract, PARTS
from .test_ppu_generic_package_host_only_gate1 import SOURCE, TARGET, coordinator, request
from .test_ppu_package_receive_admission_pr1 import loopback  # noqa: F401
from .test_ppu_package_receive_admission_pr1 import client


def bundle_v3(tmp_path: Path, *, mutate=None, legacy: bool = False, parts=PARTS):
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive, _digest = legacy_bundle(tmp_path / "legacy", parts=parts)
    with zipfile.ZipFile(archive) as src:
        manifest = json.loads(src.read("manifest.json"))
        if not legacy:
            manifest["schema"] = contract.BUNDLE_SCHEMA
            manifest["packages"] = manifest.pop("components")
            for package in manifest["packages"]:
                for member in package["files"]:
                    member["path"] = member["path"].replace(
                        "payload/components/", "payload/packages/", 1
                    )
        if mutate:
            mutate(manifest)
        target = tmp_path / ("bundle-legacy.zip" if legacy else "bundle-v3.zip")
        with zipfile.ZipFile(target, "w") as out:
            out.writestr("manifest.json", json.dumps(manifest))
            for info in src.infolist():
                if info.filename == "manifest.json":
                    continue
                dest = (info.filename if legacy else info.filename.replace(
                    "payload/components/", "payload/packages/", 1))
                out.writestr(dest, src.read(info.filename))
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


def test_v3_schema_and_single_plural_packages_exact_structure(tmp_path):
    archive, digest = bundle_v3(tmp_path)
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
    )
    assert verified.schema == "plasma.ppu.bundle.v3"
    assert len(verified.packages) == 6
    assert isinstance(verified.packages[0], contract.VerifiedBundlePackage)
    assert all(f.path.startswith("payload/packages/") for f in verified.files)
    assert verified.install_qualified is False
    assert verified.actions == ("install", "verify", "activate", "rollback")
    plan = contract.resolve_host_only_bundle(verified, trusted_inventory={})
    assert plan["schema"] == "plasma.ppu.bundle-resolution.v2"
    assert len(plan["package_order"]) == 6
    assert "component_order" not in plan and "component_sha256" not in plan
    assert plan["reuse"] == []
    assert set(plan["stage"]) == {package.id for package in verified.packages}
    assert plan["package_order"].index("ic-metadata") < plan["package_order"].index("flash-profile")
    assert plan["package_order"].index("flash-profile") < plan["package_order"].index("wordport")
    assert plan["install_qualified"] is False


def test_v3_host_only_coordinator_uses_packages_not_components(tmp_path):
    archive, digest = bundle_v3(tmp_path / "archive")
    co = coordinator(tmp_path)
    receipt = co.execute_package_host_only(request(archive, digest))
    assert receipt["result"] == "PASS"
    assert len(receipt["bundle"]["packages"]) == 6
    assert "components" not in receipt["bundle"]
    assert "package" not in receipt  # canonical v3 envelope, v2 remains legacy
    assert receipt["install_qualified"] is False
    assert not co.paths.product_root.exists()


def test_v3_real_loopback_http_admission_returns_packages_receipt(loopback, tmp_path):
    api, paths, server = loopback
    archive, digest = bundle_v3(tmp_path)
    uploaded = api.upload(archive.read_bytes())
    admission = api.submit(kind="bundle", upload_id=uploaded)
    assert admission.state == "admitted"
    receipt = api.deployment_state(admission.transaction_id)
    plan = receipt["result"]["plan"]
    assert client._valid_package_admission(receipt, kind="bundle")
    assert plan["bundle_schema"] == contract.BUNDLE_SCHEMA
    assert len(plan["packages"]) == 6
    assert "components" not in plan
    assert plan["execution_permitted"] is False
    assert receipt["result"]["install_qualified"] is False
    assert receipt["result"]["stage"] == "package_admission_only"
    assert not paths.product_root.exists()
    assert server.deployment_thread is None


def test_v2_retired_archive_rejected_at_admission(loopback, tmp_path):
    archive, digest = bundle_v3(tmp_path, legacy=True)
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_SCHEMA_UNSUPPORTED"):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
        )
    api, paths, server = loopback
    uid = api.upload(archive.read_bytes())
    with pytest.raises(Exception):
        api.submit(kind="bundle", upload_id=uid)
    assert not paths.product_root.exists()
    assert server.deployment_thread is None


@pytest.mark.parametrize("modify", [
    lambda m: m.__setitem__("components", m.pop("packages")),
    lambda m: m.__setitem__("components", list(m["packages"])),
    lambda m: m["packages"][0]["requires"].append("missing-package"),
    lambda m: m["packages"][0]["requires"].append("wordport"),
    lambda m: m["packages"][0]["files"][0].__setitem__("path", "payload/components/ic-metadata/data/device.json"),
])
def test_v3_rejects_legacy_field_dependency_or_member_path(tmp_path, modify):
    archive, digest = bundle_v3(tmp_path, mutate=modify)
    with pytest.raises(contract.UnifiedDeploymentError):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
        )


def test_client_rejects_ambiguous_v2_v3_receipt_fields():
    r = {"state": "admitted", "result": {"result": "PASS",
         "stage": "package_admission_only", "install_qualified": False,
         "plan": {
             "kind": "bundle", "bundle_schema": contract.BUNDLE_SCHEMA,
             "execution_permitted": False, "archive_sha256": "a" * 64,
             "purpose": "programming", "files": [], "requested_actions": [],
             "packages": [{"id": "x", "kind": "ic-catalog", "version": "1",
                           "requires": [], "files": []}],
         }}}
    assert client._valid_package_admission(r, kind="bundle")
    r["result"]["plan"]["components"] = list(r["result"]["plan"]["packages"])
    assert not client._valid_package_admission(r, kind="bundle")
    del r["result"]["plan"]["components"]
    del r["result"]["plan"]["bundle_schema"]
    assert not client._valid_package_admission(r, kind="bundle")



@pytest.mark.parametrize("count,accepted", [(1, True), (32, True), (33, False)])
def test_v3_exact_package_count_boundary(tmp_path, count, accepted):
    parts = [(
        f"catalog-{i:02d}", "ic-catalog", [],
        {"data/catalog.json": f'{{"i":{i}}}'.encode()},
    ) for i in range(count)]
    archive, digest = bundle_v3(tmp_path, parts=parts)
    if not accepted:
        with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_MANIFEST_CONTENT_DENIED"):
            contract.verify_host_only_artifact(
                archive, expected_sha256=digest, source_commit=SOURCE,
                target_profile=TARGET,
            )
    else:
        verified = contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE,
            target_profile=TARGET,
        )
        assert len(verified.packages) == count
