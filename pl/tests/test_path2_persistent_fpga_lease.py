"""Persistent FPGA lease Host-only contracts — no device, Vivado or SSH."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_persistent_lease as lease
import plasma_path2_f1b_adapters as adapter
import plasma_path2_stage_orchestrator as stage

NOW = 100_000
SRC = "a" * 40
BIT = "b" * 64
BASE = "c" * 64
INTENT = "d" * 64
SERVICE = "e" * 64
UIO = "f" * 64
LOAD = "1" * 64
TEST = "2" * 64
RESTORE = "3" * 64


def intent(**updates):
    val = dict(lease_id="lease-123", target_id="z2-test",
               profile_id="f1b-site1-v1", source_sha=SRC,
               artifact_sha256=BIT, recovery_sha256=BASE,
               boot_id="fixed-boot-id", owner_id="trusted-operator",
               restore_intent_sha256=INTENT, services_sha256=SERVICE,
               uio_sha256=UIO, lease_seconds=120)
    val.update(updates)
    return val


def ledger(tmp_path):
    return lease.LeaseLedger(tmp_path / "z2-test.json")


def obs(image=BASE, when=NOW, **updates):
    data = dict(observed_at=when, target_id="z2-test",
                boot_id="fixed-boot-id", image_sha256=image,
                manager_state="operating", owner_evidence_sha256="4"*64,
                axi_admission="SEPARATELY_AUTHORIZED")
    data.update(updates)
    return data


def step(store, action, when, *, facts=None, evidence=None, **other):
    return store.advance(action, when, facts=facts, evidence=evidence,
                         expected_revision=store.snapshot()["revision"], **other)


def loaded(tmp_path):
    store = ledger(tmp_path)
    store.initialize(intent(), NOW)
    step(store, "claim_load", NOW+1, facts=obs(when=NOW+1))
    step(store, "confirm_load", NOW+2, facts=obs(BIT, NOW+2),
         evidence=dict(lease_id="lease-123", load_evidence_sha256=LOAD,
                       restore_intent_sha256=INTENT))
    return store


def held_request(**updates):
    val = dict(lease_id="lease-123", source_sha=SRC, profile_id="f1b-site1-v1",
               target_id="z2-test", artifact_sha256=BIT,
               load_evidence_sha256=LOAD)
    val.update(updates)
    return val


def test_intent_persisted_before_first_load_and_single_target_lock(tmp_path):
    store=ledger(tmp_path)
    result=store.initialize(intent(), NOW)
    assert result["status"] == "RESTORE_REQUIRED"
    assert result["load_attempts"] == 0 and result["restore_intent_sha256"] == INTENT
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert json.loads(store.path.read_text())["schema"] == lease.SCHEMA
    assert lease.LeaseLedger(store.path).snapshot() == result
    with pytest.raises(lease.LeaseDenied, match="TARGET_LEASE_ALREADY_EXISTS"):
        store.initialize(intent(lease_id="lease-other"), NOW)


def test_full_lifecycle_can_reenter_testing_without_reloading(tmp_path):
    store=loaded(tmp_path)
    assert store.snapshot()["load_attempts"] == 1
    for attempt in (0, 1):
        t=NOW + 3 + attempt*2
        lease.require_testing(store.snapshot(), held_request(), obs(BIT,t), t)
        step(store, "claim_test", t, facts=obs(BIT,t))
        record=dict(lease_id="lease-123", load_evidence_sha256=LOAD,
                    test_evidence_sha256=TEST,
                    observed=dict(lease.TEST_WORDS), read32=3, write32=0,
                    native_readonly=True)
        step(store, "confirm_test", t+1, facts=obs(BIT,t+1), evidence=record)
        assert store.snapshot()["status"] == "LOADED_AND_HELD"
    step(store,"claim_restore",NOW+7,facts=obs(BIT,NOW+7))
    final=step(store,"confirm_restore",NOW+8,facts=obs(BASE,NOW+8),
        evidence=dict(lease_id="lease-123",restore_evidence_sha256=RESTORE,
                      services_sha256=SERVICE,uio_sha256=UIO))
    assert final["status"] == "RESTORED_VERIFIED"
    assert final["load_attempts"] == 1
    assert final["test_attempts"] == 2
    assert final["restore_attempts"] == 1
    assert lease.LeaseLedger(store.path).snapshot() == final
    with pytest.raises(lease.LeaseDenied, match="LOADED_LEASE_NOT_ACTIVE"):
        lease.require_testing(final,held_request(),obs(BIT,NOW+9),NOW+9)


def test_no_duplicate_load_after_crash_or_restore(tmp_path):
    store=ledger(tmp_path)
    store.initialize(intent(), NOW)
    step(store,"claim_load",NOW+1,facts=obs(when=NOW+1))
    reentered=lease.LeaseLedger(store.path)
    with pytest.raises(lease.LeaseDenied,match="TRANSITION_NOT_AUTHORIZED"):
        step(reentered,"claim_load",NOW+2,facts=obs(when=NOW+2))
    assert store.snapshot()["load_attempts"] == 1
    step(reentered,"mark_unknown",NOW+45,evidence={"reason":"CRASH_BEFORE_LOAD_CONFIRM"})
    with pytest.raises(lease.LeaseDenied,match="TRANSITION_NOT_AUTHORIZED"):
        step(store,"claim_load",NOW+46,facts=obs(when=NOW+46))


@pytest.mark.parametrize("field,wrong",[
    ("source_sha","0"*40),("profile_id","wrong-profile"),
    ("target_id","another-target"),("artifact_sha256","0"*64),
    ("load_evidence_sha256","0"*64),("lease_id","other-lease")])
def test_no_test_reentry_on_wrong_provenance(tmp_path,field,wrong):
    store=loaded(tmp_path)
    with pytest.raises(lease.LeaseDenied,match="TESTING_PROVENANCE_MISMATCH"):
        lease.require_testing(store.snapshot(),held_request(**{field:wrong}),
                              obs(BIT,NOW+3),NOW+3)
    assert store.snapshot()["test_attempts"] == 0


@pytest.mark.parametrize("field,wrong,reason",[
    ("boot_id","new-boot","BOOT_OR_TARGET_CHANGED"),
    ("target_id","other-target","BOOT_OR_TARGET_CHANGED"),
    ("image_sha256",BASE,"CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED"),
    ("manager_state","unknown","CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED"),
    ("owner_evidence_sha256","missing","CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED"),
    ("axi_admission","UNPROVEN","CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED"),
    ("observed_at",NOW,"STALE_OBSERVATION_DENIED"),
])
def test_real_observation_needed_after_restart(tmp_path,field,wrong,reason):
    store=loaded(tmp_path)
    with pytest.raises(lease.LeaseDenied,match=reason):
        lease.require_testing(store.snapshot(),held_request(),
                              obs(BIT,NOW+3,**{field:wrong}),NOW+3)


@pytest.mark.parametrize("bad",[
    {"observed":{}},
    {"observed":{"0":0x4D534C50,"4":65536}},
    {"observed":{"0":0x4D534C50,"4":65536,"16384":True}},
    {"read32":2},
    {"read32":True},
    {"write32":1},
    {"native_readonly":False},
])
def test_test_evidence_never_fabricates_pass(tmp_path,bad):
    store=loaded(tmp_path)
    step(store,"claim_test",NOW+3,facts=obs(BIT,NOW+3))
    rec=dict(lease_id="lease-123",load_evidence_sha256=LOAD,
             test_evidence_sha256=TEST,observed=dict(lease.TEST_WORDS),
             read32=3,write32=0,native_readonly=True)
    rec.update(bad)
    with pytest.raises(lease.LeaseDenied,match="IDENTITY_THREE_READS_NOT_PROVEN"):
        step(store,"confirm_test",NOW+4,facts=obs(BIT,NOW+4),evidence=rec)
    assert store.snapshot()["status"] == "TEST_IN_FLIGHT"


def test_timeout_expiration_never_auto_restores_or_retries(tmp_path):
    store=loaded(tmp_path)
    with pytest.raises(lease.LeaseDenied,match="LEASE_EXPIRED_NO_AUTOMATIC_RESTORE"):
        step(store,"claim_test",NOW+121,facts=obs(BIT,NOW+121))
    assert store.snapshot()["status"] == "LOADED_AND_HELD"
    state=step(store,"mark_expired",NOW+121)
    assert state["status"] == "EXPIRED_REVIEW_REQUIRED"
    assert state["restore_attempts"] == 0
    with pytest.raises(lease.LeaseDenied,match="LOADED_LEASE_NOT_ACTIVE"):
        lease.require_testing(state,held_request(),obs(BIT,NOW+121),NOW+121)


def test_recovery_after_unreaped_or_timeout_is_manual(tmp_path):
    store=loaded(tmp_path)
    step(store,"claim_test",NOW+3,facts=obs(BIT,NOW+3),step_seconds=1)
    with pytest.raises(lease.LeaseDenied,match="IN_FLIGHT_TIMEOUT_NO_RETRY"):
        step(store,"confirm_test",NOW+5,facts=obs(BIT,NOW+5))
    record=step(store,"mark_unknown",NOW+6,
                evidence={"reason":"UNREAPED_CHILD_UNKNOWN_AXI"})
    assert record["status"] == "UNKNOWN_MANUAL_RECOVERY"
    with pytest.raises(lease.LeaseDenied,match="TRANSITION_NOT_AUTHORIZED"):
        step(store,"claim_restore",NOW+7,facts=obs(BIT,NOW+7))
    assert record["restore_attempts"] == 0


def test_restore_requires_original_bytes_and_original_system_state(tmp_path):
    store=loaded(tmp_path)
    step(store,"claim_restore",NOW+3,facts=obs(BIT,NOW+3))
    receipt=dict(lease_id="lease-123",restore_evidence_sha256=RESTORE,
                 services_sha256=SERVICE,uio_sha256=UIO)
    with pytest.raises(lease.LeaseDenied,match="CURRENT_FIRMWARE_OR_OWNER_NOT_VERIFIED"):
        step(store,"confirm_restore",NOW+4,facts=obs(BIT,NOW+4),evidence=receipt)
    with pytest.raises(lease.LeaseDenied,match="RESTORE_PROVENANCE_DENIED"):
        step(store,"confirm_restore",NOW+4,facts=obs(BASE,NOW+4),
             evidence={**receipt,"services_sha256":"0"*64})
    assert store.snapshot()["restore_attempts"] == 1
    assert store.snapshot()["status"] == "RESTORE_IN_FLIGHT"
    with pytest.raises(lease.LeaseDenied,match="TRANSITION_NOT_AUTHORIZED"):
        step(store,"claim_restore",NOW+5,facts=obs(BIT,NOW+5))


def test_stale_revision_refuses_concurrent_update(tmp_path):
    store=loaded(tmp_path)
    before=store.snapshot()
    step(store,"claim_test",NOW+3,facts=obs(BIT,NOW+3))
    with pytest.raises(lease.LeaseDenied,match="STALE_REVISION_DENIED"):
        store.advance("claim_restore",NOW+4,facts=obs(BIT,NOW+4),
                      expected_revision=before["revision"])


def test_rollback_or_implicit_boolean_timeout_denied(tmp_path):
    store=loaded(tmp_path)
    with pytest.raises(lease.LeaseDenied,match="CLOCK_ROLLBACK_DENIED"):
        step(store,"claim_test",NOW-1,facts=obs(BIT,NOW-1))
    with pytest.raises(lease.LeaseDenied,match="STEP_TIMEOUT_DENIED"):
        step(store,"claim_test",NOW+3,facts=obs(BIT,NOW+3),
             step_seconds=True)


def test_no_symlink_ledger_or_world_writable_parent(tmp_path):
    bad=tmp_path/"bad.json"
    bad.symlink_to(tmp_path/"missing.json")
    with pytest.raises(lease.LeaseDenied,match="TARGET_LEASE_ALREADY_EXISTS"):
        lease.LeaseLedger(bad).initialize(intent(),NOW)
    root=tmp_path/"unsafe"
    root.mkdir(mode=0o777)
    os.chmod(root,0o777)
    with pytest.raises(lease.LeaseDenied,match="LEDGER_DIRECTORY_UNTRUSTED"):
        lease.LeaseLedger(root/"state.json").initialize(intent(),NOW)


@pytest.mark.parametrize("field,value",[
    ("lease_seconds",0),("lease_seconds",901),("lease_seconds",True),
    ("artifact_sha256","not-a-hash"),("restore_intent_sha256","NOT_RUN"),
    ("lease_id","../wrong"),("source_sha","other")
])
def test_invalid_intent_never_creates_state_file(tmp_path,field,value):
    store=ledger(tmp_path)
    with pytest.raises(lease.LeaseDenied):
        store.initialize(intent(**{field:value}),NOW)
    assert not store.path.exists()


def test_guarded_existing_adapter_can_consult_persisted_lease(tmp_path):
    """Integration point uses actual merged adapter API, but only fake data."""
    store=loaded(tmp_path)
    events=[]
    rawload = {"stage":"download","status":"PASS","source_sha":SRC,
               "profile_id":"f1b-site1-v1", "target_id":"z2-test",
               "artifact_sha256":BIT,"lease_id":"lease-123",
               "load_evidence_sha256":LOAD, "evidence_sha256":"5"*64}
    def guarded_identity(ctx):
        now=NOW+3
        lease.require_testing(store.snapshot(),held_request(),obs(BIT,now),now)
        events.append("identity-callback")
        return {"result":"IDENTITY_PASS", "source_sha":SRC,
                "profile_id":"f1b-site1-v1", "target_id":"z2-test",
                "artifact_sha256":BIT, "lease_id":"lease-123",
                "load_evidence_sha256":LOAD,"test_evidence_sha256":TEST,
                "observed":dict(adapter.f1b.IDENTITY),
                "read32_count":3,"write32_count":0,
                "native_readonly":True,"image_state":"LOADED_AND_HELD"}
    handlers=adapter.bind_f1b_adapters(identity_test=guarded_identity)
    out=stage.run({"stage":"test","source_sha":SRC,
                   "profile_id":"f1b-site1-v1","target_id":"z2-test",
                   "artifact_sha256":BIT,"load_receipt":rawload},
                  adapters=handlers)
    assert events==["identity-callback"]
    assert out["completed"]==["test"]
    assert out["status"]=="RECEIPTS_VALIDATED"
    assert store.snapshot()["status"]=="LOADED_AND_HELD"
    # This proves eligibility-check integration only. The test is a HOST MOCK.


def test_module_is_inert_without_hardware_entrypoint():
    source=(ROOT/"scripts"/"plasma_path2_persistent_lease.py").read_text()
    assert "if __name__" not in source
    assert "import subprocess" not in source
    assert "import paramiko" not in source
    assert "manager_write(" not in source
    assert "OWNER_DEV_RISK_ACK" not in source
