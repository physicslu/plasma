#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEX64 = re.compile(r"^[0-9a-f]{64}$")
BOUND = "BOUND"
UNKNOWN = "UNKNOWN"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence_key(item: dict) -> tuple[str, int, str]:
    source_id = item.get("source_id")
    page = item.get("pdf_page_number")
    digest = item.get("page_text_sha256")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("evidence source_id must be a non-empty string")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("evidence pdf_page_number must be a positive integer")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ValueError("evidence page_text_sha256 must be a lowercase SHA-256 hex digest")
    return source_id, page, digest


def validate_common_identity(contract: dict, definitions: dict, evidence_lock: dict, reviewed: dict) -> None:
    expected = {
        "target": contract["target"],
        "applicability_id": contract["applicability_id"],
        "source_lock_id": contract["source_lock_id"],
    }
    for name, value in expected.items():
        if evidence_lock.get(name) != value:
            raise ValueError(f"evidence lock {name} mismatch")
        if reviewed.get(name) != value:
            raise ValueError(f"reviewed claims {name} mismatch")
    if definitions.get("target") != contract["target"]:
        raise ValueError("definition target mismatch")
    if definitions.get("source_lock_id") != contract["source_lock_id"]:
        raise ValueError("definition source lock mismatch")
    if reviewed.get("definition_set_id") != definitions.get("definition_set_id"):
        raise ValueError("reviewed claims definition set mismatch")


def evidence_lock_index(evidence_lock: dict) -> dict[str, set[tuple[str, int, str]]]:
    out: dict[str, set[tuple[str, int, str]]] = {}
    for claim_id, claim in evidence_lock.get("claims", {}).items():
        out[claim_id] = {evidence_key(item) for item in claim.get("selected_evidence", [])}
    return out


def validate_reviewed_claims(contract: dict, evidence_lock: dict, reviewed: dict, evidence_lock_path: Path) -> None:
    artifact = reviewed.get("candidate_artifact", {})
    if artifact.get("evidence_lock_path") != evidence_lock_path.name:
        raise ValueError("reviewed claims evidence-lock path mismatch")
    expected_lock_digest = artifact.get("evidence_lock_sha256")
    if not isinstance(expected_lock_digest, str) or not HEX64.fullmatch(expected_lock_digest):
        raise ValueError("evidence-lock SHA-256 is invalid")
    if sha256_file(evidence_lock_path) != expected_lock_digest:
        raise ValueError("evidence-lock SHA-256 mismatch")

    generation = evidence_lock.get("generation", {})
    for key in [
        "candidate_file_sha256",
        "github_actions_run_id",
        "github_actions_artifact_id",
        "github_actions_artifact_digest",
        "generation_head",
        "preprocessing",
    ]:
        reviewed_key = "file_sha256" if key == "candidate_file_sha256" else key
        if artifact.get(reviewed_key) != generation.get(key):
            raise ValueError(f"candidate provenance mismatch: {key}")

    contract_claims = contract["candidate_claims"]
    reviewed_claims = reviewed.get("claims", {})
    if set(reviewed_claims) != set(contract_claims):
        raise ValueError("reviewed claim set does not match applicability contract")
    if set(evidence_lock.get("claims", {})) != set(contract_claims):
        raise ValueError("evidence-lock claim set does not match applicability contract")
    index = evidence_lock_index(evidence_lock)

    for claim_id, policy in contract_claims.items():
        item = reviewed_claims[claim_id]
        status = item.get("review_status")
        evidence = item.get("evidence", [])
        if status == "REVIEWED":
            if not evidence:
                raise ValueError(f"reviewed claim {claim_id} has no retained evidence")
            for ref in evidence:
                if evidence_key(ref) not in index.get(claim_id, set()):
                    raise ValueError(f"reviewed evidence for {claim_id} is not in retained candidate evidence")
        elif status == "ABSENT_REVIEWED":
            if not policy.get("optional"):
                raise ValueError(f"required claim {claim_id} cannot be absent-reviewed")
            if evidence:
                raise ValueError(f"absent-reviewed claim {claim_id} must not contain evidence")
            if item.get("absence_policy") != policy.get("absence_policy"):
                raise ValueError(f"absence policy mismatch for {claim_id}")
            if evidence_lock["claims"][claim_id].get("candidate_count") != 0:
                raise ValueError(f"claim {claim_id} cannot be absent-reviewed when candidates exist")
        elif status == "PENDING":
            for ref in evidence:
                if evidence_key(ref) not in index.get(claim_id, set()):
                    raise ValueError(f"pending evidence for {claim_id} is not in retained candidate evidence")
        else:
            raise ValueError(f"unsupported review status for {claim_id}: {status!r}")

    device_expr = reviewed_claims.get("TARGET_DEVICE_EXPRESSION", {})
    if device_expr.get("review_status") != "ABSENT_REVIEWED":
        raise ValueError("TARGET_DEVICE_EXPRESSION must remain ABSENT_REVIEWED for the retained KL25 evidence")
    if contract_claims["TARGET_DEVICE_EXPRESSION"].get("terms") != ["MKL25Z128"]:
        raise ValueError("unexpected intermediate device-expression policy")


