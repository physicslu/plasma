"""B3 v2 install + FPGA load: Host-only, NO real Z2, FPGA Manager or DUT.

Coordinator tests inject a fake Root bundle-load and a fake Runtime Job
quiesce lease. Root tests run ``fpga_image_root.bundle_load`` against a
temporary firmware folder with the hardware guard functions patched out.
Every denial must leave the PL untouched (no download) and active.json
unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from contextlib import ExitStack, contextmanager, nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from pl.hil import fpga_image_guard as protected_guard
from pl.hil import fpga_image_root as protected_root
from pl.hil import fpga_image_admission as protected_admission

from .test_ppu_bundle_v3_packages_contract import ROOT, engine, load
from .test_ppu_b3_z2_install_gate1 import (
    b3_request, build_generic_assets, make_coordinator,
)
from .test_ppu_bundle_v3_smoke_execution_gate1 import build_smoke

assets = load("ppu_b3_fpga_load_asset_set_gate1", "ppu_asset_set.py")
IMAGE_ID = "z2-custom-swd-v2"
BITSTREAM = b"synthetic-no-hardware-fpga-bin-v2"


def fpga_bundle(tmp_path: Path):
    data = json.loads(
        (ROOT / "pl/projects/z2-bluepill-rbb/image-manifest.json").read_text()
    )
    data["image_id"] = IMAGE_ID
    data["firmware_name"] = "swd.bin"
    data["firmware_sha256"] = hashlib.sha256(BITSTREAM).hexdigest()
    manifest = json.dumps(data, sort_keys=True).encode()
    archive, digest = build_generic_assets(
        tmp_path / "bundle", bitstream=BITSTREAM, fpga_manifest=manifest,
    )
    return archive, digest, data["firmware_sha256"], manifest


def load_request(archive, digest, fpga_load=True):
    request = b3_request(archive, digest)
    return engine.BundleV3InstallRequest(
        archive=request.archive, source_commit=request.source_commit,
        artifact_sha256=request.artifact_sha256,
        target_profile=request.target_profile,
        api_transaction_id=request.api_transaction_id, fpga_load=fpga_load,
    )


class Harness:
    """Fake Root bundle-load + fake Runtime lease with an ordered event log."""

    def __init__(self, tmp_path: Path, outcome=None, lease_error=None):
        self.events: list[str] = []
        self.outcome = outcome
        self.lease_error = lease_error
        self.co = make_coordinator(tmp_path)
        self.co.root_bundle_loader = self.loader
        self.co.quiescence_lease = self.lease
        self.held = False
        original = self.co.journal.write

        def write(record, state, **updates):
            self.events.append("journal:" + state)
            return original(record, state, **updates)

        self.co.journal.write = write

    @contextmanager
    def lease(self):
        if self.lease_error is not None:
            raise self.lease_error
        self.events.append("lease:acquired")
        self.held = True
        try:
            yield {"lease_kind": "connection_held", "active_job_count": 0}
        finally:
            self.held = False
            self.events.append("lease:released")

    def loader(self, digest):
        assert self.held, "Root bundle-load must run inside the Runtime quiesce lease"
        self.events.append("root:bundle-load")
        if callable(self.outcome):
            return self.outcome(digest)
        return self.outcome

    def active(self):
        return assets.read_active(self.co.paths.product_root)


def loaded(digest, bin_sha):
    return {
        "stage": "bundle-load", "result": "fpga_loaded",
        "asset_set_sha256": digest, "fpga_image_id": IMAGE_ID,
        "fpga_bin_sha256": bin_sha, "fpga_manifest_sha256": "c" * 64,
        "manifest_promoted": True, "download_count": 1, "test_count": 1,
        "identity": "IDENTITY_PASS", "lease_id": "fpga-x", "boot_id": "boot-1",
        "auto_restore": False, "dut": "NOT_RUN",
    }


# --- Coordinator ---------------------------------------------------------


def test_b3_fpga_load_publishes_active_set_only_after_identity_pass(tmp_path):
    archive, digest, bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path)
    h.outcome = lambda sha: (
        h.events.append("active-before-root:" + h.active()["state"]),
        loaded(sha, bin_sha))[1]
    receipt = h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert receipt["schema"] == "plasma.ppu.b3-deployment-receipt.v2"
    assert receipt["stage"] == "bundle_install_and_fpga_load"
    assert receipt["fpga"] == "LOADED"
    assert receipt["fpga_load"]["result"] == "fpga_loaded"
    assert receipt["fpga_load"]["fpga_image_id"] == IMAGE_ID
    assert receipt["fpga_load"]["fpga_bin_sha256"] == bin_sha
    assert receipt["fpga_load"]["identity"] == "IDENTITY_PASS"
    assert receipt["fpga_load"]["auto_restore"] is False
    assert receipt["active_asset_set"]["asset_set_sha256"] == digest
    assert receipt["runtime_site_readmission"] == "REQUIRED"
    assert receipt["dut"] == "NOT_RUN"
    assert receipt["transaction"]["state"] == "fpga_loaded"
    assert h.active()["asset_set_sha256"] == digest
    assert h.events == [
        "journal:received", "journal:verifying", "journal:verified",
        "journal:staging", "journal:bundle_installed",
        "lease:acquired", "journal:fpga_loading",
        "root:bundle-load", "active-before-root:EMPTY",
        "journal:activating", "journal:fpga_loaded", "lease:released",
    ]


def test_b3_without_fpga_load_is_install_only_v2_receipt(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome=AssertionError("must not run"))
    receipt = h.co.execute_bundle_v3_install(load_request(archive, digest, fpga_load=False))
    assert receipt["schema"] == "plasma.ppu.b3-deployment-receipt.v2"
    assert receipt["stage"] == "bundle_install_only"
    assert receipt["fpga"] == "NOT_RUN"
    assert receipt["fpga_load"] == {"requested": False, "result": "NOT_RUN"}
    assert receipt["active_asset_set"] is None
    assert receipt["runtime_site_readmission"] == "NOT_REQUIRED"
    assert "root:bundle-load" not in h.events
    assert "lease:acquired" not in h.events
    assert h.active()["state"] == "EMPTY"


def test_b3_fpga_load_requires_an_fpga_image_package(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    h = Harness(tmp_path, outcome=AssertionError("must not run"))
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_REQUIRES_FPGA_IMAGE"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    record = h.co.journal.read()
    assert record.state == "verify_failed"
    assert record.error_code == "b3_fpga_load_requires_fpga_image"
    assert "journal:staging" not in h.events
    assert "root:bundle-load" not in h.events
    assert h.active()["state"] == "EMPTY"


def test_b3_fpga_load_denied_when_runtime_quiesce_refused(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome=AssertionError("must not run"),
                lease_error=assets.AssetSetError("ASSET_SET_QUIESCE_NOT_GRANTED"))
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_DENIED"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    record = h.co.journal.read()
    assert record.state == "fpga_load_denied"
    assert record.error_code == "b3_runtime_quiesce_denied"
    assert "root:bundle-load" not in h.events
    assert h.active()["state"] == "EMPTY"
    # A denial is a known safe terminal state: the next transaction may run.
    h.lease_error = None
    h.outcome = lambda sha: loaded(sha, hashlib.sha256(BITSTREAM).hexdigest())
    assert h.co.execute_bundle_v3_install(load_request(archive, digest))["fpga"] == "LOADED"


def test_b3_fpga_load_denied_when_staged_set_tampered_after_install(tmp_path):
    archive, digest, bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path)

    original = h.co._asset_helper

    def tampering_helper():
        helper = original()
        image = (h.co.paths.product_root / "assets/staged" / digest
                 / "payload/packages/custom-swd/fpga/swd.bin")
        image.chmod(0o600)
        image.write_bytes(b"altered")
        return helper

    h.co._asset_helper = tampering_helper
    h.outcome = AssertionError("must not run")
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_DENIED"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.co.journal.read().state == "fpga_load_denied"
    assert h.co.journal.read().error_code == "b3_fpga_handoff_denied"
    assert "lease:acquired" not in h.events
    assert h.active()["state"] == "EMPTY"


@pytest.mark.parametrize("code", [
    "PROC_CONSUMER_CONFLICT", "PATH2_APPROVED_SOURCE_SHA_MISMATCH",
    "BOOT_CHANGED_MANUAL_REVIEW", "CURRENT_IMAGE_OR_RECOVERY_CHANGED",
    "BUNDLE_FPGA_FILE_CHANGED",
])
def test_b3_root_denial_keeps_pl_and_active_set_unchanged(tmp_path, code):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome={"result": "fpga_load_denied", "code": code})
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_DENIED:" + code):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    record = h.co.journal.read()
    assert record.state == "fpga_load_denied"
    assert record.error_code == code
    assert "journal:activating" not in h.events
    assert h.events[-1] == "lease:released"
    assert h.active()["state"] == "EMPTY"


def test_b3_download_failure_requires_explicit_recovery(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome={"result": "recovery_required",
                                   "code": "FPGA_MANAGER_WRITE_FAILED"})
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_REQUIRES_RECOVERY"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.co.journal.read().state == "recovery_required"
    assert h.active()["state"] == "EMPTY"
    with pytest.raises(engine.DeploymentError, match="requires recovery"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))


def test_b3_root_loader_exception_is_uncertain_not_denied(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)

    def broken(_sha):
        raise TimeoutError("lost")

    h = Harness(tmp_path, outcome=broken)
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_LOAD_REQUIRES_RECOVERY"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.co.journal.read().state == "recovery_required"
    assert h.active()["state"] == "EMPTY"


def test_b3_identity_failure_keeps_image_loaded_without_golden_restore(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome={"result": "fpga_identity_failed",
                                   "code": "IDENTITY_CHILD_VALUE_MISMATCH"})
    with pytest.raises(engine.DeploymentError, match="B3_FPGA_IDENTITY_FAILED"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    record = h.co.journal.read()
    assert record.state == "fpga_identity_failed"
    assert record.error_message == "IDENTITY_CHILD_VALUE_MISMATCH"
    assert h.events.count("root:bundle-load") == 1
    assert h.active()["state"] == "EMPTY"


@pytest.mark.parametrize("field,value", [
    ("fpga_bin_sha256", "f" * 64), ("fpga_image_id", "forged"),
    ("asset_set_sha256", "e" * 64), ("identity", "SKIPPED"),
])
def test_b3_mismatched_root_receipt_is_recovery_not_activation(tmp_path, field, value):
    archive, digest, bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome=lambda sha: {**loaded(sha, bin_sha), field: value})
    with pytest.raises(engine.DeploymentError, match="ROOT_RECEIPT_MISMATCH"):
        h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.co.journal.read().state == "recovery_required"
    assert h.active()["state"] == "EMPTY"


def test_b3_default_root_loader_refuses_non_canonical_product_root(tmp_path):
    archive, digest, _bin_sha, _ = fpga_bundle(tmp_path)
    co = make_coordinator(tmp_path)
    co.quiescence_lease = nullcontext
    with patch.object(engine, "run_root_bundle_load") as root:
        with pytest.raises(engine.DeploymentError, match="install_path_not_canonical"):
            co.execute_bundle_v3_install(load_request(archive, digest))
        root.assert_not_called()
    assert co.journal.read().state == "fpga_load_denied"


def test_b3_repeat_fpga_load_redownloads_and_keeps_active_generation(tmp_path):
    archive, digest, bin_sha, _ = fpga_bundle(tmp_path)
    h = Harness(tmp_path, outcome=lambda sha: loaded(sha, bin_sha))
    first = h.co.execute_bundle_v3_install(load_request(archive, digest))
    second = h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.events.count("root:bundle-load") == 2
    assert first["active_asset_set"]["generation"] == 1
    assert second["active_asset_set"] == {
        "asset_set_sha256": digest, "generation": 1, "already_active": True,
    }


# --- Root Entry result classification -----------------------------------


def receipt_line(result, **extra):
    return "PLASMA_BUNDLE_LOAD=" + json.dumps({"result": result, **extra}) + "\n"


@pytest.mark.parametrize("returncode,stdout,stderr,expected", [
    (0, receipt_line("fpga_loaded"), "", "fpga_loaded"),
    (3, receipt_line("fpga_load_denied", code="X"), "", "fpga_load_denied"),
    (3, receipt_line("fpga_identity_failed"), "", "fpga_identity_failed"),
    (3, receipt_line("recovery_required"), "", "recovery_required"),
    (2, "", "PATH2_APPROVED_SOURCE_SHA_MISMATCH\n", "fpga_load_denied"),
    (2, "", "Traceback (most recent call last)\n", "recovery_required"),
    (1, "", "", "recovery_required"),
    (-9, "", "", "recovery_required"),
    (0, receipt_line("fpga_load_denied"), "", "recovery_required"),
    (3, receipt_line("fpga_loaded"), "", "recovery_required"),
    (0, receipt_line("fpga_loaded") * 2, "", "recovery_required"),
    (0, "PLASMA_BUNDLE_LOAD={bad\n", "", "recovery_required"),
    (0, receipt_line("ready"), "", "recovery_required"),
])
def test_root_entry_output_classification(returncode, stdout, stderr, expected):
    assert engine.classify_root_bundle_load(returncode, stdout, stderr)["result"] == expected


def test_default_root_loader_denies_when_root_entry_not_installed(tmp_path):
    with patch.object(engine, "ROOT_ENTRY", tmp_path / "missing"), \
         patch.object(engine.subprocess, "run") as run:
        result = engine.run_root_bundle_load("a" * 64)
    assert result == {"result": "fpga_load_denied", "code": "ROOT_ENTRY_NOT_INSTALLED"}
    run.assert_not_called()


def test_root_loader_runs_entry_outside_bootstrap_sandbox_with_set_sha_only():
    argv = engine.root_bundle_load_argv("a" * 64)
    assert argv[0] == "/usr/bin/systemd-run"
    assert {"--wait", "--pipe", "--collect"} <= set(argv)
    assert argv[-3:] == ["/usr/local/libexec/plasma/z2-path2-root-entry",
                         "bundle-load", "a" * 64]
    assert not any(re.fullmatch(r"[0-9a-f]{40}", item) for item in argv)


# --- Root Entry shell allowlist ------------------------------------------

ENTRY = ROOT / "scripts/z2/plasma-path2-root-entry"
PIN = "a" * 40  # explicitly retired; no longer a Root Entry argument
SET = "b" * 64


@pytest.mark.parametrize("argv,code", [
    (["bundle-load"], "PPU_FPGA_OPERATION_ARGUMENT_REQUIRED"),
    (["bundle-load", PIN, SET], "PPU_FPGA_OPERATION_ARGUMENT_REQUIRED"),
    (["bundle-load", SET, "extra"], "PPU_FPGA_OPERATION_ARGUMENT_REQUIRED"),
    (["bundle-load", "/opt/plasma/assets/staged/" + SET], "PPU_FPGA_ASSET_SET_SHA_INVALID"),
    (["bundle-load", "../" + SET[:61]], "PPU_FPGA_ASSET_SET_SHA_INVALID"),
    (["bundle-load", SET.upper()], "PPU_FPGA_ASSET_SET_SHA_INVALID"),
    (["bundle-load", PIN], "PPU_FPGA_ASSET_SET_SHA_INVALID"),
    (["download", PIN], "PPU_FPGA_OPERATION_ARGUMENT_REQUIRED"),
    (["download", PIN, SET], "PPU_FPGA_OPERATION_ARGUMENT_REQUIRED"),
    (["install", PIN], "PPU_FPGA_OPERATION_NOT_ALLOWLISTED"),
])
def test_root_entry_bundle_load_accepts_only_set_sha(argv, code):
    completed = subprocess.run(["bash", str(ENTRY), *argv], capture_output=True,
                               text=True, timeout=10, check=False)
    assert completed.returncode == 2
    assert completed.stderr.strip() == code


def test_root_entry_trusts_immutable_code_not_git_commit_pin():
    shell = ENTRY.read_text()
    assert 'bundle-load)' in shell
    assert 'root=/opt/plasma/privileged/fpga-root' in shell
    assert 'for file in "$python"; do' in shell
    assert '"$python" -B "$verifier"' not in shell
    assert '"$python" -B -m "$module" "$operation" ${asset_set:+"$asset_set"}' in shell
    assert ".plasma-path2-source-commit" not in shell
    assert "/root/plasma-path2-approved" not in shell.splitlines()[-35:]


# --- Protected Root bundle_load ------------------------------------------


class _Port:
    def __init__(self, events):
        self.events = events

    @contextmanager
    def exclusive(self):
        self.events.append("lock:acquired")
        yield self
        self.events.append("lock:released")


def installed_set(tmp_path: Path):
    archive, digest, bin_sha, manifest = fpga_bundle(tmp_path)
    co = make_coordinator(tmp_path)
    co.execute_bundle_v3_install(load_request(archive, digest, fpga_load=False))
    return co.paths.product_root / "assets/staged", digest, bin_sha, manifest


@contextmanager
def root_sandbox(tmp_path: Path, staged: Path, *, confirm=None, run=None):
    firmware = tmp_path / "firmware"
    firmware.mkdir()
    (firmware / "base.bin").write_bytes(b"golden")
    (firmware / "plasma-image-manifest.json").write_bytes(b"old-manifest")
    events: list[str] = []

    def fake_run(operation, port, release):
        events.append("run:" + operation)
        if run is not None:
            run(operation)
        if operation == "download":
            return {"download_count": 1}
        return {"result": "IDENTITY_PASS", "test_count": 1,
                "lease_id": "fpga-1", "boot_id": "boot-1"}

    def fake_confirm(port, release, record, operation):
        events.append("confirm:" + operation)
        if confirm is not None:
            confirm()
        return {}, {}

    with ExitStack() as stack:
        stack.enter_context(patch.object(protected_root, "trusted_local"))
        stack.enter_context(patch.object(protected_root, "STAGED_ASSET_SETS", staged))
        stack.enter_context(patch.object(protected_root, "STAGED_OWNER_UID", os.getuid()))
        stack.enter_context(patch.object(protected_guard, "FIRMWARE", firmware))
        stack.enter_context(patch.object(
            protected_root, "MANIFEST_FILE", firmware / "plasma-image-manifest.json"))
        stack.enter_context(patch.object(
            protected_root, "MANIFEST_PREVIOUS", firmware / "plasma-image-manifest.json.previous"))
        stack.enter_context(patch.object(protected_guard, "protected"))
        stack.enter_context(patch.object(protected_guard, "sha_file"))
        stack.enter_context(patch.object(
            protected_guard, "RootZ2TargetPort", return_value=_Port(events)))
        stack.enter_context(patch.object(protected_root, "read_state", return_value=None))
        stack.enter_context(patch.object(protected_root, "_confirm_current", fake_confirm))
        stack.enter_context(patch.object(protected_root, "_run_locked", fake_run))
        manager = stack.enter_context(patch.object(protected_guard, "manager_write"))
        yield firmware, events
        manager.assert_not_called()  # only the patched _run_locked could load


def test_root_bundle_load_stages_promotes_then_downloads_and_tests(tmp_path):
    staged, digest, bin_sha, manifest = installed_set(tmp_path)
    with root_sandbox(tmp_path, staged) as (firmware, events):
        result = protected_root.bundle_load(digest)
    assert result["result"] == "fpga_loaded"
    assert result["asset_set_sha256"] == digest
    assert result["fpga_image_id"] == IMAGE_ID
    assert result["fpga_bin_sha256"] == bin_sha
    assert result["identity"] == "IDENTITY_PASS"
    assert result["manifest_promoted"] is True
    assert result["auto_restore"] is False
    assert events == ["lock:acquired", "confirm:download", "run:download",
                      "run:test", "lock:released"]
    assert (firmware / "plasma-image-manifest.json").read_bytes() == manifest
    assert (firmware / "plasma-image-manifest.json.previous").read_bytes() == b"old-manifest"
    assert (firmware / "swd.bin").read_bytes() == BITSTREAM
    assert (firmware / "swd.bin.manifest.json").read_bytes() == manifest


def test_root_bundle_load_census_denial_restores_manifest_and_never_downloads(tmp_path):
    staged, digest, _bin_sha, _ = installed_set(tmp_path)

    def busy():
        raise protected_guard.TargetSafetyDenied("PROC_CONSUMER_CONFLICT")

    with root_sandbox(tmp_path, staged, confirm=busy) as (firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as denied:
            protected_root.bundle_load(digest)
    assert denied.value.outcome == "fpga_load_denied"
    assert denied.value.code == "PROC_CONSUMER_CONFLICT"
    assert "run:download" not in events
    assert (firmware / "plasma-image-manifest.json").read_bytes() == b"old-manifest"


def test_root_bundle_load_census_incomplete_keeps_bounded_detail(tmp_path):
    """A pre-load census denial must report WHY (status, pid, phase, error)."""
    staged, digest, _bin_sha, _ = installed_set(tmp_path)
    code = "PROC_SCAN_INCOMPLETE:VANISHED_PID_RESCAN_EXHAUSTED:1234:MAPS:FileNotFoundError"

    def incomplete():
        raise protected_admission.AdmissionDenied(code)

    with root_sandbox(tmp_path, staged, confirm=incomplete) as (firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as denied:
            protected_root.bundle_load(digest)
    assert denied.value.outcome == "fpga_load_denied"
    assert denied.value.code == code
    assert "run:download" not in events
    assert (firmware / "plasma-image-manifest.json").read_bytes() == b"old-manifest"


@pytest.mark.parametrize("text,expected", [
    ("PROC_CONSUMER_CONFLICT", "PROC_CONSUMER_CONFLICT"),
    ("PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:88:FD:PermissionError",
     "PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:88:FD:PermissionError"),
    ("PROC_SCAN_INCOMPLETE:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN",
     "PROC_SCAN_INCOMPLETE:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN"),
    # Free-form text never crosses the Root boundary.
    ("fpga manager", "AdmissionDenied"),
    ("PROC_SCAN_INCOMPLETE:/proc/1/cmdline", "AdmissionDenied"),
    ("PROC_SCAN_INCOMPLETE:python3 -c secret", "AdmissionDenied"),
    ("PROC_SCAN_INCOMPLETE:a:b:c:d:e", "AdmissionDenied"),          # > 4 detail fields
    ("PROC_SCAN_INCOMPLETE:" + "x" * 41, "AdmissionDenied"),        # over-long token
    ("lowercase_code", "AdmissionDenied"),
    ("PROC_SCAN_INCOMPLETE:", "AdmissionDenied"),
])
def test_root_failure_code_is_bounded_and_token_only(text, expected):
    exc = protected_admission.AdmissionDenied(text)
    assert protected_root._failure_code(exc) == expected


def test_root_bundle_load_tampered_staged_bin_denied_before_lock(tmp_path):
    staged, digest, _bin_sha, _ = installed_set(tmp_path)
    image = staged / digest / "payload/packages/custom-swd/fpga/swd.bin"
    image.chmod(0o600)
    image.write_bytes(b"x" * len(BITSTREAM))
    with root_sandbox(tmp_path, staged) as (firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as denied:
            protected_root.bundle_load(digest)
    assert denied.value.outcome == "fpga_load_denied"
    assert denied.value.code == "BUNDLE_FPGA_FILE_CHANGED"
    assert events == []
    assert not (firmware / "swd.bin").exists()
    assert (firmware / "plasma-image-manifest.json").read_bytes() == b"old-manifest"


def test_root_bundle_load_unknown_set_denied(tmp_path):
    staged, _digest, _bin_sha, _ = installed_set(tmp_path)
    with root_sandbox(tmp_path, staged) as (_firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as denied:
            protected_root.bundle_load("d" * 64)
    assert denied.value.outcome == "fpga_load_denied"
    assert events == []


def test_root_bundle_load_download_failure_is_recovery_required(tmp_path):
    staged, digest, _bin_sha, manifest = installed_set(tmp_path)

    def fail(operation):
        if operation == "download":
            raise OSError("fpga manager")

    with root_sandbox(tmp_path, staged, run=fail) as (firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as failed:
            protected_root.bundle_load(digest)
    assert failed.value.outcome == "recovery_required"
    assert "run:test" not in events
    # The promoted Manifest stays: the Root journal now describes this Image.
    assert (firmware / "plasma-image-manifest.json").read_bytes() == manifest


def test_root_bundle_load_identity_failure_keeps_image_and_no_restore(tmp_path):
    staged, digest, _bin_sha, _ = installed_set(tmp_path)

    def fail(operation):
        if operation == "test":
            raise protected_root.ImageDeploymentDenied("IDENTITY_CHILD_VALUE_MISMATCH")

    with root_sandbox(tmp_path, staged, run=fail) as (_firmware, events):
        with pytest.raises(protected_root.BundleLoadOutcome) as failed:
            protected_root.bundle_load(digest)
    assert failed.value.outcome == "fpga_identity_failed"
    assert failed.value.code == "IDENTITY_CHILD_VALUE_MISMATCH"
    assert "run:restore" not in events


def test_root_main_prints_classified_receipt(tmp_path, capsys):
    staged, digest, _bin_sha, _ = installed_set(tmp_path)

    def busy():
        raise protected_guard.TargetSafetyDenied("PROC_CONSUMER_CONFLICT")

    with root_sandbox(tmp_path, staged, confirm=busy):
        assert protected_root.main(["bundle-load", digest]) == 3
    out = capsys.readouterr().out
    assert engine.classify_root_bundle_load(3, out, "") == {
        "stage": "bundle-load", "result": "fpga_load_denied",
        "code": "PROC_CONSUMER_CONFLICT", "asset_set_sha256": digest,
    }
    with pytest.raises(protected_root.ImageDeploymentDenied, match="ONE_OPERATION_REQUIRED"):
        protected_root.main(["download", digest])


def test_root_handoff_accepts_fpga_only_bundle_without_profile(tmp_path):
    staged, digest, _bin_sha, _ = installed_set(tmp_path)
    with root_sandbox(tmp_path, staged):
        handoff, manifest, bin_bytes, hwh = protected_root.read_staged_fpga_handoff(digest)
    handoff = dict(handoff, programming_profile=None)
    receipt = protected_root.validate_bundle_fpga_handoff(
        handoff, expected_active_set_sha256=digest,
        manifest_bytes=manifest, bin_bytes=bin_bytes, hwh_bytes=hwh)
    assert receipt["programming_profile_identity_sha256"] is None
    assert receipt["fpga_loaded"] is False


# --- Bootstrap HTTP service ------------------------------------------------

from .ppu_owner_authorization_fixture import admit_body, install_body  # noqa: E402
from .test_ppu_fpga_static_qualification_gate1 import (  # noqa: E402
    _b3_server, _commit, bootstrap, bundle_v3, synthetic_image, write_contracts,
)


def admitted_fpga_bundle(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    archive, _digest = bundle_v3(tmp_path / "bundle", mutate=lambda m: m.__setitem__(
        "actions", ["install", "verify"]))
    raw = archive.read_bytes()
    upload_id = _commit(paths, raw)
    _, entry = synthetic_image()
    write_contracts(paths.fpga_image_contracts, entry)
    srv.start_deployment(admit_body(paths, "bundle", upload_id))
    return srv, paths, calls, upload_id


def b3(paths, *, fpga_load=True):
    """Fresh owner B3 authorization for the device's CURRENT B2 admission."""
    return install_body(paths, bootstrap._deployment_api_record(paths), fpga_load=fpga_load)


