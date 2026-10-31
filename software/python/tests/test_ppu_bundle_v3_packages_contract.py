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

import importlib.util
import sys
from types import SimpleNamespace

from .test_ppu_package_receive_admission_pr1 import loopback  # noqa: F401
from .test_ppu_package_receive_admission_pr1 import client

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "a" * 40
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("ppu_v3_independent_contract", "ppu_unified_deployment.py")
engine = load("ppu_v3_independent_engine", "ppu-bootstrap-deployment.py")

PARTS = [
    ("ic-metadata", "ic-catalog", [], {
        "data/device.json": b'{"icpn":"STM32F103C8T6"}',
        "assets/lookup.dat": b"\\x01\\x02\\x03",
    }),
    ("flash-profile", "programming-profile", ["ic-metadata"], {
        "data/geometry.yaml": b"flash: 65536\\n",
    }),
    ("wordport", "python", ["flash-profile"], {
        "python/wordport.py": b"# NEVER EXECUTED\\n",
        "config/wordport.json": b'{"mode":"sandbox"}',
    }),
    ("bridge", "native-c", ["wordport"], {
        "bin/bridge": b"\\x7fELFhost-only-fixture",
        "lib/bridge.so": b"\\x7fELFfake-shared-object",
    }),
    ("firmware", "firmware-asset", ["flash-profile"], {
        "data/firmware.hex": b":00000001FF\\n",
    }),
    ("fpga-addon", "fpga-image", ["bridge"], {
        "fpga/addon.bit": b"FPGA NOT LOADED",
        "fpga/addon.hwh": b"HWH HOST ONLY",
    }),
]


def coordinator(tmp):
    paths = engine.DeploymentPaths(
        bootstrap_state_root=tmp / "isolated-bootstrap-state",
        product_root=tmp / "production-untouched",
        config_root=tmp / "config-untouched",
        runtime_state_root=tmp / "runtime-untouched",
        log_root=tmp / "log-untouched",
        systemd_root=tmp / "systemd-untouched",
    )
    return engine.DeploymentCoordinator(
        paths=paths, installer=SimpleNamespace(), clock=lambda: 123.0,
    )


def request(archive, digest):
    return engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET)


def bundle_v3(tmp_path: Path, *, mutate=None, parts=PARTS):
    tmp_path.mkdir(parents=True, exist_ok=True)
    files = {}
    packages = []
    for name, kind, dependencies, data in parts:
        members = []
        for suffix, raw in data.items():
            path = f"payload/packages/{name}/{suffix}"
            files[path] = raw
            members.append({
                "path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw), "executable": suffix.startswith("bin/"),
            })
        packages.append({
            "id": name, "kind": kind, "version": "1.0.0",
            "requires": list(dependencies), "files": members,
        })
    manifest = {
        "schema": contract.BUNDLE_SCHEMA,
        "name": "multi-purpose-bundle",
        "version": "2026.10.31",
        "purpose": "programming",
        "source_commit": SOURCE,
        "target": dict(TARGET),
        "packages": packages,
        "actions": ["install", "verify", "activate", "rollback"],
    }
    if mutate:
        mutate(manifest)
    target = tmp_path / "bundle-v3.zip"
    with zipfile.ZipFile(target, "w") as out:
        out.writestr("manifest.json", json.dumps(manifest))
        for filename, data in files.items():
            out.writestr(filename, data)
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


def test_minimal_delta_same_transport_repeated_v3_admission(loopback, tmp_path):
    """Reuse the proven upload/admission route; never infer installation from admission."""
    api, paths, server = loopback
    parts = [("wordport", "python", [], {"python/wordport.py": b"# host-only\n"})]
    archive, digest = bundle_v3(tmp_path, parts=parts)
    payload = archive.read_bytes()
    receipts = []
    for _ in range(2):
        upload_id = api.upload(payload)
        admitted = api.submit(kind="bundle", upload_id=upload_id)
        assert admitted.state == "admitted"
        receipt = api.deployment_state(admitted.transaction_id)
        assert client._valid_package_admission(receipt, kind="bundle")
        result = receipt["result"]
        assert result["stage"] == "package_admission_only"
        assert result["install_qualified"] is False
        assert result["plan"]["execution_permitted"] is False
        assert result["plan"]["archive_sha256"] == digest
        assert len(result["plan"]["packages"]) == 1
        receipts.append(receipt)
    assert len(receipts) == 2
    assert not paths.product_root.exists()
    assert not paths.coordinator_journal.exists()
    assert server.deployment_thread is None


