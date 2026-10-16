"""Safety boundaries with synthetic evidence; functional algorithms use actual RTL."""
from datetime import datetime, timedelta, timezone
import json
import mmap
from pathlib import Path
from unittest.mock import Mock

import pytest
from pl.hil.pspl02 import contract as c, mmio as m, runner, recovery, staging, inventory as collect
from pl.hil.pspl02 import identity
from pl.tests.test_swd04_staging import bit_fixture


def inventory():
    return dict(architecture="armv7l", pynq_version="3.1.1", device_model_confirmed=True,
                board_identity=dict(schema_version=1, board="PYNQ-Z2", method="device_tree_model",
                                    model="TUL PYNQ-Z2", compatible=["xlnx,zynq-7000"]),
                fpga_manager_state="operating", fclk0_hz=100_000_000, fclk0_enabled=True,
                root_audit_complete=True, pl_users=[], audit_errors=[], metadata_backup_matches=True,
                original_drivers_reviewed=True, services=dict.fromkeys(c.SERVICES, "active"),
                observed_utc=datetime.now(timezone.utc).isoformat(), metadata_sha256={"a": "a"*64},
                driver_bindings={"40000000.fabric": "uio_pdrv_genirq",
                                 "43c00000.audio-codec-ctrl": "uio_pdrv_genirq"}, uio=[
                    dict(name="fabric", address="0x40000000", size="0x00010000"),
                    dict(name="audio-codec-ctrl", address="0x43C00000", size="0x00010000")])


def attestation():
    return dict(schema_version=1, **dict.fromkeys(c.PREREQUISITES, True))


@pytest.mark.parametrize("field", c.PREREQUISITES)
def test_no_automatic_attestation(field):
    inv, att = inventory(), attestation()
    c.preflight(inv, att)
    for value in (False, "true", 1, None):
        att[field] = value
        with pytest.raises(c.SafetyError): c.preflight(inv, att)


@pytest.mark.parametrize("field,value", [
    ("root_audit_complete", False), ("fclk0_enabled", False), ("fclk0_hz", 10_000_000),
    ("pl_users", ["retained mmap"]), ("audit_errors", ["Permission denied"]),
    ("services", {}), ("metadata_backup_matches", False), ("original_drivers_reviewed", False),
    ("metadata_sha256", {}), ("driver_bindings", {}),
    ("uio", []), ("architecture", "x86_64"), ("observed_utc", "2026-01-01T00:00:00+00:00"),
    ("board_identity", None),
])
def test_incomplete_inventory_fails_closed(field, value):
    inv = inventory(); inv[field] = value
    with pytest.raises(c.SafetyError): c.preflight(inv, attestation())


