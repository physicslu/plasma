"""Host-only persistent FPGA lease and restore intent; no hardware authority.

This is a *claim ledger*, not authentication of observations or a new live
FPGA driver. All clocks, device facts and evidence are externally verified by
a future separately authorized target backend. Do not replay Path 3's dated
UIO risk exception. No CLI, network, subprocess, MMIO or FPGA Manager access.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import uuid

SCHEMA = "plasma.path2.fpga_lease.host_only.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
STATES = frozenset({"RESTORE_REQUIRED", "LOAD_IN_FLIGHT", "LOADED_AND_HELD",
                    "TEST_IN_FLIGHT", "RESTORE_IN_FLIGHT", "RESTORED_VERIFIED",
                    "UNKNOWN_MANUAL_RECOVERY", "EXPIRED_REVIEW_REQUIRED"})
FIELDS = frozenset({"schema", "status", "lease_id", "target_id", "profile_id",
                    "source_sha", "artifact_sha256", "recovery_sha256",
                    "boot_id", "owner_id", "restore_intent_sha256",
                    "services_sha256", "uio_sha256", "lease_deadline",
                    "step_deadline", "last_seen", "revision", "load_attempts",
                    "test_attempts", "restore_attempts", "load_evidence_sha256",
                    "test_evidence_sha256", "restore_evidence_sha256", "reason"})
OBS_FIELDS = frozenset({"observed_at", "target_id", "boot_id", "image_sha256",
                        "manager_state", "owner_evidence_sha256", "axi_admission"})
TEST_WORDS = {"0": 0x4D534C50, "4": 0x00010000, "16384": 1}


class LeaseDenied(ValueError):
    """Host-only refusal. Caller must not infer it is safe to touch hardware."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise LeaseDenied(reason)


def digest(value: object, width: int = 64) -> bool:
    return type(value) is str and (SHA40 if width == 40 else SHA64).fullmatch(value) is not None


def identifier(value: object) -> bool:
    return type(value) is str and IDENT.fullmatch(value) is not None


def tick(now: object) -> int:
    need(type(now) is int and 0 < now < 2**40, "TRUSTED_CLOCK_REQUIRED")
    return now


def fields(value: object, keys: frozenset[str], code: str) -> dict:
    need(type(value) is dict and set(value) == keys, code)
    return value


def validate_record(value: object) -> dict:
    record = fields(value, FIELDS, "LEDGER_SCHEMA_DENIED")
    need(record["schema"] == SCHEMA and record["status"] in STATES,
         "LEDGER_STATE_DENIED")
    for key in ("source_sha",):
        need(digest(record[key], 40), "LEDGER_SOURCE_DENIED")
    for key in ("artifact_sha256", "recovery_sha256", "restore_intent_sha256",
                "services_sha256", "uio_sha256"):
        need(digest(record[key]), "LEDGER_HASH_DENIED")
    for key in ("load_evidence_sha256", "test_evidence_sha256",
                "restore_evidence_sha256"):
        need(record[key] is None or digest(record[key]), "LEDGER_EVIDENCE_DENIED")
    need(all(identifier(record[k]) for k in
             ("lease_id", "target_id", "profile_id", "owner_id")) and
         type(record["boot_id"]) is str and bool(record["boot_id"]),
         "LEDGER_ID_DENIED")
    need(all(type(record[k]) is int and record[k] >= 0 for k in
             ("revision", "load_attempts", "test_attempts", "restore_attempts")),
         "LEDGER_COUNTER_DENIED")
    terminal = record["status"] in ("RESTORED_VERIFIED",
                                    "UNKNOWN_MANUAL_RECOVERY",
                                    "EXPIRED_REVIEW_REQUIRED")
    need(type(record["lease_deadline"]) is int and
         type(record["step_deadline"]) is int and
         type(record["last_seen"]) is int and
         record["last_seen"] >= 0 and
         (terminal or record["last_seen"] < record["lease_deadline"]),
         "LEDGER_CLOCK_DENIED")
    need(type(record["reason"]) is str and len(record["reason"]) <= 100,
         "LEDGER_REASON_DENIED")
    if record["status"] in ("LOAD_IN_FLIGHT", "LOADED_AND_HELD",
                            "TEST_IN_FLIGHT", "RESTORE_IN_FLIGHT",
                            "RESTORED_VERIFIED"):
        need(record["load_attempts"] == 1, "LOAD_ATTEMPT_PROVENANCE_DENIED")
    if record["status"] in ("LOADED_AND_HELD", "TEST_IN_FLIGHT",
                            "RESTORE_IN_FLIGHT", "RESTORED_VERIFIED"):
        need(digest(record["load_evidence_sha256"]), "LOADED_PROVENANCE_DENIED")
    if record["status"] == "TEST_IN_FLIGHT":
        need(record["test_attempts"] >= 1, "TEST_ATTEMPT_PROVENANCE_DENIED")
    if record["status"] in ("RESTORE_IN_FLIGHT", "RESTORED_VERIFIED"):
        need(record["restore_attempts"] == 1, "RESTORE_ATTEMPT_PROVENANCE_DENIED")
    if record["status"] == "RESTORED_VERIFIED":
        need(digest(record["restore_evidence_sha256"]),
             "RESTORE_PROOF_REQUIRED")
    return deepcopy(record)


