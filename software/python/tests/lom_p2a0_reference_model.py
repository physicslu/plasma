"""LOM-P2A-0 executable reference model of ``plasma.ppu.local-enrollment.v1``.

TEST-ONLY specification artifact. It freezes the state machine, error codes,
crash points and Recovery-Gated Takeover rules of
``docs/development/opf-local-owner-mode-p2a0-enrollment-spec.md`` so the
LOM-P2A-2 implementation can be checked against the same cases. It is NOT
product code: nothing in Bootstrap, Manager, Console or the PPU imports it, it
touches no filesystem, network, SD card, FPGA or DUT, and it grants nothing.

Durable state is a dict of atomically replaced records (one record = one
temp+fsync+rename). ``crash_at`` raises ``Crash`` at a named point so tests can
re-open the model from the surviving durable records.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "plasma.ppu.local-enrollment.v1"
TICKET_SCHEMA = "plasma.ppu.enrollment-ticket.v1"
TICKET_FILE = "plasma-enroll.json"
MAX_TICKET_FILE_BYTES = 4096
ENROLLMENT_WINDOW_S = 900
MAX_CLAIM_FAILURES = 5
LEDGER_CAPACITY = 4096

MODE_NORMAL = "NORMAL"
MODE_RECOVERY_ONLY = "RECOVERY_ONLY"
CONTROLLER_STATES = ("UNENROLLED", MODE_NORMAL, MODE_RECOVERY_ONLY, "FAULT")
ENROLLMENT_STATES = ("NONE", "ARMED", "CONSUMED", "LOCKED_OUT", "EXPIRED")
TICKET_SOURCES = ("sd-boot-partition", "serial-dev")

ERROR_CODES = frozenset({
    "ENROLLMENT_NOT_ARMED",
    "ENROLLMENT_EXPIRED",
    "ENROLLMENT_NONCE_INVALID",
    "ENROLLMENT_PROOF_INVALID",
    "ENROLLMENT_LOCKED_OUT",
    "ENROLLMENT_TICKET_INVALID",
    "ENROLLMENT_TICKET_REPLAYED",
    "ENROLLMENT_TICKET_CONSUMED",
    "ENROLLMENT_TICKET_NOT_CONSUMED",
    "ENROLLMENT_LEDGER_FULL",
    "TAKEOVER_DEFERRED_ACTIVE_OPERATION",
    "CONTROLLER_NOT_ENROLLED",
    "CONTROLLER_REVOKED",
    "CONTROLLER_RECOVERY_ONLY",
    "CONTROLLER_STATE_ROLLBACK",
    "RECOVERY_BLOCKED",
    "RECOVERY_ACTION_NOT_REQUESTED",
})

# Normal writes: forbidden in RECOVERY_ONLY.
NORMAL_WRITES = frozenset({
    "bundle.upload", "bundle.admit", "bundle.install", "runtime.deploy",
    "fpga.load", "site.job.submit", "site.settings.write", "site.activation",
})
# Explicit, controlled recovery actions: allowed in RECOVERY_ONLY and NORMAL.
RECOVERY_ACTIONS = frozenset({
    "status.read", "site.diagnose", "site.recover", "outcome.reconcile",
    "recovery.complete",
})
RECONCILIATION_DECISIONS = frozenset({
    "CONFIRMED_NOT_EXECUTED", "CONFIRMED_EXECUTED_VERIFIED", "CONFIRMED_FAILED",
})
CRASH_POINTS = (
    "boot.after_ledger_append", "boot.after_ticket_delete", "boot.after_arm",
    "claim.before_controller_commit", "claim.after_controller_commit",
    "claim.after_high_water", "recovery.before_mode_commit",
)

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")


class Crash(RuntimeError):
    """Simulated power loss at a named point; durable records survive."""


class SpecError(RuntimeError):
    def __init__(self, code: str, detail: Any = None) -> None:
        assert code in ERROR_CODES, code
        super().__init__(code)
        self.code, self.detail = code, detail


# --- ticket and key derivation (client and PPU share these definitions) -------

def make_ticket_file(ticket: str | None = None, note: str = "") -> bytes:
    ticket = ticket or secrets.token_hex(32)
    return json.dumps({"schema": TICKET_SCHEMA, "ticket": ticket, "note": note[:128]},
                      sort_keys=True).encode()


def ticket_id(ticket: str) -> str:
    return hashlib.sha256(("ticket-id\n" + ticket).encode()).hexdigest()[:32]


def ticket_key(ticket: str) -> bytes:
    return hmac.new(bytes.fromhex(ticket), f"{SCHEMA}/ticket-key".encode(), hashlib.sha256).digest()


def claim_mac(key: bytes, *, device_id: str, enrollment_id: str, nonce: str,
              controller_nonce: str, current_generation: int, label: str) -> str:
    message = "\n".join((SCHEMA, "claim", device_id, enrollment_id, nonce, controller_nonce,
                         str(current_generation), label)).encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _keystream(key: bytes, info: bytes, length: int) -> bytes:
    out, counter = b"", 0
    while len(out) < length:
        out += hmac.new(key, info + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def wrap_credential(key: bytes, *, nonce: str, controller_nonce: str, generation: int,
                    credential: str) -> dict[str, str]:
    """HMAC-SHA256 CTR keystream + encrypt-then-MAC (stdlib only; PYNQ-safe)."""
    info = f"{SCHEMA}/wrap\n{nonce}\n{controller_nonce}\n{generation}\n".encode()
    plain = credential.encode()
    cipher = bytes(a ^ b for a, b in zip(plain, _keystream(key, info, len(plain))))
    tag = hmac.new(key, info + cipher, hashlib.sha256).hexdigest()
    return {"ciphertext": cipher.hex(), "tag": tag}


def unwrap_credential(key: bytes, *, nonce: str, controller_nonce: str, generation: int,
                      wrapped: dict[str, str]) -> str:
    info = f"{SCHEMA}/wrap\n{nonce}\n{controller_nonce}\n{generation}\n".encode()
    cipher = bytes.fromhex(wrapped["ciphertext"])
    if not hmac.compare_digest(hmac.new(key, info + cipher, hashlib.sha256).hexdigest(),
                               wrapped["tag"]):
        raise ValueError("wrapped credential tag invalid")
    return bytes(a ^ b for a, b in zip(cipher, _keystream(key, info, len(cipher)))).decode()


# --- PPU safety state that enrollment must read but never modify -------------

@dataclass
class SafetyState:
    """Opaque PPU safety records. Enrollment may READ these, never rewrite them."""
    active_site_jobs: set[str] = field(default_factory=set)        # queued/running/cancelling
    active_bootstrap_deployment: str | None = None                 # queued/running/activating
    active_fpga_operation: str | None = None                       # reload fence held
    seals: dict[int, str] = field(default_factory=dict)            # site -> marker evidence
    unknown_outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_set_state: str = "ACTIVE"                               # ACTIVE/EMPTY/RECOVERY_REQUIRED
    journals: dict[str, str] = field(default_factory=dict)         # name -> opaque bytes
    active_set: dict[str, Any] = field(default_factory=dict)
    boot_ids: list[str] = field(default_factory=list)
    recovery_evidence: list[str] = field(default_factory=list)

    def active_operations(self) -> list[str]:
        ops = sorted("site-job:" + j for j in self.active_site_jobs)
        if self.active_bootstrap_deployment:
            ops.append("bootstrap-deployment:" + self.active_bootstrap_deployment)
        if self.active_fpga_operation:
            ops.append("fpga:" + self.active_fpga_operation)
        return ops

    def unresolved(self) -> list[str]:
        blockers = [f"site{site}.sealed" for site in sorted(self.seals)]
        blockers += sorted("OUTCOME_UNKNOWN:" + txn for txn, rec in self.unknown_outcomes.items()
                           if rec.get("reconciliation") is None)
        if self.active_set_state == "RECOVERY_REQUIRED":
            blockers.append("ACTIVE_SET_RECOVERY_REQUIRED")
        return blockers

    def preserved_view(self) -> str:
        """Everything takeover must leave byte-identical."""
        return json.dumps({
            "seals": self.seals, "unknown": self.unknown_outcomes,
            "active_set_state": self.active_set_state, "journals": self.journals,
            "active_set": self.active_set, "boot_ids": self.boot_ids,
            "evidence": self.recovery_evidence,
        }, sort_keys=True)


# --- the PPU-side reference model --------------------------------------------

class Disk:
    """Durable records; each ``put`` is one atomic replace."""

    def __init__(self) -> None:
        self.records: dict[str, Any] = {}
        self.boot_partition: dict[str, bytes] = {}

    def get(self, key: str) -> Any:
        value = self.records.get(key)
        return json.loads(json.dumps(value)) if value is not None else None

    def put(self, key: str, value: Any) -> None:
        self.records[key] = json.loads(json.dumps(value))

    def delete(self, key: str) -> None:
        self.records.pop(key, None)


class PPU:
    def __init__(self, disk: Disk, safety: SafetyState, *, device_id: str, boot_id: str,
                 now: float = 0.0, crash_at: str | None = None,
                 boot_partition_delete_fails: bool = False) -> None:
        self.disk, self.safety, self.device_id = disk, safety, device_id
        self.boot_id, self.crash_at = boot_id, crash_at
        self.boot_partition_delete_fails = boot_partition_delete_fails
        self.nonces: set[str] = set()       # memory only: lost on restart
        self.events: list[str] = []
        if boot_id not in safety.boot_ids:
            safety.boot_ids.append(boot_id)
        self._boot(now)

    # -- helpers
    def _point(self, name: str) -> None:
        assert name in CRASH_POINTS, name
        if self.crash_at == name:
            raise Crash(name)

    def _ledger(self) -> dict[str, Any]:
        return self.disk.get("ledger") or {"consumed": [], "high_water": 0}

    def controller(self) -> dict[str, Any] | None:
        return self.disk.get("controller")

    def controller_state(self) -> str:
        record = self.controller()
        if record is None:
            return "UNENROLLED"
        if record["generation"] < self._ledger()["high_water"]:
            return "FAULT"
        return record["mode"]

    def _pending(self, now: float) -> dict[str, Any]:
        pending = self.disk.get("pending")
        if pending is None:
            raise SpecError("ENROLLMENT_NOT_ARMED")
        if pending["boot_id"] != self.boot_id or now >= pending["deadline"]:
            self.disk.delete("pending")
            raise SpecError("ENROLLMENT_EXPIRED")
        return pending

    def enrollment_state(self, now: float) -> str:
        pending = self.disk.get("pending")
        if pending is None:
            return "NONE"
        if pending["boot_id"] != self.boot_id or now >= pending["deadline"]:
            return "EXPIRED"
        record = self.controller()
        if record and record.get("last_enrollment", {}).get("enrollment_id") == pending["enrollment_id"]:
            return "CONSUMED"
        return "ARMED"

    # -- boot-time, PPU-local, before any network service accepts mutations
    def _boot(self, now: float) -> None:
        pending = self.disk.get("pending")
        if pending is not None and pending["boot_id"] != self.boot_id:
            self.disk.delete("pending")            # a reboot always expires a window
        raw = self.disk.boot_partition.get(TICKET_FILE)
        if raw is None:
            return
        try:
            if len(raw) > MAX_TICKET_FILE_BYTES:
                raise ValueError
            doc = json.loads(raw)
            if (type(doc) is not dict or doc.get("schema") != TICKET_SCHEMA
                    or type(doc.get("ticket")) is not str or not _HEX64.fullmatch(doc["ticket"])
                    or set(doc) - {"schema", "ticket", "note"}):
                raise ValueError
        except ValueError:
            self.disk.boot_partition.pop(TICKET_FILE, None)
            self.events.append("ENROLLMENT_TICKET_INVALID")
            return
        ticket = doc["ticket"]
        tid = ticket_id(ticket)
        ledger = self._ledger()
        if tid in ledger["consumed"]:
            self.disk.boot_partition.pop(TICKET_FILE, None)
            self.events.append("ENROLLMENT_TICKET_REPLAYED")
            return
        if len(ledger["consumed"]) >= LEDGER_CAPACITY:
            self.disk.boot_partition.pop(TICKET_FILE, None)
            self.events.append("ENROLLMENT_LEDGER_FULL")
            return
        ledger["consumed"].append(tid)           # durable BEFORE the file can disappear
        self.disk.put("ledger", ledger)
        self._point("boot.after_ledger_append")
        if self.boot_partition_delete_fails:
            self.events.append("ENROLLMENT_TICKET_NOT_CONSUMED")
            return                                # not armed; next boot sees a replay
        self.disk.boot_partition.pop(TICKET_FILE, None)
        self._point("boot.after_ticket_delete")
        self._arm(tid, ticket_key(ticket), now, source="sd-boot-partition")
        self._point("boot.after_arm")

    def _arm(self, tid: str, key: bytes, now: float, *, source: str) -> None:
        assert source in TICKET_SOURCES
        self.disk.put("pending", {"enrollment_id": tid, "key": key.hex(), "boot_id": self.boot_id,
                                  "deadline": now + ENROLLMENT_WINDOW_S, "failures": 0,
                                  "source": source})
        self.events.append("ENROLLMENT_ARMED:" + source)

    def serial_arm(self, now: float, *, local_console_root: bool) -> str:
        """Development alternative: root on the PPU-local console prints a ticket once."""
        if not local_console_root:
            raise PermissionError("serial enrollment requires root on the local console")
        ticket = secrets.token_hex(32)
        tid = ticket_id(ticket)
        ledger = self._ledger()
        ledger["consumed"].append(tid)
        self.disk.put("ledger", ledger)
        self._arm(tid, ticket_key(ticket), now, source="serial-dev")
        return ticket

    # -- enrollment exchange (reachable over the LAN, inert unless ARMED)
    def challenge(self, now: float) -> dict[str, Any]:
        pending = self._pending(now)
        nonce = secrets.token_hex(16)
        self.nonces.add(nonce)
        record = self.controller()
        return {"schema": SCHEMA, "device_id": self.device_id,
                "enrollment_id": pending["enrollment_id"], "nonce": nonce,
                "current_generation": record["generation"] if record else 0}

    def claim(self, request: dict[str, Any], now: float) -> dict[str, Any]:
        pending = self._pending(now)
        if request.get("enrollment_id") != pending["enrollment_id"]:
            raise SpecError("ENROLLMENT_PROOF_INVALID")
        nonce = request.get("nonce")
        if nonce not in self.nonces:
            raise SpecError("ENROLLMENT_NONCE_INVALID")
        self.nonces.discard(nonce)                # single use, before any check
        key = bytes.fromhex(pending["key"])
        record = self.controller()
        current = record["generation"] if record else 0
        cn, label = request.get("controller_nonce"), request.get("label", "")
        if type(cn) is not str or not _HEX32.fullmatch(cn) or type(label) is not str or len(label) > 64:
            raise SpecError("ENROLLMENT_PROOF_INVALID")
        expected = claim_mac(key, device_id=self.device_id, enrollment_id=pending["enrollment_id"],
                             nonce=nonce, controller_nonce=cn, current_generation=current,
                             label=label)
        last = (record or {}).get("last_enrollment", {})
        consumed = last.get("enrollment_id") == pending["enrollment_id"]
        if consumed:
            # Retrieval after a lost response: same controller only, no new generation.
            if not hmac.compare_digest(expected, request.get("mac", "")) or cn != last["controller_nonce"]:
                raise SpecError("ENROLLMENT_TICKET_CONSUMED")
            return dict(last["response"])
        if not hmac.compare_digest(expected, request.get("mac", "")):
            pending["failures"] += 1
            if pending["failures"] >= MAX_CLAIM_FAILURES:
                self.disk.delete("pending")
                raise SpecError("ENROLLMENT_LOCKED_OUT")
            self.disk.put("pending", pending)
            raise SpecError("ENROLLMENT_PROOF_INVALID")
        if self.controller_state() == "FAULT":
            raise SpecError("CONTROLLER_STATE_ROLLBACK")
        # Recovery-Gated Takeover, evaluated under the exclusive transition fence.
        active = self.safety.active_operations()
        if active:
            raise SpecError("TAKEOVER_DEFERRED_ACTIVE_OPERATION", active)
        blockers = self.safety.unresolved()
        mode = MODE_RECOVERY_ONLY if blockers else MODE_NORMAL
        generation = max(current, self._ledger()["high_water"]) + 1
        credential = secrets.token_hex(32)
        response = {"schema": SCHEMA, "device_id": self.device_id, "generation": generation,
                    "mode": mode, "recovery_blockers": blockers, "wrap_nonce": nonce,
                    "controller_id": secrets.token_hex(16),
                    "wrapped_credential": wrap_credential(
                        key, nonce=nonce, controller_nonce=cn, generation=generation,
                        credential=credential)}
        self._point("claim.before_controller_commit")
        # ONE atomic record: new credential, generation, mode and the retrievable
        # response. The previous credential is invalid from this rename onward.
        self.disk.put("controller", {
            "generation": generation, "credential": credential, "mode": mode,
            "controller_id": response["controller_id"], "label": label,
            "last_enrollment": {"enrollment_id": pending["enrollment_id"],
                                "controller_nonce": cn, "response": response,
                                "source": pending["source"]},
        })
        self._point("claim.after_controller_commit")
        ledger = self._ledger()
        ledger["high_water"] = max(ledger["high_water"], generation)
        self.disk.put("ledger", ledger)
        self._point("claim.after_high_water")
        return response

    # -- every authenticated PPU mutation/read passes here (Bootstrap AND Gateway)
    def authorize(self, credential: str, operation: str) -> str:
        record = self.controller()
        if record is None:
            raise SpecError("CONTROLLER_NOT_ENROLLED")
        if self.controller_state() == "FAULT":
            raise SpecError("CONTROLLER_STATE_ROLLBACK")
        if not hmac.compare_digest(record["credential"], credential):
            raise SpecError("CONTROLLER_REVOKED", {"current_generation": record["generation"]})
        if operation not in NORMAL_WRITES | RECOVERY_ACTIONS:
            raise ValueError("unknown operation " + operation)
        if record["mode"] == MODE_RECOVERY_ONLY and operation in NORMAL_WRITES:
            raise SpecError("CONTROLLER_RECOVERY_ONLY", self.safety.unresolved())
        return record["mode"]

    def recover_site(self, credential: str, site: int, *, explicit_request: bool) -> None:
        self.authorize(credential, "site.recover")
        if not explicit_request:
            raise SpecError("RECOVERY_ACTION_NOT_REQUESTED")
        marker = self.safety.seals.pop(site)     # stands in for verified SAFE_OFF recovery
        self.safety.recovery_evidence.append(f"site{site}.sealed archived: {marker}")

    def reconcile(self, credential: str, txn: str, decision: str, evidence: str, *,
                  explicit_request: bool) -> None:
        self.authorize(credential, "outcome.reconcile")
        if not explicit_request:
            raise SpecError("RECOVERY_ACTION_NOT_REQUESTED")
        if decision not in RECONCILIATION_DECISIONS or not evidence:
            raise ValueError("reconciliation needs an explicit decision and evidence")
        record = self.safety.unknown_outcomes[txn]
        # The original outcome is kept; reconciliation is appended, never "PASS".
        record["reconciliation"] = {"decision": decision, "evidence": evidence}

    def recovery_complete(self, credential: str, *, observed_device_id: str) -> str:
        self.authorize(credential, "recovery.complete")
        record = self.controller()
        if record["mode"] == MODE_NORMAL:
            return MODE_NORMAL
        blockers = self.safety.active_operations() + self.safety.unresolved()
        if observed_device_id != self.device_id:
            blockers.append("DEVICE_IDENTITY_MISMATCH")
        if blockers:
            raise SpecError("RECOVERY_BLOCKED", blockers)
        record["mode"] = MODE_NORMAL
        self._point("recovery.before_mode_commit")
        self.disk.put("controller", record)
        return MODE_NORMAL


# --- client helper (what a Control Station does) -----------------------------

def client_claim(ppu: PPU, ticket: str, now: float, *, label: str = "station-b",
                 controller_nonce: str | None = None) -> tuple[dict[str, Any], str, str]:
    challenge = ppu.challenge(now)
    cn = controller_nonce or secrets.token_hex(16)
    key = ticket_key(ticket)
    request = {"enrollment_id": challenge["enrollment_id"], "nonce": challenge["nonce"],
               "controller_nonce": cn, "label": label,
               "mac": claim_mac(key, device_id=challenge["device_id"],
                                enrollment_id=challenge["enrollment_id"],
                                nonce=challenge["nonce"], controller_nonce=cn,
                                current_generation=challenge["current_generation"], label=label)}
    response = ppu.claim(request, now)
    # The wrap is bound to the nonce of the COMMITTING claim (kept for retrieval).
    credential = unwrap_credential(key, nonce=response["wrap_nonce"], controller_nonce=cn,
                                   generation=response["generation"],
                                   wrapped=response["wrapped_credential"])
    return response, credential, cn
