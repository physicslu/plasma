#!/usr/bin/env python3
"""Migrate the frozen STM32F103C pilot lineage into vendor-neutral admission v1.

This module performs a bounded, manufacturer-grounded migration. It does not
rediscover ICPNs, rerun a model, change the existing compiler, enable hardware,
or alter Production routing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IC_SUPPORT = HERE.parents[1]
REPO_ROOT = HERE.parents[3]
if str(IC_SUPPORT) not in sys.path:
    sys.path.insert(0, str(IC_SUPPORT))

from admission.digest import canonical_digest  # noqa: E402
from admission.validate import validate_admission_package  # noqa: E402


CONTRACT = json.loads(
    (HERE / "vendor-neutral-admission-contract-v1.json").read_text(encoding="utf-8")
)
GENERIC = "plasma://ic-support/admission/"
LOCAL = "plasma://ic-support/benchmarks/stm32f103c/"
COMPILER_ID = CONTRACT["legacy_inputs"]["compiler"]["compiler_id"]
PACKAGE_SUFFIX = "-vendor-neutral-admission-package.json"


class MigrationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MigrationError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(value: dict[str, Any]) -> dict[str, Any]:
    value["artifact_digest"] = canonical_digest(value)
    return value


def ref(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "artifact_id",
            "artifact_type",
            "artifact_digest",
            "schema_id",
            "schema_version",
        )
    }


def opaque(schema_suffix: str, artifact_id: str, artifact_type: str, **payload: Any) -> dict[str, Any]:
    return seal(
        {
            "schema_id": LOCAL + schema_suffix,
            "schema_version": "1.0.0",
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            **payload,
        }
    )


def _repo_path(relative: str) -> Path:
    return REPO_ROOT / relative


def _verify_blob(entry: dict[str, Any], label: str) -> None:
    path = _repo_path(entry["path"])
    require(path.is_file(), f"missing frozen input {label}: {path}")
    require(git_blob_sha1(path) == entry["git_blob_sha1"], f"{label} Git blob drifted")


def validate_frozen_inputs() -> dict[str, Any]:
    """Validate only the frozen execution-relevant STM32F103C migration inputs."""
    for name in ("ground_truth", "binding", "programming_profile", "execution_ir", "compiler"):
        _verify_blob(CONTRACT["legacy_inputs"][name], name)
    for icpn, entry in CONTRACT["legacy_inputs"]["memory_geometry_profiles"].items():
        _verify_blob(entry, f"memory geometry {icpn}")

    source_lock = read_json(HERE / "source-lock.json")
    require(
        source_lock.get("source_lock_id") == CONTRACT["source_lock"]["source_lock_id"],
        "STM32F103C source-lock identity drifted",
    )
    source_by_id = {
        item["source_id"]: item
        for item in source_lock.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    for source_id, expected_digest in CONTRACT["source_lock"]["manufacturer_sources"].items():
        source = source_by_id.get(source_id)
        require(source is not None, f"missing manufacturer source {source_id}")
        require(
            source.get("authority") == "manufacturer_official",
            f"{source_id} is not manufacturer authority",
        )
        require(
            source.get("integrity", {}).get("algorithm") == "sha256"
            and source.get("integrity", {}).get("digest") == expected_digest,
            f"{source_id} digest drifted",
        )

    ground_truth = read_json(_repo_path(CONTRACT["legacy_inputs"]["ground_truth"]["path"]))
    require(
        ground_truth.get("source_lock_id") == CONTRACT["source_lock"]["source_lock_id"],
        "ground truth source-lock binding drifted",
    )
    require(set(ground_truth.get("targets", [])) == set(CONTRACT["targets"]), "ground truth target set drifted")
    expected = ground_truth.get("expected", {})
    shared = CONTRACT["shared"]
    require(
        expected.get("programming_contract", {}).get("program_granularity_bytes")
        == shared["program_granularity_bytes"],
        "program granularity ground truth drifted",
    )
    require(
        expected.get("programming_contract", {}).get("unlock_keys") == shared["unlock_keys"],
        "unlock-key ground truth drifted",
    )

    programming_profile = read_json(
        _repo_path(CONTRACT["legacy_inputs"]["programming_profile"]["path"])
    )
    pdata = programming_profile.get("data", {})
    require(
        programming_profile.get("profile_id") == shared["programming_profile_id"],
        "programming profile identity drifted",
    )
    require(
        pdata.get("program_granularity_bytes") == shared["program_granularity_bytes"],
        "programming profile program granularity drifted",
    )
    require(pdata.get("unlock_keys") == shared["unlock_keys"], "programming profile unlock keys drifted")
    require(
        pdata.get("erase_capabilities") == ["page_erase", "mass_erase"],
        "programming profile erase capability drifted",
    )

    geometries: dict[str, dict[str, Any]] = {}
    for icpn, target in CONTRACT["targets"].items():
        path = _repo_path(CONTRACT["legacy_inputs"]["memory_geometry_profiles"][icpn]["path"])
        geometry = read_json(path)
        geometries[icpn] = geometry
        data = geometry.get("data", {})
        require(
            geometry.get("profile_id") == target["memory_geometry_profile_id"],
            f"{icpn} geometry profile identity drifted",
        )
        for key in (
            "main_flash_start",
            "page_size_bytes",
            "erase_granularity_bytes",
            "program_granularity_bytes",
        ):
            require(data.get(key) == shared[key], f"{icpn} {key} drifted")
        for key in ("main_flash_size_bytes", "main_flash_end", "page_count"):
            require(data.get(key) == target[key], f"{icpn} {key} drifted")
        require(
            target["page_count"] * shared["page_size_bytes"] == target["main_flash_size_bytes"],
            f"{icpn} page geometry is internally inconsistent",
        )

    binding = read_json(_repo_path(CONTRACT["legacy_inputs"]["binding"]["path"]))
    rows = {row["icpn"]: row for row in binding.get("bindings", [])}
    require(set(rows) == set(CONTRACT["targets"]), "STM32F103C binding target set drifted")
    for icpn, target in CONTRACT["targets"].items():
        row = rows[icpn]
        require(
            row.get("profiles", {}).get("programming") == shared["programming_profile_id"],
            f"{icpn} programming-profile binding drifted",
        )
        require(
            row.get("profiles", {}).get("memory_geometry")
            == target["memory_geometry_profile_id"],
            f"{icpn} memory-geometry binding drifted",
        )
        require(
            row.get("expected_catalog", {}).get("openocd_target_config")
            == shared["openocd_target_config"],
            f"{icpn} OpenOCD target binding drifted",
        )

    execution_ir = read_json(_repo_path(CONTRACT["legacy_inputs"]["execution_ir"]["path"]))
    ir_targets = {
        row["icpn"]: row.get("memory_geometry_profile")
        for row in execution_ir.get("targets", [])
    }
    require(
        ir_targets
        == {
            icpn: target["memory_geometry_profile_id"]
            for icpn, target in CONTRACT["targets"].items()
        },
        "Execution IR target geometry binding drifted",
    )
    operation_ids = {
        row.get("operation_id")
        for row in execution_ir.get("operations", [])
        if isinstance(row, dict)
    }
    require(
        {
            "flash_unlock",
            "flash_program_unit",
            "flash_erase_page",
            "flash_mass_erase",
            "flash_lock",
            "option_program",
            "option_erase",
            "rdp_disable_transition",
        }
        <= operation_ids,
        "Execution IR operation surface drifted",
    )

    compiler_path = _repo_path(CONTRACT["legacy_inputs"]["compiler"]["path"])
    compiler_text = compiler_path.read_text(encoding="utf-8")
    for sentinel in (
        "class OpenOCDPlanCompiler:",
        'f"flash erase_address {_hex32(geometry.start)} {_hex32(geometry.size_bytes)}"',
        '"flash write_image"',
        '"flash verify_image"',
        "dump_image ",
        '"hardware_runtime_ready": False',
    ):
        require(sentinel in compiler_text, f"compiler semantic sentinel missing: {sentinel}")

    return {
        "source_lock": source_lock,
        "ground_truth": ground_truth,
        "programming_profile": programming_profile,
        "geometries": geometries,
        "binding": binding,
        "execution_ir": execution_ir,
    }


def _evidence(source_lock_artifact: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    digest = CONTRACT["source_lock"]["manufacturer_sources"][item["source_id"]]
    result: dict[str, Any] = {
        "source_lock_id": source_lock_artifact["artifact_id"],
        "source_id": item["source_id"],
        "source_digest": digest,
        "authority": "manufacturer",
        "locator": item["locator"],
    }
    if "page" in item:
        result["page"] = item["page"]
    return result


def _canonical_requirements(vendor_payload: dict[str, Any], pointers: list[str]) -> list[dict[str, Any]]:
    return [{"artifact": ref(vendor_payload), "pointer": pointer} for pointer in pointers]


def _source_lock_artifact() -> dict[str, Any]:
    sources = []
    source_lock = read_json(HERE / "source-lock.json")
    raw = {item["source_id"]: item for item in source_lock["sources"]}
    for source_id, digest in CONTRACT["source_lock"]["manufacturer_sources"].items():
        item = raw[source_id]
        sources.append(
            {
                "source_id": source_id,
                "source_digest": digest,
                "authority": "manufacturer",
                "document_number": item["document_number"],
                "revision": item["revision"],
            }
        )
    return opaque(
        "source-lock-wrapper-v1",
        "stm32f103c-manufacturer-source-lock-v1",
        "source_lock",
        legacy_source_lock_id=CONTRACT["source_lock"]["source_lock_id"],
        sources=sources,
    )


def _review_chain(artifacts: dict[str, dict[str, Any]], source_lock: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fact_refs = []
    dispositions = []
    candidate_reviews = []

    for raw in CONTRACT["review_facts"]:
        fact = opaque(
            "manufacturer-fact-v1",
            raw["fact_id"],
            "manufacturer_fact",
            statement=raw["statement"],
            evidence=[_evidence(source_lock, item) for item in raw["evidence"]],
        )
        artifacts[fact["artifact_id"]] = fact
        fact_refs.append(ref(fact))

    fact_set = opaque(
        "reviewed-fact-set-v1",
        "stm32f103c-reviewed-fact-set-v1",
        "reviewed_fact_set",
        migration_base_commit=CONTRACT["migration_base_commit"],
        facts=fact_refs,
    )
    review_report = opaque(
        "manufacturer-review-v1",
        "stm32f103c-bounded-manufacturer-review-v1",
        "review_artifact",
        review_scope="execution_relevant_semantic_closure",
        source_documents=["DS5319 Rev 20", "PM0075 Rev 2"],
        status="COMPLETE",
        finding_count=0,
        model_invocation=False,
        icpn_rediscovery=False,
    )
    artifacts[fact_set["artifact_id"]] = fact_set
    artifacts[review_report["artifact_id"]] = review_report

    review_binding = seal(
        {
            "schema_id": GENERIC + "review-binding-v1",
            "schema_version": "1.0.0",
            "artifact_id": "stm32f103c-review-binding-v1",
            "artifact_type": "review_binding",
            "reviewed_artifact": ref(fact_set),
            "review_artifact": ref(review_report),
            "review_subjects": fact_refs,
            "review_status": "COMPLETE",
        }
    )
    artifacts[review_binding["artifact_id"]] = review_binding

    for raw in CONTRACT["review_facts"]:
        fact = artifacts[raw["fact_id"]]
        candidate = opaque(
            "candidate-fact-v1",
            raw["fact_id"] + "-candidate-v1",
            "candidate_fact",
            statement=raw["statement"],
        )
        artifacts[candidate["artifact_id"]] = candidate
        dispositions.append(
            {
                "source_fact": ref(fact),
                "action": "ACCEPT",
                "projection_state": raw["projection_state"],
                "candidate_artifacts": [ref(candidate)],
            }
        )
        candidate_reviews.append(
            {
                "candidate": ref(candidate),
                "evidence": [_evidence(source_lock, item) for item in raw["evidence"]],
                "review_status": "MANUFACTURER_REVIEW_PASS",
                "dimensions": {
                    "semantic_support": "SUPPORTED",
                    "citation_entailment": "COMPLETE",
                    "atomicity": "PASS",
                    "scope": "PASS",
                    "terminology": "PASS",
                },
            }
        )

    disposition = seal(
        {
            "schema_id": GENERIC + "post-review-disposition-v1",
            "schema_version": "1.0.0",
            "artifact_id": "stm32f103c-post-review-disposition-v1",
            "artifact_type": "post_review_disposition",
            "review_binding": ref(review_binding),
            "dispositions": dispositions,
        }
    )
    artifacts[disposition["artifact_id"]] = disposition

    candidate_review = seal(
        {
            "schema_id": GENERIC + "candidate-review-v1",
            "schema_version": "1.0.0",
            "artifact_id": "stm32f103c-candidate-review-v1",
            "artifact_type": "candidate_manufacturer_review",
            "disposition": ref(disposition),
            "candidate_reviews": candidate_reviews,
        }
    )
    artifacts[candidate_review["artifact_id"]] = candidate_review
    return review_binding, disposition, candidate_review


def _backend_binding(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    compiler = CONTRACT["legacy_inputs"]["compiler"]
    implementation_source = opaque(
        "implementation-source-v1",
        "stm32f103c-openocd-plan-compiler-source-v1",
        "implementation_source",
        migration_base_commit=CONTRACT["migration_base_commit"],
        path=compiler["path"],
        git_blob_sha1=compiler["git_blob_sha1"],
        compiler_id=compiler["compiler_id"],
    )
    constraints = opaque(
        "backend-constraints-v1",
        "stm32f103c-openocd-backend-constraints-v1",
        "vendor_backend_constraints",
        target_config=CONTRACT["shared"]["openocd_target_config"],
        programming_profile_id=CONTRACT["shared"]["programming_profile_id"],
        erase_scope=CONTRACT["operations"]["erase_scope"],
        program_implicit_erase=CONTRACT["operations"]["program_implicit_erase"],
        controller_mass_erase_equivalent_claim=False,
        hardware_runtime_ready=False,
    )
    artifacts[implementation_source["artifact_id"]] = implementation_source
    artifacts[constraints["artifact_id"]] = constraints

    backend = {
        "schema_id": GENERIC + "backend-implementation-binding-v1",
        "schema_version": "1.0.0",
        "artifact_id": "stm32f103c-openocd-backend-v1",
        "artifact_type": "backend_implementation_binding",
        "backend_id": "stm32f103c-openocd-backend-v1",
        "implementation": {
            "identity": "Plasma OpenOCDPlanCompiler",
            "revision": CONTRACT["migration_base_commit"],
        },
        "implementation_evidence": [ref(implementation_source)],
        "vendor_constraint_payload": ref(constraints),
    }
    backend["lock_digest"] = canonical_digest(
        backend, omit=("artifact_digest", "lock_digest")
    )
    seal(backend)
    artifacts[backend["artifact_id"]] = backend
    return backend


def _vendor_payload(target_icpn: str, artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    target = CONTRACT["targets"][target_icpn]
    shared = CONTRACT["shared"]
    payload = opaque(
        "vendor-canonical-payload-v1",
        f"stm32f103c-{target_icpn.lower()}-vendor-payload-v1",
        "vendor_canonical_payload",
        target={
            "icpn": target_icpn,
            "base_device": target["base_device"],
            "density_class": target["density_class"],
        },
        memory={
            "main_flash_start": shared["main_flash_start"],
            "main_flash_size_bytes": target["main_flash_size_bytes"],
            "main_flash_end": target["main_flash_end"],
            "page_size_bytes": shared["page_size_bytes"],
            "page_count": target["page_count"],
            "erase_granularity_bytes": shared["erase_granularity_bytes"],
            "program_granularity_bytes": shared["program_granularity_bytes"],
        },
        programming={
            "programming_profile_id": shared["programming_profile_id"],
            "unlock_keys": shared["unlock_keys"],
            "program_granularity_bytes": shared["program_granularity_bytes"],
        },
        backend_semantics={
            "openocd_target_config": shared["openocd_target_config"],
            "erase_scope": CONTRACT["operations"]["erase_scope"],
            "program_implicit_erase": CONTRACT["operations"]["program_implicit_erase"],
            "erase_controller_command_equivalence_claim": False,
        },
        safety={
            "destructive_security_operations_admitted": False,
            "hardware_runtime_ready": False,
        },
        legacy_lineage={
            "memory_geometry_profile_id": target["memory_geometry_profile_id"],
            "binding_set_id": "stm32f103c-pilot-v0",
            "execution_ir_id": "stm32f103c-programming-execution-ir-v0",
        },
    )
    artifacts[payload["artifact_id"]] = payload
    return payload


def _operation_contract(
    artifacts: dict[str, dict[str, Any]],
    operation: str,
    *,
    state: str,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_operation": operation,
        "state": state,
    }
    if operation == "READ":
        payload.update({"scope": "resolved_main_flash_only", "write_effect": False})
    elif operation == "VERIFY":
        payload.update({"scope": "image_from_resolved_main_flash_start", "write_effect": False})
    elif operation == "PROGRAM":
        payload.update(
            {
                "scope": "image_from_resolved_main_flash_start",
                "program_unit_bytes": CONTRACT["shared"]["program_granularity_bytes"],
                "implicit_erase": CONTRACT["operations"]["program_implicit_erase"],
            }
        )
    elif operation == "ERASE":
        payload.update(
            {
                "scope": CONTRACT["operations"]["erase_scope"],
                "implementation": "flash erase_address <resolved_main_flash_start> <resolved_main_flash_size>",
                "destructive_scope": "all bytes in resolved main Flash",
                "controller_mass_erase_equivalent_claim": False,
            }
        )
    else:
        payload.update(
            {
                "scope": "destructive_or_security_sensitive",
                "reason": reason or "not admitted by STM32F103C migration v1",
            }
        )
    artifact = opaque(
        "operation-contract-v1",
        "stm32f103c-operation-contract-" + operation.lower().replace("_", "-") + "-v1",
        "operation_contract",
        **payload,
    )
    artifacts[artifact["artifact_id"]] = artifact
    return artifact


def build_package(target_icpn: str) -> dict[str, Any]:
    require(target_icpn in CONTRACT["targets"], f"unsupported migration target {target_icpn}")
    validate_frozen_inputs()

    artifacts: dict[str, dict[str, Any]] = {}
    source_lock = _source_lock_artifact()
    artifacts[source_lock["artifact_id"]] = source_lock
    review_binding, disposition, candidate_review = _review_chain(artifacts, source_lock)
    backend = _backend_binding(artifacts)
    vendor_payload = _vendor_payload(target_icpn, artifacts)

    envelope = seal(
        {
            "schema_id": GENERIC + "canonical-admission-envelope-v1",
            "schema_version": "1.0.0",
            "artifact_id": f"stm32f103c-{target_icpn.lower()}-canonical-admission-v1",
            "artifact_type": "canonical_admission_envelope",
            "target": {
                "vendor_id": CONTRACT["shared"]["vendor_id"],
                "icpn": target_icpn,
            },
            "vendor_payload": ref(vendor_payload),
            "lineage": {
                "source_lock": ref(source_lock),
                "review_binding": ref(review_binding),
                "disposition": ref(disposition),
                "candidate_review": ref(candidate_review),
            },
            "admission": {"state": "ADMITTED", "unresolved_requirements": []},
        }
    )
    artifacts[envelope["artifact_id"]] = envelope

    pointers = {
        "READ": ["/memory/main_flash_start", "/memory/main_flash_size_bytes"],
        "VERIFY": [
            "/memory/main_flash_start",
            "/memory/main_flash_size_bytes",
            "/programming/programming_profile_id",
        ],
        "PROGRAM": [
            "/memory/main_flash_start",
            "/memory/main_flash_size_bytes",
            "/programming/program_granularity_bytes",
            "/programming/unlock_keys",
            "/backend_semantics/program_implicit_erase",
        ],
        "ERASE": [
            "/memory/main_flash_start",
            "/memory/main_flash_size_bytes",
            "/backend_semantics/erase_scope",
        ],
    }

    rows = []
    for operation in CONTRACT["operations"]["admitted"]:
        op_contract = _operation_contract(artifacts, operation, state="ADMITTED")
        rows.append(
            {
                "request_operation": operation,
                "operation_contract_id": op_contract["artifact_id"],
                "operation_contract_digest": op_contract["artifact_digest"],
                "state": "ADMITTED",
                "canonical_admission_digest": envelope["artifact_digest"],
                "backend_id": backend["backend_id"],
                "backend_lock_digest": backend["lock_digest"],
                "compiler_id": COMPILER_ID,
                "canonical_requirements": _canonical_requirements(
                    vendor_payload, pointers[operation]
                ),
                "unresolved_requirements": [],
                "hardware_runtime_ready": False,
            }
        )

    for operation in CONTRACT["operations"]["blocked"]:
        op_contract = _operation_contract(
            artifacts,
            operation,
            state="BLOCKED",
            reason="destructive/security operation is outside STM32F103C migration v1 admission",
        )
        rows.append(
            {
                "request_operation": operation,
                "operation_contract_id": op_contract["artifact_id"],
                "operation_contract_digest": op_contract["artifact_digest"],
                "state": "BLOCKED",
                "canonical_admission_digest": envelope["artifact_digest"],
                "backend_id": backend["backend_id"],
                "backend_lock_digest": backend["lock_digest"],
                "compiler_id": COMPILER_ID,
                "canonical_requirements": [],
                "unresolved_requirements": [
                    "destructive/security operation is not admitted by STM32F103C migration v1"
                ],
                "hardware_runtime_ready": False,
            }
        )

    operation_admission = seal(
        {
            "schema_id": GENERIC + "operation-admission-v1",
            "schema_version": "1.0.0",
            "artifact_id": f"stm32f103c-{target_icpn.lower()}-operation-admission-v1",
            "artifact_type": "operation_admission",
            "target": envelope["target"],
            "operations": rows,
        }
    )
    artifacts[operation_admission["artifact_id"]] = operation_admission

    return {
        "artifacts": artifacts,
        "compiler_bindings": {backend["backend_id"]: [COMPILER_ID]},
        "root_envelope_id": envelope["artifact_id"],
        "operation_admission_id": operation_admission["artifact_id"],
    }


def validate_projection(package: dict[str, Any], target_icpn: str) -> dict[str, Any]:
    result = validate_admission_package(package)
    require(result["status"] == "VALID", "generic validator did not return VALID")
    require(result["target"]["icpn"] == target_icpn, "generic target mismatch")
    require(
        result["candidate_count"] == len(CONTRACT["review_facts"]),
        "bounded review candidate count mismatch",
    )

    artifacts = package["artifacts"]
    envelope = artifacts[package["root_envelope_id"]]
    payload = artifacts[envelope["vendor_payload"]["artifact_id"]]
    target = CONTRACT["targets"][target_icpn]
    shared = CONTRACT["shared"]

    require(payload["target"]["icpn"] == target_icpn, "vendor payload target mismatch")
    require(payload["target"]["base_device"] == target["base_device"], "base-device applicability drifted")
    require(payload["target"]["density_class"] == target["density_class"], "density-class applicability drifted")
    for key in (
        "main_flash_start",
        "page_size_bytes",
        "erase_granularity_bytes",
        "program_granularity_bytes",
    ):
        require(payload["memory"][key] == shared[key], f"vendor payload {key} drifted")
    for key in ("main_flash_size_bytes", "main_flash_end", "page_count"):
        require(payload["memory"][key] == target[key], f"vendor payload {key} drifted")
    require(
        payload["programming"]["unlock_keys"] == shared["unlock_keys"],
        "vendor payload unlock keys drifted",
    )
    require(
        payload["programming"]["program_granularity_bytes"]
        == shared["program_granularity_bytes"],
        "vendor payload program unit drifted",
    )
    require(
        payload["backend_semantics"]["openocd_target_config"]
        == shared["openocd_target_config"],
        "OpenOCD target config drifted",
    )
    require(
        payload["backend_semantics"]["erase_scope"]
        == CONTRACT["operations"]["erase_scope"],
        "STM32 ERASE scope drifted",
    )
    require(
        payload["backend_semantics"]["program_implicit_erase"] is False,
        "PROGRAM must not gain implicit erase",
    )
    require(
        payload["safety"]["destructive_security_operations_admitted"] is False,
        "destructive/security admission must remain false",
    )
    require(
        payload["safety"]["hardware_runtime_ready"] is False,
        "vendor payload hardware runtime readiness must remain false",
    )

    rows = {
        row["request_operation"]: row
        for row in artifacts[package["operation_admission_id"]]["operations"]
    }
    require(
        set(rows)
        == set(CONTRACT["operations"]["admitted"] + CONTRACT["operations"]["blocked"]),
        "operation surface drifted",
    )
    require(
        {name for name, row in rows.items() if row["state"] == "ADMITTED"}
        == set(CONTRACT["operations"]["admitted"]),
        "admitted operation set drifted",
    )
    require(
        {name for name, row in rows.items() if row["state"] == "BLOCKED"}
        == set(CONTRACT["operations"]["blocked"]),
        "blocked operation set drifted",
    )
    require(
        all(row["hardware_runtime_ready"] is False for row in rows.values()),
        "hardware runtime readiness must remain false",
    )
    require(
        all(row["compiler_id"] == COMPILER_ID for row in rows.values()),
        "compiler binding drifted",
    )

    erase_contract = artifacts[rows["ERASE"]["operation_contract_id"]]
    require(
        erase_contract["scope"] == CONTRACT["operations"]["erase_scope"],
        "ERASE operation contract scope drifted",
    )
    require(
        erase_contract["controller_mass_erase_equivalent_claim"] is False,
        "ERASE must not claim controller Mass Erase equivalence",
    )

    backend = artifacts[rows["READ"]["backend_id"]]
    require(
        backend["implementation"]["revision"] == CONTRACT["migration_base_commit"],
        "backend implementation revision drifted",
    )
    require(
        package["compiler_bindings"].get(backend["backend_id"]) == [COMPILER_ID],
        "compiler registry binding drifted",
    )
    return result


def _manifest_digest(files: dict[str, str]) -> str:
    raw = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def build_sidecar(output_dir: Path) -> dict[str, Any]:
    validate_frozen_inputs()
    output_dir.mkdir(parents=True, exist_ok=False)

    validation: dict[str, Any] = {}
    package_files = []
    for target_icpn in sorted(CONTRACT["targets"]):
        package = build_package(target_icpn)
        validation[target_icpn] = validate_projection(package, target_icpn)
        name = target_icpn.lower() + PACKAGE_SUFFIX
        write_json_new(output_dir / name, package)
        package_files.append(name)

    qualification = {
        "schema_version": "1.0.0",
        "artifact_type": "stm32f103c_vendor_neutral_admission_qualification",
        "migration_base_commit": CONTRACT["migration_base_commit"],
        "source_lock_id": CONTRACT["source_lock"]["source_lock_id"],
        "manufacturer_review_fact_count": len(CONTRACT["review_facts"]),
        "targets": validation,
        "admitted_operations": CONTRACT["operations"]["admitted"],
        "blocked_operations": CONTRACT["operations"]["blocked"],
        "hardware_runtime_ready": False,
        "model_invocation": False,
        "icpn_rediscovery": False,
        "production_admission": False,
    }
    write_json_new(output_dir / "qualification.json", qualification)

    files = {
        name: sha256_file(output_dir / name)
        for name in sorted(package_files + ["qualification.json"])
    }
    manifest = {
        "schema_version": "1.0.0",
        "artifact_type": "stm32f103c_vendor_neutral_admission_sidecar_manifest",
        "migration_base_commit": CONTRACT["migration_base_commit"],
        "source_lock_id": CONTRACT["source_lock"]["source_lock_id"],
        "files": files,
        "release_digest": _manifest_digest(files),
    }
    write_json_new(output_dir / "release-manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(CONTRACT["targets"]))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    if args.output_dir is not None:
        manifest = build_sidecar(args.output_dir)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    targets = [args.target] if args.target else sorted(CONTRACT["targets"])
    summary = {}
    for target in targets:
        package = build_package(target)
        summary[target] = validate_projection(package, target)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