def observation(value: object, record: dict, now: int, image: str) -> None:
    obs = fields(value, OBS_FIELDS, "OBSERVATION_FIELDS_DENIED")
    need(obs["observed_at"] == now and type(obs["observed_at"]) is int,
         "STALE_OBSERVATION_DENIED")
    need(obs["target_id"] == record["target_id"] and
         obs["boot_id"] == record["boot_id"], "BOOT_OR_TARGET_CHANGED")
    need(obs["image_sha256"] == image and
         obs["manager_state"] == "operating" and
         digest(obs["owner_evidence_sha256"]) and
         obs["axi_admission"] == "SEPARATELY_AUTHORIZED",
         "CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED")


def test_evidence(data: object, record: dict) -> str:
    keys = frozenset({"lease_id", "load_evidence_sha256", "test_evidence_sha256",
                      "observed", "read32", "write32", "native_readonly"})
    v = fields(data, keys, "TEST_RECEIPT_FIELDS_DENIED")
    need(v["lease_id"] == record["lease_id"] and
         v["load_evidence_sha256"] == record["load_evidence_sha256"] and
         digest(v["test_evidence_sha256"]), "TEST_PROVENANCE_DENIED")
    need(type(v["observed"]) is dict and v["observed"] == TEST_WORDS and
         all(type(x) is int for x in v["observed"].values()) and
         type(v["read32"]) is int and v["read32"] == 3 and
         type(v["write32"]) is int and v["write32"] == 0 and
         v["native_readonly"] is True,
         "IDENTITY_THREE_READS_NOT_PROVEN")
    return v["test_evidence_sha256"]


def create_record(intent: dict, now: int) -> dict:
    tick(now)
    keys = frozenset({"lease_id", "target_id", "profile_id", "source_sha",
                      "artifact_sha256", "recovery_sha256", "boot_id",
                      "owner_id", "restore_intent_sha256", "services_sha256",
                      "uio_sha256", "lease_seconds"})
    item = fields(intent, keys, "RESTORE_INTENT_FIELDS_DENIED")
    need(type(item["lease_seconds"]) is int and
         0 < item["lease_seconds"] <= 900, "LEASE_TTL_DENIED")
    d = dict(item)
    duration = d.pop("lease_seconds")
    d.update(schema=SCHEMA, status="RESTORE_REQUIRED",
             lease_deadline=now + duration, step_deadline=now + duration,
             last_seen=now, revision=0, load_attempts=0, test_attempts=0,
             restore_attempts=0, load_evidence_sha256=None,
             test_evidence_sha256=None, restore_evidence_sha256=None,
             reason="")
    return validate_record(d)


