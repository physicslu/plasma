"""Host-only safety contracts for the temporary S2 Factory Path 2 helper."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/plasma_s2_factory_refresh_path2.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("plasma_s2_factory_refresh_tested", SOURCE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_source_factory_archive_has_accepted_worker_and_manifest():
    mod = load_helper()
    archive = mod.make_archive()  # local source only, no network or device access
    assert 0 < len(archive) <= 2 * 1024 * 1024
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as f:
        entries = {
            m.name[len(mod.BUNDLE_ROOT)+1:]: f.extractfile(m).read()
            for m in f.getmembers()
            if m.isfile() and m.name.startswith(mod.BUNDLE_ROOT + "/")
        }
    assert set(entries) == set(mod.ALL_FILES) | {"manifest.json", "SHA256SUMS"}
    manifest = json.loads(entries["manifest.json"])
    assert manifest["git_sha"] == "37a7823d89973dd0f6656ed276a7a290eb033f98"
    assert manifest["runtime_included"] is False
    assert manifest["fpga_update"] is False
    assert mod.ACTIVE_B == "387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c"
    worker = entries["scripts/ppu_site_worker.py"]
    blob = hashlib.sha1(f"blob {len(worker)}\0".encode() + worker).hexdigest()
    assert blob == mod.EXPECTED_WORKER_BLOB
    assert b"OPERATION_IN_PROGRESS" in worker
    expected = "".join(
        hashlib.sha256(entries[k]).hexdigest() + "  " + k + "\n"
        for k in ["manifest.json", *sorted(mod.ALL_FILES)]
    )
    assert entries["SHA256SUMS"].decode() == expected


def test_wrong_worker_source_fails_before_any_transfer(monkeypatch):
    mod = load_helper()
    monkeypatch.setattr(mod, "EXPECTED_WORKER_BLOB", "0" * 40)
    with pytest.raises(RuntimeError, match="FACTORY_ACCEPTED_S2_WORKER_SOURCE_MISMATCH"):
        mod.make_archive()


def test_no_explicit_once_approval_denies_before_device_access(monkeypatch, capsys):
    mod = load_helper()
    actual = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    monkeypatch.setattr(sys, "argv", [
        str(SOURCE), "--host", "192.168.2.99", "--source-sha", actual
    ])
    assert mod.main() == 69
    output = capsys.readouterr().out
    payload = json.loads(output.split("PLASMA_FACTORY_REFRESH=", 1)[1])
    assert payload["reason"] == "OWNER_ONCE_APPROVAL_REQUIRED"
    assert payload["fpga"] == payload["dut"] == "NOT_RUN"


def test_wrong_source_sha_denies_before_device_access(monkeypatch, capsys):
    mod = load_helper()
    monkeypatch.setattr(sys, "argv", [
        str(SOURCE), "--host", "192.168.2.99", "--source-sha", "0" * 40,
        "--approved-once"
    ])
    assert mod.main() == 69
    output = capsys.readouterr().out
    payload = json.loads(output.split("PLASMA_FACTORY_REFRESH=", 1)[1])
    assert payload["reason"] == "SOURCE_SHA_MISMATCH"
    assert payload["runtime_install"] == "NOT_RUN"


def _safe_snapshot(mod):
    return {
        "status": "READ_ONLY_OBSERVED",
        "readiness": "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS",
        "blockers": [],
        "z2": {
            "release": {"current": mod.OLD},
            "engine": {"status": "VERIFIED", "driver": "plasma_swd",
                       "abi": 5,
                       "openocd_sha256_observed": mod.EXPECTED_ENGINE_BINARY,
                       "admission_sha256_observed": mod.EXPECTED_ENGINE_ADMISSION},
            "fpga": {"status": "IMAGE", "boot_match": True,
                     "manager_state": "operating", "image_id": "paired-image"},
            "site2_seal": {"present": False},
            "site2_admission": {"present": False},
            "openocd_pids": [],
        },
        "rest": {"active_job_count": 0, "lease_busy": False,
                 "activation_active": False, "site2_idle": True},
    }


def test_live_preflight_requires_all_safety_fields():
    mod = load_helper()
    record = _safe_snapshot(mod)
    assert mod.require_site2_safe_observation(record)["fpga_image_id"] == "paired-image"
    from copy import deepcopy
    mutations = [
        ("readiness", "BLOCKED_OR_UNVERIFIED"),
        ("z2", {"release": {"current": mod.OLD}}),
        ("rest", {"active_job_count": 1}),
    ]
    for key, value in mutations:
        invalid = deepcopy(record)
        invalid[key] = value
        with pytest.raises(RuntimeError, match="SITE2_PHYSICAL_PRECHECK_BLOCKED"):
            mod.require_site2_safe_observation(invalid)
    for key in ("site2_seal", "site2_admission"):
        invalid = deepcopy(record)
        invalid["z2"][key]["present"] = True
        with pytest.raises(RuntimeError, match="SITE2_PHYSICAL_PRECHECK_BLOCKED"):
            mod.require_site2_safe_observation(invalid)
    invalid = deepcopy(record)
    invalid["z2"]["fpga"]["boot_match"] = False
    with pytest.raises(RuntimeError, match="SITE2_PHYSICAL_PRECHECK_BLOCKED"):
        mod.require_site2_safe_observation(invalid)
