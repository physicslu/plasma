"""Host-only regression for durable per-Site uncertainty (NO DEVICE/HIL)."""
from __future__ import annotations

from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

import pytest

from plasma_interfaces import swd_site_recovery as recovery
from plasma_interfaces.swd_site_recovery import (
    SiteRecoveryBlocked,
    SiteRecoveryIdentity,
    SiteRecoveryJournal,
)


@pytest.fixture
def private_dir(tmp_path: Path) -> Path:
    root = tmp_path / "ps-private-site-state"
    root.mkdir(mode=0o700)
    return root


def identity(site_id: int = 1, *, boot: str = "boot-a",
             image: str = "a") -> SiteRecoveryIdentity:
    return SiteRecoveryIdentity(
        site_id, boot, image * 64, "b" * 64)


def provision_test_only(root: Path, ident: SiteRecoveryIdentity) -> None:
    """Fixture only: no deployed writer or Root authority is implemented."""
    payload = {
        "schema": 1, "state": "READY", "identity": asdict(ident),
        "generation": 0, "operation_id": None,
    }
    record = dict(payload, checksum=recovery._checksum(payload))
    target = root / f"site-{ident.site_id}.json"
    target.write_bytes(recovery._canonical(record) + b"\n")
    target.chmod(0o600)


def test_missing_record_is_never_first_write_permission(private_dir):
    journal = SiteRecoveryJournal(private_dir, identity())
    called = []
    with pytest.raises(SiteRecoveryBlocked, match="Missing"):
        journal.guard_write("write-1", lambda: called.append("PUSH"))
    assert called == []


