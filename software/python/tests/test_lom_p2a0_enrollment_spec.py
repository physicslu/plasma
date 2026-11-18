"""LOM-P2A-0 specification tests (Host-only, reference model only).

These freeze ``plasma.ppu.local-enrollment.v1`` and Recovery-Gated Takeover
(owner decision B3 (b), 2026-11-09). They exercise the TEST-ONLY reference model
in ``lom_p2a0_reference_model.py``; LOM-P2A-2 must make the real Bootstrap /
Manager pass equivalent cases. No SD card, network, PPU, FPGA or DUT is used.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from . import lom_p2a0_reference_model as m

DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"
SPEC = Path(__file__).resolve().parents[3] / "docs/development/opf-local-owner-mode-p2a0-enrollment-spec.md"


def safety(**kwargs) -> m.SafetyState:
    state = m.SafetyState(journals={"deployment.json": "asset_set_active d929e985",
                                    "site2.worker": "idle"},
                          active_set={"sha256": "4d2837d4", "generation": 13}, **kwargs)
    return state


def boot(disk, state, boot_id="boot-1", now=0.0, **kwargs) -> m.PPU:
    return m.PPU(disk, state, device_id=DEVICE, boot_id=boot_id, now=now, **kwargs)


def insert_ticket(disk) -> str:
    ticket = m.secrets.token_hex(32)
    disk.boot_partition[m.TICKET_FILE] = m.make_ticket_file(ticket, note="owner reclaim")
    return ticket


def enrolled(state=None, label="station-a"):
    """A PPU with controller generation 1 (station A) and nothing armed."""
    disk, state = m.Disk(), state or safety()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state)
    _resp, credential, _cn = m.client_claim(ppu, ticket, 10.0, label=label)
    return disk, state, credential


def no_boot_view(state: m.SafetyState) -> str:
    view = json.loads(state.preserved_view())
    view.pop("boot_ids")
    return json.dumps(view, sort_keys=True)


# --- positive ---------------------------------------------------------------

def test_first_enrollment_from_sd_ticket_reaches_normal():
    disk, state = m.Disk(), safety()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state)
    assert m.TICKET_FILE not in disk.boot_partition           # consumed at boot
    assert ppu.enrollment_state(1.0) == "ARMED"
    assert ppu.controller_state() == "UNENROLLED"
    response, credential, _ = m.client_claim(ppu, ticket, 5.0)
    assert (response["generation"], response["mode"]) == (1, m.MODE_NORMAL)
    assert ppu.authorize(credential, "bundle.install") == m.MODE_NORMAL
    assert ppu.enrollment_state(6.0) == "CONSUMED"
    assert credential not in json.dumps(response)              # only the wrapped form is sent


def test_replacement_station_reclaims_without_old_computer_or_token():
    disk, state, credential_a = enrolled()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    response, credential_b, _ = m.client_claim(ppu, ticket, 3.0, label="station-b")
    assert response["generation"] == 2 and response["mode"] == m.MODE_NORMAL
    assert ppu.authorize(credential_b, "site.job.submit") == m.MODE_NORMAL
    with pytest.raises(m.SpecError) as exc:
        ppu.authorize(credential_a, "status.read")
    assert exc.value.code == "CONTROLLER_REVOKED"
    assert exc.value.detail == {"current_generation": 2}


def test_engineering_cli_is_a_labelled_controlled_development_entry():
    disk, state = m.Disk(), safety()
    ppu = boot(disk, state)
    with pytest.raises(m.SpecError) as denied:
        ppu.engineering_arm(0.0, authorized=False)
    assert denied.value.code == "ENGINEERING_MODE_NOT_AUTHORIZED"
    ticket = ppu.engineering_arm(0.0, authorized=True)
    m.client_claim(ppu, ticket, 1.0)
    assert ppu.controller()["last_enrollment"]["source"] == "engineering-cli"


@pytest.mark.parametrize("unsafe", ["seal", "unknown", "active_set"])
def test_recovery_gated_takeover_enters_recovery_only(unsafe):
    disk, state, credential_a = enrolled()
    if unsafe == "seal":
        state.seals[2] = "marker 2026-11-09"
    elif unsafe == "unknown":
        state.unknown_outcomes["run-7bc4"] = {"outcome": "OUTCOME_UNKNOWN", "reconciliation": None}
    else:
        state.active_set_state = "RECOVERY_REQUIRED"
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    before = no_boot_view(state)
    response, credential_b, _ = m.client_claim(ppu, ticket, 2.0)
    assert response["mode"] == m.MODE_RECOVERY_ONLY and response["recovery_blockers"]
    assert ppu.controller_state() == m.MODE_RECOVERY_ONLY
    assert no_boot_view(state) == before                       # nothing erased or rewritten
    with pytest.raises(m.SpecError) as exc:
        ppu.authorize(credential_a, "status.read")
    assert exc.value.code == "CONTROLLER_REVOKED"               # still one active controller
    for write in sorted(m.NORMAL_WRITES):
        with pytest.raises(m.SpecError) as denied:
            ppu.authorize(credential_b, write)
        assert denied.value.code == "CONTROLLER_RECOVERY_ONLY"
    for action in ("status.read", "site.diagnose"):
        assert ppu.authorize(credential_b, action) == m.MODE_RECOVERY_ONLY


def test_recovery_only_to_ready_requires_explicit_recovery_and_verification():
    disk, state, _a = enrolled()
    state.seals[2] = "marker"
    state.unknown_outcomes["run-x"] = {"outcome": "OUTCOME_UNKNOWN", "reconciliation": None}
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    _r, cred, _ = m.client_claim(ppu, ticket, 1.0)
    with pytest.raises(m.SpecError) as blocked:
        ppu.recovery_complete(cred, observed_device_id=DEVICE)
    assert blocked.value.code == "RECOVERY_BLOCKED"
    assert set(blocked.value.detail) == {"site2.sealed", "OUTCOME_UNKNOWN:run-x"}
    ppu.recover_site(cred, 2, explicit_request=True)
    ppu.reconcile(cred, "run-x", "CONFIRMED_NOT_EXECUTED", "PPU job status + journal",
                  explicit_request=True)
    assert state.unknown_outcomes["run-x"]["outcome"] == "OUTCOME_UNKNOWN"   # never PASS
    assert any("site2.sealed archived" in item for item in state.recovery_evidence)
    with pytest.raises(m.SpecError) as wrong_device:
        ppu.recovery_complete(cred, observed_device_id="ppu-device-" + "f" * 24)
    assert "DEVICE_IDENTITY_MISMATCH" in wrong_device.value.detail
    assert ppu.recovery_complete(cred, observed_device_id=DEVICE) == m.MODE_NORMAL
    assert ppu.authorize(cred, "site.job.submit") == m.MODE_NORMAL
    assert ppu.controller()["generation"] == 2                  # mode change, same generation


def test_lost_response_is_retrievable_by_the_same_controller_only():
    disk, state = m.Disk(), safety()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state)
    first, cred, cn = m.client_claim(ppu, ticket, 1.0)
    again, cred_again, _ = m.client_claim(ppu, ticket, 2.0, controller_nonce=cn)
    assert again == first and cred_again == cred and ppu.controller()["generation"] == 1
    with pytest.raises(m.SpecError) as exc:
        m.client_claim(ppu, ticket, 3.0)                         # another station, same ticket
    assert exc.value.code == "ENROLLMENT_TICKET_CONSUMED"


# --- negative ---------------------------------------------------------------

def test_lan_cannot_arm_or_claim_without_a_boot_consumed_ticket():
    disk, state, cred_a = enrolled()
    ppu = boot(disk, state, boot_id="boot-2")
    with pytest.raises(m.SpecError) as exc:
        ppu.challenge(0.0)
    assert exc.value.code == "ENROLLMENT_NOT_ARMED"
    disk.boot_partition[m.TICKET_FILE] = m.make_ticket_file()   # written at runtime
    with pytest.raises(m.SpecError) as runtime_write:
        ppu.challenge(1.0)
    assert runtime_write.value.code == "ENROLLMENT_NOT_ARMED"   # only boot-time read counts
    assert ppu.authorize(cred_a, "bundle.install") == m.MODE_NORMAL


@pytest.mark.parametrize("raw", [
    b"not json",
    json.dumps({"schema": "wrong", "ticket": "a" * 64}).encode(),
    json.dumps({"schema": m.TICKET_SCHEMA, "ticket": "A" * 64}).encode(),
    json.dumps({"schema": m.TICKET_SCHEMA, "ticket": "a" * 63}).encode(),
    json.dumps({"schema": m.TICKET_SCHEMA, "ticket": "a" * 64, "credential": "x"}).encode(),
    b" " * (m.MAX_TICKET_FILE_BYTES + 1),
])
def test_invalid_ticket_file_is_deleted_and_never_arms(raw):
    disk, state = m.Disk(), safety()
    disk.boot_partition[m.TICKET_FILE] = raw
    ppu = boot(disk, state)
    assert m.TICKET_FILE not in disk.boot_partition
    assert "ENROLLMENT_TICKET_INVALID" in ppu.events
    assert ppu.enrollment_state(0.0) == "NONE"


def test_sd_ticket_replay_is_rejected():
    disk, state = m.Disk(), safety()
    raw = m.make_ticket_file()
    disk.boot_partition[m.TICKET_FILE] = raw
    ppu = boot(disk, state)
    ticket = json.loads(raw)["ticket"]
    m.client_claim(ppu, ticket, 1.0)
    disk.boot_partition[m.TICKET_FILE] = raw                   # copied back to the card
    replay = boot(disk, state, boot_id="boot-2")
    assert "ENROLLMENT_TICKET_REPLAYED" in replay.events
    assert m.TICKET_FILE not in disk.boot_partition
    assert replay.enrollment_state(0.0) == "NONE"
    assert replay.controller()["generation"] == 1


def test_window_expires_by_time_and_by_reboot():
    disk, state = m.Disk(), safety()
    insert_ticket(disk)
    ppu = boot(disk, state, now=100.0)
    with pytest.raises(m.SpecError) as exc:
        ppu.challenge(100.0 + m.ENROLLMENT_WINDOW_S)
    assert exc.value.code == "ENROLLMENT_EXPIRED"
    disk2, state2 = m.Disk(), safety()
    insert_ticket(disk2)
    boot(disk2, state2)
    after_reboot = boot(disk2, state2, boot_id="boot-2")
    with pytest.raises(m.SpecError) as exc2:
        after_reboot.challenge(1.0)
    assert exc2.value.code == "ENROLLMENT_NOT_ARMED"


def test_wrong_proof_counts_and_locks_out():
    disk, state = m.Disk(), safety()
    insert_ticket(disk)
    ppu = boot(disk, state)
    wrong = m.secrets.token_hex(32)
    for attempt in range(1, m.MAX_CLAIM_FAILURES + 1):
        with pytest.raises(m.SpecError) as exc:
            m.client_claim(ppu, wrong, float(attempt))
        expected = "ENROLLMENT_LOCKED_OUT" if attempt == m.MAX_CLAIM_FAILURES else "ENROLLMENT_PROOF_INVALID"
        assert exc.value.code == expected
    with pytest.raises(m.SpecError) as after:
        ppu.challenge(10.0)
    assert after.value.code == "ENROLLMENT_NOT_ARMED"
    assert ppu.controller_state() == "UNENROLLED"


def test_nonce_is_single_use_and_bound_to_device():
    disk, state = m.Disk(), safety()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state)
    challenge = ppu.challenge(1.0)
    key, cn = m.ticket_key(ticket), m.secrets.token_hex(16)
    def request(device):
        return {"enrollment_id": challenge["enrollment_id"], "nonce": challenge["nonce"],
                "controller_nonce": cn, "label": "x",
                "mac": m.claim_mac(key, device_id=device, enrollment_id=challenge["enrollment_id"],
                                   nonce=challenge["nonce"], controller_nonce=cn,
                                   current_generation=0, label="x")}
    with pytest.raises(m.SpecError) as wrong_device:
        ppu.claim(request("ppu-device-" + "f" * 24), 2.0)
    assert wrong_device.value.code == "ENROLLMENT_PROOF_INVALID"
    with pytest.raises(m.SpecError) as reused:
        ppu.claim(request(DEVICE), 3.0)                        # same nonce again
    assert reused.value.code == "ENROLLMENT_NONCE_INVALID"


@pytest.mark.parametrize("active", ["site_job", "bootstrap", "fpga"])
def test_active_operation_defers_takeover_without_side_effects(active):
    disk, state, cred_a = enrolled()
    if active == "site_job":
        state.active_site_jobs.add("job-20261109-083059")
    elif active == "bootstrap":
        state.active_bootstrap_deployment = "d929e985"
    else:
        state.active_fpga_operation = "reload-fence"
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    before = (json.dumps(disk.records, sort_keys=True), no_boot_view(state))
    with pytest.raises(m.SpecError) as exc:
        m.client_claim(ppu, ticket, 1.0)
    assert exc.value.code == "TAKEOVER_DEFERRED_ACTIVE_OPERATION" and exc.value.detail
    assert (json.dumps(disk.records, sort_keys=True), no_boot_view(state)) == before
    assert ppu.authorize(cred_a, "status.read") == m.MODE_NORMAL   # no rotation, no cancel
    state.active_site_jobs.clear()
    state.active_bootstrap_deployment = state.active_fpga_operation = None
    response, _cred_b, _ = m.client_claim(ppu, ticket, 2.0)    # re-evaluated after terminal
    assert response["generation"] == 2


def test_recovery_actions_need_an_explicit_request():
    disk, state, _a = enrolled()
    state.seals[1] = "marker"
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    _r, cred, _ = m.client_claim(ppu, ticket, 1.0)
    with pytest.raises(m.SpecError) as exc:
        ppu.recover_site(cred, 1, explicit_request=False)
    assert exc.value.code == "RECOVERY_ACTION_NOT_REQUESTED"
    assert 1 in state.seals


def test_unenrolled_and_unknown_operations_fail_closed():
    ppu = boot(m.Disk(), safety())
    with pytest.raises(m.SpecError) as exc:
        ppu.authorize("x" * 64, "status.read")
    assert exc.value.code == "CONTROLLER_NOT_ENROLLED"
    disk, state, cred = enrolled()
    with pytest.raises(m.SpecError) as unclassified:
        boot(disk, state).authorize(cred, "shell.exec")
    assert unclassified.value.code == "CONTROLLER_OPERATION_UNCLASSIFIED"


def test_ticket_not_consumed_or_ledger_full_never_arms():
    disk, state = m.Disk(), safety()
    insert_ticket(disk)
    ppu = boot(disk, state, boot_partition_delete_fails=True)
    assert "ENROLLMENT_TICKET_NOT_CONSUMED" in ppu.events and ppu.enrollment_state(0.0) == "NONE"
    next_boot = boot(disk, state, boot_id="boot-2")
    assert "ENROLLMENT_TICKET_REPLAYED" in next_boot.events
    full = m.Disk()
    full.put("ledger", {"consumed": [f"{i:032x}" for i in range(m.LEDGER_CAPACITY)], "high_water": 0})
    insert_ticket(full)
    assert "ENROLLMENT_LEDGER_FULL" in boot(full, safety()).events


# --- controller conflicts ---------------------------------------------------

def test_two_stations_with_the_same_ticket_first_wins_once():
    disk, state, _a = enrolled()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    c1, c2 = ppu.challenge(1.0), ppu.challenge(1.0)
    key = m.ticket_key(ticket)
    def req(ch, label):
        cn = m.secrets.token_hex(16)
        return {"enrollment_id": ch["enrollment_id"], "nonce": ch["nonce"], "controller_nonce": cn,
                "label": label, "mac": m.claim_mac(key, device_id=DEVICE,
                                                   enrollment_id=ch["enrollment_id"], nonce=ch["nonce"],
                                                   controller_nonce=cn,
                                                   current_generation=ch["current_generation"],
                                                   label=label)}
    r1, r2 = req(c1, "b"), req(c2, "c")
    assert ppu.claim(r1, 2.0)["generation"] == 2
    with pytest.raises(m.SpecError) as exc:
        ppu.claim(r2, 2.0)
    assert exc.value.code == "ENROLLMENT_TICKET_CONSUMED"
    assert ppu.controller()["generation"] == 2 and ppu.controller()["label"] == "b"


def test_restored_old_controller_record_is_a_rollback_fault():
    disk, state, cred_a = enrolled()
    old = disk.get("controller")
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    m.client_claim(ppu, ticket, 1.0)
    disk.put("controller", old)                                # restored from a backup
    restored = boot(disk, state, boot_id="boot-3")
    assert restored.controller_state() == "FAULT"
    with pytest.raises(m.SpecError) as exc:
        restored.authorize(cred_a, "status.read")
    assert exc.value.code == "CONTROLLER_STATE_ROLLBACK"


# --- crash recovery ---------------------------------------------------------

def test_crash_after_ledger_append_turns_the_file_into_a_rejected_replay():
    disk, state, cred_a = enrolled()
    insert_ticket(disk)
    with pytest.raises(m.Crash):
        boot(disk, state, boot_id="boot-2", crash_at="boot.after_ledger_append")
    after = boot(disk, state, boot_id="boot-3")
    assert "ENROLLMENT_TICKET_REPLAYED" in after.events and after.enrollment_state(0.0) == "NONE"
    assert after.authorize(cred_a, "bundle.install") == m.MODE_NORMAL


def test_crash_after_ticket_delete_fails_closed_without_arming():
    disk, state, cred_a = enrolled()
    insert_ticket(disk)
    with pytest.raises(m.Crash):
        boot(disk, state, boot_id="boot-2", crash_at="boot.after_ticket_delete")
    after = boot(disk, state, boot_id="boot-2")
    assert after.enrollment_state(0.0) == "NONE"
    assert after.authorize(cred_a, "bundle.install") == m.MODE_NORMAL


def test_crash_after_arm_keeps_the_window_within_the_same_boot():
    disk, state = m.Disk(), safety()
    ticket = insert_ticket(disk)
    with pytest.raises(m.Crash):
        boot(disk, state, crash_at="boot.after_arm")
    restarted = boot(disk, state)                              # service restart, same boot
    assert m.client_claim(restarted, ticket, 1.0)[0]["generation"] == 1


def test_crash_before_controller_commit_keeps_the_old_controller():
    disk, state, cred_a = enrolled()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2", crash_at="claim.before_controller_commit")
    view = no_boot_view(state)
    with pytest.raises(m.Crash):
        m.client_claim(ppu, ticket, 1.0)
    restarted = boot(disk, state, boot_id="boot-2")
    assert restarted.authorize(cred_a, "bundle.install") == m.MODE_NORMAL
    assert restarted.controller()["generation"] == 1
    assert m.client_claim(restarted, ticket, 2.0)[0]["generation"] == 2   # retry, fresh nonce
    assert no_boot_view(state) == view


@pytest.mark.parametrize("point", ["claim.after_controller_commit", "claim.after_high_water"])
def test_crash_after_commit_is_atomic_cutover_and_retrievable(point):
    disk, state, cred_a = enrolled()
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2", crash_at=point)
    cn = m.secrets.token_hex(16)
    with pytest.raises(m.Crash):
        m.client_claim(ppu, ticket, 1.0, controller_nonce=cn)
    restarted = boot(disk, state, boot_id="boot-2")
    assert restarted.controller_state() == m.MODE_NORMAL       # not FAULT if high-water lags
    with pytest.raises(m.SpecError) as revoked:
        restarted.authorize(cred_a, "status.read")
    assert revoked.value.code == "CONTROLLER_REVOKED"
    response, cred_b, _ = m.client_claim(restarted, ticket, 2.0, controller_nonce=cn)
    assert response["generation"] == 2
    assert restarted.authorize(cred_b, "bundle.install") == m.MODE_NORMAL


def test_crash_before_recovery_mode_commit_stays_recovery_only():
    disk, state, _a = enrolled()
    state.seals[2] = "marker"
    ticket = insert_ticket(disk)
    ppu = boot(disk, state, boot_id="boot-2")
    _r, cred, _ = m.client_claim(ppu, ticket, 1.0)
    ppu.recover_site(cred, 2, explicit_request=True)
    ppu.crash_at = "recovery.before_mode_commit"
    with pytest.raises(m.Crash):
        ppu.recovery_complete(cred, observed_device_id=DEVICE)
    restarted = boot(disk, state, boot_id="boot-2")
    assert restarted.controller_state() == m.MODE_RECOVERY_ONLY
    assert restarted.recovery_complete(cred, observed_device_id=DEVICE) == m.MODE_NORMAL


# --- specification document stays in lock-step with the model ---------------

def test_spec_document_lists_exactly_the_model_codes_states_and_crash_points():
    text = SPEC.read_text(encoding="utf-8")
    def section(title):
        match = re.search(r"^## " + re.escape(title) + r"\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        assert match, title
        return set(re.findall(r"`([A-Z][A-Z_]+|[a-z]+(?:\.[a-z_]+)+)`", match.group(1)))
    assert section("Error codes") == set(m.ERROR_CODES)
    assert section("Crash points") == set(m.CRASH_POINTS)
    states = section("States")
    assert set(m.CONTROLLER_STATES) <= states and set(m.ENROLLMENT_STATES) <= states
    ops = section("Operation classes")
    assert set(m.NORMAL_WRITES) | set(m.RECOVERY_ACTIONS) <= ops
    for constant in (m.SCHEMA, m.TICKET_SCHEMA, m.TICKET_FILE):
        assert constant in text
    for number in (str(m.ENROLLMENT_WINDOW_S), str(m.MAX_CLAIM_FAILURES), str(m.LEDGER_CAPACITY)):
        assert number in text