@pytest.mark.parametrize("failure,expected_state", [
    ("after_stage", "rolled_back"),
    ("after_activate", "rolled_back"),
    ("rollback_unknown", "recovery_required"),
])
def test_v3_host_only_activation_and_rollback(tmp_path, failure, expected_state):
    """Exercise v3 activation receipt and failure recovery in a temp sandbox only."""

    parts_old = [("wordport", "python", [], {
        "python/wordport.py": b"# prior v3 release\\n",
    })]
    parts_new = [("wordport", "python", [], {
        "python/wordport.py": b"# replacement v3 release\\n",
    })]
    old_archive, old_digest = bundle_v3(tmp_path / "old", parts=parts_old)
    new_archive, new_digest = bundle_v3(tmp_path / "new", parts=parts_new)
    co = coordinator(tmp_path)
    first = co.execute_package_host_only(request(old_archive, old_digest))
    assert first["result"] == "PASS"
    assert first["transaction"]["state"] == "package_active"
    assert first["install_qualified"] is False
    active = (co.paths.bootstrap_state_root / "host-only-packages" / "active"
              / "multi-purpose-bundle.json")
    previous = active.read_bytes()
    assert json.loads(previous)["archive_sha256"] == old_digest

    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_INJECTED"):
        co.execute_package_host_only(
            request(new_archive, new_digest), inject_failure=failure,
        )
    assert co.journal.read().state == expected_state
    if expected_state == "rolled_back":
        assert active.read_bytes() == previous
    else:
        with pytest.raises(engine.DeploymentError, match="requires recovery"):
            co.execute_package_host_only(request(old_archive, old_digest))

    for path in (co.paths.product_root, co.paths.systemd_root,
                 co.paths.config_root, co.paths.runtime_state_root):
        assert not path.exists()


def test_v3_host_only_activation_switches_receipt_without_running_payload(tmp_path):
    parts_old = [("wordport", "python", [], {
        "python/wordport.py": b"# old release\\n",
    })]
    parts_new = [("wordport", "python", [], {
        "python/wordport.py": b"# new release\\n",
    })]
    old_archive, old_digest = bundle_v3(tmp_path / "old", parts=parts_old)
    new_archive, new_digest = bundle_v3(tmp_path / "new", parts=parts_new)
    co = coordinator(tmp_path)
    co.execute_package_host_only(request(old_archive, old_digest))
    second = co.execute_package_host_only(request(new_archive, new_digest))
    assert second["result"] == "PASS"
    assert second["transaction"]["state"] == "package_active"
    assert second["transaction"]["previous_release"] is not None
    assert second["install_qualified"] is False
    active = (co.paths.bootstrap_state_root / "host-only-packages" / "active"
              / "multi-purpose-bundle.json")
    assert json.loads(active.read_bytes())["archive_sha256"] == new_digest
    assert not co.paths.product_root.exists()
    assert not co.paths.systemd_root.exists()


def test_v3_rejects_legacy_package_v1_at_canonical_entry(tmp_path):
    archive, digest = bundle_v3(tmp_path)
    with zipfile.ZipFile(archive, "r") as source:
        manifest = json.loads(source.read("manifest.json"))
        members = [(name, source.read(name)) for name in source.namelist() if name != "manifest.json"]
    manifest["schema"] = "plasma.ppu.package.v1"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        for name, data in members:
            output.writestr(name, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_SCHEMA_UNSUPPORTED"):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
        )


def test_v3_rejects_duplicate_manifest_key(tmp_path):
    archive, _ = bundle_v3(tmp_path)
    with zipfile.ZipFile(archive) as source:
        raw = source.read("manifest.json").decode()
        members = [(name, source.read(name)) for name in source.namelist() if name != "manifest.json"]
    malformed = raw.replace('{"schema":', '{"schema":"plasma.ppu.bundle.v3","schema":', 1)
    assert malformed != raw
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", malformed)
        for name, data in members:
            output.writestr(name, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
        )


def test_v3_rejects_file_hash_mismatch(tmp_path):
    archive, digest = bundle_v3(tmp_path, mutate=lambda m: m["packages"][0]["files"][0].update(sha256="0" * 64))
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_FILE_SHA256_MISMATCH"):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET
        )