def test_service_forwards_explicit_fpga_load_to_coordinator(tmp_path):
    srv, paths, calls, upload_id = admitted_fpga_bundle(tmp_path)
    srv.start_deployment(b3(paths))
    srv.deployment_thread.join(timeout=10)
    assert len(calls) == 1
    assert calls[0][2]["fpga_load"] is True
    assert set(calls[0][2]) == {"api_transaction_id", "source_commit",
                                "archive_sha256", "target", "fpga_load"}


@pytest.mark.parametrize("body", [
    {"fpga_load": "true"}, {"fpga_load": 1}, {"fpga_load": None},
    {"fpga_load": True, "path": "/opt/plasma/assets"},
    {"fpga_load": True, "idle": True},
])
def test_service_rejects_non_boolean_or_extra_b3_fields(tmp_path, body):
    srv, paths, calls, upload_id = admitted_fpga_bundle(tmp_path)
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_INSTALL_REQUEST_FIELDS_DENIED"):
        srv.start_deployment({**b3(paths), **body})
    assert calls == []


def test_service_retired_install_only_field_is_not_a_b3_request(tmp_path):
    srv, _paths, calls, upload_id = admitted_fpga_bundle(tmp_path)
    with pytest.raises(bootstrap.BootstrapServiceError):
        srv.start_deployment({"kind": "bundle", "upload_id": upload_id, "install_only": True})
    assert calls == []


