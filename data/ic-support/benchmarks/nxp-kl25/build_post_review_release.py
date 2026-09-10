#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import canonical_admission
import gate58_review
import post_review_disposition as disposition

HERE = Path(__file__).resolve().parent
RM = disposition.CONTRACT["manufacturer_sources"]["nxp_kl25_rm_rev3"]
DS = disposition.CONTRACT["manufacturer_sources"]["nxp_kl25_ds_rev5"]
BACKEND = json.loads((HERE / "backend-implementation-lock.json").read_text())


def evidence(page: int, locator: str, source_id: str = "nxp_kl25_rm_rev3") -> dict[str, Any]:
    return {"source_id": source_id, "pdf_page_number": page, "source_sha256": RM if source_id.endswith("rm_rev3") else DS, "locator": locator}


CORRECTIONS: dict[str, tuple[str, list[tuple[str, str, list[dict[str, Any]]]]]] = {
    "nxp-kl25-erase-all-blocks-v0-002": ("CITATION_SUPPLEMENT_FOR_CANONICAL", [("launch", "After loading FCCOB0 with 0x44, Erase All Blocks is launched by writing 1 to FSTAT[CCIF] to clear CCIF.", [evidence(425, "27.3.3.1 FSTAT CCIF"), evidence(452, "27.4.10.9")])]),
    "nxp-kl25-erase-sector-v0-f004": ("CITATION_SUPPLEMENT_FOR_CANONICAL", [("launch", "Erase Flash Sector is launched by writing 1 to FSTAT[CCIF] to clear CCIF after its FCCOB parameters are loaded.", [evidence(425, "27.3.3.1 FSTAT CCIF"), evidence(446, "27.4.10.5")])]),
    "nxp-kl25-erase-sector-v0-f011": ("CITATION_SUPPLEMENT_FOR_CANONICAL", [("suspend", "During Erase Flash Sector, FTFA samples FCNFG[ERSSUSP] at convenient points; when it detects ERSSUSP set, it suspends the operation and sets FSTAT[CCIF].", [evidence(446, "27.4.10.5.1 first paragraph"), evidence(447, "27.4.10.5.1 continuation")])]),
    "nxp-kl25-flash-security-v0-001": ("REPLACE_WITH_MANUFACTURER_FACT", [("normal", "In NVM Normal mode the full FTFA command set is available in both the unsecure and secure chip security states.", [evidence(454, "Table 27-51 NVM Normal row")]), ("special-secure", "In NVM Special mode with a secure chip, FTFA access is restricted to Erase All Blocks and Read 1s All Blocks.", [evidence(454, "Table 27-51 NVM Special/Secure cell")])]),
    "nxp-kl25-ftfa-command-sequencing-v0-025": ("SPLIT", [("behavior", "Erase All Blocks erases the program flash block, verifies the erased state, and releases MCU security.", [evidence(439, "Table 27-24 FCMD 0x44")]), ("protection", "The commanded Erase All Blocks operation is possible only when all program flash locations are unprotected.", [evidence(439, "Table 27-24 FCMD 0x44 note"), evidence(452, "27.4.10.9")])]),
    "nxp-kl25-ftfa-command-sequencing-v0-028": ("REPLACE_WITH_MANUFACTURER_FACT", [("normal-meen10", "In NVM Normal mode, Read 1s All Blocks (0x40) and Erase All Blocks (0x44) are executable when MEEN=10.", [evidence(439, "Table 27-25 rows 0x40 and 0x44, NVM Normal MEEN=10")])]),
    "nxp-kl25-program-longword-v0-005": ("SPLIT", [("direction", "Program Longword can move NVM bits only from erased 1 to programmed 0.", [evidence(445, "27.4.10.4 programming direction")]), ("cumulative", "Cumulative programming of a flash location without an intervening erase, including reprogramming existing 0 bits to 0, is not allowed.", [evidence(445, "27.4.10.4 CAUTION")])]),
    "nxp-kl25-swd-mdm-ap-v0-008": ("NARROW", [("gated", "Setting MDM-AP Control bit 0 requests mass erase only when MEEN and SEC permit mass erase; hardware clears the bit after completion. If mass erase is disabled, no erase request occurs and the bit remains asserted until system reset.", [evidence(153, "Table 9-3 bit 0")])]),
    "nxp-kl25-swd-mdm-ap-v0-013": ("NARROW", [("reset-exception", "MDM-AP Control VLLDBGREQ configures reset hold after the next VLLSx recovery, except that it is ignored for VLLS wakeup through the Reset pin.", [evidence(154, "Table 9-3 bit 5")])]),
    "nxp-kl25-swd-mdm-ap-v0-028": ("NARROW", [("sleeping", "When MDM-AP Status SLEEPING is 1, SLEEPDEEP=0 indicates wait or VLPW and SLEEPDEEP=1 indicates stop or VLPS.", [evidence(156, "Table 9-4 bit 18")])]),
}


