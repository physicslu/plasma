#!/usr/bin/env python3
"""Project the immutable KL25 review release into vendor-neutral admission v1.

The legacy validators run first and remain authoritative.  Projection is a
deterministic, content-addressed compatibility layer; it performs no model or
hardware execution and never edits its inputs.
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
if str(IC_SUPPORT) not in sys.path:
    sys.path.insert(0, str(IC_SUPPORT))

from admission.digest import canonical_digest  # noqa: E402
from admission.validate import validate_admission_package  # noqa: E402

import canonical_admission  # noqa: E402
import gate58_review  # noqa: E402
import post_review_disposition as legacy_disposition  # noqa: E402


CONTRACT = json.loads((HERE / "vendor-neutral-admission-adapter-contract-v1.json").read_text(encoding="utf-8"))
SOURCE_LOCK_PATH = HERE / "source-lock.json"
PASS = {
    "semantic_support": "SUPPORTED",
    "citation_entailment": "COMPLETE",
    "atomicity": "PASS",
    "scope": "PASS",
    "terminology": "PASS",
}
GENERIC = "plasma://ic-support/admission/"
LOCAL = "plasma://ic-support/benchmarks/nxp-kl25/"
COMPILER_ID = "plasma_interfaces.kl25_openocd_plan.KL25OpenOCDPlanCompiler"
PACKAGE_FILE = "vendor-neutral-admission-package.json"


class AdapterError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdapterError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(value: dict[str, Any]) -> dict[str, Any]:
    value["artifact_digest"] = canonical_digest(value)
    return value


def ref(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("artifact_id", "artifact_type", "artifact_digest", "schema_id", "schema_version")
    }


def opaque(schema: str, artifact_id: str, artifact_type: str, **payload: Any) -> dict[str, Any]:
    return seal(
        {
            "schema_id": schema,
            "schema_version": "1.0.0",
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            **payload,
        }
    )


def _manifest_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_legacy_inputs(run_dir: Path, gate58_dir: Path, release_dir: Path) -> dict[str, Any]:
    """Run legacy validation and enforce all immutable identities before projection."""
    required = {
        "run": run_dir / "aggregate-report.json",
        "review_view": gate58_dir / "review-view.json",
        "review_verdict": gate58_dir / "review-verdict.json",
        "release_manifest": release_dir / "release-manifest.json",
    }
    for label, path in required.items():
        require(path.is_file(), f"missing {label}: {path}")

    require(sha256_file(required["run"]) == CONTRACT["retained_run"]["aggregate_file_sha256"], "retained aggregate bytes drifted")
    require(sha256_file(required["review_view"]) == CONTRACT["gate58"]["review_view_file_sha256"], "Gate 5.8 review view bytes drifted")
    require(sha256_file(required["review_verdict"]) == CONTRACT["gate58"]["review_verdict_file_sha256"], "Gate 5.8 verdict bytes drifted")
    require(sha256_file(required["release_manifest"]) == CONTRACT["legacy_release"]["manifest_file_sha256"], "legacy release manifest bytes drifted")

    view = read_json(required["review_view"])
    verdict = read_json(required["review_verdict"])
    require(view.get("retained_run_id") == CONTRACT["retained_run"]["run_id"], "retained run identity mismatch")
    require(view.get("aggregate_digest") == CONTRACT["retained_run"]["aggregate_digest"], "retained aggregate digest mismatch")
    require(view.get("review_view_digest") == CONTRACT["gate58"]["review_view_digest"], "Gate 5.8 review digest mismatch")
    require(verdict.get("review_view_digest") == view.get("review_view_digest"), "Gate 5.8 verdict/view binding mismatch")

    report = gate58_review.qualify_review(run_dir, verdict)
    require(report.get("status") == CONTRACT["gate58"]["qualification_status"], "Gate 5.8 status mismatch")
    require(report.get("report_digest") == CONTRACT["gate58"]["qualification_digest"], "Gate 5.8 qualification digest mismatch")

    release_manifest = read_json(required["release_manifest"])
    release_files = release_manifest.get("files")
    require(isinstance(release_files, dict), "legacy release file manifest missing")
    for name, digest in release_files.items():
        path = release_dir / name
        require(path.is_file() and sha256_file(path) == digest, f"legacy release file drifted: {name}")
    require(_manifest_digest(release_files) == release_manifest.get("release_digest"), "legacy release digest is invalid")
    require(release_manifest["release_digest"] == CONTRACT["legacy_release"]["release_digest"], "legacy release identity mismatch")

    disposition = read_json(release_dir / "post-review-disposition.json")
    candidate_review = read_json(release_dir / "candidate-manufacturer-review.json")
    canonical_spec = read_json(release_dir / "canonical-specification.json")
    operations = read_json(release_dir / "operation-admission.json")
    backend_lock = read_json(release_dir / "backend-implementation-lock.json")
    legacy_qualification = read_json(release_dir / "qualification.json")
    disposition_result = legacy_disposition.validate_disposition(view, verdict, disposition)
    review_result = legacy_disposition.validate_candidate_review(disposition, candidate_review)
    canonical_result = canonical_admission.validate(disposition, candidate_review, canonical_spec, operations)
    require(canonical_result == legacy_qualification, "legacy qualification artifact mismatch")
    require(backend_lock.get("lock_digest") == CONTRACT["legacy_release"]["backend_lock_digest"], "legacy backend lock mismatch")
    require(backend_lock.get("commit") == CONTRACT["legacy_release"]["openocd_commit"], "OpenOCD commit mismatch")

    facts = [fact for unit in view.get("units", []) for fact in unit.get("facts", [])]
    verdicts = verdict.get("fact_verdicts", [])
    full_pass = sum(all(row.get(key) == expected for key, expected in PASS.items()) for row in verdicts)
    expected = CONTRACT["expected_counts"]
    require(len(facts) == len(verdicts) == expected["facts"], "Gate 5.8 fact count mismatch")
    require(full_pass == expected["gate58_full_pass"], "Gate 5.8 full-PASS count mismatch")
    require(len(verdicts) - full_pass == expected["gate58_findings"], "Gate 5.8 finding count mismatch")
    require(disposition_result["candidate_count"] == expected["candidates"], "legacy candidate count mismatch")
    require(len(review_result["manufacturer_review_pass_candidates"]) == expected["candidates"], "legacy candidate review coverage mismatch")
    return {
        "view": view,
        "verdict": verdict,
        "disposition": disposition,
        "candidate_review": candidate_review,
        "canonical_spec": canonical_spec,
        "operations": operations,
        "backend_lock": backend_lock,
        "release_manifest": release_manifest,
        "legacy_qualification": legacy_qualification,
        "legacy_validation": {
            "gate58_status": report["status"],
            "fact_count": len(facts),
            "full_pass_count": full_pass,
            "finding_count": len(facts) - full_pass,
            "candidate_count": disposition_result["candidate_count"],
            "candidate_review_count": len(review_result["manufacturer_review_pass_candidates"]),
            "status": "PASS",
        },
    }


def _evidence(value: dict[str, Any], source_lock_id: str) -> dict[str, Any]:
    result = {
        "source_lock_id": source_lock_id,
        "source_id": value["source_id"],
        "source_digest": value["source_sha256"],
        "authority": "manufacturer",
        "locator": value["locator"],
    }
    if "pdf_page_number" in value:
        result["page"] = value["pdf_page_number"]
    return result


def _pointer(path: str) -> str:
    return "/canonical_fields_by_path/" + path.replace("~", "~0").replace("/", "~1") + "/value"


def build_package(legacy: dict[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    source_lock_raw = read_json(SOURCE_LOCK_PATH)
    source_lock_content_digest = canonical_digest(source_lock_raw, omit=())
    require(source_lock_content_digest == CONTRACT["source_lock_content_digest"], "source lock content drifted")
    source_lock = opaque(
        LOCAL + "source-lock-wrapper-v1",
        "nxp-kl25-source-lock-wrapper-v1",
        "source_lock",
        legacy_source_lock_id=source_lock_raw["source_lock_id"],
        legacy_content_digest=source_lock_content_digest,
        sources=[
            {
                "source_id": source["source_id"],
                "source_digest": source["integrity"]["digest"],
                "authority": source["authority"],
                "document_number": source["document_number"],
                "revision": source["revision"],
            }
            for source in source_lock_raw["sources"]
        ],
    )
    artifacts[source_lock["artifact_id"]] = source_lock

    fact_by_id: dict[str, dict[str, Any]] = {}
    for unit in legacy["view"]["units"]:
        for fact in unit["facts"]:
            wrapped = opaque(
                LOCAL + "fact-wrapper-v1",
                fact["fact_id"],
                "manufacturer_fact",
                primary_unit_id=unit["primary_unit_id"],
                legacy_fact_digest=fact["fact_digest"],
                kind=fact["kind"],
                statement=fact["statement"],
                citations=fact["all_citations"],
            )
            artifacts[wrapped["artifact_id"]] = wrapped
            fact_by_id[fact["fact_id"]] = wrapped

    fact_set = opaque(
        LOCAL + "reviewed-fact-set-wrapper-v1",
        "nxp-kl25-gate58-reviewed-fact-set-v1",
        "reviewed_fact_set",
        retained_run_id=CONTRACT["retained_run"]["run_id"],
        aggregate_digest=CONTRACT["retained_run"]["aggregate_digest"],
        review_view_digest=CONTRACT["gate58"]["review_view_digest"],
        review_view_file_sha256=CONTRACT["gate58"]["review_view_file_sha256"],
        facts=[ref(fact_by_id[fact_id]) for fact_id in sorted(fact_by_id)],
    )
    review_report = opaque(
        LOCAL + "review-verdict-wrapper-v1",
        "nxp-kl25-gate58-review-verdict-v1",
        "review_artifact",
        retained_run_id=CONTRACT["retained_run"]["run_id"],
        qualification_digest=CONTRACT["gate58"]["qualification_digest"],
        qualification_status=CONTRACT["gate58"]["qualification_status"],
        legacy_file_sha256=CONTRACT["gate58"]["review_verdict_file_sha256"],
        full_pass_count=CONTRACT["expected_counts"]["gate58_full_pass"],
        finding_count=CONTRACT["expected_counts"]["gate58_findings"],
        findings=[
            {
                "primary_unit_id": row["primary_unit_id"],
                "fact_id": row["fact_id"],
                "fact_digest": row["fact_digest"],
                "dimensions": {key: row[key] for key in CONTRACT["review_dimensions"]},
                "rationale": row["rationale"],
            }
            for row in legacy["verdict"]["fact_verdicts"]
            if not all(row.get(key) == expected for key, expected in PASS.items())
        ],
    )
    artifacts.update({fact_set["artifact_id"]: fact_set, review_report["artifact_id"]: review_report})
    review_binding = seal(
        {
            "schema_id": GENERIC + "review-binding-v1",
            "schema_version": "1.0.0",
            "artifact_id": "nxp-kl25-review-binding-v1",
            "artifact_type": "review_binding",
            "reviewed_artifact": ref(fact_set),
            "review_artifact": ref(review_report),
            "review_subjects": [ref(fact_by_id[fact_id]) for fact_id in sorted(fact_by_id)],
            "review_status": "COMPLETE_WITH_FINDINGS",
        }
    )
    artifacts[review_binding["artifact_id"]] = review_binding

    candidates: dict[str, dict[str, Any]] = {}
    disposition_rows = []
    legacy_dispositions: dict[str, dict[str, Any]] = {}
    for row in legacy["disposition"]["dispositions"]:
        candidate_refs = []
        legacy_dispositions[row["fact_id"]] = row
        for candidate in row["candidates"]:
            wrapped = opaque(
                LOCAL + "candidate-wrapper-v1",
                candidate["candidate_id"],
                "candidate_fact",
                legacy_candidate_digest=candidate["candidate_digest"],
                statement=candidate["statement"],
                manufacturer_evidence=candidate["evidence"],
            )
            candidates[wrapped["artifact_id"]] = wrapped
            artifacts[wrapped["artifact_id"]] = wrapped
            candidate_refs.append(ref(wrapped))
        disposition_rows.append(
            {
                "source_fact": ref(fact_by_id[row["fact_id"]]),
                "action": row["action"],
                "projection_state": row["projection_state"],
                "candidate_artifacts": candidate_refs,
            }
        )
    disposition = seal(
        {
            "schema_id": GENERIC + "post-review-disposition-v1",
            "schema_version": "1.0.0",
            "artifact_id": "nxp-kl25-post-review-disposition-v1",
            "artifact_type": "post_review_disposition",
            "review_binding": ref(review_binding),
            "dispositions": disposition_rows,
        }
    )
    artifacts[disposition["artifact_id"]] = disposition

    verdict_by_fact = {row["fact_id"]: row for row in legacy["verdict"]["fact_verdicts"]}
    transformed_review = {row["candidate_id"]: row for row in legacy["candidate_review"]["candidate_reviews"]}
    candidate_reviews = []
    accepted_count = transformed_count = 0
    for fact_id, row in legacy_dispositions.items():
        for raw_candidate in row["candidates"]:
            candidate = candidates[raw_candidate["candidate_id"]]
            if row["action"] == "ACCEPT":
                dimensions = {key: verdict_by_fact[fact_id][key] for key in CONTRACT["review_dimensions"]}
                status = "INHERITED_GATE58_FULL_PASS"
                accepted_count += 1
            else:
                local = transformed_review[raw_candidate["candidate_id"]]
                dimensions = {key: local[key] for key in CONTRACT["review_dimensions"]}
                status = "EXPLICIT_POST_REVIEW_PASS"
                transformed_count += 1
            candidate_reviews.append(
                {
                    "candidate": ref(candidate),
                    "evidence": [_evidence(item, source_lock["artifact_id"]) for item in raw_candidate["evidence"]],
                    "review_status": status,
                    "dimensions": dimensions,
                }
            )
    require(accepted_count == CONTRACT["expected_counts"]["accepted_candidates"], "accepted candidate count mismatch")
    require(transformed_count == CONTRACT["expected_counts"]["transformed_candidates"], "transformed candidate count mismatch")
    candidate_review = seal(
        {
            "schema_id": GENERIC + "candidate-review-v1",
            "schema_version": "1.0.0",
            "artifact_id": "nxp-kl25-candidate-review-v1",
            "artifact_type": "candidate_manufacturer_review",
            "disposition": ref(disposition),
            "candidate_reviews": sorted(candidate_reviews, key=lambda item: item["candidate"]["artifact_id"]),
        }
    )
    artifacts[candidate_review["artifact_id"]] = candidate_review

    canonical_fields = {field["path"]: {key: value for key, value in field.items() if key != "path"} for field in legacy["canonical_spec"]["canonical_fields"]}
    vendor_payload = opaque(
        LOCAL + "vendor-neutral-admission-payload-v1",
        "nxp-kl25-vendor-payload-v1",
        "vendor_canonical_payload",
        target=legacy["canonical_spec"]["target"],
        legacy_release={
            "release_digest": CONTRACT["legacy_release"]["release_digest"],
            "canonical_spec_digest": legacy["canonical_spec"]["spec_digest"],
        },
        canonical_fields_by_path=canonical_fields,
        blocked_fields=legacy["canonical_spec"]["blocked_fields"],
        silicon=legacy["canonical_spec"]["silicon"],
    )
    artifacts[vendor_payload["artifact_id"]] = vendor_payload

    implementation_source = opaque(
        LOCAL + "backend-lock-wrapper-v1",
        "nxp-kl25-openocd-implementation-source-v1",
        "implementation_source",
        legacy_release_digest=CONTRACT["legacy_release"]["release_digest"],
        legacy_lock_digest=legacy["backend_lock"]["lock_digest"],
        commit=legacy["backend_lock"]["commit"],
        files=legacy["backend_lock"]["files"],
    )
    constraints = opaque(
        LOCAL + "backend-constraint-wrapper-v1",
        "nxp-kl25-openocd-constraints-v1",
        "vendor_backend_constraints",
        legacy_lock_digest=legacy["backend_lock"]["lock_digest"],
        admitted_constraints=legacy["backend_lock"]["admitted_constraints"],
        trust_boundary=legacy["backend_lock"]["trust_boundary"],
    )
    artifacts.update({implementation_source["artifact_id"]: implementation_source, constraints["artifact_id"]: constraints})
    backend = {
        "schema_id": GENERIC + "backend-implementation-binding-v1",
        "schema_version": "1.0.0",
        "artifact_id": "nxp-kl25-openocd-backend-v1",
        "artifact_type": "backend_implementation_binding",
        "backend_id": "nxp-kl25-openocd-backend-v1",
        "implementation": {"identity": "OpenOCD", "revision": legacy["backend_lock"]["commit"]},
        "implementation_evidence": [ref(implementation_source)],
        "vendor_constraint_payload": ref(constraints),
    }
    backend["lock_digest"] = canonical_digest(backend, omit=("artifact_digest", "lock_digest"))
    seal(backend)
    artifacts[backend["artifact_id"]] = backend

    envelope = seal(
        {
            "schema_id": GENERIC + "canonical-admission-envelope-v1",
            "schema_version": "1.0.0",
            "artifact_id": "nxp-kl25-canonical-admission-envelope-v1",
            "artifact_type": "canonical_admission_envelope",
            "target": CONTRACT["target"],
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

    operation_rows = []
    for legacy_name, row in legacy["operations"]["operations"].items():
        request_name = CONTRACT["operation_mapping"][legacy_name]
        contract_payload: dict[str, Any] = {
            "request_operation": request_name,
            "target_operation": legacy_name,
            "state": row["state"],
        }
        if legacy_name == "ERASE_SECTOR":
            contract_payload["erase_scope"] = "exact_sector_range"
            contract_payload["implicit_range_padding"] = False
        if "reason" in row:
            contract_payload["reason"] = row["reason"]
        operation_contract = opaque(
            LOCAL + "operation-contract-v1",
            "nxp-kl25-operation-contract-" + legacy_name.lower().replace("_", "-") + "-v1",
            "operation_contract",
            **contract_payload,
        )
        artifacts[operation_contract["artifact_id"]] = operation_contract
        required = row.get("required_fields", [])
        operation_rows.append(
            {
                "request_operation": request_name,
                "operation_contract_id": operation_contract["artifact_id"],
                "operation_contract_digest": operation_contract["artifact_digest"],
                "state": row["state"],
                "canonical_admission_digest": envelope["artifact_digest"],
                "backend_id": backend["backend_id"],
                "backend_lock_digest": backend["lock_digest"],
                "compiler_id": COMPILER_ID,
                "canonical_requirements": [
                    {"artifact": ref(vendor_payload), "pointer": _pointer(path)} for path in required
                ],
                "unresolved_requirements": [] if row["state"] == "ADMITTED" else [row["reason"]],
                "hardware_runtime_ready": False,
            }
        )
    operation_admission = seal(
        {
            "schema_id": GENERIC + "operation-admission-v1",
            "schema_version": "1.0.0",
            "artifact_id": "nxp-kl25-operation-admission-v1",
            "artifact_type": "operation_admission",
            "target": CONTRACT["target"],
            "operations": operation_rows,
        }
    )
    artifacts[operation_admission["artifact_id"]] = operation_admission
    return {
        "artifacts": artifacts,
        "compiler_bindings": {backend["backend_id"]: [COMPILER_ID]},
        "root_envelope_id": envelope["artifact_id"],
        "operation_admission_id": operation_admission["artifact_id"],
    }


def validate_projection(package: dict[str, Any]) -> dict[str, Any]:
    result = validate_admission_package(package)
    expected = CONTRACT["expected_counts"]
    require(result["candidate_count"] == expected["candidates"], "generic candidate count mismatch")
    require(result["operation_count"] == expected["admitted_operations"] + expected["blocked_operations"], "generic operation count mismatch")
    require(result["admitted_operation_count"] == expected["admitted_operations"], "generic admitted operation count mismatch")
    operations = package["artifacts"][package["operation_admission_id"]]["operations"]
    states = {row["request_operation"]: row["state"] for row in operations}
    require({name for name, state in states.items() if state == "ADMITTED"} == {"READ", "VERIFY", "PROGRAM", "ERASE"}, "admitted operation set mismatch")
    require(all(row["hardware_runtime_ready"] is False for row in operations), "hardware runtime readiness must remain false")
    return result


def write_json_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def build_sidecar(run_dir: Path, gate58_dir: Path, release_dir: Path, output_dir: Path) -> dict[str, Any]:
    legacy = validate_legacy_inputs(run_dir, gate58_dir, release_dir)
    package = build_package(legacy)
    generic = validate_projection(package)
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json_new(output_dir / PACKAGE_FILE, package)
    qualification = {
        "schema_version": "1.0.0",
        "artifact_type": "nxp_kl25_vendor_neutral_admission_qualification",
        "legacy_validation": legacy["legacy_validation"],
        "generic_validation": generic,
        "legacy_release_digest": CONTRACT["legacy_release"]["release_digest"],
        "legacy_backend_lock_digest": CONTRACT["legacy_release"]["backend_lock_digest"],
        "generic_backend_lock_digest": package["artifacts"]["nxp-kl25-openocd-backend-v1"]["lock_digest"],
        "hardware_runtime_ready": False,
    }
    write_json_new(output_dir / "qualification.json", qualification)
    files = {name: sha256_file(output_dir / name) for name in (PACKAGE_FILE, "qualification.json")}
    manifest = {
        "schema_version": "1.0.0",
        "artifact_type": "nxp_kl25_vendor_neutral_sidecar_release_manifest",
        "source_release_digest": CONTRACT["legacy_release"]["release_digest"],
        "retained_run_id": CONTRACT["retained_run"]["run_id"],
        "gate58_review_view_digest": CONTRACT["gate58"]["review_view_digest"],
        "files": files,
        "release_digest": _manifest_digest(files),
    }
    write_json_new(output_dir / "release-manifest.json", manifest)
    return {**qualification, "sidecar_release_digest": manifest["release_digest"]}


def validate_sidecar(run_dir: Path, gate58_dir: Path, release_dir: Path, sidecar_dir: Path) -> dict[str, Any]:
    legacy = validate_legacy_inputs(run_dir, gate58_dir, release_dir)
    package = read_json(sidecar_dir / PACKAGE_FILE)
    require(package == build_package(legacy), "sidecar projection differs from deterministic legacy projection")
    generic = validate_projection(package)
    manifest = read_json(sidecar_dir / "release-manifest.json")
    require(manifest.get("source_release_digest") == CONTRACT["legacy_release"]["release_digest"], "sidecar source release mismatch")
    require(manifest.get("retained_run_id") == CONTRACT["retained_run"]["run_id"], "sidecar retained run mismatch")
    require(manifest.get("gate58_review_view_digest") == CONTRACT["gate58"]["review_view_digest"], "sidecar Gate 5.8 binding mismatch")
    files = manifest.get("files")
    require(isinstance(files, dict), "sidecar file manifest missing")
    for name, digest in files.items():
        require((sidecar_dir / name).is_file() and sha256_file(sidecar_dir / name) == digest, f"sidecar file drifted: {name}")
    require(manifest.get("release_digest") == _manifest_digest(files), "sidecar release digest mismatch")
    qualification = read_json(sidecar_dir / "qualification.json")
    require(qualification.get("legacy_validation") == legacy["legacy_validation"], "sidecar legacy qualification mismatch")
    require(qualification.get("generic_validation") == generic, "sidecar generic qualification mismatch")
    require(qualification.get("hardware_runtime_ready") is False, "sidecar cannot claim hardware readiness")
    return {**qualification, "sidecar_release_digest": manifest["release_digest"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--gate58-dir", type=Path, required=True)
        command.add_argument("--legacy-release-dir", type=Path, required=True)
        command.add_argument("--sidecar-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build_sidecar(args.run_dir, args.gate58_dir, args.legacy_release_dir, args.sidecar_dir)
    else:
        result = validate_sidecar(args.run_dir, args.gate58_dir, args.legacy_release_dir, args.sidecar_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
