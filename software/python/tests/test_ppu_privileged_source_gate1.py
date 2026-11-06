"""Host-only privilege-source closure qualification; no root, Z2 or FPGA."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

spec = importlib.util.spec_from_file_location(
    "ppu_privileged_source_test", ROOT / "scripts/ppu_privileged_source.py")
assert spec and spec.loader
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "trusted-fpga-code"
    root.mkdir()
    checksums = {}
    for rel in sorted(source.CODE_FILES):
        src = ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        target.chmod(0o644)
        checksums[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = root / source.MANIFEST
    manifest.write_text(json.dumps({
        "schema": source.SCHEMA, "files": checksums,
    }, sort_keys=True), encoding="utf-8")
    manifest.chmod(0o600)
    # Test confinement: real CLI NEVER overrides the root ownership/ancestor
    # checks, and always requires euid=0; these fixtures are not privileged.
    monkeypatch.setattr(source, "_parent_chain",
                        lambda path, uid: source._trusted(path, uid=uid, directory=True))
    return root


def check(root):
    return source.verify_source(root, expected_uid=os.getuid())


def test_privileged_source_exact_closure_verifies_without_execute(tmp_path, monkeypatch):
    root = fixture(tmp_path, monkeypatch)
    evidence = check(root)
    assert evidence["status"] == "VERIFIED_NOT_EXECUTED"
    assert evidence["source_commit_pin"] == "RETIRED"
    assert evidence["code_files"] == len(source.CODE_FILES)
    assert evidence["fpga_loaded"] is False


@pytest.mark.parametrize("attack,code", [
    ("alter_file", "PRIVILEGED_CODE_HASH_MISMATCH"),
    ("replace_symlink", "PRIVILEGED_CODE_OWNERSHIP_DENIED"),
    ("unlisted_py", "PRIVILEGED_CODE_EXTRA_FILE_DENIED"),
    ("unlisted_pyc", "PRIVILEGED_CODE_EXTRA_FILE_DENIED"),
    ("world_writable", "PRIVILEGED_CODE_OWNERSHIP_DENIED"),
    ("manifest_missing", "PRIVILEGED_CODE_MANIFEST_MISSING"),
    ("manifest_extra", "PRIVILEGED_CODE_MANIFEST_INVALID"),
    ("symlink_subdir", "PRIVILEGED_CODE_OWNERSHIP_DENIED"),
])
def test_privileged_source_denies_mutation(tmp_path, monkeypatch, attack, code):
    root = fixture(tmp_path, monkeypatch)
    source_file = root / "pl/hil/fpga_image_root.py"
    if attack == "alter_file":
        source_file.write_bytes(b"modified")
    elif attack == "replace_symlink":
        source_file.unlink()
        source_file.symlink_to(ROOT / "pl/hil/fpga_image_root.py")
    elif attack == "unlisted_py":
        (root / "pl/hil/unreviewed.py").write_text("print('attack')")
    elif attack == "unlisted_pyc":
        (root / "pl/hil/__pycache__.pyc").write_bytes(b"bytecode")
    elif attack == "world_writable":
        source_file.chmod(0o666)
    elif attack == "manifest_missing":
        (root / source.MANIFEST).unlink()
    elif attack == "manifest_extra":
        file = root / source.MANIFEST
        data = json.loads(file.read_text())
        data["files"]["pl/hil/surprise.py"] = "b" * 64
        file.write_text(json.dumps(data))
    elif attack == "symlink_subdir":
        (root / "pl/hil").rename(root / "pl/hil-real")
        (root / "pl/hil").symlink_to(root / "pl/hil-real", target_is_directory=True)
    with pytest.raises((source.PrivilegedSourceDenied, OSError), match=code):
        check(root)


def test_privileged_source_cli_denies_parameters_and_unprivileged(monkeypatch, capsys):
    assert source.main(["/tmp/unsafe"]) == 2
    monkeypatch.setattr(source.os, "geteuid", lambda: 1000)
    assert source.main([]) == 2
    assert "PRIVILEGED_CODE_ROOT_REQUIRED" in capsys.readouterr().err


def _installer_fixture(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    files = list(source.CODE_FILES) + ["ppu_privileged_source.py"]
    for rel in files:
        src = ROOT / (("scripts/" + rel) if rel == "ppu_privileged_source.py" else rel)
        dst = factory / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(0o644)
    spec = importlib.util.spec_from_file_location(
        "ppu_privileged_source_install_test",
        ROOT / "scripts/ppu-privileged-source-install.py",
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    monkeypatch.setattr(installer, "_verifier", lambda _: source)
    monkeypatch.setattr(source, "_parent_chain",
                        lambda path, uid: source._trusted(path, uid=uid, directory=True))
    return installer, factory, tmp_path / "privileged/fpga-root"


def test_privileged_source_explicit_provision_no_hardware(tmp_path, monkeypatch):
    installer, factory, destination = _installer_fixture(tmp_path, monkeypatch)
    outcome = installer.provision(factory, destination, _test_uid=os.getuid())
    assert outcome["result"] == "PROVISIONED_NOT_EXECUTED"
    assert check(destination)["status"] == "VERIFIED_NOT_EXECUTED"
    assert outcome["fpga_loaded"] is False
    with pytest.raises(installer.ProvisionDenied, match="ALREADY_INSTALLED"):
        installer.provision(factory, destination, _test_uid=os.getuid())



def _offline_upgrade_fixture(tmp_path, monkeypatch):
    from contextlib import nullcontext
    installer, factory, destination = _installer_fixture(tmp_path, monkeypatch)
    installer.provision(factory, destination, _test_uid=os.getuid())
    old = source.verify_source(destination, expected_uid=os.getuid())
    journal = tmp_path / "state" / "fpga-deployment-state.json"
    journal.parent.mkdir(mode=0o700)
    journal.parent.chmod(0o700)
    journal.write_text(json.dumps({
        "status": "IMAGE", "boot_id": "boot-verified-1234"
    }), encoding="utf-8")
    journal.chmod(0o600)
    boot = tmp_path / "boot"
    boot.write_text("boot-verified-1234\n")
    manager = tmp_path / "manager-state"
    manager.write_text("operating\n")
    monkeypatch.setattr(installer, "JOURNAL", journal)
    monkeypatch.setattr(installer, "BOOT_ID", boot)
    monkeypatch.setattr(installer, "FPGA_MANAGER", manager)
    monkeypatch.setattr(installer, "_quiescent", lambda: None)
    monkeypatch.setattr(installer, "_maintenance_locks", lambda _uid: nullcontext())
    # New Root code, same known-good Manifest schema and exact source inventory.
    candidate = factory / "pl/hil/fpga_image_admission.py"
    candidate.write_text(candidate.read_text() + "\n# host-only candidate v2\n")
    return installer, factory, destination, journal, old["code_manifest_sha256"]


def test_root_upgrade_is_offline_atomic_with_retained_rollback(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    before = journal.read_bytes()
    result = installer.upgrade(
        factory, destination, expected_current_manifest_sha256=old_sha,
        _test_uid=os.getuid())
    assert result["result"] == "UPGRADED_NOT_EXECUTED"
    assert result["previous_manifest_sha256"] == old_sha
    assert result["current_manifest_sha256"] != old_sha
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == result["current_manifest_sha256"]
    assert source.verify_source(
        destination.with_name(destination.name + ".previous"),
        expected_uid=os.getuid())["code_manifest_sha256"] == old_sha
    assert journal.read_bytes() == before
    assert result["dut"] == "NOT_RUN" and result["fpga_reloaded"] is False
    assert result["service_restarted"] is False


def test_root_upgrade_rejects_stale_source_without_modification(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    with pytest.raises(installer.ProvisionDenied, match="STALE_SOURCE"):
        installer.upgrade(
            factory, destination, expected_current_manifest_sha256="0"*64,
            _test_uid=os.getuid())
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha
    assert not destination.with_name(destination.name + ".previous").exists()


def test_root_upgrade_rejects_changed_boot_or_manager(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    journal.write_text(json.dumps({"status": "IMAGE", "boot_id": "wrong-boot"}))
    with pytest.raises(installer.ProvisionDenied, match="IMAGE_UNVERIFIED"):
        installer.upgrade(
            factory, destination, expected_current_manifest_sha256=old_sha,
            _test_uid=os.getuid())
    assert not destination.with_name(destination.name + ".previous").exists()


def test_root_upgrade_requires_quiescence(tmp_path, monkeypatch):
    from types import SimpleNamespace
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    monkeypatch.undo()  # prove the production checker, not the injected no-op
    # Load a distinct module for isolated direct quiescence test.
    spec = importlib.util.spec_from_file_location(
        "ppu_privileged_quiescence_test", ROOT / "scripts/ppu-privileged-source-install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def running(argv, **kwargs):
        if argv[0] == "/bin/systemctl":
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\nActiveState=active\nSubState=running\n"))
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(module.subprocess, "run", running)
    with pytest.raises(module.ProvisionDenied, match="SERVICE_NOT_QUIESCENT"):
        module._quiescent()


def test_root_upgrade_requires_no_admission_or_openocd(tmp_path, monkeypatch):
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location(
        "ppu_privileged_owners_test", ROOT / "scripts/ppu-privileged-source-install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = tmp_path / "admissions"
    records.mkdir()
    monkeypatch.setattr(module, "ADMISSIONS", records)
    def stopped(argv, **kwargs):
        if argv[0] == "/bin/systemctl":
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\nActiveState=inactive\nSubState=dead\n"))
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(module.subprocess, "run", stopped)
    module._quiescent()
    (records / "swd-site2-admission").touch()
    with pytest.raises(module.ProvisionDenied, match="ADMISSION_OWNER_PRESENT"):
        module._quiescent()
    (records / "swd-site2-admission").unlink()
    def openocd(argv, **kwargs):
        if argv[0] == "/usr/bin/pgrep":
            return SimpleNamespace(returncode=0, stdout=b"1234")
        return stopped(argv, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", openocd)
    with pytest.raises(module.ProvisionDenied, match="OPENOCD_PRESENT"):
        module._quiescent()


def test_root_rollback_restores_verified_old_code_and_preserves_journal(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    new = installer.upgrade(
        factory, destination, expected_current_manifest_sha256=old_sha,
        _test_uid=os.getuid())
    before = journal.read_bytes()
    result = installer.rollback(
        factory, destination, expected_backup_manifest_sha256=old_sha,
        _test_uid=os.getuid())
    assert result["result"] == "ROLLED_BACK_NOT_EXECUTED"
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha
    assert journal.read_bytes() == before
    rejected = destination.with_name(destination.name + ".rejected")
    assert source.verify_source(rejected, expected_uid=os.getuid())[
        "code_manifest_sha256"] == new["current_manifest_sha256"]
    assert result["dut"] == "NOT_RUN"


def test_root_rollback_recovers_interrupted_directory_swap(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    installer.upgrade(factory, destination,
                      expected_current_manifest_sha256=old_sha,
                      _test_uid=os.getuid())
    destination.rename(destination.with_name(destination.name + ".next"))
    result = installer.rollback(
        factory, destination, expected_backup_manifest_sha256=old_sha,
        _test_uid=os.getuid())
    assert result["result"] == "ROLLED_BACK_NOT_EXECUTED"
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha


def test_root_upgrade_rejects_untrusted_factory_file_and_preserves_old(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    candidate = factory / "pl/hil/fpga_image_admission.py"
    candidate.unlink()
    candidate.symlink_to(ROOT / "pl/hil/fpga_image_admission.py")
    with pytest.raises(installer.ProvisionDenied, match="SYMLINK_DENIED"):
        installer.upgrade(
            factory, destination, expected_current_manifest_sha256=old_sha,
            _test_uid=os.getuid())
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha



def test_root_upgrade_no_change_cleans_unactivated_stage(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    same = factory / "pl/hil/fpga_image_admission.py"
    shutil.copyfile(ROOT / "pl/hil/fpga_image_admission.py", same)
    with pytest.raises(installer.ProvisionDenied, match="PRIVILEGED_UPGRADE_NO_CHANGE"):
        installer.upgrade(
            factory, destination, expected_current_manifest_sha256=old_sha,
            _test_uid=os.getuid())
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha
    assert not destination.with_name(destination.name + ".next").exists()
    assert not destination.with_name(destination.name + ".previous").exists()


def test_root_upgrade_postverify_failure_restores_old_source(tmp_path, monkeypatch):
    installer, factory, destination, journal, old_sha = _offline_upgrade_fixture(
        tmp_path, monkeypatch)
    original = installer._held_image_fingerprint
    observed = {"calls": 0}
    def fault(uid):
        observed["calls"] += 1
        return original(uid) if observed["calls"] == 1 else "0" * 64
    monkeypatch.setattr(installer, "_held_image_fingerprint", fault)
    with pytest.raises(installer.ProvisionDenied, match="POSTVERIFY_FAILED"):
        installer.upgrade(
            factory, destination, expected_current_manifest_sha256=old_sha,
            _test_uid=os.getuid())
    assert source.verify_source(destination, expected_uid=os.getuid())[
        "code_manifest_sha256"] == old_sha
    assert not destination.with_name(destination.name + ".previous").exists()
    # Failed new source is quarantined, not silently activated.
    assert destination.with_name(destination.name + ".next").is_dir()


def test_root_upgrade_lock_is_exclusive_and_fail_closed(tmp_path, monkeypatch):
    from contextlib import ExitStack
    installer, _, _, _, _ = _offline_upgrade_fixture(tmp_path, monkeypatch)
    owner = tmp_path / "owner"
    owner.mkdir(mode=0o700)
    monkeypatch.setattr(installer, "GLOBAL_LOCK", owner / "supervisor.lock")
    monkeypatch.setattr(installer, "RELOAD_FENCE", tmp_path / "reload.lock")
    # Test the real _maintenance_locks() while keeping host-only paths.
    spec = importlib.util.spec_from_file_location(
        "ppu_privileged_lock_test", ROOT / "scripts/ppu-privileged-source-install.py")
    lock_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lock_mod)
    monkeypatch.setattr(lock_mod, "GLOBAL_LOCK", owner / "supervisor.lock")
    monkeypatch.setattr(lock_mod, "RELOAD_FENCE", tmp_path / "reload.lock")
    with lock_mod._maintenance_locks(os.getuid()):
        with pytest.raises(lock_mod.ProvisionDenied, match="OWNER_BUSY"):
            with lock_mod._maintenance_locks(os.getuid()):
                pytest.fail("second maintenance lock must never be acquired")
    # First holder released both FDs: next verified acquire is allowed.
    with lock_mod._maintenance_locks(os.getuid()):
        pass



def test_privileged_source_provision_denies_untrusted_input(tmp_path, monkeypatch):
    installer, factory, destination = _installer_fixture(tmp_path, monkeypatch)
    (factory / "pl/hil/fpga_image_root.py").unlink()
    (factory / "pl/hil/fpga_image_root.py").symlink_to(ROOT / "pl/hil/fpga_image_root.py")
    with pytest.raises(installer.ProvisionDenied, match="SYMLINK_DENIED"):
        installer.provision(factory, destination, _test_uid=os.getuid())
    assert not destination.exists()
