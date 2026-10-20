"""Path 2 three-stage coordinator: injectable existing adapters, never hardware authority.

Host-only Gate 1: no SSH, sudo, Vivado, FPGA Manager, network or subprocess.
The trusted Development Dispatcher must authorize each execution *before*
supplying adapter callables. This module cannot activate a hardware route.
"""
from __future__ import annotations

from copy import deepcopy
import re
from collections.abc import Callable, Mapping

STAGES = ("build", "download", "test")
FLAGS = ("auto_download_after_build_success", "auto_test_after_download_success")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
REASON = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z")

class StageDenied(ValueError):
    """A stage receipt or explicit option failed closed."""


def require(test: bool, code: str) -> None:
    if not test:
        raise StageDenied(code)


def _sha(value: object, width: int) -> bool:
    return (type(value) is str and
            (SHA40 if width == 40 else SHA256).fullmatch(value) is not None)


def _fields(value: object, required: set[str], code: str) -> dict:
    require(type(value) is dict and set(value) == required, code)
    return value


def _validate_receipt(stage: str, value: object, context: dict) -> dict:
    base = {"stage", "status", "source_sha", "profile_id",
            "artifact_sha256", "evidence_sha256"}
    if stage == "download":
        base |= {"target_id", "lease_id", "load_evidence_sha256"}
    elif stage == "test":
        base |= {"target_id", "lease_id", "load_evidence_sha256",
                 "test_evidence_sha256"}
    r = _fields(value, base, "STAGE_RECEIPT_FIELDS_DENIED")
    require(r["status"] == "PASS" and r["stage"] == stage,
            "STAGE_RECEIPT_STATUS_DENIED")
    require(r["source_sha"] == context["source_sha"] and
            r["profile_id"] == context["profile_id"], "SOURCE_OR_PROFILE_MISMATCH")
    require(_sha(r["artifact_sha256"], 64) and
            _sha(r["evidence_sha256"], 64), "RECEIPT_HASH_DENIED")
    if stage != "build":
        require(r["artifact_sha256"] == context["build_receipt"]["artifact_sha256"],
                "ARTIFACT_PROVENANCE_MISMATCH")
        require(r["target_id"] == context["target_id"] and
                type(r["lease_id"]) is str and
                IDENT.fullmatch(r["lease_id"]) is not None,
                "TARGET_OR_LEASE_MISMATCH")
    if stage == "test":
        load = context["load_receipt"]
        require(r["lease_id"] == load["lease_id"] and
                r["load_evidence_sha256"] == load["load_evidence_sha256"] and
                _sha(r["test_evidence_sha256"], 64),
                "TEST_LOAD_PROVENANCE_MISMATCH")
    if stage == "download":
        require(_sha(r["load_evidence_sha256"], 64),
                "LOAD_EVIDENCE_MISSING")
    return deepcopy(r)


def validate_request(request: object) -> dict:
    require(type(request) is dict, "REQUEST_OBJECT_REQUIRED")
    stage = request.get("stage")
    require(type(stage) is str and stage in STAGES, "STAGE_NOT_SUPPORTED")
    required = {"stage", "source_sha", "profile_id", "target_id"}
    allowed = required | {"options"}
    if stage == "download":
        required |= {"build_receipt"}
        allowed |= {"build_receipt"}
    if stage == "test":
        required |= {"load_receipt"}
        allowed |= {"load_receipt"}
    require(required <= set(request) <= allowed, "REQUEST_FIELDS_DENIED")
    require(_sha(request["source_sha"], 40), "SOURCE_SHA_DENIED")
    for key in ("profile_id", "target_id"):
        require(type(request[key]) is str and
                IDENT.fullmatch(request[key]) is not None,
                "IDENTIFIER_DENIED")
    opts = request.get("options", {})
    require(type(opts) is dict and set(opts) <= set(FLAGS) and all(
        type(v) is bool for v in opts.values()), "AUTOMATION_OPTIONS_DENIED")
    opts = {flag: opts.get(flag, False) for flag in FLAGS}
    require(stage == "build" or not opts[FLAGS[0]],
            "AUTO_DOWNLOAD_REQUIRES_BUILD_TRIGGER")
    require(stage != "test" or not opts[FLAGS[1]],
            "AUTO_TEST_NOT_VALID_FOR_TEST_TRIGGER")
    clean = {k: request[k] for k in ("stage", "source_sha", "profile_id", "target_id")}
    clean["options"] = opts
    ctx = {**clean}
    if stage == "download":
        ctx["build_receipt"] = _validate_receipt(
            "build", request["build_receipt"], ctx)
    if stage == "test":
        # A direct test can begin from a verified prior load receipt;
        # the build receipt is derived rather than requiring another Build.
        load = request["load_receipt"]
        require(type(load) is dict, "LOAD_RECEIPT_REQUIRED")
        synthetic_build = {
            "stage": "build", "status": "PASS",
            "source_sha": request["source_sha"], "profile_id": request["profile_id"],
            "artifact_sha256": load.get("artifact_sha256"),
            "evidence_sha256": load.get("artifact_sha256")}
        ctx["build_receipt"] = _validate_receipt("build", synthetic_build, ctx)
        ctx["load_receipt"] = _validate_receipt("download", load, ctx)
    return ctx


