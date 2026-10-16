"""Board identity from fake DT/files only; no hardware, network or real host ID."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pl.hil.pspl02 import identity as b, contract as c, runner, inventory
from pl.hil.swd04.collect import collect
from pl.tests.test_swd04_collect import fake_z2


def enrolled(tmp_path, monkeypatch):
    dt = tmp_path/"dt"; dt.mkdir()
    (dt/"compatible").write_bytes(b"xlnx,zynq-7000\0")
    machine = tmp_path/"machine-id"; machine.write_text("0123456789abcdef0123456789abcdef\n")
    physical = tmp_path/"physical-review"; physical.write_bytes(b"synthetic independent physical evidence")
    base_bin = tmp_path/"base.bin"; base_bin.write_bytes(b"synthetic recovery firmware")
    base_hwh = tmp_path/"base.hwh"; base_hwh.write_bytes(b"synthetic recovery handoff")
    monkeypatch.setattr(b, "RECOVERY_BIN_SHA256", b.sha256_file(base_bin))
    monkeypatch.setattr(b, "RECOVERY_HWH_SHA256", b.sha256_file(base_hwh))
    record = dict(schema_version=1, board="PYNQ-Z2", physical_board_marking_verified=True,
                  machine_id_sha256=hashlib.sha256(machine.read_text().strip().encode()).hexdigest(),
                  physical_evidence_sha256=b.sha256_file(physical), base_bin_sha256=b.sha256_file(base_bin),
                  base_hwh_sha256=b.sha256_file(base_hwh))
    path = tmp_path/"enrollment.json"; path.write_text(json.dumps(record))
    return dict(device_tree=dt, machine_id=machine, board_record=path,
                board_record_sha256=b.sha256_file(path), board_physical_evidence=physical,
                board_base_bin=base_bin, board_base_hwh=base_hwh)


@pytest.mark.parametrize("model", [b"TUL PYNQ-Z2\0", b"PYNQ-Z2\0", b"PYNQ Z2\0"])
def test_valid_board_specific_model(tmp_path, model):
    (tmp_path/"model").write_bytes(model)
    (tmp_path/"compatible").write_bytes(b"xlnx,zynq-7000\0")
    report = b.verify(device_tree=tmp_path)
    assert report["method"] == "device_tree_model"
    b.validate_report(report)


def test_missing_model_with_independently_pinned_enrollment(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    # Match the real Linux DT symlink arrangement without creating a model.
    symlink = tmp_path/"proc-device-tree"; symlink.symlink_to(args["device_tree"], target_is_directory=True)
    args["device_tree"] = symlink
    report = b.verify(**args)
    assert report["model"] is None and report["method"] == "reviewed_enrollment"
    assert report["enrollment_sha256"] == args["board_record_sha256"]
    assert not (symlink/"model").exists()
    assert "0123456789abcdef0123456789abcdef" not in json.dumps(report)


@pytest.mark.parametrize("compatible", [None, b"xlnx,zynq-7000\0"])
def test_generic_compatible_or_no_properties_never_identifies_board(tmp_path, monkeypatch, compatible):
    if compatible is not None: (tmp_path/"compatible").write_bytes(compatible)
    monkeypatch.setenv("BOARD", "PYNQ-Z2")
    with pytest.raises(c.SafetyError): b.verify(device_tree=tmp_path)


@pytest.mark.parametrize("model", [b"Other board\0", b"not-PYNQ-Z2\0", b"PYNQ-Z20\0", b"\0",
                                   b"TUL PYNQ-Z2\0Other board\0", b"TUL PYNQ-Z2\0\0"])
def test_incompatible_or_malformed_model_cannot_be_overridden(tmp_path, monkeypatch, model):
    args = enrolled(tmp_path, monkeypatch)
    (args["device_tree"]/"model").write_bytes(model)
    with pytest.raises(c.SafetyError): b.verify(**args)


@pytest.mark.parametrize("compatible", [b"vendor,other-board\0xlnx,zynq-7000\0",
                                         b"xlnx,zynq-7000\0vendor,other-board\0",
                                         b"xlnx,zynq-7000\0\0invalid\0", b"xlnx,zynq-7000\0\0", b""])
def test_incompatible_or_malformed_compatible(tmp_path, monkeypatch, compatible):
    args = enrolled(tmp_path, monkeypatch)
    (args["device_tree"]/"compatible").write_bytes(compatible)
    with pytest.raises(c.SafetyError): b.verify(**args)


@pytest.mark.parametrize("missing", b.OPTION_NAMES)
def test_no_partial_or_self_declared_enrollment(tmp_path, monkeypatch, missing):
    args = enrolled(tmp_path, monkeypatch); args[missing] = None
    with pytest.raises(c.SafetyError): b.verify(**args)


@pytest.mark.parametrize("changed", ["board_record", "machine_id", "board_physical_evidence",
                                    "board_base_bin", "board_base_hwh"])
def test_changed_actual_evidence_rejected(tmp_path, monkeypatch, changed):
    args = enrolled(tmp_path, monkeypatch)
    b.verify(**args)
    args[changed].write_bytes(b"changed after review")
    with pytest.raises((c.SafetyError, ValueError)): b.verify(**args)


@pytest.mark.parametrize("field,value", [("board", "PYNQ-Z1"), ("schema_version", True),
    ("physical_board_marking_verified", False), ("physical_board_marking_verified", 1),
    ("machine_id_sha256", "0"*64), ("physical_evidence_sha256", "0"*64)])
def test_even_pinned_record_requires_supported_evidence(tmp_path, monkeypatch, field, value):
    args = enrolled(tmp_path, monkeypatch)
    record = json.loads(args["board_record"].read_text()); record[field] = value
    args["board_record"].write_text(json.dumps(record))
    args["board_record_sha256"] = b.sha256_file(args["board_record"])
    with pytest.raises(c.SafetyError): b.verify(**args)


def test_copying_all_software_fingerprints_does_not_replace_physical_review(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    record = json.loads(args["board_record"].read_text())
    record.pop("physical_board_marking_verified")
    args["board_record"].write_text(json.dumps(record))
    args["board_record_sha256"] = b.sha256_file(args["board_record"])
    with pytest.raises(c.SafetyError): b.verify(**args)


def test_empty_physical_evidence_rejected_even_with_matching_pin(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    args["board_physical_evidence"].write_bytes(b"")
    record = json.loads(args["board_record"].read_text())
    record["physical_evidence_sha256"] = b.sha256_file(args["board_physical_evidence"])
    args["board_record"].write_text(json.dumps(record))
    args["board_record_sha256"] = b.sha256_file(args["board_record"])
    with pytest.raises(c.SafetyError, match="nonempty"): b.verify(**args)


def test_duplicate_enrollment_keys_rejected_even_with_matching_pin(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    raw = args["board_record"].read_text()
    args["board_record"].write_text('{"board": "different", '+raw[1:])
    args["board_record_sha256"] = b.sha256_file(args["board_record"])
    with pytest.raises(c.SafetyError, match="Duplicate"): b.verify(**args)


def test_wrong_recovery_pair_rejected_even_if_record_matches_it(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    record = json.loads(args["board_record"].read_text())
    args["board_base_bin"].write_bytes(b"different firmware")
    record["base_bin_sha256"] = b.sha256_file(args["board_base_bin"])
    args["board_record"].write_text(json.dumps(record))
    args["board_record_sha256"] = b.sha256_file(args["board_record"])
    with pytest.raises(c.SafetyError, match="recovery fingerprints"): b.verify(**args)


def test_permission_error_not_treated_as_missing_model(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    original = Path.read_bytes
    def read(path):
        if path == args["device_tree"]/"model": raise PermissionError("synthetic unreadable model")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(PermissionError): b.verify(**args)


def test_swd04_default_model_behavior_unchanged(tmp_path):
    sysroot, dt, clock, metadata = fake_z2(tmp_path)
    args = dict(sysroot=sysroot, device_tree=dt, clock_summary=clock, metadata_path=metadata,
                service_status=lambda _: "active", architecture="armv7l", pynq_version="3.1.1")
    assert collect(**args)["device_model_confirmed"] is True
    (dt/"model").write_bytes(b"other board\0")
    assert collect(**args)["device_model_confirmed"] is False
    (dt/"model").unlink()
    (dt/"compatible").write_bytes(b"xlnx,zynq-7000\0")
    with pytest.raises(FileNotFoundError): collect(**args)


def test_inventory_and_runtime_use_same_verified_missing_model_identity(tmp_path, monkeypatch):
    args = enrolled(tmp_path, monkeypatch)
    report = b.verify(**args)
    fake = tmp_path/"collector"; fake.mkdir()
    sysroot, dt, clock, metadata = fake_z2(fake)
    (dt/"model").unlink()
    snapshot = collect(sysroot=sysroot, device_tree=dt, clock_summary=clock,
                       metadata_path=metadata, service_status=lambda _: "active",
                       architecture="armv7l", pynq_version="3.1.1",
                       board_identity_check=lambda: b.verify(**args))
    assert snapshot["board_identity"] == report and snapshot["device_model_confirmed"] is True
    # Fake the remaining read-only runtime prerequisites; never open /dev/mem.
    root = tmp_path/"runtime"; root.mkdir()
    state = root/"sys/class/fpga_manager/fpga0/state"; state.parent.mkdir(parents=True)
    state.write_text("operating")
    summary = root/"sys/kernel/debug/clk/clk_summary"; summary.parent.mkdir(parents=True)
    summary.write_text("fclk0 1 1 0 100000000\n")
    for name in ("metadata", "backup"):
        folder = root/name; folder.mkdir(); (folder/"_current_metadata.pkl").write_bytes(b"retained bytes")
    selected, backup = root/"metadata/_current_metadata.pkl", root/"backup/_current_metadata.pkl"
    session = dict(metadata_file=str(selected), metadata_backup=str(backup),
                   metadata_sha256=b.sha256_file(selected), board_identity_sha256=b.digest_report(report))
    original_verify = b.verify
    monkeypatch.setattr(b, "verify", lambda **unused: original_verify(**args))
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setattr(runner.platform, "machine", lambda: "armv7l")
    monkeypatch.setattr(runner, "Path", lambda value: root/str(value).lstrip("/")
                        if str(value).startswith("/sys/") else Path(value))
    monkeypatch.setattr(runner, "systemctl_status", lambda _: "active")
    monkeypatch.setattr(inventory, "process_users", lambda: ([], []))
    runner.runtime_audit(session)
    args["board_physical_evidence"].write_bytes(b"changed since inventory")
    with pytest.raises(c.SafetyError): runner.runtime_audit(session)


def test_runtime_rejects_identity_different_from_preflight_before_other_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    monkeypatch.setattr(runner.platform, "machine", lambda: "armv7l")
    state = tmp_path/"state"; state.write_text("operating")
    monkeypatch.setattr(runner, "Path", lambda _: state)
    monkeypatch.setattr(b, "verify", lambda **unused: dict(schema_version=1, board="PYNQ-Z2",
        method="device_tree_model", model="TUL PYNQ-Z2", compatible=["xlnx,zynq-7000"]))
    with pytest.raises(c.SafetyError, match="differs from preflight"):
        runner.runtime_audit(dict(board_identity_sha256="0"*64))
