#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "evidence/stm32h7rs-exact-icpn-live-2026-09-16"
SUMMARY = EVIDENCE / "discovery-summary.json"
EXACT = EVIDENCE / "exact-icpns.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT = 36
EXPECTED_SHA256 = "82c7aadf665af597bd02b0bfae2a5649bed3407e44ed58074c86b76e2d2e0fce"
EXPECTED_BASES = 20
EXPECTED_NEXT = "stm32h7rs-bounded-exact-icpn-admission-readiness-gate"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> None:
    s = json.loads(SUMMARY.read_text())
    e = json.loads(EXACT.read_text())
    p = json.loads(PRODUCTION.read_text())

    req(s.get("discovery_id") == "stm32h7rs-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(s.get("selected_partition") == "STM32H7RS", "partition drifted")
    req(s.get("target_config") == "tcl/target/stm32h7rsx.cfg", "target config drifted")
    req(s.get("attempted_targets") == EXPECTED_BASES, "attempted target count drifted")
    req(s.get("successful_targets") == EXPECTED_BASES, "success target count drifted")
    req(s.get("base_device_count") == EXPECTED_BASES, "base-device count drifted")
    req(s.get("manual_review_targets") == 0, "manual review opened")
    req(s.get("excluded_non_active_part_number_count") == 0, "unexpected lifecycle exclusions")
    req(s.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(s.get("active_exact_icpn_count") == EXPECTED_COUNT, "exact ICPN count drifted")
    req(s.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact set digest drifted")
    req(s.get("next_gate") == EXPECTED_NEXT, "next gate drifted")

    exact = s.get("active_exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_COUNT, "exact set malformed")
    req(exact == sorted(set(exact)), "exact set not sorted unique")
    digest = hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_SHA256, "recomputed exact digest mismatch")

    req(e.get("active_exact_icpn_count") == EXPECTED_COUNT, "exact snapshot count drifted")
    req(e.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact snapshot digest drifted")
    req(e.get("active_exact_icpns") == exact, "exact snapshot set differs from summary")

    claims = s.get("claims") or {}
    req(claims.get("exact_icpn_discovery_completed") is True, "discovery completion must be true")
    for key in (
        "production_write_authorized",
        "icpn_admission_authorized",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
    ):
        req(claims.get(key) is False, f"{key} must remain false")

    prod_count = sum(int(src.get("row_count", 0)) for src in p.get("sources", []))
    req(prod_count == 2282, "Production catalog changed during research-only discovery")
    req(all(src.get("family") != "STM32H7RS" for src in p.get("sources", [])), "STM32H7RS leaked into Production")

    results = s.get("results") or []
    req(len(results) == EXPECTED_BASES, "result count drifted")
    req(all(r.get("acquisition_status") == "success" for r in results), "acquisition failure retained")
    req(all(r.get("manual_intervention_required") is False for r in results), "manual intervention retained")

    print(f"PASS: STM32H7RS exact ICPN discovery: {EXPECTED_COUNT} Active ICPNs / {EXPECTED_BASES} Base Devices; Production unchanged at 2282")

if __name__ == "__main__":
    main()