def required_stages(initial: str, options: Mapping) -> tuple[str, ...]:
    if initial == "test":
        return ("test",)
    if initial == "download":
        return ("download", "test") if options[FLAGS[1]] else ("download",)
    if not options[FLAGS[0]]:
        return ("build",)
    return ("build", "download", "test") if options[FLAGS[1]] else ("build", "download")


def run(request: dict, *, adapters: Mapping[str, Callable[[dict], dict]]) -> dict:
    """Invoke only explicit stage(s) with externally authorized adapters.

    Receipts are *validated callback claims*, not cryptographic attestations
    or permission to access hardware. The caller must provide the trusted
    reviewed stage adapter and gate each transition independently.
    """
    ctx = validate_request(request)
    stages = required_stages(ctx["stage"], ctx["options"])
    require(isinstance(adapters, Mapping) and all(
        callable(adapters.get(stage)) for stage in stages),
        "REVIEWED_STAGE_ADAPTER_REQUIRED")
    outcome = {"schema": "plasma.path2.three_stage.gate1",
               "scope": "ADAPTER_RECEIPTS_ONLY",
               "initial_stage": ctx["stage"], "status": "NO_GO",
               "options": deepcopy(ctx["options"]),
               "completed": [], "receipts": {}, "transitions": []}
    for index, stage in enumerate(stages):
        call = {k: deepcopy(ctx[k]) for k in
                ("source_sha", "profile_id", "target_id")}
        call["stage"] = stage
        if stage != "build":
            require("build_receipt" in ctx, "MISSING_APPROVED_BUILD_RECEIPT")
            call["build_receipt"] = deepcopy(ctx["build_receipt"])
        if stage == "test":
            require("load_receipt" in ctx, "MISSING_APPROVED_LOAD_RECEIPT")
            call["load_receipt"] = deepcopy(ctx["load_receipt"])
        result = adapters[stage](deepcopy(call))
        if type(result) is dict and result.get("status") == "NO_GO":
            _fields(result, {"stage", "status", "reason"}, "DENIAL_RECEIPT_FIELDS")
            require(result["stage"] == stage and type(result["reason"]) is str
                    and REASON.fullmatch(result["reason"]) is not None,
                    "DENIAL_RECEIPT_INVALID")
            outcome["failed_stage"] = stage
            outcome["failure_code"] = result["reason"]
            return outcome
        verified = _validate_receipt(stage, result, call)
        outcome["completed"].append(stage)
        outcome["receipts"][stage] = verified
        if stage == "build":
            ctx["build_receipt"] = verified
        elif stage == "download":
            ctx["load_receipt"] = verified
        if index + 1 < len(stages):
            outcome["transitions"].append({"from": stage, "to": stages[index + 1],
                                            "decision": "EXPLICIT_OPTION_TRUE"})
    outcome["status"] = "RECEIPTS_VALIDATED"
    return outcome