@pytest.mark.parametrize("stamp", [None, "", "invalid", "2026-10-15T10:00:00",
    (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()])
def test_freshness(stamp):
    with pytest.raises(c.SafetyError): c.require_fresh(stamp)


def artifacts(tmp_path, monkeypatch):
    payload = bytes.fromhex("ffffffffaa99556620000000")
    values = dict(bit=bit_fixture(payload), bin=b"".join(payload[i:i+4][::-1]
                  for i in range(0, len(payload), 4))+bytes.fromhex("00000020"),
                  hwh=b"hwh", **{"base.bin": b"base", "base.hwh": b"basehwh"})
    doc = dict(source_git_sha=c.SOURCE, design_variant="control_waveform_loopback",
               acceptance={"LB-HOST": "PASS", "LB-Z2": "NOT_RUN", "real_swd_target": "NOT_RUN"})
    values["manifest"] = json.dumps(doc).encode()
    paths = {key: tmp_path/key for key in values}
    for key, path in paths.items(): path.write_bytes(values[key])
    monkeypatch.setattr(c, "HASHES", {key: c.sha256_file(path) for key, path in paths.items()})
    return paths


@pytest.mark.parametrize("bad", list(c.HASHES))
def test_every_artifact_and_recovery_byte_is_bound(tmp_path, monkeypatch, bad):
    paths = artifacts(tmp_path, monkeypatch)
    assert c.verify_artifacts(paths)["hardware_execution"] == "NOT_RUN"
    paths[bad].write_bytes(paths[bad].read_bytes()+b"corrupt")
    with pytest.raises(c.SafetyError): c.verify_artifacts(paths)


def test_bin_format_independent_of_hash(tmp_path, monkeypatch):
    paths = artifacts(tmp_path, monkeypatch)
    paths["bin"].write_bytes(paths["bit"].read_bytes())
    monkeypatch.setitem(c.HASHES, "bin", c.sha256_file(paths["bin"]))
    with pytest.raises(c.SafetyError, match="conversion"): c.verify_artifacts(paths)


def test_existing_evidence_immutable(tmp_path):
    path = tmp_path/"result.json"
    c.write_record(path, {"first": True})
    with pytest.raises(FileExistsError): c.write_record(path, {})
    assert c.json_object(path) == {"first": True}


def test_bad_mmio_never_reaches_backend():
    hw = Mock(); io = m.RestrictedMMIO(hw)
    for address in (0, 0x40003000, m.TX+1, True):
        with pytest.raises(c.SafetyError): io.read(address)
        with pytest.raises(c.SafetyError): io.write(address, 0)
    for address, value in ((m.COUNT, 0), (m.HALF, 1), (m.CMD, 3), (m.TX, -1), (m.TX, True)):
        with pytest.raises(c.SafetyError): io.write(address, value)
    with pytest.raises(c.SafetyError): m.RestrictedMMIO(hw, readonly=True).write(m.CMD, 1)
    assert hw.mock_calls == []


def test_identity_mismatch_stops_before_writes():
    hw = Mock(); hw.read32.return_value = 0
    with pytest.raises(c.SafetyError): m.identity(m.RestrictedMMIO(hw))
    hw.read32.assert_called_once_with(m.IDENTITY)
    hw.write32.assert_not_called()


def test_poll_bound_and_no_reset_or_retry():
    hw = Mock(); hw.read32.return_value = 1
    with pytest.raises(c.SafetyError): m.completion(m.RestrictedMMIO(hw), limit=3, sleep_seconds=0)
    assert hw.read32.call_count == 3
    hw.write32.assert_not_called()


def test_failed_write_retains_attempt_in_audit():
    hw = Mock(); hw.write32.side_effect = OSError("bus error")
    io = m.RestrictedMMIO(hw)
    with pytest.raises(OSError): io.write(m.CMD, 1)
    assert io.audit == [{"op": "write", "address": m.CMD, "value": 1, "state": "attempted"}]


def test_live_default_inert_before_artifacts_or_devices(tmp_path, monkeypatch):
    verify = Mock(side_effect=AssertionError("must not read artifacts"))
    monkeypatch.setattr(c, "verify_artifacts", verify)
    args = ["live", "--output", str(tmp_path/"live")]
    for key in c.HASHES: args.extend(["--"+key.replace(".", "-"), "missing"])
    assert runner.main(args) == 2
    verify.assert_not_called()
    assert not (tmp_path/"live").exists()


def recovery_observations():
    fields = ("base_loaded_once_and_operating", "metadata_backup_matches", "drivers_restored",
              "ssh_verified", "uart_still_usable", "jupyter_http_verified", "gateway_live_verified",
              "gateway_ready_verified", "no_new_kernel_axi_or_fpga_errors", "no_shared_service_changes",
              "no_ps7_init_or_ddr_reinitialization")
    return dict(recovery_sha256={k: c.HASHES[k] for k in ("base.bin", "base.hwh")},
                **dict.fromkeys(fields, True))


def test_recovery_compares_resource_identity_and_requires_independent_observations():
    before, after, observed = inventory(), inventory(), recovery_observations()
    after["uio"].reverse()
    assert recovery.verify(before, after, observed)["restoration"] == "PASS"
    for key in observed:
        bad = dict(observed, **{key: False})
        with pytest.raises(c.SafetyError): recovery.verify(before, after, bad)
    after["driver_bindings"] = {"fabric": "different"}
    with pytest.raises(c.SafetyError): recovery.verify(before, after, observed)


def session_files(tmp_path):
    p0, session, log = (tmp_path/name for name in ("p0.json", "session.json", "load.log"))
    log.write_text("synthetic load record; no hardware action")
    c.write_record(p0, dict(qualification="PSPL-02/SWD-00", preflight="PASS", sha256=c.HASHES,
                            inventory=inventory(), attestation=attestation()))
    fields = ("candidate_loaded_and_verified", "original_uios_unbound",
              "kernel_and_clocks_reviewed_after_load", "uart_login_verified_now",
              "independent_power_recovery_ready", "operator_present", "no_shared_service_changes",
              "no_asynchronous_pl_reconfiguration")
    record = dict(stage="IDENTITY", p0_sha256=c.sha256_file(p0), observed_utc=runner.utc(),
                  board_identity_sha256=identity.digest_report(inventory()["board_identity"]),
                  load_log=str(log), load_log_sha256=c.sha256_file(log), **dict.fromkeys(fields, True))
    c.write_record(session, record)
    return p0, session, record


@pytest.mark.parametrize("bad", ["stage", "p0_sha256", "observed_utc", "load_log_sha256",
                                 "operator_present", "no_shared_service_changes", "board_identity_sha256"])
def test_live_session_binds_current_loading_session(tmp_path, bad):
    p0, path, record = session_files(tmp_path)
    runner.require_session(p0, path, "IDENTITY", None)
    record[bad] = False
    path.write_text(json.dumps(record))
    with pytest.raises(c.SafetyError): runner.require_session(p0, path, "IDENTITY", None)


def test_no_skipping_stages_or_reusing_other_load_result(tmp_path):
    p0, path, record = session_files(tmp_path)
    record["stage"] = "PSPL02"; path.write_text(json.dumps(record))
    with pytest.raises(c.SafetyError): runner.require_session(p0, path, "PSPL02", None)
    prior = tmp_path/"previous.json"
    proof = dict(qualification="PSPL-02/SWD-00", result="PASS", stage="IDENTITY",
                 p0_sha256=c.sha256_file(p0), load_log_sha256=record["load_log_sha256"], sha256=c.HASHES)
    c.write_record(prior, proof)
    runner.require_session(p0, path, "PSPL02", prior)
    for field, value in (("stage", "RESET"), ("result", "FAIL"),
                         ("load_log_sha256", "0"*64), ("p0_sha256", "0"*64)):
        prior.write_text(json.dumps(dict(proof, **{field: value})))
        with pytest.raises(c.SafetyError): runner.require_session(p0, path, "PSPL02", prior)


def test_staging_templates_default_false_and_no_overwrite(tmp_path, monkeypatch):
    paths = artifacts(tmp_path, monkeypatch)
    output = tmp_path/"kit"
    assert staging.create(paths, output)["hardware_execution"] == "NOT_RUN"
    att = c.json_object(output/"templates/attestation.json")
    assert all(att[key] is False for key in c.PREREQUISITES)
    for stage in c.STAGES:
        assert c.json_object(output/f"templates/session-{stage}.json")["operator_present"] is False
    for line in (output/"SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        assert c.sha256_file(output/name) == digest
    with pytest.raises(FileExistsError): staging.create(paths, output)


def test_retained_mmio_mapping_detected_after_fd_closed(tmp_path):
    process = tmp_path/"100"; process.mkdir(); (process/"fd").mkdir()
    (process/"maps").write_text("40000000-40001000 rw-s /dev/mem\n")
    hits, errors = collect.process_users(tmp_path)
    assert not errors and hits[0]["kind"] == "mmap"
    (process/"fd/2").symlink_to("/dev/dri/renderD128")
    hits, errors = collect.process_users(tmp_path)
    assert not errors and len(hits) == 2


def test_metadata_is_hashed_never_unpickled(tmp_path):
    (tmp_path/"_current_metadata.pkl").write_bytes(b"not even a pickle")
    (tmp_path/"global_pl_state_0.json").write_text("invalid json but retained bytes")
    (tmp_path/"unrelated").write_text("ignore")
    assert set(collect.metadata_hashes(tmp_path)) == {"_current_metadata.pkl", "global_pl_state_0.json"}


def test_development_preflight_skips_repeated_human_attestations():
    inv = inventory()
    # Existing trusted identity and fresh privileged inventory remain mandatory.
    att = dict(schema_version=1, **dict.fromkeys(c.DEVELOPMENT_PREREQUISITES, True))
    c.preflight(inv, att, profile="development")
    with pytest.raises(c.SafetyError, match="Unverified prerequisite"):
        c.preflight(inv, att, profile="qualification")
    for key in c.DEVELOPMENT_PREREQUISITES:
        bad = dict(att, **{key: False})
        with pytest.raises(c.SafetyError, match="Unverified prerequisite"):
            c.preflight(inv, bad, profile="development")
    bad_inventory = dict(inv, pl_users=[{"pid": "123", "kind": "mmap"}])
    with pytest.raises(c.SafetyError, match="PL users"):
        c.preflight(bad_inventory, att, profile="development")


def test_development_session_rejects_axi_fault_stages_without_human_booleans(tmp_path):
    p0, session, record = session_files(tmp_path)
    proof = c.json_object(p0)
    proof["profile"] = "development"
    proof["attestation"] = dict(
        schema_version=1, **dict.fromkeys(c.DEVELOPMENT_PREREQUISITES, True))
    p0.write_text(json.dumps(proof))
    record["p0_sha256"] = c.sha256_file(p0)
    for name in ("uart_login_verified_now", "independent_power_recovery_ready", "operator_present"):
        del record[name]
    session.write_text(json.dumps(record))
    assert runner.require_session(p0, session, "IDENTITY", None)["profile"] == "development"
    with pytest.raises(c.SafetyError, match="excludes ERROR/RESET"):
        runner.require_session(p0, session, "ERROR", None)


def test_staging_includes_false_by_default_development_templates(tmp_path, monkeypatch):
    kit = tmp_path/"kit"
    staging.create(artifacts(tmp_path, monkeypatch), kit)
    dev_att = c.json_object(kit/"templates/attestation-development.json")
    assert dev_att["schema_version"] == 1
    assert all(dev_att[key] is False for key in c.DEVELOPMENT_PREREQUISITES)
    for stage in c.DEVELOPMENT_STAGES:
        dev_session = c.json_object(kit/f"templates/session-development-{stage}.json")
        assert "operator_present" not in dev_session
        assert dev_session["candidate_loaded_and_verified"] is False
    assert not (kit/"templates/session-development-ERROR.json").exists()


# The real backend is exercised against ordinary file-backed RAM, never PL.
@pytest.fixture
def mapped_ram(tmp_path, monkeypatch):
    native_mmap = mmap.mmap
    opened, mappings = [], []
    monkeypatch.setattr(runner.Path, "is_char_device", lambda _: True)
    monkeypatch.setattr(runner.os, "open", lambda *args: 123)
    close = Mock()
    monkeypatch.setattr(runner.os, "close", close)

    def map_ram(fd, length, *, flags, prot, offset):
        assert fd == 123 and length == 4096 and flags == mmap.MAP_SHARED
        path = tmp_path / str(offset)
        if not path.exists():
            path.write_bytes(bytes.fromhex("aabbccdd") * 1024)
        f = path.open("r+b")
        opened.append(f)
        page = native_mmap(f.fileno(), length, flags=flags, prot=prot)
        mappings.append((offset, page, prot, path))
        return page

    monkeypatch.setattr(runner.mmap, "mmap", map_ram)
    yield mappings, close
    for f in opened:
        f.close()


def test_word_writes_preserve_neighbors_and_use_word_indices(mapped_ram):
    mappings, close = mapped_ram
    with runner.DevMem(readonly=False) as hardware:
        hardware.write32(m.CONTROL, 0x12345678)
        assert hardware.read32(m.CONTROL) == 0x12345678
        assert hardware.read32(m.CONTROL+4) == 0xddccbbaa
        hardware.write32(m.TX, 0x87654321)  # byte offset 8 -> word index 2
        assert hardware.read32(m.TX) == 0x87654321
        assert hardware.read32(m.SWD+4) == 0xddccbbaa
        assert hardware.read32(m.SWD+12) == 0xddccbbaa
        hardware.write32(m.CONTROL, 0xffffffff)
        hardware.write32(m.CONTROL, 0)
        assert hardware.read32(m.CONTROL) == 0
        assert len(mappings) == 2  # one mapping per aperture, reused
    assert all(page.closed for _, page, _, _ in mappings)
    assert mappings[1][3].read_bytes()[8:12] == bytes.fromhex("21436587")
    close.assert_called_once_with(123)


def test_identity_mapping_stays_read_only_and_views_release_on_error(mapped_ram):
    mappings, close = mapped_ram
    with pytest.raises(RuntimeError, match="stage failure"):
        with runner.DevMem(readonly=True) as hardware:
            assert hardware.read32(m.IDENTITY) == 0xddccbbaa
            with pytest.raises(c.SafetyError):
                hardware.write32(m.CONTROL, 0)
            assert mappings[0][2] == mmap.PROT_READ
            assert hardware.words[m.IDENTITY].readonly
            raise RuntimeError("stage failure")
    assert mappings[0][1].closed  # no retained exported view / BufferError
    close.assert_called_once_with(123)


def test_invalid_access_fails_before_any_mapping(mapped_ram):
    mappings, _ = mapped_ram
    with runner.DevMem(readonly=False) as hardware:
        for address in (m.CONTROL+1, m.CONTROL+2, m.CONTROL+3, 0x40003000):
            with pytest.raises(c.SafetyError):
                hardware.write32(address, 0)
        for value in (-1, 1 << 32, True):
            with pytest.raises(c.SafetyError):
                hardware.write32(m.CONTROL, value)
        assert mappings == []
