#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32L4 Phase L4.2 evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32l4_phase_l4_1_foundation import validate_production_prestate
from stm32l4_phase_l4_2_discovery import (
    AUTHORITY_SURFACE,
    COMMERCIAL_IDENTITY_AUTHORITY,
    EXPECTED_L4_1_BASELINE_SHA256,
    EXPECTED_L4_1_REPRESENTATIVES,
    FAMILY,
    PARSER_PROFILE,
    PHASE,
    TARGET_CONFIG,
    deterministic_targets,
    read_catalog,
    target_manifest,
    validate_l4_1_boundary,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l4-phase-l4.2-discovery-baseline.json"
DISCOVERY = HERE / "stm32l4-phase-l4.2-discovery-manifest.json"
EVIDENCE = HERE / "evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13"
EXPECTED_BASE_DEVICE_COUNT = 138
EXPECTED_RUN_ID = 34706887794
EXPECTED_EXEC_SHA = "021250051672f375f991693bcc451194adff1541"
EXPECTED_OPENOCD_SHA = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_PRESTATE_SHA = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"


class Error(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise Error(message)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(payload, dict), f"{path.name}: expected JSON object")
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_sha(values: list[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    validate_l4_1_boundary()
    production = validate_production_prestate()
    sources = production.get("sources")
    req(isinstance(sources, list), "immutable Production prestate sources missing")
    counts = {
        item.get("family"): item.get("row_count")
        for item in sources if isinstance(item, dict)
    }
    req(sum(v for v in counts.values() if isinstance(v, int)) == 1272, "immutable Production count drift")
    req(counts.get("STM32L4", 0) == 0, "immutable Production prestate unexpectedly contains STM32L4")

    baseline = read_json(BASELINE)
    summary = read_json(EVIDENCE / "live-summary.json")
    targets = read_json(EVIDENCE / "targets.json")
    provenance = read_json(EVIDENCE / "provenance.json")
    leaf_map = read_json(EVIDENCE / "leaf-digests.json")
    retained = read_json(EVIDENCE / "retained-manifest.json")

    req(baseline.get("phase") == PHASE and baseline.get("family") == FAMILY, "baseline identity drift")
    req(summary.get("phase") == PHASE and summary.get("family") == FAMILY, "summary identity drift")
    req(targets.get("phase") == PHASE and targets.get("family") == FAMILY, "targets identity drift")
    req(all_false(baseline.get("claims")), "baseline claims escaped fail-closed state")
    req(all_false(summary.get("claims")), "summary claims escaped fail-closed state")
    req(all_false(targets.get("claims")), "target claims escaped fail-closed state")
    req(all_false(retained.get("claims")), "retained manifest claims escaped fail-closed state")
    req(summary.get("commercial_identity_authority") == COMMERCIAL_IDENTITY_AUTHORITY, "summary authority drift")

    source_bindings = baseline.get("source_bindings")
    req(isinstance(source_bindings, dict), "baseline source bindings missing")
    req(source_bindings.get("l4_1_foundation_sha256") == EXPECTED_L4_1_BASELINE_SHA256, "L4.1 binding drift")
    req(source_bindings.get("openocd_catalog_sha256") == EXPECTED_OPENOCD_SHA, "OpenOCD binding drift")
    req(source_bindings.get("production_prestate_sha256") == EXPECTED_PRODUCTION_PRESTATE_SHA, "Production prestate binding drift")
    req(source_bindings.get("production_prestate_exact_icpn_count") == 1272, "Production count binding drift")
    req(source_bindings.get("stm32l4_production_prestate_exact_icpn_count") == 0, "STM32L4 Production prestate binding drift")

    retained_binding = baseline.get("retained_evidence")
    req(isinstance(retained_binding, dict), "baseline retained-evidence binding missing")
    req(retained_binding.get("workflow_run_id") == EXPECTED_RUN_ID, "workflow run binding drift")
    req(retained_binding.get("workflow_run_attempt") == 1, "workflow run attempt drift")
    req(retained_binding.get("executed_git_sha") == EXPECTED_EXEC_SHA, "executed acquisition SHA drift")
    req(retained_binding.get("live_summary_sha256") == sha256(EVIDENCE / "live-summary.json"), "live summary digest drift")
    req(retained_binding.get("targets_sha256") == sha256(EVIDENCE / "targets.json"), "targets digest drift")
    req(retained_binding.get("provenance_sha256") == sha256(EVIDENCE / "provenance.json"), "provenance digest drift")
    req(retained_binding.get("leaf_digests_sha256") == sha256(EVIDENCE / "leaf-digests.json"), "leaf digest-map drift")
    req(retained_binding.get("retained_manifest_sha256") == sha256(EVIDENCE / "retained-manifest.json"), "retained manifest digest drift")

    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "provenance workflow run drift")
    req(provenance.get("workflow_run_attempt") == 1, "provenance run attempt drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "provenance execution SHA drift")
    req(provenance.get("source_repository") == "physicslu/plasma", "provenance repository drift")
    req(provenance.get("source_branch") == "agent/device-catalog-stm32l4-phase-l42-discovery", "provenance branch drift")
    req(provenance.get("canonical_admission_authorized") is False, "provenance admitted canonical data")
    req(provenance.get("production_write_authorized") is False, "provenance authorized Production")
    req(provenance.get("runtime_programming_support_claimed") is False, "provenance claimed runtime support")
    browser = provenance.get("browser")
    req(isinstance(browser, dict), "browser provenance missing")
    req(browser.get("headless") is False, "retained acquisition must remain headed")
    req(browser.get("evidence_profile") == PARSER_PROFILE, "evidence profile drift")
    req(summary.get("browser") == browser, "summary/provenance browser profile drift")

    expected_manifest = target_manifest(deterministic_targets(read_catalog()))
    req(canonical_json_bytes(expected_manifest) == DISCOVERY.read_bytes(), "deterministic root discovery manifest drift")
    req(DISCOVERY.read_bytes() == (EVIDENCE / "targets.json").read_bytes(), "root/evidence target manifests differ")

    aggregate = baseline.get("aggregate")
    req(isinstance(aggregate, dict), "baseline aggregate missing")
    req(summary.get("base_device_count") == summary.get("attempted") == EXPECTED_BASE_DEVICE_COUNT, "summary target count drift")
    req(summary.get("commercial_identity_verified_targets") == EXPECTED_BASE_DEVICE_COUNT, "verified identity count drift")
    req(summary.get("dispositioned_targets") == EXPECTED_BASE_DEVICE_COUNT, "disposition count drift")
    req(summary.get("source_unavailable_exclusions") == 0, "source-unavailable target drift")
    req(summary.get("identity_manual_intervention_required") == 0, "manual review drift")
    req(summary.get("acquisition_failure") == 0, "acquisition failure drift")
    req(summary.get("representative_continuity_clean") is True, "representative continuity drift")
    req(summary.get("commercial_identity_clean") is True, "commercial identity clean state drift")
    req(summary.get("bounded_discovery_clean") is True, "bounded discovery clean state drift")
    for key in (
        "base_device_count", "active_candidate_targets", "lifecycle_excluded_targets",
        "active_exact_icpn_candidates", "excluded_non_active_part_numbers",
        "source_unavailable_exclusions", "identity_manual_intervention_required",
        "acquisition_failure", "representative_continuity_clean", "routing_followup_required",
        "bounded_discovery_clean",
    ):
        req(aggregate.get(key) == summary.get(key), f"aggregate {key} drift")
    routing = summary.get("openocd_routing")
    req(isinstance(routing, dict) and routing.get("gates_commercial_identity") is False, "OpenOCD routing became identity authority")
    req(aggregate.get("openocd_unique_targets") == routing.get("unique"), "routing unique aggregate drift")

    target_rows = targets.get("targets")
    result_rows = summary.get("results")
    digests = leaf_map.get("sha256_by_file")
    req(isinstance(target_rows, list) and len(target_rows) == EXPECTED_BASE_DEVICE_COUNT, "target row count drift")
    req(isinstance(result_rows, list) and len(result_rows) == EXPECTED_BASE_DEVICE_COUNT, "result row count drift")
    req(leaf_map.get("leaf_count") == EXPECTED_BASE_DEVICE_COUNT and isinstance(digests, dict) and len(digests) == EXPECTED_BASE_DEVICE_COUNT, "leaf digest count drift")

    active: list[str] = []
    excluded: list[str] = []
    bases: list[str] = []
    seen_exact: set[str] = set()
    rep_status: dict[str, str] = {}
    for target, result in zip(target_rows, result_rows):
        req(isinstance(target, dict) and isinstance(result, dict), "invalid target/result row")
        base = target.get("base_device")
        req(isinstance(base, str) and result.get("base_device") == base, "target/result order drift")
        req(result.get("subfamily") == target.get("subfamily"), f"{base}: subfamily drift")
        req(result.get("source_url") == target.get("source_url"), f"{base}: source URL drift")
        req(str(result.get("source_url", "")).startswith("https://www.st.com/en/microcontrollers-microprocessors/"), f"{base}: non-ST source")
        req(result.get("acquisition_status") == "success", f"{base}: acquisition status drift")
        disposition = result.get("disposition")
        identity = result.get("commercial_identity_status")
        req((identity, disposition) in {
            ("verified_active", "active_candidates"),
            ("verified_non_active_only", "lifecycle_excluded"),
        }, f"{base}: invalid identity/lifecycle disposition")
        req(result.get("manual_intervention_required") is False, f"{base}: manual review drift")
        route = result.get("openocd_routing")
        req(isinstance(route, dict) and route.get("gates_commercial_identity") is False, f"{base}: routing escaped diagnostic role")

        evidence = result.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device drift")
        req(evidence.get("evidence_surface") == AUTHORITY_SURFACE, f"{base}: evidence authority surface drift")
        req(evidence.get("parser_profile") == PARSER_PROFILE, f"{base}: parser profile drift")
        exact = evidence.get("exact_icpns")
        non_active = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(non_active, list), f"{base}: malformed exact lifecycle sets")
        req(bool(exact) or bool(non_active), f"{base}: no exact lifecycle disposition")
        if identity == "verified_active":
            req(bool(exact), f"{base}: Active target has no exact ICPN")
        else:
            req(not exact and bool(non_active), f"{base}: lifecycle-only target has Active exact ICPN")
        for value in exact:
            req(isinstance(value, str) and value.startswith(base), f"{base}: invalid Active exact ICPN")
            req(value not in seen_exact, f"{value}: duplicate exact ICPN across Base Devices")
            seen_exact.add(value)
            active.append(value)
        for item in non_active:
            req(isinstance(item, dict), f"{base}: invalid lifecycle exclusion row")
            value = item.get("icpn")
            status = item.get("marketing_status")
            req(isinstance(value, str) and value.startswith(base), f"{base}: invalid excluded exact ICPN")
            req(isinstance(status, str) and bool(status.strip()), f"{base}: missing lifecycle status")
            req(value not in seen_exact, f"{value}: exact ICPN appears in Active and excluded sets")
            excluded.append(value)
        leaf_name = f"{base.lower()}.json"
        req(digests.get(leaf_name) == hashlib.sha256(canonical_json_bytes(result)).hexdigest(), f"{base}: reconstructed leaf digest drift")
        bases.append(base)
        if base in EXPECTED_L4_1_REPRESENTATIVES:
            rep_status[base] = str(identity)

    req(set(rep_status) == EXPECTED_L4_1_REPRESENTATIVES, "L4.1 representative set lost")
    req(set(rep_status.values()) == {"verified_active"}, "L4.1 representative lifecycle continuity regressed")
    req(len(active) == summary.get("active_exact_icpn_candidates"), "Active exact ICPN count drift")
    req(len(excluded) == summary.get("excluded_non_active_part_numbers"), "excluded non-Active count drift")
    req(len(set(excluded)) == len(excluded), "duplicate excluded exact Part Number")

    set_digests = baseline.get("set_digests")
    req(isinstance(set_digests, dict), "baseline set digests missing")
    req(set_digests.get("base_device_set_sha256") == set_sha(bases), "Base Device set digest drift")
    req(set_digests.get("active_exact_icpn_set_sha256") == set_sha(active), "Active exact ICPN set digest drift")
    req(set_digests.get("excluded_non_active_set_sha256") == set_sha(excluded), "excluded exact PN set digest drift")
    req(baseline.get("excluded_non_active_exact_part_numbers") == sorted(excluded), "baseline excluded exact PN list drift")

    req(retained.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "retained manifest Base Device count drift")
    req(retained.get("active_exact_icpn_candidates") == len(active), "retained manifest Active exact count drift")
    req(retained.get("excluded_non_active_part_numbers") == len(excluded), "retained manifest excluded exact count drift")
    req(retained.get("live_summary_sha256") == sha256(EVIDENCE / "live-summary.json"), "retained live summary SHA drift")
    req(retained.get("targets_sha256") == sha256(EVIDENCE / "targets.json"), "retained targets SHA drift")
    req(retained.get("provenance_sha256") == sha256(EVIDENCE / "provenance.json"), "retained provenance SHA drift")
    req(retained.get("leaf_digests_sha256") == sha256(EVIDENCE / "leaf-digests.json"), "retained leaf-map SHA drift")

    print("STM32L4 L4.2 retained evidence validation: PASS")
    print(json.dumps({
        "base_devices": len(bases),
        "active_candidate_targets": summary.get("active_candidate_targets"),
        "lifecycle_excluded_targets": summary.get("lifecycle_excluded_targets"),
        "active_exact_icpns": len(active),
        "excluded_non_active_exact_part_numbers": len(excluded),
        "routing_followup_required": summary.get("routing_followup_required"),
        "production_exact_icpns": 1272,
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Error, AcquisitionError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"STM32L4 L4.2 retained evidence validation: FAIL: {exc}")
