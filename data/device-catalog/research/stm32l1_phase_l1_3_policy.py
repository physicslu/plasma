#!/usr/bin/env python3
"""STM32L1 L1.3 deterministic manufacturer-metadata planner."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32l1_metadata_policy import (
    FAMILY,
    METADATA_FIELDS,
    build_candidate_inputs,
    build_metadata_row,
    load_exact_variant_exceptions,
    load_ordering_authority,
)
from validate_stm32l1_phase_l1_2_retained_evidence import (
    EXPECTED_ACTIVE_SET_SHA256,
    main as validate_retained,
)

HERE = Path(__file__).resolve().parent
PHASE = "L1.3"
ADMISSION_PHASE = "L1.4"
PRODUCTION = HERE.parent / "production" / "icpn-v1-manifest.json"
EXPECTED_PRODUCTION_GIT_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"
EXPECTED_CANDIDATE_COUNT = 144
EXPECTED_BASE_DEVICE_COUNT = 59


def _set_sha(values: list[str]) -> str:
    return hashlib.sha256(("".join(value + "\n" for value in sorted(values))).encode()).hexdigest()


def _rows_sha(rows: list[dict[str, str]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def production_snapshot() -> dict[str, Any]:
    if _git_blob_sha(PRODUCTION) != EXPECTED_PRODUCTION_GIT_BLOB:
        raise RuntimeError("L1.3 Production manifest Git blob drifted")
    payload = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "production":
        raise RuntimeError("L1.3 Production manifest invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("L1.3 Production sources missing")
    counts = {item.get("family"): item.get("row_count") for item in sources if isinstance(item, dict)}
    if any(not isinstance(k, str) or not isinstance(v, int) for k, v in counts.items()):
        raise RuntimeError("L1.3 Production family counts malformed")
    bases: set[tuple[str, str]] = set()
    for source in sources:
        family = source["family"]
        path = (PRODUCTION.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != source["row_count"]:
            raise RuntimeError(f"{family}: Production source count drifted")
        for row in rows:
            bases.add((family, row["base_device"]))
    exact_count = sum(counts.values())
    if exact_count != 1718 or len(bases) != 530 or counts.get(FAMILY, 0) != 0 or len(counts) != 12:
        raise RuntimeError("L1.3 Production aggregate prestate drifted")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(bases),
        "family_count": len(counts),
        "family_exact_icpn_counts": counts,
        "stm32l1_exact_icpn_count": 0,
        "manifest_git_blob": EXPECTED_PRODUCTION_GIT_BLOB,
    }


def contract() -> dict[str, Any]:
    return {
        "identity_lifecycle_authority": "retained L1.2 official ST exact-set evidence",
        "metadata_authority": "official ST datasheet Ordering Information across ten deterministic records",
        "generation_migration_authority": "TN1176",
        "exact_variant_exception_count": 0,
        "exact_variant_exceptions_expand_identity_scope": False,
        "canonical_admission_authorized": False,
        "production_write_authorized": False,
        "programming_policy_defined": False,
        "flash_geometry_qualified": False,
        "option_security_semantics_qualified": False,
        "physical_hil_qualified": False,
        "runtime_programming_support_claimed": False,
        "openocd_routing_gates_metadata": False,
        "cmsis_alias_gates_metadata": False,
        "scope_expansion_authorized": False,
        "admission_deferred_to": ADMISSION_PHASE,
    }


def build_plan() -> dict[str, Any]:
    if validate_retained() != 0:
        raise RuntimeError("L1.2 retained evidence validation failed")
    load_ordering_authority()
    load_exact_variant_exceptions()
    items: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    rows: list[dict[str, str]] = []
    for candidate in build_candidate_inputs():
        decision = "metadata_ready"
        issues: list[str] = []
        row = None
        try:
            row = build_metadata_row(candidate, list(METADATA_FIELDS))
        except CandidateManualReview as exc:
            decision = "manual_review_required"
            issues = [str(exc)]
        except CandidateReject as exc:
            decision = "reject"
            issues = [str(exc)]
        counts[decision] += 1
        if row is not None:
            rows.append(row)
        items.append({
            "base_device": candidate["base_device"],
            "icpn": candidate["icpn"],
            "decision": decision,
            "issues": issues,
            "metadata": row,
        })
    items.sort(key=lambda x: (x["base_device"], x["icpn"]))
    rows.sort(key=lambda x: (x["base_device"], x["icpn"]))
    dist = {
        field: dict(sorted(Counter(row[field] for row in rows).items()))
        for field in ("flash_size", "package", "pin_count", "temperature_grade", "option_suffix", "series")
    }
    ready = [x["icpn"] for x in items if x["decision"] == "metadata_ready"]
    manual = [x["icpn"] for x in items if x["decision"] == "manual_review_required"]
    rejected = [x["icpn"] for x in items if x["decision"] == "reject"]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "candidate_count": len(items),
        "base_device_count": len({x["base_device"] for x in items}),
        "decision_counts": {
            "metadata_ready": counts["metadata_ready"],
            "manual_review_required": counts["manual_review_required"],
            "reject": counts["reject"],
        },
        "metadata_ready_set_sha256": _set_sha(ready),
        "manual_review_set_sha256": _set_sha(manual),
        "reject_set_sha256": _set_sha(rejected),
        "metadata_rows_sha256": _rows_sha(rows),
        "metadata_distribution": dist,
        "exact_variant_exception_icpns": [],
        "issues": sorted({issue for item in items for issue in item["issues"]}),
        "manual_review_base_devices": sorted({
            x["base_device"] for x in items if x["decision"] == "manual_review_required"
        }),
        "production_snapshot": production_snapshot(),
        "metadata_contract": contract(),
        "canonical_dataset_admission": "deferred",
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "physical_hil_qualified": False,
        "runtime_support_claimed": False,
        "candidates": items,
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    dc = plan.get("decision_counts", {})
    return (
        plan.get("candidate_count") == EXPECTED_CANDIDATE_COUNT
        and plan.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT
        and dc == {"metadata_ready": 144, "manual_review_required": 0, "reject": 0}
        and plan.get("metadata_ready_set_sha256") == EXPECTED_ACTIVE_SET_SHA256
        and plan.get("exact_variant_exception_icpns") == []
        and plan.get("issues") == []
        and plan.get("manual_review_base_devices") == []
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == 1718
        and plan.get("production_snapshot", {}).get("base_device_count") == 530
        and plan.get("production_snapshot", {}).get("family_count") == 12
        and plan.get("production_snapshot", {}).get("stm32l1_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False
        and plan.get("metadata_contract", {}).get("exact_variant_exception_count") == 0
        and plan.get("metadata_contract", {}).get("exact_variant_exceptions_expand_identity_scope") is False
        and set(plan.get("metadata_contract", {}).get(key) for key in (
            "canonical_admission_authorized", "production_write_authorized", "programming_policy_defined",
            "flash_geometry_qualified", "option_security_semantics_qualified", "physical_hil_qualified",
            "runtime_programming_support_claimed", "scope_expansion_authorized",
        )) == {False}
    )


def summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: plan[key] for key in (
        "phase", "family", "candidate_count", "base_device_count", "decision_counts",
        "metadata_ready_set_sha256", "manual_review_set_sha256", "reject_set_sha256",
        "metadata_rows_sha256", "metadata_distribution", "exact_variant_exception_icpns", "issues",
        "manual_review_base_devices", "production_snapshot", "metadata_contract",
    )}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    value = summary(plan) if args.summary_only else plan
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if plan_is_clean(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