def digest(value: dict[str, Any], key: str) -> str:
    return disposition.canonical_digest(value, key)


def build(view: dict[str, Any], verdict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verdicts = {x["fact_id"]: x for x in verdict["fact_verdicts"]}
    rows = []
    reviews = []
    for unit in view["units"]:
        uid = unit["primary_unit_id"]
        for fact in unit["facts"]:
            fid = fact["fact_id"]
            if fid in CORRECTIONS:
                action, definitions = CORRECTIONS[fid]
                projection = "CANONICAL_REQUIRED" if "swd-mdm" not in fid and "flash-security" not in fid else "KNOWLEDGE_ONLY"
            else:
                action = "ACCEPT"
                definitions = [("accepted", fact["statement"], [evidence(c["pdf_page_number"], "retained fact citation", c["source_id"]) for c in fact["all_citations"]])]
                projection = "EXECUTION_PROFILE_REQUIRED" if any(x in uid for x in ("program-longword", "erase-sector")) else "KNOWLEDGE_ONLY"
            candidates = []
            for suffix, statement, refs in definitions:
                candidate = {"candidate_id": f"{fid}-{suffix}", "statement": statement, "evidence": refs}
                candidate["candidate_digest"] = digest(candidate, "candidate_digest")
                candidates.append(candidate)
                if action != "ACCEPT":
                    review = {"candidate_id": candidate["candidate_id"], "candidate_digest": candidate["candidate_digest"], **disposition.PASS, "reviewer_rationale": "Explicitly reviewed against the cited locked NXP manufacturer evidence after Gate 5.8 disposition."}
                    reviews.append(review)
            rows.append({"primary_unit_id": uid, "fact_id": fid, "fact_digest": fact["fact_digest"], "action": action, "projection_state": projection, "rationale": verdicts[fid]["rationale"], "candidates": candidates})
    artifact = {"schema_version": "0.1.0", "artifact_type": "post_review_disposition", "source": disposition.CONTRACT["source"], "dispositions": rows}
    artifact["artifact_digest"] = digest(artifact, "artifact_digest")
    review_artifact = {"schema_version": "0.1.0", "artifact_type": "kl25_candidate_manufacturer_review", "review_basis": "explicit_manufacturer_evidence_review", "deterministic_semantic_authority": False, "candidate_reviews": reviews, "supplemental_reviews": []}
    review_artifact["review_digest"] = digest(review_artifact, "review_digest")
    return artifact, review_artifact


def direct_review(review: dict[str, Any], review_id: str, path: str, refs: list[dict[str, Any]]) -> None:
    review["supplemental_reviews"].append({"review_record_id": review_id, "path": path, "evidence": refs, **disposition.PASS, "reviewer_rationale": "Explicitly reviewed against locked manufacturer evidence for the canonical field."})


def canonical(artifact: dict[str, Any], review: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidates = {c["candidate_id"]: c for d in artifact["dispositions"] for c in d["candidates"]}
    def ids(fragment: str) -> list[str]:
        found = [cid for cid in candidates if fragment in cid]
        if not found:
            raise RuntimeError(f"candidate not found: {fragment}")
        return found
    fields = []
    def field(path: str, value: Any, candidate_ids: list[str] | None = None, refs: list[dict[str, Any]] | None = None) -> None:
        review_id = None
        refs = refs or []
        if refs:
            review_id = "review-" + path.replace(".", "-").replace("_", "-")
            direct_review(review, review_id, path, refs)
        fields.append({"path": path, "value": value, "candidate_ids": candidate_ids or [], "manufacturer_evidence": refs, "review_record_id": review_id})
    field("target.icpn", "MKL25Z128VLK4", refs=[evidence(2, "Ordering Information / MKL25Z128VLK4", "nxp_kl25_ds_rev5")])
    field("memory.main_flash_start", "0x00000000", refs=[evidence(73, "Table 3-27 MKL25Z128VLK4 address range")])
    field("memory.main_flash_size_bytes", 131072, refs=[evidence(2, "Ordering Information / MKL25Z128VLK4 Flash 128 KB", "nxp_kl25_ds_rev5"), evidence(73, "Table 3-27")])
    field("memory.main_flash_end", "0x0001FFFF", refs=[evidence(73, "Table 3-27 MKL25Z128VLK4")])
    field("memory.sector_size_bytes", 1024, refs=[evidence(420, "27.1.1.1 Sector size")])
    field("memory.sector_count", 128, refs=[evidence(73, "Table 3-27"), evidence(420, "27.1.1.1 Sector size")])
    field("silicon.program_primitive", "Program Longword", ids("program-longword-v0-001"))
    field("silicon.program_granularity_bytes", 4, ids("program-longword-v0-001"))
    field("silicon.program_start_alignment_bytes", 4, ids("program-longword-v0-003"))
    field("silicon.program_direction", "erased_1_to_programmed_0", ids("program-longword-v0-005-direction"))
    field("silicon.cumulative_programming_allowed", False, ids("program-longword-v0-005-cumulative"))
    field("silicon.erase_primitive", "Erase Flash Sector", ids("erase-sector-v0-f001"))
    field("silicon.command_interface", "FCCOB/FSTAT", ids("ftfa-register-model-v0-019") + ids("ftfa-register-model-v0-001"))
    field("safety.flash_configuration_field_start", "0x00000400", refs=[evidence(423, "27.3.1 Flash Configuration Field")])
    field("safety.flash_configuration_field_size_bytes", 16, refs=[evidence(423, "27.3.1 Flash Configuration Field")])
    field("security.destructive_operations_admitted", False, ids("debug-security-interaction-v0-009"))
    review["review_digest"] = digest(review, "review_digest")
    spec = {"schema_version": "0.1.0", "artifact_type": "nxp_kl25_canonical_specification", "target": "MKL25Z128VLK4", "applicability": {"exact_target_evidence": canonical_admission.CONTRACT["required_target_evidence"]}, "silicon": {"controller": "FTFA", "debug": "SWD/MDM-AP", "backend_constraints_included": False}, "canonical_fields": fields, "blocked_fields": [{"path": "package.minimum_programming_hardware", "reason": "not required for fake-process Software Executor validation"}, {"path": "security.destructive_workflows", "reason": "explicitly outside milestone and not admitted"}]}
    spec["spec_digest"] = digest(spec, "spec_digest")
    programming = {"schema_version": "0.1.0", "profile_id": "nxp-kl25-ftfa-programming-v0", "kind": "programming", "status": "software_executor_candidate", "canonical_spec_digest": spec["spec_digest"], "data": {"controller": "FTFA", "program_primitive": "Program Longword", "program_granularity_bytes": 4, "silicon_program_start_alignment_bytes": 4, "program_direction": "erased_1_to_programmed_0", "cumulative_programming_allowed": False, "erase_primitive": "Erase Flash Sector"}}
    programming["profile_digest"] = digest(programming, "profile_digest")
    geometry = {"schema_version": "0.1.0", "profile_id": "nxp-mkl25z128-128k-v0", "kind": "memory_geometry", "status": "software_executor_candidate", "canonical_spec_digest": spec["spec_digest"], "data": {"main_flash_start": "0x00000000", "main_flash_size_bytes": 131072, "main_flash_end": "0x0001FFFF", "page_size_bytes": 1024, "page_count": 128, "erase_granularity_bytes": 1024, "program_granularity_bytes": 4, "flash_configuration_field_start": "0x00000400", "flash_configuration_field_size_bytes": 16}}
    geometry["profile_digest"] = digest(geometry, "profile_digest")
    return spec, programming, geometry, review


def operation_matrix(spec: dict[str, Any]) -> dict[str, Any]:
    fields = {f["path"] for f in spec["canonical_fields"]}
    req = {
        "READ": ["memory.main_flash_start", "memory.main_flash_size_bytes"],
        "VERIFY": ["memory.main_flash_start", "memory.main_flash_size_bytes"],
        "PROGRAM": ["memory.main_flash_start", "memory.main_flash_size_bytes", "silicon.program_granularity_bytes", "safety.flash_configuration_field_start"],
        "ERASE_SECTOR": ["memory.main_flash_start", "memory.main_flash_size_bytes", "memory.sector_size_bytes", "safety.flash_configuration_field_start"],
    }
    operations = {name: {"state": "ADMITTED" if set(paths) <= fields else "BLOCKED", "required_fields": paths, "canonical_spec_digest": spec["spec_digest"], "backend_lock_digest": BACKEND["lock_digest"], "hardware_runtime_ready": False} for name, paths in req.items()}
    operations.update({name: {"state": "BLOCKED", "reason": "outside frozen non-destructive Software Executor scope", "hardware_runtime_ready": False} for name in canonical_admission.CONTRACT["forbidden_operations"]})
    value = {"schema_version": "0.1.0", "artifact_type": "kl25_software_executor_operation_admission", "operations": operations}
    value["admission_digest"] = digest(value, "admission_digest")
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gate58-dir", type=Path, required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    args = parser.parse_args()
    args.staging_dir.mkdir(parents=True, exist_ok=False)
    view = gate58_review.read_json(args.gate58_dir / "review-view.json")
    verdict = gate58_review.read_json(args.gate58_dir / "review-verdict.json")
    report = gate58_review.qualify_review(args.run_dir, verdict)
    if report.get("report_digest") != disposition.CONTRACT["source"]["qualification_digest"] or report.get("status") != "REJECTED_REVIEW":
        raise RuntimeError("frozen Gate 5.8 rejection binding mismatch")
    artifact, review = build(view, verdict)
    disposition.validate_disposition(view, verdict, artifact)
    spec, programming, geometry, review = canonical(artifact, review)
    operations = operation_matrix(spec)
    result = canonical_admission.validate(artifact, review, spec, operations)
    outputs = {"post-review-disposition.json": artifact, "candidate-manufacturer-review.json": review, "canonical-specification.json": spec, "programming-profile.json": programming, "memory-geometry-profile.json": geometry, "operation-admission.json": operations, "qualification.json": result, "backend-implementation-lock.json": BACKEND}
    for name, value in outputs.items():
        write_new(args.staging_dir / name, value)
    release_payload = {name: hashlib.sha256((args.staging_dir / name).read_bytes()).hexdigest() for name in sorted(outputs)}
    release_digest = hashlib.sha256(json.dumps(release_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    write_new(args.staging_dir / "release-manifest.json", {"schema_version": "0.1.0", "artifact_type": "kl25_post_review_release_manifest", "files": release_payload, "release_digest": release_digest})
    print(json.dumps({**result, "release_digest": release_digest, "action_counts": disposition.validate_disposition(view, verdict, artifact)["action_counts"], "candidate_count": sum(len(d["candidates"]) for d in artifact["dispositions"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
