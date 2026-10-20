"""F1-B Path 2 adapter bindings, Gate 1 contract only (not hardware authority).

Reuses existing Vivado host-build.run, F1-B HardwareProfile and the
one_shot/F1-B TestCallback *interface*. Hardware closures are injected by a
separately authorized runtime. No privileged transport, CLI, or automatic
hardware execution is registered here.

Important: one_shot.run_live restores base.bin as part of its one-shot
transaction. It CANNOT be used as the persistent Download-only stage.
The future Download backend must independently prove a held/leased image.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import hashlib
import json
import re

import plasma_path2_stage_orchestrator as stages
import plasma_vivado_host_build as vivado
from pl.hil import f1b
from pl.hil.swd04 import one_shot

PROFILE_ID = "f1b-site1-v1"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise stages.StageDenied(code)


def sha_ok(value: object) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def exact(raw: object, keys: set[str], code: str) -> dict:
    require(type(raw) is dict and set(raw) == keys, code)
    return raw


def adapter_hash(raw: dict) -> str:
    """Canonical hash of validated HOST receipt, not hardware attestation."""
    return hashlib.sha256(json.dumps(
        raw, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def existing_host_build(*, task: dict, workspace: Path, approval: dict,
                        evidence_dir: Path, executor=None) -> dict:
    """Thin, explicit call of the EXISTING Vivado engine, never a new builder.

    Never called by importing this module. Gate 1 tests inject a fake driver,
    not this function. Only a future trusted Dispatcher may invoke it.
    """
    require(type(approval) is dict and
            approval.get("execution_path") == "path2-cli" and
            approval.get("execution_capability") == "vivado-host-build" and
            type(approval.get("pr_number")) is int and
            type(approval.get("pinned_sha")) is str and
            stages._sha(approval["pinned_sha"], 40) and
            type(approval.get("trusted_sha")) is str and
            stages._sha(approval["trusted_sha"], 40) and
            ((approval["pr_number"] == 0 and
              approval["pinned_sha"] == approval["trusted_sha"]) or
             (approval["pr_number"] > 0 and
              approval["pinned_sha"] != approval["trusted_sha"])),
            "HOST_BUILD_TRUSTED_APPROVAL_REQUIRED")
    arguments = dict(task=task, workspace=workspace, approval=approval,
                     evidence_dir=evidence_dir)
    if executor is not None:
        arguments["executor"] = executor
    return vivado.run(**arguments)


def bind_f1b_adapters(
    *, build_driver: Callable[[dict], dict] | None = None,
    build_qualification: Callable[[dict], dict] | None = None,
    held_download: Callable[[dict], dict] | None = None,
    identity_test: Callable[[dict], dict] | None = None,
) -> Mapping[str, Callable[[dict], dict]]:
    """Construct stage callables; all external authority is explicit/injected.

    Build driver: the existing reviewed Vivado HOST build, with an independent
    qualification gate. Download: an independently reviewed *persistent* load
    with lease and durable recovery intent. Test: existing f1b.identity_callback
    / f1b.read_identity driven by an approved backend (not a no-op).
    No real backend is registered at Gate 1.
    """
    profile = f1b.PROFILE
    require(profile.apertures == (("identity", 0x40000000, 0x10000),) and
            dict(profile.identity_words) == f1b.IDENTITY,
            "F1B_PROFILE_MISMATCH")

    def common(ctx: dict, stage: str) -> None:
        require(ctx.get("stage") == stage and
                ctx.get("profile_id") == PROFILE_ID,
                "STAGE_OR_PROFILE_DENIED")

    def build(ctx: dict) -> dict:
        common(ctx, "build")
        require(callable(build_driver) and callable(build_qualification),
                "BUILD_BACKEND_NOT_AUTHORIZED")
        raw = build_driver(dict(ctx))
        require(type(raw) is dict and
                raw.get("status") == "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED" and
                raw.get("source_sha") == ctx["source_sha"] and
                raw.get("execution_capability") == "vivado-host-build" and
                raw.get("physical_load") == "NOT_RUN" and
                raw.get("z2_hil") == "NOT_RUN" and raw.get("m1") == "NO_GO" and
                sha_ok(raw.get("bit_sha256")) and
                sha_ok(raw.get("hwh_sha256")) and
                type(raw.get("report_sha256")) is dict and
                bool(raw["report_sha256"]) and
                all(sha_ok(x) for x in raw["report_sha256"].values()),
                "VIVADO_BUILD_EVIDENCE_NOT_QUALIFIED")
        decision = build_qualification(dict(raw))
        exact(decision, {"decision", "source_sha", "bit_sha256", "hwh_sha256",
                         "qualification_evidence_sha256"}, "BUILD_QUALIFICATION_FIELDS")
        require(decision["decision"] == "APPROVED" and
                decision["source_sha"] == ctx["source_sha"] and
                decision["bit_sha256"] == raw["bit_sha256"] and
                decision["hwh_sha256"] == raw["hwh_sha256"] and
                sha_ok(decision["qualification_evidence_sha256"]),
                "BUILD_QUALIFICATION_REQUIRED")
        # Qualification is an injected trusted boundary; host-only tests use
        # mock decisions, which are never proof of physical/programming PASS.
        return dict(stage="build", status="PASS",
                    source_sha=ctx["source_sha"], profile_id=ctx["profile_id"],
                    artifact_sha256=raw["bit_sha256"],
                    evidence_sha256=decision["qualification_evidence_sha256"])

    def download(ctx: dict) -> dict:
        common(ctx, "download")
        require(callable(held_download), "DOWNLOAD_BACKEND_NOT_AUTHORIZED")
        build_receipt = ctx["build_receipt"]
        expected = build_receipt["artifact_sha256"]
        raw = held_download(dict(ctx))
        # A historical one-shot which restored base.bin must never qualify.
        exact(raw, {"result", "source_sha", "profile_id", "target_id",
                    "artifact_sha256", "lease_id", "boot_id",
                    "load_evidence_sha256", "restore_intent_sha256",
                    "manager_state", "image_state"},
              "DOWNLOAD_EVIDENCE_FIELDS_DENIED")
        require(raw["result"] == "LOADED" and
                raw["source_sha"] == ctx["source_sha"] and
                raw["profile_id"] == ctx["profile_id"] and
                raw["target_id"] == ctx["target_id"] and
                raw["artifact_sha256"] == expected and
                raw["manager_state"] == "operating" and
                raw["image_state"] == "LOADED_AND_HELD" and
                type(raw["lease_id"]) is str and ID.fullmatch(raw["lease_id"]) and
                type(raw["boot_id"]) is str and bool(raw["boot_id"]) and
                sha_ok(raw["load_evidence_sha256"]) and
                sha_ok(raw["restore_intent_sha256"]),
                "LOADED_IMAGE_NOT_PROVEN_HELD")
        return dict(stage="download", status="PASS",
                    source_sha=ctx["source_sha"], profile_id=ctx["profile_id"],
                    artifact_sha256=expected, target_id=ctx["target_id"],
                    lease_id=raw["lease_id"],
                    load_evidence_sha256=raw["load_evidence_sha256"],
                    evidence_sha256=adapter_hash(raw))

    def test(ctx: dict) -> dict:
        common(ctx, "test")
        require(callable(identity_test), "TEST_BACKEND_NOT_AUTHORIZED")
        load = ctx["load_receipt"]
        raw = identity_test(dict(ctx))
        exact(raw, {"result", "source_sha", "profile_id", "target_id",
                    "artifact_sha256", "lease_id", "load_evidence_sha256",
                    "test_evidence_sha256", "observed",
                    "read32_count", "write32_count",
                    "native_readonly", "image_state"}, "TEST_EVIDENCE_FIELDS_DENIED")
        require(raw["result"] == "IDENTITY_PASS" and
                raw["source_sha"] == ctx["source_sha"] and
                raw["profile_id"] == ctx["profile_id"] and
                raw["target_id"] == ctx["target_id"] and
                raw["artifact_sha256"] == load["artifact_sha256"] and
                raw["lease_id"] == load["lease_id"] and
                raw["load_evidence_sha256"] == load["load_evidence_sha256"] and
                sha_ok(raw["test_evidence_sha256"]) and
                raw["native_readonly"] is True and
                raw["image_state"] == "LOADED_AND_HELD" and
                type(raw["read32_count"]) is int and
                raw["read32_count"] == 3 and
                type(raw["write32_count"]) is int and
                raw["write32_count"] == 0 and
                type(raw["observed"]) is dict and
                set(raw["observed"]) == set(f1b.IDENTITY) and
                all(type(value) is int and value == f1b.IDENTITY[offset]
                    for offset, value in raw["observed"].items()),
                "IDENTITY_NOT_PROVEN_FROM_LOADED_IMAGE")
        return dict(stage="test", status="PASS", source_sha=ctx["source_sha"],
                    profile_id=ctx["profile_id"],
                    artifact_sha256=load["artifact_sha256"],
                    target_id=ctx["target_id"], lease_id=load["lease_id"],
                    load_evidence_sha256=load["load_evidence_sha256"],
                    test_evidence_sha256=raw["test_evidence_sha256"],
                    evidence_sha256=adapter_hash({
                        **raw, "observed": {str(k): v for k, v in raw["observed"].items()}}))

    return {"build": build, "download": download, "test": test}


def f1b_identity_adapter(*, output: Path, callback_factory=None) -> dict:
    """Target-only adapter THUNK for the already-reviewed F1-B callback.

    Requires a separate trusted caller. This method has no CLI entrypoint.
    A result file written by the actual native 3-read callback is required.
    It does not perform FPGA Load or Restore itself, nor assert lease safety.
    """
    factory = f1b.identity_callback if callback_factory is None else callback_factory
    state = {"test": "NOT_RUN"}
    factory(output)(state)
    require(state.get("test") == "PASS", "F1B_CALLBACK_DID_NOT_PASS")
    data = json.loads(output.read_text(encoding="utf-8"))
    require(type(data) is dict and type(data.get("observed")) is dict and
            data["observed"] == {str(k): v for k, v in f1b.IDENTITY.items()},
            "F1B_CALLBACK_READBACK_MISMATCH")
    return data


def gate1_host_only_contract(request: dict, *, adapters: Mapping[str, Callable]) -> dict:
    """No adapter discovery, no direct hardware capability or CLI."""
    return stages.run(request, adapters=adapters)