def next_record(prev: dict, action: str, now: int, *, facts: dict | None = None,
                evidence: dict | None = None, step_seconds: int = 30) -> dict:
    """Pure, fail-closed transition. Never performs a device command.

    In-flight deadlines and expired leases require explicit reconciliation,
    not retry. Call 'mark_unknown' to persist the incident without touching PL.
    """
    state = validate_record(prev)
    tick(now)
    need(now >= state["last_seen"], "CLOCK_ROLLBACK_DENIED")
    need(type(step_seconds) is int and 0 < step_seconds <= 120,
         "STEP_TIMEOUT_DENIED")
    if action == "mark_unknown":
        need(state["status"] not in ("RESTORED_VERIFIED", "UNKNOWN_MANUAL_RECOVERY"),
             "UNKNOWN_TRANSITION_DENIED")
        reason = (evidence or {}).get("reason")
        need(type(reason) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", reason)
             is not None, "INCIDENT_REASON_DENIED")
        state["status"] = "UNKNOWN_MANUAL_RECOVERY"
        state["reason"] = reason
    elif action == "mark_expired":
        need(now >= state["lease_deadline"] and
             state["status"] in ("LOADED_AND_HELD", "RESTORE_REQUIRED"),
             "EXPIRY_NOT_APPLICABLE")
        state["status"] = "EXPIRED_REVIEW_REQUIRED"
        state["reason"] = "LEASE_EXPIRED_NO_AUTOMATIC_RESTORE"
    else:
        need(now < state["lease_deadline"], "LEASE_EXPIRED_NO_AUTOMATIC_RESTORE")
        need(state["status"] not in ("LOAD_IN_FLIGHT", "TEST_IN_FLIGHT",
                                    "RESTORE_IN_FLIGHT") or
             now <= state["step_deadline"], "IN_FLIGHT_TIMEOUT_NO_RETRY")
        target = {
            "claim_load": ("RESTORE_REQUIRED", "LOAD_IN_FLIGHT"),
            "confirm_load": ("LOAD_IN_FLIGHT", "LOADED_AND_HELD"),
            "claim_test": ("LOADED_AND_HELD", "TEST_IN_FLIGHT"),
            "confirm_test": ("TEST_IN_FLIGHT", "LOADED_AND_HELD"),
            "claim_restore": ("LOADED_AND_HELD", "RESTORE_IN_FLIGHT"),
            "confirm_restore": ("RESTORE_IN_FLIGHT", "RESTORED_VERIFIED"),
        }.get(action)
        need(target is not None and state["status"] == target[0],
             "TRANSITION_NOT_AUTHORIZED")
        if action in ("claim_load", "claim_test", "claim_restore"):
            observation(facts, state, now, state["recovery_sha256"]
                        if action == "claim_load" else state["artifact_sha256"])
            state["step_deadline"] = min(state["lease_deadline"], now + step_seconds)
        if action == "claim_load":
            need(state["load_attempts"] == 0, "LOAD_RETRY_DENIED")
            state["load_attempts"] += 1
        if action == "confirm_load":
            observation(facts, state, now, state["artifact_sha256"])
            receipt = fields(evidence, frozenset({"lease_id", "load_evidence_sha256",
                                                 "restore_intent_sha256"}),
                             "LOAD_RECEIPT_FIELDS_DENIED")
            need(receipt["lease_id"] == state["lease_id"] and
                 receipt["restore_intent_sha256"] == state["restore_intent_sha256"] and
                 digest(receipt["load_evidence_sha256"]), "LOAD_PROVENANCE_DENIED")
            state["load_evidence_sha256"] = receipt["load_evidence_sha256"]
        if action == "claim_test":
            need(digest(state["load_evidence_sha256"]), "LOADED_EVIDENCE_REQUIRED")
            state["test_attempts"] += 1
        if action == "confirm_test":
            observation(facts, state, now, state["artifact_sha256"])
            state["test_evidence_sha256"] = test_evidence(evidence, state)
        if action == "claim_restore":
            need(state["restore_attempts"] == 0 and
                 digest(state["load_evidence_sha256"]), "RESTORE_RETRY_DENIED")
            state["restore_attempts"] += 1
        if action == "confirm_restore":
            observation(facts, state, now, state["recovery_sha256"])
            receipt = fields(evidence, frozenset({"lease_id", "restore_evidence_sha256",
                                                 "services_sha256", "uio_sha256"}),
                             "RESTORE_RECEIPT_FIELDS_DENIED")
            need(receipt["lease_id"] == state["lease_id"] and
                 receipt["services_sha256"] == state["services_sha256"] and
                 receipt["uio_sha256"] == state["uio_sha256"] and
                 digest(receipt["restore_evidence_sha256"]),
                 "RESTORE_PROVENANCE_DENIED")
            state["restore_evidence_sha256"] = receipt["restore_evidence_sha256"]
        state["status"] = target[1]
    state["last_seen"] = now
    state["revision"] += 1
    # Terminal records retain historical lease_deadline; equality/greater
    # timestamps are valid after a terminal incident or successful restore.
    return state


