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
    ("manifest_missing", "FileNotFoundError"),
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
