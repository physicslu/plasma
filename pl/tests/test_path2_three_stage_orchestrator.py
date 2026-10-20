"""Host-only three-stage Path 2 contract tests; all adapters are inert fakes."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import plasma_path2_stage_orchestrator as stage

S = "a" * 40
H = "b" * 64
E = "c" * 64
L = "d" * 64
T = "e" * 64


def req(initial="build", **kwargs):
    if initial != "build":
        kwargs.setdefault("artifact_sha256", H)
    return dict(stage=initial, source_sha=S, profile_id="f1b-site1-v1",
                target_id="ppu-z2-lab", **kwargs)


def fake_adapters(events):
    def build(ctx):
        events.append("build")
        return dict(stage="build", status="PASS", source_sha=S,
                    profile_id=ctx["profile_id"],
                    artifact_sha256=H, evidence_sha256=E)
    def download(ctx):
        events.append("download")
        return dict(stage="download", status="PASS", source_sha=S,
                    profile_id=ctx["profile_id"], target_id=ctx["target_id"],
                    artifact_sha256=ctx["build_receipt"]["artifact_sha256"],
                    lease_id="single-lease-01", load_evidence_sha256=L,
                    evidence_sha256=E)
    def test(ctx):
        events.append("test")
        return dict(stage="test", status="PASS", source_sha=S,
                    profile_id=ctx["profile_id"], target_id=ctx["target_id"],
                    artifact_sha256=ctx["load_receipt"]["artifact_sha256"],
                    lease_id=ctx["load_receipt"]["lease_id"],
                    load_evidence_sha256=ctx["load_receipt"]["load_evidence_sha256"],
                    test_evidence_sha256=T, evidence_sha256=E)
    return dict(build=build, download=download, test=test)


def prior(events=None):
    handlers=fake_adapters([] if events is None else events)
    build=handlers["build"](req())
    download=handlers["download"]({**req(), "build_receipt": build})
    return build, download


@pytest.mark.parametrize("initial,options,expected", [
    ("build", {}, ["build"]),
    ("build", {"auto_download_after_build_success": False,
               "auto_test_after_download_success": True}, ["build"]),
    ("build", {"auto_download_after_build_success": True}, ["build","download"]),
    ("build", {"auto_download_after_build_success": True,
               "auto_test_after_download_success": True}, ["build","download","test"]),
    ("download", {}, ["download"]),
    ("download", {"auto_test_after_download_success": True}, ["download","test"]),
    ("test", {}, ["test"]),
])
def test_independent_and_optional_transitions(initial, options, expected):
    events=[]
    inputs=req(initial, options=options)
    b, l=prior()
    if initial=="download":
        inputs["build_receipt"]=b
    if initial=="test":
        inputs["load_receipt"]=l
    result=stage.run(inputs, adapters=fake_adapters(events))
    assert events==expected
    assert result["completed"]==expected
    assert result["status"]=="RECEIPTS_VALIDATED"
    assert len(result["transitions"])==len(expected)-1
    assert all(t["decision"]=="EXPLICIT_OPTION_TRUE" for t in result["transitions"])
    assert result["options"]["auto_download_after_build_success"] is options.get(
        "auto_download_after_build_success", False)
    assert result["options"]["auto_test_after_download_success"] is options.get(
        "auto_test_after_download_success", False)


@pytest.mark.parametrize("option", ["true", 1, None, "yes", []])
def test_no_truthy_automation_flag(option):
    with pytest.raises(stage.StageDenied,match="AUTOMATION_OPTIONS_DENIED"):
        stage.run(req(options={"auto_download_after_build_success":option}),
                  adapters=fake_adapters([]))


def test_unknown_option_rejected_without_execution():
    events=[]
    with pytest.raises(stage.StageDenied):
        stage.run(req(options={"auto_load_unsafe": True}),
                  adapters=fake_adapters(events))
    assert events==[]


def test_download_and_test_require_prior_receipts():
    for trigger in ("download","test"):
        with pytest.raises(stage.StageDenied,match="REQUEST_FIELDS_DENIED"):
            stage.run(req(trigger),adapters=fake_adapters([]))


def test_independent_download_requires_matching_expected_image_hash():
    b,_=prior()
    events=[]
    with pytest.raises(stage.StageDenied, match="PINNED_ARTIFACT_MISMATCH"):
        stage.run(req("download",build_receipt=b,artifact_sha256="f"*64),
                  adapters=fake_adapters(events))
    assert events==[]


def test_no_replay_build_on_download_or_test():
    for trigger in ("download","test"):
        events=[]
        b,l=prior()
        result=stage.run(req(trigger,**({"build_receipt":b} if trigger=="download"
                                         else {"load_receipt":l})),
                         adapters=fake_adapters(events))
        assert events==[trigger]
        assert result["initial_stage"]==trigger


def test_handler_preflight_is_atomic():
    events=[]
    with pytest.raises(stage.StageDenied,match="REVIEWED_STAGE_ADAPTER_REQUIRED"):
        stage.run(req(options={"auto_download_after_build_success":True}),
                  adapters={"build":fake_adapters(events)["build"]})
    assert events==[]


@pytest.mark.parametrize("field,value",[
    ("source_sha", "f"*40),("profile_id","different-profile"),
    ("artifact_sha256","f"*64),("status","NO_GO")
])
def test_wrong_build_provenance_denied_before_download(field,value):
    b,_=prior()
    b[field]=value
    events=[]
    with pytest.raises(stage.StageDenied):
        stage.run(req("download",build_receipt=b),adapters=fake_adapters(events))
    assert events==[]


@pytest.mark.parametrize("field,value",[
    ("target_id","other-site"),("source_sha","f"*40),("profile_id","other-profile"),
    ("load_evidence_sha256","missing"),("lease_id","not valid lease"),
])
def test_wrong_load_provenance_denied_before_testing(field,value):
    _,l=prior()
    l[field]=value
    events=[]
    with pytest.raises(stage.StageDenied):
        stage.run(req("test",load_receipt=l),adapters=fake_adapters(events))
    assert events==[]


def test_no_go_blocks_next_stage_and_no_automatic_retry():
    events=[]
    handlers=fake_adapters(events)
    def denied(ctx):
        events.append("download")
        return {"stage":"download","status":"NO_GO","reason":"HARDWARE_LEASE_BUSY"}
    handlers["download"]=denied
    result=stage.run(req(options={"auto_download_after_build_success":True,
                                  "auto_test_after_download_success":True}),
                     adapters=handlers)
    assert events==["build","download"]
    assert result["status"]=="NO_GO"
    assert result["failed_stage"]=="download"
    assert "test" not in result["receipts"]
    assert result["transitions"]==[{"from":"build","to":"download",
                                     "decision":"EXPLICIT_OPTION_TRUE"}]


def test_direct_test_uses_real_load_receipt_not_fabricated_build():
    events=[]
    _, load=prior()
    def check(ctx):
        assert "load_receipt" in ctx
        assert "build_receipt" not in ctx
        return fake_adapters(events)["test"](ctx)
    result=stage.run(req("test",load_receipt=load),adapters={"test":check})
    assert events==["test"]
    assert result["completed"]==["test"]


def test_bad_test_callback_cannot_synthesize_pass():
    events=[]
    b,l=prior()
    handlers=fake_adapters(events)
    handlers["test"]=lambda ctx: {"stage":"test","status":"PASS"}
    with pytest.raises(stage.StageDenied,match="STAGE_RECEIPT_FIELDS_DENIED"):
        stage.run(req("test",load_receipt=l),adapters=handlers)


def test_bad_receipt_or_exception_never_triggers_following_stage():
    events=[]
    handlers=fake_adapters(events)
    def failed(ctx):
        events.append("build")
        raise RuntimeError("build failed")
    handlers["build"]=failed
    with pytest.raises(RuntimeError):
        stage.run(req(options={"auto_download_after_build_success":True}),
                  adapters=handlers)
    assert events==["build"]


def test_adapter_not_called_with_mutable_original_request():
    events=[]
    original=req(options={"auto_download_after_build_success":False})
    saved=copy.deepcopy(original)
    handler=fake_adapters(events)
    def malicious(ctx):
        ctx["source_sha"]="f"*40
        return handler["build"](req())
    result=stage.run(original, adapters={"build":malicious})
    assert original==saved
    assert result["completed"]==["build"]


def test_explicit_boolean_gates_not_a_deployment_permission():
    source=(Path(__file__).resolve().parents[2]/"scripts"/
            "plasma_path2_stage_orchestrator.py").read_text()
    assert "import subprocess" not in source
    assert "import paramiko" not in source and "import asyncssh" not in source
    assert "fpga_manager" not in source.lower()
    assert "OWNER_DEV_RISK_ACK" not in source
