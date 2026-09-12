#!/usr/bin/env python3
"""Build deterministic retained STM32L4 L4.2 baseline from clean live evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from stm32l4_phase_l4_2_discovery import (
    COMMERCIAL_IDENTITY_AUTHORITY,
    EXPECTED_L4_1_BASELINE_SHA256,
)

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13"
DEFAULT_BASELINE = HERE / "stm32l4-phase-l4.2-discovery-baseline.json"
DEFAULT_MANIFEST = HERE / "stm32l4-phase-l4.2-discovery-manifest.json"
EXPECTED_OPENOCD_CATALOG_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_sha(values: list[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    summary = read_json(EVIDENCE / "live-summary.json")
    targets = read_json(EVIDENCE / "targets.json")
    provenance = read_json(EVIDENCE / "provenance.json")
    leaf = read_json(EVIDENCE / "leaf-digests.json")
    retained = read_json(EVIDENCE / "retained-manifest.json")

    if summary.get("phase") != "L4.2" or summary.get("family") != "STM32L4":
        raise RuntimeError("unexpected retained summary identity")
    if summary.get("base_device_count") != 138 or summary.get("attempted") != 138:
        raise RuntimeError("L4.2 deterministic Base Device count drifted")
    if summary.get("bounded_discovery_clean") is not True:
        raise RuntimeError("L4.2 retained discovery is not clean")
    if summary.get("commercial_identity_authority") != COMMERCIAL_IDENTITY_AUTHORITY:
        raise RuntimeError("commercial identity authority drifted")
    if any(v is not False for v in summary.get("claims", {}).values()):
        raise RuntimeError("summary authority boundary escaped fail-closed state")

    target_rows = targets.get("targets")
    result_rows = summary.get("results")
    if not isinstance(target_rows, list) or len(target_rows) != 138:
        raise RuntimeError("target manifest count drifted")
    if not isinstance(result_rows, list) or len(result_rows) != 138:
        raise RuntimeError("retained result count drifted")
    if leaf.get("leaf_count") != 138:
        raise RuntimeError("leaf digest count drifted")

    bases: list[str] = []
    active: list[str] = []
    excluded: list[str] = []
    for target, result in zip(target_rows, result_rows):
        if not isinstance(target, dict) or not isinstance(result, dict):
            raise RuntimeError("invalid target/result row")
        base = target.get("base_device")
        if not isinstance(base, str) or result.get("base_device") != base:
            raise RuntimeError("target/result order drift")
        bases.append(base)
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise RuntimeError(f"{base}: missing evidence")
        exact = evidence.get("exact_icpns")
        non_active = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(exact, list) or not isinstance(non_active, list):
            raise RuntimeError(f"{base}: malformed lifecycle evidence")
        active.extend(value for value in exact if isinstance(value, str))
        for item in non_active:
            if isinstance(item, dict) and isinstance(item.get("icpn"), str):
                excluded.append(item["icpn"])

    if len(active) != summary.get("active_exact_icpn_candidates"):
        raise RuntimeError("Active exact ICPN count drifted")
    if len(excluded) != summary.get("excluded_non_active_part_numbers"):
        raise RuntimeError("excluded non-Active count drifted")
    if len(set(active)) != len(active) or len(set(excluded)) != len(excluded):
        raise RuntimeError("duplicate exact Part Number in retained evidence")

    baseline = {
        "schema_version": 1,
        "phase": "L4.2",
        "family": "STM32L4",
        "scope": "retained official-ST complete commercial identity/lifecycle discovery; no Production write",
        "commercial_identity_authority": COMMERCIAL_IDENTITY_AUTHORITY,
        "evidence_root": "data/device-catalog/research/evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13",
        "aggregate": {
            "base_device_count": 138,
            "active_candidate_targets": summary["active_candidate_targets"],
            "lifecycle_excluded_targets": summary["lifecycle_excluded_targets"],
            "active_exact_icpn_candidates": summary["active_exact_icpn_candidates"],
            "excluded_non_active_part_numbers": summary["excluded_non_active_part_numbers"],
            "source_unavailable_exclusions": summary["source_unavailable_exclusions"],
            "identity_manual_intervention_required": summary["identity_manual_intervention_required"],
            "acquisition_failure": summary["acquisition_failure"],
            "representative_continuity_clean": summary["representative_continuity_clean"],
            "routing_followup_required": summary["routing_followup_required"],
            "openocd_unique_targets": summary.get("openocd_routing", {}).get("unique"),
            "bounded_discovery_clean": summary["bounded_discovery_clean"],
        },
        "excluded_non_active_exact_part_numbers": sorted(excluded),
        "retained_evidence": {
            "workflow_run_id": provenance.get("workflow_run_id"),
            "workflow_run_attempt": provenance.get("workflow_run_attempt"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "live_summary_sha256": sha256(EVIDENCE / "live-summary.json"),
            "targets_sha256": sha256(EVIDENCE / "targets.json"),
            "provenance_sha256": sha256(EVIDENCE / "provenance.json"),
            "leaf_digests_sha256": sha256(EVIDENCE / "leaf-digests.json"),
            "retained_manifest_sha256": sha256(EVIDENCE / "retained-manifest.json"),
        },
        "set_digests": {
            "base_device_set_sha256": set_sha(bases),
            "active_exact_icpn_set_sha256": set_sha(active),
            "excluded_non_active_set_sha256": set_sha(excluded),
        },
        "source_bindings": {
            "l4_1_foundation_sha256": EXPECTED_L4_1_BASELINE_SHA256,
            "openocd_catalog_sha256": EXPECTED_OPENOCD_CATALOG_SHA256,
            "production_prestate_sha256": EXPECTED_PRODUCTION_PRESTATE_SHA256,
            "production_prestate_exact_icpn_count": 1272,
            "stm32l4_production_prestate_exact_icpn_count": 0,
        },
        "claims": {
            "canonical_admission_authorized": False,
            "flash_geometry_qualified": False,
            "manufacturer_evidence_is_admission": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
        },
    }

    args.baseline.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.manifest.write_bytes((EVIDENCE / "targets.json").read_bytes())
    print(json.dumps({
        "base_device_count": len(bases),
        "active_exact_icpn_candidates": len(active),
        "excluded_non_active_part_numbers": len(excluded),
        "base_set_sha256": baseline["set_digests"]["base_device_set_sha256"],
        "active_set_sha256": baseline["set_digests"]["active_exact_icpn_set_sha256"],
        "excluded_set_sha256": baseline["set_digests"]["excluded_non_active_set_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