def test_durable_uncertain_before_push_and_never_auto_clear(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    journal = SiteRecoveryJournal(private_dir, ident)
    observed = []

    def fake_push():
        payload = json.loads((private_dir / "site-1.json").read_text())
        assert payload["state"] == "UNCERTAIN"
        assert payload["operation_id"] == "job-A-write-01"
        assert payload["generation"] == 1
        observed.append("PUSH")
        return 9

    assert journal.guard_write("job-A-write-01", fake_push) == 9
    assert observed == ["PUSH"]
    assert journal.status() == "UNCERTAIN"
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        journal.guard_write("job-A-write-02", lambda: observed.append("REPLAY"))
    assert observed == ["PUSH"]


def test_sigkill_owner_and_new_process_still_blocked(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    script = """
import os, signal, sys
from plasma_interfaces.swd_site_recovery import SiteRecoveryIdentity, SiteRecoveryJournal, SiteRecoveryBlocked
identity = SiteRecoveryIdentity(1, "boot-a", "a"*64, "b"*64)
journal = SiteRecoveryJournal(sys.argv[1], identity)
if sys.argv[2] == "crash":
    journal.guard_write("job-sigkill", lambda: os.kill(os.getpid(), signal.SIGKILL))
else:
    try:
        journal.guard_write("job-incorrect-replay", lambda: sys.exit(31))
    except SiteRecoveryBlocked:
        sys.exit(17)
    sys.exit(32)
"""
    child = subprocess.run([sys.executable, "-c", script,
                            str(private_dir), "crash"], check=False, timeout=15)
    assert child.returncode == -signal.SIGKILL
    restarted = subprocess.run([sys.executable, "-c", script,
                                str(private_dir), "replay"],
                               check=False, timeout=15)
    assert restarted.returncode == 17
    assert SiteRecoveryJournal(private_dir, ident).status() == "UNCERTAIN"


def test_injected_power_loss_before_rename_never_calls_push(
        private_dir, monkeypatch):
    ident = identity()
    provision_test_only(private_dir, ident)
    dispatched = []
    def loss(*args, **kwargs):
        raise OSError("synthetic power failure before rename")
    monkeypatch.setattr(recovery.os, "replace", loss)
    journal = SiteRecoveryJournal(private_dir, ident)
    with pytest.raises(SiteRecoveryBlocked, match="durably"):
        journal.guard_write("job-power-loss", lambda: dispatched.append("PUSH"))
    assert dispatched == []
    assert list(private_dir.glob("site-1.json.pending-*"))
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        journal.assert_ready()


def test_intent_survives_rollback_of_unfsynced_rename(private_dir, monkeypatch):
    """After rename but before dir fsync, power loss may resurrect old READY.

    The independently fsynced intent must still deny any replay.
    This is an explicit host-model of filesystem crash recovery, not
    a physical disk power-cut qualification.
    """
    ident = identity()
    provision_test_only(private_dir, ident)
    original = (private_dir / "site-1.json").read_bytes()
    original_replace = recovery.os.replace
    original_fsync = recovery.os.fsync
    renamed = []
    pushed = []

    def observe_rename(*args, **kwargs):
        result = original_replace(*args, **kwargs)
        renamed.append(True)
        return result

    def interrupt_final_directory_sync(fd):
        if renamed and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("simulated crash before final rename fsync")
        return original_fsync(fd)

    monkeypatch.setattr(recovery.os, "replace", observe_rename)
    monkeypatch.setattr(recovery.os, "fsync", interrupt_final_directory_sync)
    journal = SiteRecoveryJournal(private_dir, ident)
    with pytest.raises(SiteRecoveryBlocked, match="durably"):
        journal.guard_write("power-fail-rename", lambda: pushed.append("PUSH"))
    assert renamed == [True]
    assert pushed == []
    assert (private_dir / "site-1.intent").is_file()

    # Model the admissible crash outcome: final journal rename did not last.
    # The earlier fsync of the *independent* intent did.
    (private_dir / "site-1.json").write_bytes(original)
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        journal.assert_ready()
    assert journal.status() == "UNCERTAIN"


def test_failure_before_intent_directory_sync_never_calls_write(
        private_dir, monkeypatch):
    ident = identity()
    provision_test_only(private_dir, ident)
    original_fsync = recovery.os.fsync
    pushed = []

    def before_intent_directory_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("crash before intent directory fsync")
        return original_fsync(fd)

    monkeypatch.setattr(recovery.os, "fsync", before_intent_directory_sync)
    journal = SiteRecoveryJournal(private_dir, ident)
    with pytest.raises(SiteRecoveryBlocked, match="durably"):
        journal.guard_write("intent-not-published", lambda: pushed.append("PUSH"))
    assert pushed == []


@pytest.mark.parametrize("defect", ["truncate", "symlink", "corrupt"])
def test_intent_presence_always_blocks_even_if_journal_ready(
        private_dir, defect):
    ident = identity()
    provision_test_only(private_dir, ident)
    journal = SiteRecoveryJournal(private_dir, ident)
    journal.guard_write("completed-or-not", lambda: None)
    # Simulate un-fsynced journal replacement being rolled back to READY.
    provision_test_only(private_dir, ident)
    intent = private_dir / "site-1.intent"
    if defect == "truncate":
        intent.write_bytes(b"")
    elif defect == "corrupt":
        intent.write_text("{bad")
    elif defect == "symlink":
        old = private_dir / "old-intent"
        intent.rename(old)
        intent.symlink_to(old)
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        journal.assert_ready()
    assert journal.status() == "UNCERTAIN"


def test_unknown_completion_and_exception_never_retry(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    writes = []

    def fake_unknown_completion():
        writes.append("possibly accepted SWD Write")
        raise TimeoutError("completion not observed")

    journal = SiteRecoveryJournal(private_dir, ident)
    with pytest.raises(TimeoutError):
        journal.guard_write("job-unknown", fake_unknown_completion)
    assert journal.status() == "UNCERTAIN"
    with pytest.raises(SiteRecoveryBlocked):
        journal.guard_write("job-repeat", lambda: writes.append("REPLAY"))
    assert writes == ["possibly accepted SWD Write"]


def test_fifo_pending_and_reload_do_not_erase_uncertainty(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    journal = SiteRecoveryJournal(private_dir, ident)
    # A still-READY record must reject stale Boot/Image identity.
    with pytest.raises(SiteRecoveryBlocked, match="stale"):
        SiteRecoveryJournal(private_dir, identity(boot="boot-b")).assert_ready()
    with pytest.raises(SiteRecoveryBlocked, match="stale"):
        SiteRecoveryJournal(private_dir, identity(image="f")).assert_ready()
    journal.guard_write("fifo-pending", lambda: None)
    assert journal.status() == "UNCERTAIN"
    # Changing the boot or image after an in-flight write never erases intent.
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        SiteRecoveryJournal(private_dir, identity(boot="boot-b")).assert_ready()
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        SiteRecoveryJournal(private_dir, identity(image="f")).assert_ready()
    # A read-only status inspection cannot authorize a write.
    with pytest.raises(SiteRecoveryBlocked, match="intent"):
        journal.assert_ready()


def test_two_sites_independent_durable_records(private_dir):
    first, second = identity(1), identity(2)
    provision_test_only(private_dir, first)
    provision_test_only(private_dir, second)
    a = SiteRecoveryJournal(private_dir, first)
    b = SiteRecoveryJournal(private_dir, second)
    a.guard_write("site1-push", lambda: None)
    assert a.status() == "UNCERTAIN"
    assert b.status() == "READY"
    b.guard_write("site2-push", lambda: None)
    assert b.status() == "UNCERTAIN"
    assert (private_dir / "site-1.json").read_bytes() != (
        private_dir / "site-2.json").read_bytes()


@pytest.mark.parametrize("defect", ["truncate", "checksum", "symlink", "mode", "hardlink"])
def test_corrupt_or_untrusted_record_is_denied(private_dir, defect):
    ident = identity()
    provision_test_only(private_dir, ident)
    target = private_dir / "site-1.json"
    if defect == "truncate":
        target.write_text("{")
    if defect == "checksum":
        contents = json.loads(target.read_text())
        contents["checksum"] = "0" * 64
        target.write_text(json.dumps(contents))
    if defect == "symlink":
        other = private_dir / "other"
        target.rename(other)
        target.symlink_to(other)
    if defect == "mode":
        target.chmod(0o666)
    if defect == "hardlink":
        os.link(target, private_dir / "another-link")
    with pytest.raises(SiteRecoveryBlocked):
        SiteRecoveryJournal(private_dir, ident).assert_ready()


def test_unsafe_parent_and_stale_owner_lock_are_denied(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    private_dir.chmod(0o777)
    with pytest.raises(SiteRecoveryBlocked, match="Unsafe"):
        SiteRecoveryJournal(private_dir, ident).assert_ready()
    private_dir.chmod(0o700)
    lock = private_dir / "site-1.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o666)
    with pytest.raises(SiteRecoveryBlocked):
        SiteRecoveryJournal(private_dir, ident).assert_ready()


def test_contending_process_cannot_obtain_recovery_lock(private_dir):
    ident = identity()
    provision_test_only(private_dir, ident)
    lock_path = private_dir / "site-1.lock"
    with lock_path.open("w") as stream:
        os.chmod(lock_path, stat.S_IRUSR | stat.S_IWUSR)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        script = """
import sys
from plasma_interfaces.swd_site_recovery import SiteRecoveryJournal, SiteRecoveryIdentity, SiteRecoveryBlocked
j = SiteRecoveryJournal(sys.argv[1], SiteRecoveryIdentity(1, "boot-a", "a"*64, "b"*64))
try:
    j.assert_ready()
except SiteRecoveryBlocked:
    sys.exit(17)
sys.exit(18)
"""
        result = subprocess.run([sys.executable, "-c", script,
                                 str(private_dir)], check=False, timeout=15)
        assert result.returncode == 17


def test_no_privileged_deployed_recovery_or_auto_replay_interface():
    module = Path(recovery.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess.", "/dev/mem", "sudo ", "os.system(",
                      "mark_ready(", "clear_uncertain(", "retry_write("):
        assert forbidden not in module
    assert "os.fsync(fd)" in module and "os.fsync(directory)" in module
    assert "os.replace(" in module
