#!/usr/bin/env python3
"""STM32L4 L4.3 deterministic manufacturer-metadata planner."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32l4_metadata_policy import FAMILY, METADATA_FIELDS, build_candidate_inputs, build_metadata_row, load_ordering_authority
from stm32l4_phase_l4_1_foundation import validate_production_prestate
from validate_stm32l4_phase_l4_2_retained_evidence import main as validate_retained

HERE = Path(__file__).resolve().parent
PHASE = "L4.3"
ADMISSION_PHASE = "L4.4"
PRODUCTION = HERE / "stm32-post-l0-production-manifest-prestate.json"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"


def _set_sha(values: list[str]) -> str:
    return hashlib.sha256(("".join(value + "\n" for value in sorted(values))).encode()).hexdigest()


def _rows_sha(rows: list[dict[str, str]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def production_snapshot() -> dict[str, Any]:
    payload = validate_production_prestate(PRODUCTION)
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("L4.3 Production prestate sources missing")
    counts = {item.get("family"): item.get("row_count") for item in sources if isinstance(item, dict)}
    if any(not isinstance(k, str) or not isinstance(v, int) for k, v in counts.items()):
        raise RuntimeError("L4.3 Production family counts malformed")
    bases: set[tuple[str, str]] = set()
    for source in sources:
        family = source["family"]
        path = (PRODUCTION.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != source["row_count"]:
            raise RuntimeError(f"{family}: Production prestate source count drifted")
        for row in rows:
            bases.add((family, row["base_device"]))
    exact_count = sum(counts.values())
    if exact_count != 1272 or len(bases) != 392 or counts.get(FAMILY, 0) != 0 or len(counts) != 11:
        raise RuntimeError("L4.3 Production aggregate prestate drifted")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(bases),
        "family_count": len(counts),
        "family_exact_icpn_counts": counts,
        "stm32l4_exact_icpn_count": 0,
        "manifest_sha256": EXPECTED_PRODUCTION_PRESTATE_SHA256,
    }


def contract() -> dict[str, Any]:
    return {
        "identity_lifecycle_authority": "retained L4.2 official ST dual-surface exact-set evidence",
        "metadata_authority": "official ST datasheet Ordering Information",
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
        raise RuntimeError("L4.2 retained evidence validation failed")
    load_ordering_authority()
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
        items.append({"base_device": candidate["base_device"], "icpn": candidate["icpn"], "decision": decision, "issues": issues, "metadata": row})
    items.sort(key=lambda x: (x["base_device"], x["icpn"]))
    rows.sort(key=lambda x: (x["base_device"], x["icpn"]))
    dist = {field: dict(sorted(Counter(row[field] for row in rows).items())) for field in ("flash_size", "package", "pin_count", "temperature_grade", "option_suffix", "series")}
    ready = [x["icpn"] for x in items if x["decision"] == "metadata_ready"]
    manual = [x["icpn"] for x in items if x["decision"] == "manual_review_required"]
    rejected = [x["icpn"] for x in items if x["decision"] == "reject"]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "candidate_count": len(items),
        "base_device_count": len({x["base_device"] for x in items}),
        "decision_counts": {"metadata_ready": counts["metadata_ready"], "manual_review_required": counts["manual_review_required"], "reject": counts["reject"]},
        "metadata_ready_set_sha256": _set_sha(ready),
        "manual_review_set_sha256": _set_sha(manual),
        "reject_set_sha256": _set_sha(rejected),
        "metadata_rows_sha256": _rows_sha(rows),
        "metadata_distribution": dist,
        "issues": sorted({issue for item in items for issue in item["issues"]}),
        "manual_review_base_devices": sorted({x["base_device"] for x in items if x["decision"] == "manual_review_required"}),
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
        plan.get("candidate_count") == 446
        and plan.get("base_device_count") == 138
        and dc == {"metadata_ready": 446, "manual_review_required": 0, "reject": 0}
        and plan.get("issues") == []
        and plan.get("manual_review_base_devices") == []
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == 1272
        and plan.get("production_snapshot", {}).get("base_device_count") == 392
        and plan.get("production_snapshot", {}).get("stm32l4_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False
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
        "metadata_rows_sha256", "metadata_distribution", "issues", "manual_review_base_devices",
        "production_snapshot", "metadata_contract",
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
