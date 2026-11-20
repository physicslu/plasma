"""Host-only evidence integrity for the ABI-v5 C3 OpenOCD subprocess.

No OpenOCD binary is executed; all calls are in-memory mocks.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_adapter_abi5 as abi5  # noqa: E402
import ppu_site_worker as worker  # noqa: E402

GOOD = (b"Info : SWD DPIDR 0x1ba01477\n"
        b"PLASMA_DPREG0=0x1ba01477\n"
        b"Info : plasma_swd: SAFE_OFF_MODE_OFF_VERIFIED\n")


class FakeProc:
    def __init__(self, log: bytes, rc: int):
        self.pid = 999999
        self.stdout = io.BytesIO(log)
        self.expected_rc = rc
        self.returncode = None

    def poll(self):
        self.returncode = self.expected_rc
        return self.returncode


def rig(tmp_path, *, log=GOOD, rc=0, admit=True, evidence_dir=None):
    record_dir = tmp_path / "admissions"
    record_dir.mkdir()
    calls = []

    def run(argv, **kwargs):
        calls.append(argv[-2:])
        if argv[-2] == "admit":
            return subprocess.CompletedProcess(
                argv, 0 if admit else 1,
                "SITE_ADMISSION_RECORD_ISSUED" if admit else "", "")
        return subprocess.CompletedProcess(argv, 0, "revoked", "")

    adapter = abi5.Abi5OpenocdAdapter(
        openocd_root=tmp_path / "engine", python=Path(sys.executable),
        adapter_khz=2000, record_dir=record_dir, run=run,
        popen=lambda *a, **kw: FakeProc(log, rc),
        openocd_running=lambda: False, poll_s=0.005,
        evidence_dir=evidence_dir if evidence_dir is not None else tmp_path / "private",
    )
    return adapter, calls


def attempt(adapter):
    return adapter.run(2, "probe", deadline=time.monotonic() + 5,
                       cancel=threading.Event())


def evidence(directory, count=1):
    raw_files = sorted(directory.glob("site2-*.stdout"))
    assert len(raw_files) == count
    records = []
    for path in raw_files:
        meta = path.with_suffix(".json")
        assert meta.is_file()
        info = json.loads(meta.read_text(encoding="utf-8"))
        assert info["stdout_file"] == path.name
        assert info["stdout_bytes"] == len(path.read_bytes())
        assert info["stdout_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert info["schema"] == "plasma.ppu.openocd-evidence.v1"
        assert info["site"] == 2
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(meta.stat().st_mode) == 0o600
        records.append((path.read_bytes(), info))
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    return records


# Every Adapter receipt reports the safe release it observed, never a literal:
# the ps_owner marker AND the revoked root admission AND no cancel / timeout.
SAFE_OFF_RECEIPT = {"safe_off": True,
                    "safe_off_evidence": {"marker_present": True,
                                          "admission_revoked": True,
                                          "termination_reason": None}}


def test_success_persists_exact_stdout_and_safe_off_receipt(tmp_path):
    raw = GOOD + b"raw-byte:\xff\n"
    adapter, calls = rig(tmp_path, log=raw)
    result = attempt(adapter)
    assert result == {"result": "PASS", "dpidr": "0x1ba01477", **SAFE_OFF_RECEIPT}
    [(logged, info)] = evidence(tmp_path / "private")
    assert logged == raw
    assert info["openocd_rc"] == 0
    assert info["safe_off_marker_present"] is True
    assert info["safe_off_verified"] is True
    assert info["admission_revoked"] is True
    assert info["termination_reason"] is None
    assert calls == [["admit", "2"], ["revoke", "2"]]
    assert "raw-byte" not in json.dumps(result)


@pytest.mark.parametrize("raw,rc", [
    (b"Error : PS_OWNER_DEVMEM_OPEN_FAILED\n", 1),
    (b"Warning : plasma_swd: SAFE_OFF_UNCERTAIN\n", 3),
    (b"SWD DPIDR 0x1ba01477\n", 0),
])
def test_missing_safe_off_persists_raw_failure_before_seal(tmp_path, raw, rc):
    adapter, calls = rig(tmp_path, log=raw, rc=rc)
    with pytest.raises(worker.TransportUnknown, match="SAFE_OFF_NOT_VERIFIED"):
        attempt(adapter)
    [(logged, info)] = evidence(tmp_path / "private")
    assert logged == raw
    assert info["openocd_rc"] == rc
    assert info["safe_off_marker_present"] is False
    assert info["safe_off_verified"] is False
    assert calls == [["admit", "2"], ["revoke", "2"]]


def test_openocd_failure_with_safe_off_does_not_claim_probe_pass(tmp_path):
    adapter, _ = rig(tmp_path, log=GOOD, rc=42)
    assert attempt(adapter) == {
        "result": "FAIL", "code": "DPIDR_NOT_READ", "openocd_rc": 42,
        **SAFE_OFF_RECEIPT,
    }
    [(_raw, info)] = evidence(tmp_path / "private")
    assert info["openocd_rc"] == 42 and info["safe_off_verified"] is True


def test_admission_denial_starts_no_child_and_creates_no_evidence(tmp_path):
    adapter, calls = rig(tmp_path, admit=False)
    with pytest.raises(worker.TransportDenied, match="ADMISSION_DENIED"):
        attempt(adapter)
    assert calls == [["admit", "2"], ["revoke", "2"]]
    assert not (tmp_path / "private").exists()


def test_admission_denial_preserves_only_structured_safe_code(tmp_path):
    adapter, calls = rig(tmp_path, admit=False)
    old_run = adapter._run

    def run(argv, **kwargs):
        if argv[-2] == "admit":
            receipt = {"result": "DENIED", "code": "ROOT_JOURNAL_NOT_HELD_IMAGE"}
            return subprocess.CompletedProcess(
                argv, 1, "PLASMA_SWD_SITE_ADMISSION=" + json.dumps(receipt), "")
        return old_run(argv, **kwargs)

    adapter._run = run
    with pytest.raises(worker.TransportDenied,
                       match="ADMISSION_DENIED:ROOT_JOURNAL_NOT_HELD_IMAGE"):
        attempt(adapter)
    assert calls == [["revoke", "2"]]
    assert not (tmp_path / "private").exists()


def test_admission_denial_does_not_expose_arbitrary_text(tmp_path):
    adapter, calls = rig(tmp_path, admit=False)
    old_run = adapter._run

    def run(argv, **kwargs):
        if argv[-2] == "admit":
            receipt = {"result": "DENIED", "code": "/secret/password"}
            return subprocess.CompletedProcess(
                argv, 1, "PLASMA_SWD_SITE_ADMISSION=" + json.dumps(receipt), "")
        return old_run(argv, **kwargs)

    adapter._run = run
    with pytest.raises(worker.TransportDenied, match="^ADMISSION_DENIED$"):
        attempt(adapter)
    assert calls == [["revoke", "2"]]


def test_private_directory_required_fail_closed_when_write_untrusted(tmp_path):
    directory = tmp_path / "too-open"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    adapter, calls = rig(tmp_path, evidence_dir=directory)
    with pytest.raises(worker.TransportUnknown, match="OPENOCD_EVIDENCE_WRITE_FAILED"):
        attempt(adapter)
    assert calls == [["admit", "2"], ["revoke", "2"]]
    assert list(directory.iterdir()) == []


def test_consecutive_sessions_keep_separate_immutable_evidence(tmp_path):
    adapter, calls = rig(tmp_path)
    assert attempt(adapter)["result"] == "PASS"
    assert attempt(adapter)["result"] == "PASS"
    records = evidence(tmp_path / "private", count=2)
    assert all(raw == GOOD for raw, _ in records)
    assert len({record["stdout_file"] for _, record in records}) == 2
    assert calls == [["admit", "2"], ["revoke", "2"]] * 2


def _deny_with(tmp_path, receipt):
    adapter, calls = rig(tmp_path, admit=False)
    old_run = adapter._run

    def run(argv, **kwargs):
        if argv[-2] == "admit":
            return subprocess.CompletedProcess(
                argv, 1, "PLASMA_SWD_SITE_ADMISSION=" + json.dumps(receipt), "")
        return old_run(argv, **kwargs)

    adapter._run = run
    with pytest.raises(worker.TransportDenied) as caught:
        attempt(adapter)
    assert calls == [["revoke", "2"]]  # refused before any OpenOCD / hardware
    assert not (tmp_path / "private").exists()
    return caught.value.code


@pytest.mark.parametrize("receipt, expected", [
    # The /proc owner census code (pl/hil/fpga_image_admission.py) used to be
    # dropped whole because of its ':'-separated fields (2-Site HIL 2026-11-19).
    ({"result": "DENIED", "error": "ValueError",
      "code": "PROC_SCAN_INCOMPLETE:VANISHED_PID_RESCAN_EXHAUSTED:4321:FD:FileNotFoundError"},
     "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE:VANISHED_PID_RESCAN_EXHAUSTED:4321:FD:FileNotFoundError"),
    ({"result": "DENIED", "error": "ValueError",
      "code": "PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:UNKNOWN:MAPS:PermissionError"},
     "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:UNKNOWN:MAPS:PermissionError"),
    ({"result": "DENIED", "error": "ValueError", "code": "PROC_RESOURCE_OWNER_CONFLICT"},
     "ADMISSION_DENIED:PROC_RESOURCE_OWNER_CONFLICT"),
    # Census conflict detail (2-Site HIL 2026-11-20 C98 left no PID behind).
    ({"result": "DENIED", "error": "ValueError",
      "code": "PROC_RESOURCE_OWNER_CONFLICT:4242:913377:DEVMEM:OWNER_UNPROVEN:LOCK:STILL_HELD"},
     "ADMISSION_DENIED:PROC_RESOURCE_OWNER_CONFLICT:4242:913377:DEVMEM:OWNER_UNPROVEN:LOCK:STILL_HELD"),
    # Unstructured fields: keep the token, withhold the rest.
    ({"result": "DENIED", "error": "ValueError",
      "code": "PROC_SCAN_INCOMPLETE:/proc/42/fd: some text"},
     "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE:DETAIL_WITHHELD"),
    # No usable code: only the exception TYPE, never its message.
    ({"result": "DENIED", "error": "BlockingIOError",
      "code": "[Errno 11] Resource temporarily unavailable: '/run/lock/x'"},
     "ADMISSION_DENIED:UNSTRUCTURED:BlockingIOError"),
    ({"result": "DENIED", "error": "bad type name!", "code": "/secret/password"},
     "ADMISSION_DENIED"),
    ({"result": "DENIED", "code": "A" + ":x" * 7}, "ADMISSION_DENIED:A:DETAIL_WITHHELD"),
])
def test_admission_denial_keeps_structured_cause_and_never_free_text(tmp_path, receipt, expected):
    code = _deny_with(tmp_path, receipt)
    assert code == expected
    assert "/" not in code and " " not in code and "'" not in code


def test_admission_census_codes_round_trip_through_the_filter():
    """Every census code shape the Root admission can emit stays attributable."""
    detail = ":".join(str(v)[:40] for v in ("VANISHED_PID_RESCAN_EXHAUSTED", 31337, "FD",
                                            "FileNotFoundError"))
    for code in ("PROC_SCAN_INCOMPLETE:" + detail, "PROC_SCAN_INCOMPLETE:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN",
                 "PROC_RESOURCE_OWNER_CONFLICT", "ROOT_JOURNAL_NOT_HELD_IMAGE"):
        assert abi5.admission_denial_detail({"code": code}) == ":" + code