def validate_exclusions(evidence_lock: dict, reviewed: dict) -> bool:
    block = reviewed.get("applicability_exclusions", {})
    if block.get("review_status") != "REVIEWED":
        return False
    entries = block.get("entries")
    if not isinstance(entries, list) or not entries:
        return False
    index = evidence_lock_index(evidence_lock)
    seen: set[str] = set()
    for entry in entries:
        exclusion_id = entry.get("exclusion_id")
        if not isinstance(exclusion_id, str) or not exclusion_id or exclusion_id in seen:
            raise ValueError("applicability exclusion IDs must be unique non-empty strings")
        seen.add(exclusion_id)
        anchor = entry.get("anchor_claim_id")
        if anchor not in index:
            raise ValueError(f"unknown exclusion anchor claim: {anchor}")
        if evidence_key(entry) not in index[anchor]:
            raise ValueError(f"exclusion evidence {exclusion_id} is not retained candidate evidence")
        if not isinstance(entry.get("effect"), str) or not entry["effect"].strip():
            raise ValueError(f"exclusion {exclusion_id} has no effect description")
    if block.get("destructive_security_operation_admission") is not False:
        raise ValueError("destructive security operation admission must remain false")
    return True


def derive(contract: dict, definitions: dict, evidence_lock: dict, reviewed: dict, evidence_lock_path: Path) -> dict:
    validate_common_identity(contract, definitions, evidence_lock, reviewed)
    validate_reviewed_claims(contract, evidence_lock, reviewed, evidence_lock_path)

    claims = reviewed["claims"]
    required_scope_claims = contract["scope_bridge"]["required_claims"]
    scope_missing = [
        claim_id
        for claim_id in required_scope_claims
        if claims.get(claim_id, {}).get("review_status") != "REVIEWED"
        or not claims.get(claim_id, {}).get("evidence")
    ]
    scope_status = BOUND if not scope_missing else UNKNOWN

    definitions_by_id = {unit["unit_id"]: unit for unit in definitions["units"]}
    if set(definitions_by_id) != set(contract["unit_requirements"]):
        raise ValueError("unit requirements do not exactly cover reviewed Evidence Unit definitions")

    section_review = reviewed.get("unit_section_review", {})
    reviewed_unit_ids = (
        set(section_review.get("unit_ids", []))
        if section_review.get("review_status") == "REVIEWED"
        else set()
    )
    if not reviewed_unit_ids.issubset(definitions_by_id):
        raise ValueError("unit section review references an unknown Evidence Unit")

    exclusions_reviewed = validate_exclusions(evidence_lock, reviewed)
    bindings: dict[str, dict] = {}
    for unit_id, requirements in contract["unit_requirements"].items():
        missing: list[str] = []
        if scope_status != BOUND:
            missing.append("scope_bridge_reviewed")
        if unit_id not in reviewed_unit_ids:
            missing.append("unit_section_within_applicable_manufacturer_document_reviewed")
        if not exclusions_reviewed:
            missing.append("applicability_exclusions_reviewed")
        for claim_id in requirements:
            claim = claims.get(claim_id, {})
            if claim.get("review_status") != "REVIEWED" or not claim.get("evidence"):
                missing.append(claim_id)
        status = BOUND if not missing else UNKNOWN
        unit = definitions_by_id[unit_id]
        bindings[unit_id] = {
            "status": status,
            "source_id": unit["source_id"],
            "pdf_page_range": unit["pdf_page_range"],
            "required_claims": list(requirements),
            "missing_prerequisites": missing,
        }

    all_bound = all(item["status"] == BOUND for item in bindings.values())
    catalog_admitted = (
        section_review.get("review_status") == "REVIEWED"
        and reviewed_unit_ids == set(definitions_by_id)
        and definitions.get("status") in {
            "reviewed_definitions_not_admitted_catalog",
            "admitted_evidence_unit_catalog",
        }
    )

    return {
        "schema_version": "0.1.0",
        "artifact_type": "deterministic_applicability_binding",
        "binding_id": "nxp-kl25-applicability-binding-v0",
        "applicability_id": contract["applicability_id"],
        "reviewed_claims_id": reviewed["reviewed_claims_id"],
        "definition_set_id": definitions["definition_set_id"],
        "source_lock_id": contract["source_lock_id"],
        "target": contract["target"],
        "scope_bridge": {
            "status": scope_status,
            "required_claims": list(required_scope_claims),
            "missing_prerequisites": scope_missing,
            "intermediate_device_expression_required": False,
            "fuzzy_identity_matching_used": False,
        },
        "applicability_exclusions_reviewed": exclusions_reviewed,
        "unit_bindings": bindings,
        "admission": {
            "scope_bridge": scope_status == BOUND,
            "evidence_unit_catalog": catalog_admitted,
            "applicability_binding": (
                all_bound and scope_status == BOUND and exclusions_reviewed and catalog_admitted
            ),
            "evidence_pack": False,
            "semantic_extraction": False,
            "canonical_dataset": False,
            "hil": False,
            "production": False,
            "destructive_security_operation": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive fail-closed KL25 Evidence Unit applicability bindings")
    parser.add_argument("--contract", type=Path, default=HERE / "applicability-contract.json")
    parser.add_argument("--definitions", type=Path, default=HERE / "reviewed-evidence-unit-definitions.json")
    parser.add_argument("--evidence-lock", type=Path, default=HERE / "retained-applicability-evidence-lock.json")
    parser.add_argument("--reviewed", type=Path, default=HERE / "reviewed-applicability-claims.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = derive(
        load_json(args.contract),
        load_json(args.definitions),
        load_json(args.evidence_lock),
        load_json(args.reviewed),
        args.evidence_lock,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"scope_bridge {result['scope_bridge']['status']}")
    for unit_id, item in result["unit_bindings"].items():
        print(f"{unit_id} {item['status']}")
    print(f"applicability_binding_admission {str(result['admission']['applicability_binding']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