def test_service_rejects_fpga_load_for_bundle_without_fpga_image(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    archive, _digest = build_smoke(tmp_path / "bundle")
    raw = archive.read_bytes()
    upload_id = _commit(paths, raw)
    srv.start_deployment(admit_body(paths, "bundle", upload_id))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_FPGA_LOAD_REQUIRES_FPGA_IMAGE"):
        srv.start_deployment(b3(paths))
    assert calls == []


@pytest.mark.parametrize("state,api_state", [
    ("fpga_load_denied", "failed"),
    ("fpga_identity_failed", "failed"),
    ("recovery_required", "recovery_required"),
])
def test_service_reconciles_known_b3_failures_from_coordinator_journal(
    tmp_path, state, api_state,
):
    srv, paths, _calls, upload_id = admitted_fpga_bundle(tmp_path)

    def runner(used_paths, _upload_id, request):
        journal = engine.Journal(used_paths.coordinator_journal)
        record = engine.DeploymentRecord(
            schema_version=1, transaction_id="coordinator-1", state="received",
            sequence=0, started_at_epoch_s=1.0, updated_at_epoch_s=1.0,
            release_artifact="x", kind="bundle",
            api_transaction_id=request["api_transaction_id"],
        )
        journal.write(record, state, error_code="b3_runtime_quiesce_denied")
        raise bootstrap.BootstrapServiceError("B3_DEVICE_INSTALL_SUBPROCESS_FAILED")

    srv.bundle_install_runner = runner
    srv.start_deployment(b3(paths))
    srv.deployment_thread.join(timeout=10)
    record = bootstrap._deployment_api_record(paths)
    assert record["state"] == api_state
    if api_state == "failed":
        assert record["error_code"] == "b3_runtime_quiesce_denied"
        assert record["result"]["coordinator_receipt"]["coordinator_state"] == state
    else:
        assert record["error_code"] == "b3_install_outcome_unreconciled"