def require_testing(entry: dict, request: dict, facts: dict, now: int) -> None:
    """Cross-trigger gate; caller must independently authenticate fresh facts."""
    rec = validate_record(entry)
    tick(now)
    need(rec["status"] == "LOADED_AND_HELD" and now >= rec["last_seen"]
         and now < rec["lease_deadline"], "LOADED_LEASE_NOT_ACTIVE")
    need(type(request) is dict and
         set(request) == {"lease_id", "source_sha", "profile_id", "target_id",
                          "artifact_sha256", "load_evidence_sha256"} and
         all(request[k] == rec[k] for k in request),
         "TESTING_PROVENANCE_MISMATCH")
    observation(facts, rec, now, rec["artifact_sha256"])


class LeaseLedger:
    """Single target-specific durable file with inter-process flock + fsync.

    Caller owns the trusted private directory and chooses *one canonical
    file per target*. A separate authorized global hardware lock remains
    mandatory. The ledger is not a proof of truthful device observations.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _locked(self):
        root = self.path.parent
        need(root.is_dir() and not root.is_symlink(), "PRIVATE_LEDGER_DIRECTORY_REQUIRED")
        st = root.stat()
        need(st.st_uid == os.geteuid() and st.st_mode & 0o022 == 0,
             "LEDGER_DIRECTORY_UNTRUSTED")
        need(self.path.name not in (".", "..") and
             self.path.suffix == ".json", "LEDGER_PATH_DENIED")
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            s = os.fstat(fd)
            need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
                 s.st_uid == os.geteuid() and s.st_mode & 0o077 == 0,
                 "LEDGER_LOCK_UNTRUSTED")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def _read(self) -> dict:
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                 and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0
                 and info.st_size <= 16384, "LEDGER_FILE_UNTRUSTED")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as source:
                raw = json.load(source)
        finally:
            os.close(fd)
        return validate_record(raw)

    def _write(self, value: dict) -> None:
        rec = validate_record(value)
        payload = (json.dumps(rec, sort_keys=True, indent=2) + "\n").encode()
        need(len(payload) <= 16384, "LEDGER_TOO_LARGE")
        tmp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                need(written > 0, "LEDGER_WRITE_INCOMPLETE")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def initialize(self, intent: dict, now: int) -> dict:
        with self._locked():
            need(not self.path.exists() and not self.path.is_symlink(),
                 "TARGET_LEASE_ALREADY_EXISTS")
            result = create_record(intent, now)
            self._write(result)
            return deepcopy(result)

    def advance(self, action: str, now: int, *, facts: dict | None = None,
                evidence: dict | None = None, step_seconds: int = 30,
                expected_revision: int) -> dict:
        with self._locked():
            prior = self._read()
            need(type(expected_revision) is int and
                 expected_revision == prior["revision"], "STALE_REVISION_DENIED")
            result = next_record(prior, action, now, facts=facts,
                                 evidence=evidence, step_seconds=step_seconds)
            self._write(result)
            return deepcopy(result)

    def snapshot(self) -> dict:
        with self._locked():
            return self._read()
