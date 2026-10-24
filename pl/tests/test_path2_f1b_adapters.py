"""Path 2 F1-B adapter integration Gate 1: strictly Host-only Mock callbacks."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_f1b_adapters as a
import plasma_path2_stage_orchestrator as stages

SOURCE = "a" * 40
BIT = "b" * 64
HWH = "c" * 64
EVIDENCE = "d" * 64
LOAD = "e" * 64
INTENT = "f" * 64
TEST = "1" * 64
TARGET = "z2-development"
LEASE = "lease-01"


def request(stage="build", **kwargs):
    data = {"stage": stage, "source_sha": SOURCE,
            "profile_id": a.PROFILE_ID, "target_id": TARGET}
    if stage != "build":
        data["artifact_sha256"] = BIT
    data.update(kwargs)
    return data


def build_raw():
    # The actual existing Vivado host-build driver returns this status until
    # an independently approved qualification step; it is not immediate PASS.
    return {"status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
            "source_sha": SOURCE,
            "execution_capability": "vivado-host-build",
            "bit_sha256": BIT, "hwh_sha256": HWH,
            "report_sha256": {"timing_summary.rpt": EVIDENCE},
            "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN", "m1": "NO_GO"}


def qualify(raw):
    return {"decision": "APPROVED", "source_sha": SOURCE,
            "bit_sha256": raw["bit_sha256"], "hwh_sha256": raw["hwh_sha256"],
            "qualification_evidence_sha256": EVIDENCE}


def download_raw(ctx):
    return {"result": "LOADED", "source_sha": SOURCE,
            "profile_id": a.PROFILE_ID, "target_id": TARGET,
            "artifact_sha256": ctx["build_receipt"]["artifact_sha256"],
            "lease_id": LEASE, "boot_id": "boot-123",
            "load_evidence_sha256": LOAD,
            "restore_intent_sha256": INTENT,
            "manager_state": "operating", "image_state": "LOADED_AND_HELD"}


def identity_raw(ctx):
    load = ctx["load_receipt"]
    return {"result": "IDENTITY_PASS", "source_sha": SOURCE,
            "profile_id": a.PROFILE_ID, "target_id": TARGET,
            "artifact_sha256": load["artifact_sha256"],
            "lease_id": load["lease_id"],
            "load_evidence_sha256": load["load_evidence_sha256"],
            "test_evidence_sha256": TEST,
            "observed": dict(a.f1b.IDENTITY), "read32_count": 3,
            "write32_count": 0, "native_readonly": True,
            "image_state": "LOADED_AND_HELD"}


def adapters(events, *, build_mutate=None, download_mutate=None, test_mutate=None):
    def build(ctx):
        events.append("build")
        raw = build_raw()
        return build_mutate(raw) if build_mutate else raw

    def download(ctx):
        events.append("download")
        raw = download_raw(ctx)
        return download_mutate(raw) if download_mutate else raw

    def test(ctx):
        events.append("test")
        raw = identity_raw(ctx)
        return test_mutate(raw) if test_mutate else raw

    return a.bind_f1b_adapters(
        build_driver=build, build_qualification=qualify,
        held_download=download, identity_test=test)


def receipts():
    events = []
    handlers = adapters(events)
    build = handlers["build"](request())
    download = handlers["download"]({**request(), "stage": "download",
                                      "build_receipt": build})
    assert events == ["build", "download"]
    return build, download


@pytest.mark.parametrize("initial,options,expected", [
    ("build", {}, ["build"]),
    ("build", {"auto_download_after_build_success": True}, ["build", "download"]),
    ("build", {"auto_test_after_download_success": True}, ["build"]),
    ("build", {"auto_download_after_build_success": True,
               "auto_test_after_download_success": True},
     ["build", "download", "test"]),
    ("download", {}, ["download"]),
    ("download", {"auto_test_after_download_success": True},
     ["download", "test"]),
    ("test", {}, ["test"]),
])
def test_independent_stages_reuse_real_interfaces_only_as_mock(initial, options,
                                                                expected):
    events = []
    handlers = adapters(events)
    b, d = receipts()
    ctx = request(initial, options=options)
    if initial == "download":
        ctx["build_receipt"] = b
    if initial == "test":
        ctx["load_receipt"] = d
    result = stages.run(ctx, adapters=handlers)
    assert result["completed"] == expected
    assert events == expected
    assert result["status"] == "RECEIPTS_VALIDATED"
    assert result["scope"] == "ADAPTER_RECEIPTS_ONLY"
    assert result["options"]["auto_download_after_build_success"] is options.get(
        "auto_download_after_build_success", False)
    assert result["options"]["auto_test_after_download_success"] is options.get(
        "auto_test_after_download_success", False)


def test_empty_ports_fail_closed():
    handlers = a.bind_f1b_adapters()
    with pytest.raises(stages.StageDenied, match="BUILD_BACKEND_NOT_AUTHORIZED"):
        stages.run(request(), adapters=handlers)
    b, d = receipts()
    with pytest.raises(stages.StageDenied, match="DOWNLOAD_BACKEND_NOT_AUTHORIZED"):
        stages.run(request("download", build_receipt=b), adapters=handlers)
    with pytest.raises(stages.StageDenied, match="TEST_BACKEND_NOT_AUTHORIZED"):
        stages.run(request("test", load_receipt=d), adapters=handlers)


@pytest.mark.parametrize("field,bad", [
    ("status", "PASS"), ("source_sha", "f"*40),
    ("physical_load", "PASS"), ("z2_hil", "PASS"),
    ("m1", "PASS"), ("bit_sha256", "not-a-hash"),
    ("hwh_sha256", "not-a-hash"),
])
def test_existing_vivado_build_must_be_qualified(field, bad):
    events=[]
    def mutate(data):
        return {**data, field: bad}
    with pytest.raises(stages.StageDenied, match="VIVADO_BUILD_EVIDENCE_NOT_QUALIFIED"):
        stages.run(request(), adapters=adapters(events, build_mutate=mutate))
    assert events == ["build"]


def test_qualification_not_automatic_pass():
    events=[]
    handlers = a.bind_f1b_adapters(build_driver=lambda c: build_raw(),
          build_qualification=lambda raw: {**qualify(raw), "decision": "PENDING"})
    with pytest.raises(stages.StageDenied, match="BUILD_QUALIFICATION_REQUIRED"):
        stages.run(request(options={"auto_download_after_build_success":True}),
                   adapters=handlers)
    assert events == []


@pytest.mark.parametrize("field,bad", [
    ("result", "RESTORED"), ("image_state", "RESTORED_BASE"),
    ("artifact_sha256", "f"*64), ("manager_state", "unknown"),
    ("source_sha", "f"*40), ("target_id", "other-target"),
    ("lease_id", ""), ("load_evidence_sha256", "NOT_RUN"),
    ("restore_intent_sha256", "NOT_RUN"),
])
def test_download_requires_persistent_held_image(field, bad):
    b, _ = receipts()
    events=[]
    def mutate(raw):
        return {**raw, field: bad}
    with pytest.raises(stages.StageDenied, match="LOADED_IMAGE_NOT_PROVEN_HELD"):
        stages.run(request("download", build_receipt=b,
                           options={"auto_test_after_download_success":True}),
                   adapters=adapters(events, download_mutate=mutate))
    assert events == ["download"]


@pytest.mark.parametrize("field,bad", [
    ("result", "NOT_RUN"), ("image_state", "RESTORED_BASE"),
    ("write32_count", 1), ("read32_count", 2),
    ("native_readonly", False), ("artifact_sha256", "f"*64),
    ("lease_id", "other-lease"), ("load_evidence_sha256", "f"*64),
    ("test_evidence_sha256", "not-a-sha"),
    ("observed", {}), ("observed", {0: 0x4D534C50, 4: 0x00010000}),
    ("observed", {0: 0x4D534C50, 4: 0x00010000, 0x4000: True}),
])
def test_test_requires_three_real_equal_identity_words(field,bad):
    _, d=receipts()
    events=[]
    def mutate(raw):
        return {**raw, field: bad}
    with pytest.raises(stages.StageDenied, match="IDENTITY_NOT_PROVEN_FROM_LOADED_IMAGE"):
        stages.run(request("test",load_receipt=d),
                   adapters=adapters(events,test_mutate=mutate))
    assert events==["test"]


def test_error_download_blocks_test_no_unsafe_retry():
    events=[]
    handlers=adapters(events,download_mutate=lambda raw: {
        **raw, "image_state":"RESTORED_BASE"})
    with pytest.raises(stages.StageDenied,match="LOADED_IMAGE_NOT_PROVEN_HELD"):
        stages.run(request(options={"auto_download_after_build_success":True,
                                    "auto_test_after_download_success":True}),
                   adapters=handlers)
    assert events==["build","download"]


def test_stage_binding_does_not_mutate_request():
    original=request(options={"auto_download_after_build_success":True})
    saved=copy.deepcopy(original)
    result=stages.run(original, adapters=adapters([]))
    assert original == saved
    assert result["completed"] == ["build","download"]


def test_direct_existing_vivado_bridge_requires_authorized_approval():
    from pathlib import Path
    with patch.object(a.vivado, "run", return_value=build_raw()) as build:
        for approval in ({}, {"execution_path": "path2-cli",
                             "execution_capability": "vivado-host-build",
                             "pr_number": 0, "pinned_sha": SOURCE,
                             "trusted_sha": "f"*40}):
            with pytest.raises(stages.StageDenied,match="HOST_BUILD_TRUSTED_APPROVAL_REQUIRED"):
                a.existing_host_build(task={}, workspace=Path("/tmp"),
                                      approval=approval, evidence_dir=Path("/tmp"))
        build.assert_not_called()
        approval = {"execution_path": "path2-cli",
                    "execution_capability": "vivado-host-build",
                    "pr_number": 0, "pinned_sha": SOURCE, "trusted_sha": SOURCE}
        observed=a.existing_host_build(task={"name":"fixed"},
                            workspace=Path("/tmp"), approval=approval,
                            evidence_dir=Path("/tmp"))
        assert observed["status"] == "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED"
        build.assert_called_once()


def test_f1b_existing_identity_callback_integration_without_hardware(tmp_path):
    events=[]
    def fake_factory(path):
        def fake_callback(state):
            events.append("three-read-callback")
            path.write_text(json.dumps({"observed": {str(k): v
                for k,v in a.f1b.IDENTITY.items()}}))
            state["test"]="PASS"
        return fake_callback
    evidence=a.f1b_identity_adapter(output=tmp_path/"identity.json",
                                   callback_factory=fake_factory)
    assert evidence["observed"] == {str(k): v for k,v in a.f1b.IDENTITY.items()}
    assert events == ["three-read-callback"]


def test_noop_identity_callback_not_pass(tmp_path):
    with pytest.raises(stages.StageDenied, match="F1B_CALLBACK_DID_NOT_PASS"):
        a.f1b_identity_adapter(output=tmp_path/"missing.json",
                              callback_factory=lambda p: (lambda state: None))


def test_real_one_shot_restores_and_is_not_independent_download():
    from pl.hil.swd04 import one_shot
    import inspect
    code=inspect.getsource(one_shot.run_live)
    assert "restore=restore" in code
    assert "verify_restoration=verify_restoration" in code
    assert "LOADED_AND_HELD" not in code
    # The implementation may reuse one_shot primitives, but it MUST NOT
    # call run_live as the independent Download adapter.
    bridge=(ROOT/"scripts"/"plasma_path2_f1b_adapters.py").read_text()
    assert "one_shot.run_live(" not in bridge.split("def bind_f1b_adapters(",1)[1]


def test_adapter_registration_has_no_live_or_cli_route():
    import inspect
    src=inspect.getsource(a)
    assert "if __name__" not in src
    assert "subprocess.run(" not in src
    assert "manager_write(" not in src
    assert "OWNER_DEV_RISK_ACK" not in src
