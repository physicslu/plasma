"""PR2: Bundle v2 multi-component admission + sandbox-only install/activate/rollback.

No real PPU, SWPC, Web Console, FPGA or DUT is contacted. Uses local HTTP
loopback and temporary filesystem fixtures; no payload gets executed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from .test_ppu_generic_package_host_only_gate1 import (
    SOURCE, TARGET, coordinator, load, request, engine,
)
from .test_ppu_package_receive_admission_pr1 import loopback  # noqa: F401

contract = load("ppu_pr2_bundle_v2_contract", "ppu_unified_deployment.py")

PARTS = [
    ("ic-metadata", "ic-catalog", [], {
        "data/device.json": b'{"icpn":"STM32F103C8T6"}',
        "assets/lookup.dat": b"\x01\x02\x03",
    }),
    ("flash-profile", "programming-profile", ["ic-metadata"], {
        "data/geometry.yaml": b"flash: 65536\n",
    }),
    ("wordport", "python", ["flash-profile"], {
        "python/wordport.py": b"# NEVER EXECUTED\n",
        "config/wordport.json": b'{"mode":"sandbox"}',
    }),
    ("bridge", "native-c", ["wordport"], {
        "bin/bridge": b"\x7fELFhost-only-fixture",
        "lib/bridge.so": b"\x7fELFfake-shared-object",
    }),
    ("firmware", "firmware-asset", ["flash-profile"], {
        "data/firmware.hex": b":00000001FF\n",
    }),
    ("fpga-addon", "fpga-image", ["bridge"], {
        "fpga/addon.bit": b"FPGA NOT LOADED",
        "fpga/addon.hwh": b"HWH HOST ONLY",
    }),
]


def bundle(tmp: Path, *, version: str = "2026.10.31", changed: dict | None = None,
           mutate=None, parts=PARTS) -> tuple[Path, str]:
    tmp.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    components = []
    for name, kind, dependencies, data in parts:
        component_files = []
        for suffix, raw in data.items():
            path = f"payload/components/{name}/{suffix}"
            raw = changed.get(path, raw) if changed else raw
            files[path] = raw
            component_files.append({
                "path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw), "executable": suffix.startswith("bin/"),
            })
        components.append({
            "id": name, "kind": kind, "version": "1.0.0",
            "requires": list(dependencies), "files": component_files,
        })
    manifest = {
        "schema": contract.LEGACY_BUNDLE_SCHEMA, "name": "multi-purpose-bundle",
        "version": version, "purpose": "programming",
        "source_commit": SOURCE, "target": dict(TARGET),
        "components": components,
        "actions": ["install", "verify", "activate", "rollback"],
    }
    if mutate:
        mutate(manifest)
    archive = tmp / "bundle-v2.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        for path, raw in files.items():
            output.writestr(path, raw)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_bundle_v2_accepts_mixed_code_fpga_and_unbounded_data_categories(tmp_path):
    archive, digest = bundle(tmp_path)
    result = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET)
    assert result.kind == "bundle" and result.purpose == "programming"
    assert result.install_qualified is False
    assert len(result.components) == 6
    assert {c.kind for c in result.components} >= {
        "python", "native-c", "fpga-image", "ic-catalog", "programming-profile",
        "firmware-asset",
    }
    assert sum(len(c.files) for c in result.components) == len(result.files)


def test_bundle_v2_existing_one_lock_one_journal_host_only_transaction(tmp_path):
    archive, digest = bundle(tmp_path / "artifact")
    co = coordinator(tmp_path)
    receipt = co.execute_package_host_only(request(archive, digest))
    assert receipt["result"] == "PASS"
    assert receipt["host_only"] is True and receipt["install_qualified"] is False
    assert receipt["transaction"]["state"] == "package_active"
    assert receipt["package"]["purpose"] == "programming"
    assert len(receipt["package"]["components"]) == 6
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / "multi-purpose-bundle.json"
    selected = json.loads(active.read_text())
    stage = (co.paths.bootstrap_state_root / "host-only-packages" / "releases"
             / "multi-purpose-bundle" / selected["release_id"])
    assert (stage / "payload/components/ic-metadata/data/device.json").is_file()
    assert (stage / "payload/components/fpga-addon/fpga/addon.hwh").is_file()
    assert co.paths.journal.stat().st_mode & 0o077 == 0
    assert co.paths.lock.stat().st_mode & 0o077 == 0
    for path in (co.paths.product_root, co.paths.systemd_root, co.paths.config_root,
                 co.paths.runtime_state_root):
        assert not path.exists()


def test_bundle_v3_reuses_existing_http_admission_only(loopback, tmp_path):
    from .test_ppu_bundle_v3_packages_contract import bundle_v3
    api, paths, server = loopback
    archive, digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    submission = api.submit(kind="bundle", upload_id=upload_id)
    assert submission.state == "admitted"
    result = api.deployment_state(submission.transaction_id)["result"]
    assert result["stage"] == "package_admission_only"
    assert result["install_qualified"] is False
    plan = result["plan"]
    assert plan["kind"] == "bundle"
    assert plan["purpose"] == "programming"
    assert plan["archive_sha256"] == digest
    assert plan["bundle_schema"] == contract.BUNDLE_SCHEMA
    assert len(plan["packages"]) == 6
    assert "components" not in plan
    assert plan["execution_permitted"] is False
    assert server.deployment_thread is None
    assert not paths.product_root.exists()
    assert not paths.coordinator_journal.exists()


def test_bundle_v2_rollback_restores_previously_active_receipt(tmp_path):
    first, first_digest = bundle(tmp_path / "first")
    co = coordinator(tmp_path)
    assert co.execute_package_host_only(request(first, first_digest))["result"] == "PASS"
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / "multi-purpose-bundle.json"
    old = active.read_bytes()
    changed = {"payload/components/ic-metadata/data/device.json": b'{"icpn":"other"}'}
    second, second_digest = bundle(tmp_path / "second", version="2026.11.01", changed=changed)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_INJECTED_ACTIVATION_FAILURE"):
        co.execute_package_host_only(request(second, second_digest), inject_failure="after_activate")
    assert active.read_bytes() == old
    assert co.journal.read().state == "rolled_back"
    assert not co.paths.product_root.exists()


def test_bundle_v2_unprovable_rollback_latches_recovery_required(tmp_path):
    archive, digest = bundle(tmp_path / "first")
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_INJECTED_ACTIVATION_FAILURE"):
        co.execute_package_host_only(request(archive, digest), inject_failure="rollback_unknown")
    assert co.journal.read().state == "recovery_required"
    with pytest.raises(engine.DeploymentError, match="requires recovery"):
        co.execute_package_host_only(request(archive, digest))
    assert not co.paths.product_root.exists()


@pytest.mark.parametrize("mutator,reason", [
    (lambda m: m["target"].update(board="unexpected"), "BUNDLE_MANIFEST_CONTENT_DENIED"),
    (lambda m: m["components"][1]["requires"].append("absent"), "BUNDLE_DEPENDENCY_UNKNOWN"),
    (lambda m: m["components"][0]["requires"].append("bridge"), "BUNDLE_DEPENDENCY_CYCLE"),
    (lambda m: m["components"][1].update(id="ic-metadata"), "BUNDLE_COMPONENT_INVALID"),
    (lambda m: m["components"][0]["files"][0].update(executable=True),
     "BUNDLE_COMPONENT_FILE_KIND_DENIED"),
    (lambda m: m["components"][2]["files"][0].update(path="payload/components/other/python/wordport.py"),
     "BUNDLE_COMPONENT_FILE_KIND_DENIED"),
    (lambda m: m["components"][0]["files"][0].update(sha256="0"*64),
     "BUNDLE_FILE_SHA256_MISMATCH"),
    (lambda m: m.update(actions=["shell"]), "BUNDLE_ACTIONS_DENIED"),
    (lambda m: m["components"][5]["files"].pop(), "BUNDLE_FPGA_PAIR_DENIED"),
    (lambda m: m["components"][0].update(kind={"danger": "shell"}), "BUNDLE_COMPONENT_INVALID"),
    (lambda m: m.update(source_commit="b"*40), "BUNDLE_MANIFEST_CONTENT_DENIED"),
])
def test_bundle_v2_bad_manifest_rejected_before_install(tmp_path, mutator, reason):
    archive, digest = bundle(tmp_path, mutate=mutator)
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match=reason):
        co.execute_package_host_only(request(archive, digest))
    assert co.journal.read().state == "verify_failed"
    assert not co.paths.product_root.exists()
    assert not (co.paths.bootstrap_state_root / "host-only-packages").exists()


def test_retired_v2_and_v1_rejected_with_sha256_guard_preserved(tmp_path):
    archive, digest = bundle(tmp_path)
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_ARCHIVE_SHA256_MISMATCH"):
        contract.verify_host_only_artifact(
            archive, expected_sha256="0" * 64,
            source_commit=SOURCE, target_profile=TARGET,
        )
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_SCHEMA_UNSUPPORTED"):
        contract.verify_host_only_artifact(
            archive, expected_sha256=digest,
            source_commit=SOURCE, target_profile=TARGET,
        )

    from .test_ppu_generic_package_host_only_gate1 import package
    v1, v1digest = package(
        tmp_path / "legacy-v1", "compat-python", "python",
        {"payload/python/test.py": b"# retired v1"},
    )
    with pytest.raises(contract.UnifiedDeploymentError, match="PACKAGE_SCHEMA_UNSUPPORTED"):
        contract.verify_host_only_artifact(
            v1, expected_sha256=v1digest,
            source_commit=SOURCE, target_profile=TARGET,
        )


def test_bundle_v2_zip_symlink_and_unmanifested_file_denied(tmp_path):
    archive, digest = bundle(tmp_path / "normal")
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr("payload/components/ic-metadata/data/unlisted.dat", b"extra")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_UNDECLARED_OR_DUPLICATE_FILES"):
        contract.verify_host_only_artifact(archive, expected_sha256=digest,
                                           source_commit=SOURCE, target_profile=TARGET)
    archive, _ = bundle(tmp_path / "symlink")
    with zipfile.ZipFile(archive, "a") as zf:
        info = zipfile.ZipInfo("payload/components/ic-metadata/data/hidden")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "../escape")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_FILE_SET_DENIED"):
        contract.verify_host_only_artifact(archive, expected_sha256=digest,
                                           source_commit=SOURCE, target_profile=TARGET)


def test_bundle_v2_no_implicit_exec_or_fpga_load(tmp_path):
    archive, digest = bundle(tmp_path / "artifact")
    co = coordinator(tmp_path)
    result = co.execute_package_host_only(request(archive, digest))
    assert result["install_qualified"] is False
    assert "FPGA load" in result["not_claimed"]
    assert not co.paths.product_root.exists()
    assert not co.paths.systemd_root.exists()


def test_bundle_v2_client_fails_closed_for_incomplete_receipt():
    from .test_ppu_package_receive_admission_pr1 import client
    base_plan = {
        "kind": "bundle", "archive_sha256": "a" * 64,
        "execution_permitted": False, "requested_actions": [],
        "files": [], "purpose": "diagnostics",
        "components": [],
    }
    receipt = {
        "state": "admitted", "result": {
            "result": "PASS", "stage": "package_admission_only",
            "install_qualified": False, "plan": base_plan,
        },
    }
    assert not client._valid_package_admission(receipt, kind="bundle")
    base_plan["components"] = [
        {"id": "same", "kind": "ic-catalog", "version": "1",
         "requires": [], "files": ["payload/components/same/data/catalog.json"]},
        {"id": "same", "kind": "profile", "version": "1",
         "requires": [], "files": ["payload/components/same/data/profile.json"]},
    ]
    assert not client._valid_package_admission(receipt, kind="bundle")
